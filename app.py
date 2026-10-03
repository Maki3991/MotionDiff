#!/usr/bin/env python3
"""Local browser app for MotionDiff's two-video MediaPipe comparison demo."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import sys
import threading
import time
import uuid
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

from tools.ai_feedback import AIConfig, generate_feedback, load_env


ROOT = Path(__file__).resolve().parent
load_env(ROOT / ".env")
STATIC_DIR = ROOT / "static"


def env_int(name: str, default: int) -> int:
    """Read a positive integer environment setting without hiding bad values."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


RUNS_DIR = Path(os.environ.get("MOTIONDIFF_RUNS_DIR", str(ROOT / "analysis" / "app_runs")))
MODEL_PATH = Path(os.environ.get(
    "MOTIONDIFF_MODEL_PATH",
    str(ROOT / "models" / "mediapipe" / "pose_landmarker_full.task"),
))
MAX_UPLOAD_BYTES = env_int("MOTIONDIFF_MAX_UPLOAD_BYTES", 101 * 1024 * 1024)
MAX_VIDEO_BYTES = env_int("MOTIONDIFF_MAX_VIDEO_BYTES", 50 * 1024 * 1024)
MAX_VIDEO_SECONDS = env_int("MOTIONDIFF_MAX_VIDEO_SECONDS", 60)
MAX_VIDEO_FRAMES = env_int("MOTIONDIFF_MAX_VIDEO_FRAMES", 3600)
MAX_ALIGNMENT_CELLS = env_int("MOTIONDIFF_MAX_ALIGNMENT_CELLS", 1800 * 1800)
RUN_ID_RE = re.compile(r"^[a-f0-9]{32}$")


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._slot = threading.BoundedSemaphore(1)

    def reserve(self) -> bool:
        return self._slot.acquire(blocking=False)

    def release(self) -> None:
        self._slot.release()

    def create(self, reference: bytes, student: bytes, reference_name: str,
                student_name: str, action: str = "generic") -> str:
        run_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[run_id] = {
                "run_id": run_id, "status": "queued", "progress": 0,
                "message": "等待分析", "error": None, "result": None,
                "created_at": time.time(),
            }
        thread = threading.Thread(
            target=self._run, args=(run_id, reference, student, reference_name, student_name, action),
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            with self._lock:
                self._jobs.pop(run_id, None)
            raise
        return run_id

    def update(self, run_id: str, **values: object) -> None:
        with self._lock:
            if run_id in self._jobs:
                self._jobs[run_id].update(values)

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(run_id)
            return dict(job) if job else None

    def _run(self, run_id: str, reference: bytes, student: bytes,
              reference_name: str, student_name: str, action: str = "generic") -> None:
        started = time.perf_counter()
        run_dir = RUNS_DIR / run_id
        try:
            self.update(run_id, status="processing", progress=3, message="保存视频")
            input_dir = run_dir / "input"
            reference_dir = run_dir / "pose" / "reference"
            student_dir = run_dir / "pose" / "student"
            input_dir.mkdir(parents=True, exist_ok=False)
            (run_dir / "report").mkdir(parents=True, exist_ok=True)
            reference_path = input_dir / "reference.mp4"
            student_path = input_dir / "student.mp4"
            reference_path.write_bytes(reference)
            student_path.write_bytes(student)
            (input_dir / "source_names.json").write_text(
                json.dumps({"reference": reference_name, "student": student_name},
                           ensure_ascii=False, indent=2), encoding="utf-8"
            )

            self.update(run_id, progress=5, message="检查两段视频的时长")
            import cv2
            from tools.video_limits import inspect_video
            try:
                checked = {}
                for label, path in (("参考", reference_path), ("学员", student_path)):
                    try:
                        checked[label] = inspect_video(
                            path, cv2, max_duration_seconds=MAX_VIDEO_SECONDS,
                            max_frames=MAX_VIDEO_FRAMES,
                        )
                    except ValueError as exc:
                        raise ValueError(f"{label}视频：{exc}") from exc
                if checked["参考"]["frames"] * checked["学员"]["frames"] > MAX_ALIGNMENT_CELLS:
                    raise ValueError("两段视频的总比较帧数过多，请剪短视频或降低帧率后重试。")
            except ValueError:
                # Rejected uploads must not accumulate large source files on disk.
                for path in (reference_path, student_path, input_dir / "source_names.json"):
                    path.unlink(missing_ok=True)
                raise

            self.update(run_id, progress=8, message="加载 MediaPipe")
            if not MODEL_PATH.is_file():
                raise RuntimeError(f"MediaPipe 模型不存在：{MODEL_PATH}")
            try:
                import mediapipe as mp
            except ImportError as exc:
                raise RuntimeError(
                    "当前 Python 环境没有 MediaPipe 依赖，请使用 .venv-mediapipe 启动应用。"
                ) from exc
            from tools.export_mediapipe_json import export_video
            from tools.compare_mediapipe_sequences import compare, load_sequence, write_report

            export_summaries = {}
            for label, video_path, output_dir, progress in (
                ("reference", reference_path, reference_dir, 12),
                ("student", student_path, student_dir, 42),
            ):
                self.update(run_id, progress=progress, message=f"MediaPipe 逐帧处理 {label}")
                args = SimpleNamespace(video=video_path, model=MODEL_PATH,
                                       output_dir=output_dir, running_mode="VIDEO",
                                       max_duration_seconds=MAX_VIDEO_SECONDS,
                                       max_frames=MAX_VIDEO_FRAMES)
                export_summaries[label] = export_video(args, mp, cv2)

            self.update(run_id, progress=78, message="对齐动作序列并计算差异")
            reference_sequence = load_sequence(reference_dir)
            student_sequence = load_sequence(student_dir)
            if len(reference_sequence["frames"]) * len(student_sequence["frames"]) > MAX_ALIGNMENT_CELLS:
                raise ValueError("实际视频帧数超过比较预算，请剪短视频或降低帧率。")
            result = compare(reference_sequence, student_sequence)
            if action == "squat":
                self.update(run_id, progress=86, message="提取深蹲阶段与动作证据")
                from tools.squat_evidence import build_evidence, evidence_images
                try:
                    evidence = build_evidence(reference_sequence, student_sequence)
                except Exception:
                    evidence = {"status": "insufficient_data", "reasons": ["深蹲证据提取失败，本地比较报告已保留。"]}
                result["squat_evidence"] = evidence
                self.update(run_id, progress=90, message="正在检查深蹲证据并生成 AI 建议")
                try:
                    config = AIConfig.from_env()
                    result["ai_feedback"] = generate_feedback(
                        config, evidence,
                        lambda: evidence_images(evidence, reference_path, student_path, cv2),
                    )
                except (ValueError, TypeError):
                    result["ai_feedback"] = {"status": "error", "message": "AI 环境变量无效，本地报告已保留。"}
                result["limitations"][1] = "深蹲建议要求相近的侧面机位；二维单目数据不能消除机位差异。"
            else:
                result["ai_feedback"] = {"status": "unsupported", "message": "本次为通用比较，AI 建议目前仅支持侧面单次深蹲。"}
            top_finding = (result.get("findings") or [None])[0]
            if top_finding:
                result["visualization"] = {
                    "reference": f"/runs/{run_id}/pose/reference/{top_finding['peak_reference_frame_index']}",
                    "student": f"/runs/{run_id}/pose/student/{top_finding['peak_target_frame_index']}",
                    "joint": top_finding["joint"],
                }
            result["run"] = {
                "run_id": run_id,
                "reference_video": str(reference_path),
                "student_video": str(student_path),
                "elapsed_seconds": time.perf_counter() - started,
                "reference_export": export_summaries["reference"],
                "student_export": export_summaries["student"],
            }
            report_path = run_dir / "report" / "comparison.json"
            write_report(result, report_path)
            self.update(run_id, status="complete", progress=100, message="分析完成",
                        result={
                            "comparison": result,
                            "video_urls": {
                                "reference": f"/runs/{run_id}/input/reference.mp4",
                                "student": f"/runs/{run_id}/input/student.mp4",
                            },
                            "report_url": f"/runs/{run_id}/report/comparison.md",
                            "json_url": f"/runs/{run_id}/report/comparison.json",
                        })
        except Exception as exc:
            self.update(run_id, status="failed", progress=100,
                        message="分析失败", error=f"{type(exc).__name__}: {exc}")
        finally:
            self.release()


STORE = JobStore()


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def parse_upload(body: bytes, content_type: str) -> dict[str, tuple[str, bytes]]:
    """Parse browser FormData using the stdlib email MIME parser."""
    headers = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8")
    message = BytesParser(policy=policy.default).parsebytes(headers + body)
    files: dict[str, tuple[str, bytes]] = {}
    for part in message.iter_parts():
        disposition = part.get_content_disposition()
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        if disposition == "form-data" and name and filename is not None:
            files[name] = (filename, part.get_payload(decode=True) or b"")
        elif disposition == "form-data" and name == "action":
            files[name] = ("", part.get_payload(decode=True) or b"")
    return files


class MotionDiffHandler(BaseHTTPRequestHandler):
    server_version = "MotionDiff/0.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, json_bytes(payload), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path == "/healthz":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/api/limits":
            self._json(HTTPStatus.OK, {
                "max_video_seconds": MAX_VIDEO_SECONDS,
                "max_video_bytes": MAX_VIDEO_BYTES,
                "max_upload_bytes": MAX_UPLOAD_BYTES,
            })
            return
        if path == "/" or path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            relative = Path(path.removeprefix("/static/"))
            if any(part in ("", ".", "..") for part in relative.parts):
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            file_path = STATIC_DIR / relative
            self._serve_file(file_path, mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
            return
        run_match = re.match(r"^/runs/([a-f0-9]{32})/(input|report)/(reference|student)\.mp4$", path)
        report_match = re.match(r"^/runs/([a-f0-9]{32})/report/(comparison\.(?:md|json))$", path)
        pose_match = re.match(r"^/runs/([a-f0-9]{32})/pose/(reference|student)/(\d+)$", path)
        if run_match:
            run_id, category, filename = run_match.groups()
            self._serve_file(RUNS_DIR / run_id / category / f"{filename}.mp4", "video/mp4")
            return
        if report_match:
            run_id, filename = report_match.groups()
            content_type = "application/json; charset=utf-8" if filename.endswith(".json") else "text/markdown; charset=utf-8"
            self._serve_file(RUNS_DIR / run_id / "report" / filename, content_type)
            return
        if pose_match:
            run_id, side, frame = pose_match.groups()
            pose_dir = RUNS_DIR / run_id / "pose" / side
            files = sorted(pose_dir.glob(f"*_{int(frame):012d}_keypoints.json"))
            if files:
                self._serve_file(files[0], "application/json; charset=utf-8")
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "pose frame not found"})
            return
        status_match = re.match(r"^/api/status/([a-f0-9]{32})$", path)
        if status_match:
            job = STORE.get(status_match.group(1))
            if not job:
                self._json(HTTPStatus.NOT_FOUND, {"error": "run not found"})
            else:
                self._json(HTTPStatus.OK, job)
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path != "/api/analyze":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "无效的请求长度"})
            return
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            self.close_connection = True
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "上传内容过大或为空"})
            return
        if not STORE.reserve():
            self.close_connection = True
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "服务器正在处理其他视频，请稍后再试。"})
            return
        submitted = False
        try:
            # A hard deadline also bounds a client that keeps sending tiny chunks.
            deadline = time.monotonic() + 120
            chunks = []
            received = 0
            while received < length:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("upload deadline exceeded")
                self.connection.settimeout(min(30, remaining))
                chunk = self.rfile.read1(min(1024 * 1024, length - received))
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
            body = b"".join(chunks)
            chunks.clear()
            if len(body) != length:
                self.close_connection = True
                self._json(HTTPStatus.BAD_REQUEST, {"error": "视频上传不完整，请重试。"})
                return
            try:
                files = parse_upload(body, self.headers.get("Content-Type", ""))
                reference_name, reference = files["reference"]
                student_name, student = files["student"]
            except (KeyError, ValueError, TypeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": f"需要 reference 和 student 两个视频：{exc}"})
                return
            if not reference or not student:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "两个视频都不能为空"})
                return
            if max(len(reference), len(student)) > MAX_VIDEO_BYTES:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {
                    "error": f"每个视频不能超过 {MAX_VIDEO_BYTES / 1024 / 1024:g} MB，请压缩后上传。",
                })
                return
            action = files.get("action", ("", b"generic"))[1].decode("utf-8", errors="replace")
            if action not in ("generic", "squat"):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "当前不支持此动作。"})
                return
            run_id = STORE.create(reference, student, reference_name, student_name, action)
            submitted = True
            self._json(HTTPStatus.ACCEPTED, {"run_id": run_id, "status": "queued"})
        except TimeoutError:
            self.close_connection = True
            self._json(HTTPStatus.REQUEST_TIMEOUT, {"error": "上传超时，请重试。"})
        finally:
            if not submitted:
                STORE.release()

    def _serve_file(self, path: Path, content_type: str) -> None:
        try:
            resolved = path.resolve()
            allowed = (STATIC_DIR.resolve(), RUNS_DIR.resolve())
            if not any(resolved == root or root in resolved.parents for root in allowed):
                raise FileNotFoundError
            body = resolved.read_bytes()
        except (FileNotFoundError, OSError):
            self._json(HTTPStatus.NOT_FOUND, {"error": "file not found"})
            return
        if content_type == "video/mp4":
            total = len(body)
            start, end = 0, total - 1
            range_header = self.headers.get("Range")
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
                if match and any(match.groups()):
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), total - 1) if last else total - 1
                    else:
                        start = max(0, total - int(last))
                        if int(last) == 0:
                            start = total
                else:
                    start = total
                if start >= total or end < start:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{total}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            self.send_response(HTTPStatus.PARTIAL_CONTENT if range_header else HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-store")
            if range_header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.end_headers()
            self.wfile.write(body[start:end + 1])
            return
        self._send(HTTPStatus.OK, body, content_type)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


class MotionDiffServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self) -> None:
        # Windows SO_REUSEADDR can let two independent job stores share a port.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default=os.environ.get("MOTIONDIFF_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=env_int("MOTIONDIFF_PORT", env_int("PORT", 8765)),
    )
    args = parser.parse_args()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    server = MotionDiffServer((args.host, args.port), MotionDiffHandler)
    print(f"MotionDiff running at http://{args.host}:{args.port}")
    try:
        config = AIConfig.from_env()
        print(f"AI enabled={config.enabled}, model={config.model}, timeout={config.timeout}s")
    except (ValueError, TypeError):
        print("AI configuration is invalid; local comparison remains available.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping MotionDiff.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
