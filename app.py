#!/usr/bin/env python3
"""Local browser app for MotionDiff's two-video MediaPipe comparison demo."""
from __future__ import annotations

import json
import mimetypes
import os
import re
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


ROOT = Path(__file__).resolve().parent
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
MAX_UPLOAD_BYTES = env_int("MOTIONDIFF_MAX_UPLOAD_BYTES", 512 * 1024 * 1024)
RUN_ID_RE = re.compile(r"^[a-f0-9]{32}$")


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def create(self, reference: bytes, student: bytes, reference_name: str,
               student_name: str) -> str:
        run_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[run_id] = {
                "run_id": run_id, "status": "queued", "progress": 0,
                "message": "等待分析", "error": None, "result": None,
                "created_at": time.time(),
            }
        thread = threading.Thread(
            target=self._run, args=(run_id, reference, student, reference_name, student_name),
            daemon=True,
        )
        thread.start()
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
             reference_name: str, student_name: str) -> None:
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

            self.update(run_id, progress=8, message="加载 MediaPipe")
            if not MODEL_PATH.is_file():
                raise RuntimeError(f"MediaPipe 模型不存在：{MODEL_PATH}")
            try:
                import cv2
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
                                       output_dir=output_dir, running_mode="VIDEO")
                export_summaries[label] = export_video(args, mp, cv2)

            self.update(run_id, progress=78, message="对齐动作序列并计算差异")
            result = compare(load_sequence(reference_dir), load_sequence(student_dir))
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
    return files


class MotionDiffHandler(BaseHTTPRequestHandler):
    server_version = "MotionDiff/0.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, json_bytes(payload), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path == "/healthz":
            self._json(HTTPStatus.OK, {"status": "ok"})
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
            self._serve_file(RUNS_DIR / run_id / category / filename, "video/mp4")
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
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "上传内容过大或为空"})
            return
        body = self.rfile.read(length)
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
        run_id = STORE.create(reference, student, reference_name, student_name)
        self._json(HTTPStatus.ACCEPTED, {"run_id": run_id, "status": "queued"})

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
        self._send(HTTPStatus.OK, body, content_type)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


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
    server = ThreadingHTTPServer((args.host, args.port), MotionDiffHandler)
    print(f"MotionDiff running at http://{args.host}:{args.port}")
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
