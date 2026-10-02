#!/usr/bin/env python3
"""Measure sequential, full-frame pose exports from subprocess launch to exit."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parent
LOCAL_ZONE = timezone(timedelta(hours=8))


def now() -> str:
    return datetime.now(LOCAL_ZONE).isoformat()


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cpu_name() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except (ImportError, OSError):
        return platform.processor()


def pid_is_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        # Unknown/access-denied processes are conservatively treated as active.
        return ctypes.get_last_error() != 87
    try:
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == 259
    finally:
        kernel.CloseHandle(handle)


def validate_output(directory: Path, stem: str, expected: int, engine: str) -> dict:
    paths = sorted(directory.glob("*_keypoints.json"))
    expected_names = [f"{stem}_{index:012d}_keypoints.json" for index in range(expected)]
    if [p.name for p in paths] != expected_names:
        raise ValueError(f"{engine}: expected continuous frames 0..{expected - 1}, got {len(paths)} files")
    with_pose = 0
    pose_counts = []
    prior_timestamp = -1
    for index, path in enumerate(paths):
        def reject_constant(value):
            raise ValueError(f"Invalid JSON numeric constant: {value}")
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
        people = data["people"]
        if not isinstance(people, list):
            raise ValueError(f"Invalid people list in {path}")
        with_pose += bool(people)
        pose_counts.append(len(people))
        if engine == "mediapipe":
            if data["frame_index"] != index or data["timestamp_ms"] <= prior_timestamp:
                raise ValueError(f"Frame index/timestamp inconsistency in {path}")
            prior_timestamp = data["timestamp_ms"]
            if any(len(person["keypoints"]) != 33 for person in people):
                raise ValueError(f"Unexpected MediaPipe landmark count in {path}")
        elif any(len(person["pose_keypoints_2d"]) != 75 for person in people):
            raise ValueError(f"Unexpected BODY_25 landmark count in {path}")
    summary = {"json_frames": len(paths), "continuous_frame_indices": True,
               "frames_with_pose": with_pose, "frames_without_pose": expected - with_pose,
               "max_people_in_frame": max(pose_counts),
               "frame_json_bytes": sum(path.stat().st_size for path in paths)}
    if engine == "mediapipe":
        internal = json.loads((directory / "_meta/run_summary.json").read_text(encoding="utf-8"))
        if internal["status"] != "complete" or internal["decoded_frames"] != expected:
            raise ValueError("MediaPipe internal summary is not a complete export")
        summary["exporter_summary"] = internal
    return summary


def run_engine(engine: str, command: list[str], cwd: Path, folder: Path,
               expected: int, stem: str) -> dict:
    folder.mkdir()
    output = folder / stem
    output.mkdir()
    record = {"engine": engine, "status": "running", "started_at": now(),
              "command": command, "cwd": str(cwd), "output_directory": str(output),
              "measurement": "subprocess launch to exit, including startup and JSON output"}
    save(folder / "process.json", record)
    process = None
    print(f"START {engine}: all {expected} frames; CPU; output={output}", flush=True)
    with (folder / "stdout.log").open("wb") as stdout, (folder / "stderr.log").open("wb") as stderr:
        started = time.perf_counter()
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            record["pid"] = process.pid
            save(folder / "process.json", record)
            while True:
                try:
                    exit_code = process.wait(timeout=20)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.perf_counter() - started
                    count = len(list(output.glob("*_keypoints.json")))
                    record.update({"elapsed_seconds_so_far": elapsed, "json_files_so_far": count})
                    save(folder / "process.json", record)
                    print(f"PROGRESS {engine}: {elapsed:.1f}s, {count}/{expected} JSON files", flush=True)
            record.update({"process_wall_seconds": time.perf_counter() - started,
                           "exit_code": exit_code, "finished_at": now()})
            if exit_code != 0:
                raise RuntimeError(f"{engine} returned {exit_code}; see {folder / 'stderr.log'}")
            record["validation"] = validate_output(output, stem, expected, engine)
            record["end_to_end_fps"] = expected / record["process_wall_seconds"]
            record["status"] = "complete"
        except BaseException as error:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
            record["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
            record["error"] = f"{type(error).__name__}: {error}"
            record.setdefault("process_wall_seconds", time.perf_counter() - started)
            raise
        finally:
            save(folder / "process.json", record)
    print(f"DONE {engine}: {record['process_wall_seconds']:.3f}s; {expected}/{expected} valid JSON files", flush=True)
    return record


def write_report(root: Path, manifest: dict) -> None:
    records = {record["engine"]: record for record in manifest["runs"]}
    mp, op = records["mediapipe"], records["openpose"]
    ratio = op["process_wall_seconds"] / mp["process_wall_seconds"]
    manifest["openpose_over_mediapipe_time_ratio"] = ratio
    lines = ["# A 视频逐帧 JSON 导出速度对比", "",
             f"- 测试开始：{manifest['started_at']}（UTC+08:00）",
             f"- CPU：{manifest['environment']['cpu_name']}；逻辑处理器 {manifest['environment']['logical_cpu_count']}。",
             f"- 输入：A.mp4，{manifest['input']['width']}×{manifest['input']['height']}，{manifest['input']['fps']} FPS，{manifest['input']['frame_count']} 帧。",
             "- 相同输入文件，两引擎顺序运行，每帧处理，无抽帧、无显示、无渲染、无输出视频，无额外独立人脸/手部任务。",
             "- 主指标：同一个 Python 计时器，子进程启动到退出，含初始化、解码、识别、JSON 写盘及清理；不含安装、模型下载、输入/模型哈希和输出校验。",
             "", "| 引擎及配置 | 总耗时（秒） | 端到端帧/秒 | JSON 数量 | 检出人体的帧 |",
             "|---|---:|---:|---:|---:|"]
    for key, label in (("mediapipe", "MediaPipe 1.0.1 / Full / CPU / VIDEO"),
                       ("openpose", "OpenPose 1.7.0 CPU / BODY_25 / net_resolution -1x368")):
        record = records[key]
        valid = record["validation"]
        lines.append(f"| {label} | {record['process_wall_seconds']:.3f} | {record['end_to_end_fps']:.3f} | {valid['json_frames']} | {valid['frames_with_pose']} |")
    lines += ["", f"本次 OpenPose 总耗时是 MediaPipe 的 **{ratio:.2f} 倍**。",
              "", "## 验证和解释边界",
              "", "- 两边均核对全部帧文件连续编号、JSON 可解析、原生关节点数组长度；MediaPipe 还核对帧号、时间戳和内部导出完成状态。",
              "- 每个引擎只有一次完整视频的计时；不是多轮平均或中位数，也没有清除操作系统文件缓存。首次 SDK/字体缓存开销会包含在对应运行里。",
              "- MediaPipe VIDEO 会利用视频跟踪，但每个输入帧仍得到一次同步结果；OpenPose 使用 BODY_25。内部网络、输入尺寸、原生输出点数和 JSON 大小不同，本次比较端到端交付用时，不是相同算力工作量或等精度比较。",
              "- 检出人体不代表关节点准确；本次不评价两套模型的动作差异识别质量。",
              "- CPU 使用各运行时默认线程策略；记录继承的线程环境变量，没有人为限核或调整系统电源模式。",
              "", "## 证据", "",
              "- benchmark.json：输入 SHA-256、设备信息、模型 SHA-256、完整命令及结果。",
              "- mediapipe/process.json、openpose/process.json：分别记录外部总耗时与逐帧校验。",
              "- mediapipe/A/、openpose/A/：逐帧 JSON；各引擎目录保存 stdout.log / stderr.log。",
              "- mediapipe/A/_meta/run_summary.json：MediaPipe 初始化、推理、JSON 写盘等分项计时，不能单独替代本表的外部总耗时。"]
    if manifest.get("interrupted_attempts"):
        lines += ["", "## 中断记录", "",
                  "OpenPose 先前进程退出但没有写入完整计时结果；保留其日志和部分 JSON，并重新运行。中断尝试的时间不计入上表；MediaPipe 已完成的原始计时保留。"]
        for attempt in manifest["interrupted_attempts"]:
            lines.append(f"- {attempt['directory']}：{attempt['json_frames']} 份 JSON；仅作中断记录，不作为完整测试。")
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=PROJECT / "videos/test1/A.mp4")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="Keep verified completed runs and archive interrupted attempts")
    args = parser.parse_args()
    video, root = args.video.resolve(), args.output_dir.resolve()
    python = PROJECT / ".venv-mediapipe/Scripts/python.exe"
    exporter = PROJECT / "tools/export_mediapipe_json.py"
    mp_model = PROJECT / "models/mediapipe/pose_landmarker_full.task"
    openpose = WORKSPACE / "openPose"
    executable = openpose / "bin/OpenPoseDemo.exe"
    op_model = openpose / "models/pose/body_25/pose_iter_584000.caffemodel"
    for path in (video, python, exporter, mp_model, executable, op_model):
        if not path.is_file():
            raise FileNotFoundError(path)
    if root.exists() and not args.resume:
        raise ValueError(f"Use a new benchmark directory: {root}")
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open input: {video}")
    input_info = {"path": str(video), "sha256": sha256(video),
                  "frame_count": round(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                  "fps": cap.get(cv2.CAP_PROP_FPS),
                  "width": round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                  "height": round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
    cap.release()
    if input_info["frame_count"] <= 0:
        raise ValueError("Cannot verify input frame count")
    root.mkdir(parents=True, exist_ok=args.resume)
    manifest = {"status": "running", "started_at": now(), "input": input_info,
                "environment": {"cpu_name": cpu_name(), "logical_cpu_count": os.cpu_count(),
                                "platform": platform.platform(), "python": sys.version,
                                "thread_environment": {key: os.environ.get(key) for key in (
                                    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_WAIT_POLICY")}},
                "models": {"mediapipe_full_sha256": sha256(mp_model),
                           "openpose_body25_sha256": sha256(op_model)}, "runs": []}
    if args.resume:
        previous = json.loads((root / "benchmark.json").read_text(encoding="utf-8"))
        if previous["input"] != input_info or previous["models"] != manifest["models"]:
            raise ValueError("Input video or models changed; use a new benchmark")
        manifest = previous
        manifest["status"] = "running"
        manifest.pop("error", None)
        manifest.setdefault("resumed_at", []).append(now())
    save(root / "benchmark.json", manifest)
    configurations = [
        ("mediapipe", [str(python), str(exporter), "--video", str(video), "--model", str(mp_model),
                       "--output-dir", str(root / "mediapipe" / video.stem), "--running-mode", "VIDEO"], PROJECT),
        ("openpose", [str(executable), "--video", str(video), "--model_folder", str(openpose / "models") + os.sep,
                      "--write_json", str(root / "openpose" / video.stem), "--model_pose", "BODY_25",
                      "--net_resolution", "-1x368", "--number_people_max", "1",
                      "--display", "0", "--render_pose", "0", "--face=false", "--hand=false",
                      "--frame_first", "0", "--frame_step", "1", "--process_real_time=false",
                      "--keypoint_scale", "0"], openpose),
    ]
    try:
        for engine, command, cwd in configurations:
            completed = next((r for r in manifest["runs"] if r["engine"] == engine and r["status"] == "complete"), None)
            if completed:
                validate_output(Path(completed["output_directory"]), video.stem, input_info["frame_count"], engine)
                print(f"KEEP {engine}: verified completed run ({completed['process_wall_seconds']:.3f}s)", flush=True)
                continue
            folder = root / engine
            if folder.exists():
                old = json.loads((folder / "process.json").read_text(encoding="utf-8"))
                if old.get("pid") and pid_is_running(int(old["pid"])):
                    raise RuntimeError(f"Refusing to resume while PID {old['pid']} is active")
                counter = 1
                archived = root / f"{engine}_interrupted_{counter}"
                while archived.exists():
                    counter += 1
                    archived = root / f"{engine}_interrupted_{counter}"
                if folder.resolve().parent != root or archived.resolve().parent != root:
                    raise ValueError("Archive path escaped the explicit benchmark directory")
                old.update({"status": "interrupted", "observed_at": now(),
                            "termination_reason": "Process absent without completion record; cause unknown"})
                save(folder / "process.json", old)
                count = len(list((folder / video.stem).glob("*_keypoints.json")))
                folder.rename(archived)
                manifest.setdefault("interrupted_attempts", []).append(
                    {"engine": engine, "directory": archived.name, "json_frames": count})
                save(root / "benchmark.json", manifest)
            record = run_engine(engine, command, cwd, root / engine, input_info["frame_count"], video.stem)
            manifest["runs"].append(record)
            save(root / "benchmark.json", manifest)
        manifest["status"] = "complete"
        manifest["finished_at"] = now()
        write_report(root, manifest)
    except BaseException as error:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        save(root / "benchmark.json", manifest)
    print(f"COMPLETE: {root / 'report.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
