#!/usr/bin/env python3
"""Export EVERY decoded video frame with MediaPipe Pose Landmarker.

No frame sampling, rendering, model downloads, or comparison/scoring happens here.
See docs/MEDIAPIPE_EXPORT.md for setup, the schema, and timing boundaries.
"""
from __future__ import annotations

import time

SCRIPT_STARTED = time.perf_counter()

import argparse
import hashlib
import json
import math
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LANDMARK_NAMES = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer", "left_ear",
    "right_ear", "mouth_left", "mouth_right", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist",
    "right_wrist", "left_pinky", "right_pinky", "left_index",
    "right_index", "left_thumb", "right_thumb", "left_hip",
    "right_hip", "left_knee", "right_knee", "left_ankle",
    "right_ankle", "left_heel", "right_heel", "left_foot_index",
    "right_foot_index",
)
SCHEMA_VERSION = "mediapipe-pose-frame/1.0"


def finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def serialize_people(result: Any, width: int, height: int) -> list[dict]:
    """Keep native confidence semantics; do not invent OpenPose BODY_25 points."""
    people = []
    world_people = result.pose_world_landmarks or []
    for person_index, landmarks in enumerate(result.pose_landmarks):
        if len(landmarks) != len(LANDMARK_NAMES):
            raise ValueError(f"Expected 33 pose landmarks, got {len(landmarks)}")
        world = world_people[person_index] if person_index < len(world_people) else []
        if world and len(world) != len(LANDMARK_NAMES):
            raise ValueError(f"Expected 33 world landmarks, got {len(world)}")
        points = []
        for index, (name, landmark) in enumerate(zip(LANDMARK_NAMES, landmarks)):
            x, y = finite_or_none(landmark.x), finite_or_none(landmark.y)
            point = {
                "index": index, "name": name,
                "x": x * width if x is not None else None,
                "y": y * height if y is not None else None,
                "normalized_x": x, "normalized_y": y,
                "normalized_z": finite_or_none(landmark.z),
                "confidence": None,
                "visibility": finite_or_none(getattr(landmark, "visibility", None)),
                "presence": finite_or_none(getattr(landmark, "presence", None)),
                "world": None,
            }
            if world:
                point["world"] = {
                    key: finite_or_none(getattr(world[index], key, None))
                    for key in ("x", "y", "z", "visibility", "presence")
                }
            points.append(point)
        # This index is local to a frame, NOT a persistent tracked-person ID.
        people.append({"person_index": person_index, "keypoints": points})
    return people


class FrameClock:
    def __init__(self, fps: float) -> None:
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Video FPS must be finite and positive for timestamp fallback")
        self.fps = fps
        self.previous_source_ms = -1.0
        self.previous_inference_ms = -1
        self.fallbacks = 0
        self.inference_adjustments = 0

    def next(self, frame_index: int, decoder_ms: float) -> tuple[float, int, str]:
        timestamp = finite_or_none(decoder_ms)
        source = "opencv_pos_msec"
        if timestamp is None or timestamp < 0 or timestamp <= self.previous_source_ms:
            timestamp = frame_index * 1000.0 / self.fps
            source = "frame_index_over_fps"
            self.fallbacks += 1
            if timestamp <= self.previous_source_ms:
                raise ValueError("Neither decoder timestamps nor FPS fallback are monotonic")
        inference_ms = round(timestamp)
        if inference_ms <= self.previous_inference_ms:
            inference_ms = self.previous_inference_ms + 1
            self.inference_adjustments += 1
        self.previous_source_ms = timestamp
        self.previous_inference_ms = inference_ms
        return timestamp, inference_ms, source


def write_json(path: Path, payload: dict, *, exclusive: bool = False) -> None:
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        file.write("\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path, help="Local .task model bundle")
    parser.add_argument("--output-dir", required=True, type=Path, help="New or empty directory")
    parser.add_argument("--running-mode", choices=("VIDEO", "IMAGE"), default="VIDEO",
                        help="Both process EVERY frame; VIDEO also enables temporal tracking")
    args = parser.parse_args(argv)
    args.video, args.model, args.output_dir = (
        path.resolve() for path in (args.video, args.model, args.output_dir)
    )
    for kind, path in (("Video", args.video), ("Model", args.model)):
        if not path.is_file():
            parser.error(f"{kind} file does not exist: {path}")
    if args.output_dir.exists() and (not args.output_dir.is_dir() or any(args.output_dir.iterdir())):
        parser.error(f"Output directory must be new or empty: {args.output_dir}")
    return args


def export_video(args: argparse.Namespace, mp: Any, cv2: Any,
                 *, import_seconds: float = 0.0) -> dict:
    """Synchronous calls guarantee one result per decoded frame, including no-person results."""
    started = time.perf_counter()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"Refusing to mix results in nonempty directory: {output}")
    metadata = output / "_meta"
    metadata.mkdir()
    timings = {key: 0.0 for key in (
        "model_initialization_seconds", "decode_seconds", "image_conversion_seconds",
        "inference_seconds", "serialization_and_write_seconds", "cleanup_seconds",
    )}
    summary = {
        "schema_version": "mediapipe-pose-run/1.0", "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "engine": {"name": "mediapipe_pose_landmarker",
                   "version": getattr(mp, "__version__", "unknown"),
                   "module_path": getattr(mp, "__file__", None)},
        "environment": {"python": platform.python_version(),
                        "python_executable": sys.executable, "platform": platform.platform(),
                        "logical_cpu_count": os.cpu_count(),
                        "opencv_version": getattr(cv2, "__version__", "unknown")},
        "input": {"video": str(args.video)},
        "settings": {"running_mode": args.running_mode, "delegate": "CPU",
                     "sample_every": 1, "num_poses": 1,
                     "min_pose_detection_confidence": 0.5,
                     "min_pose_presence_confidence": 0.5, "min_tracking_confidence": 0.5,
                     "output_segmentation_masks": False, "rendering": False},
        "output_directory": str(output), "decoded_frames": 0, "json_frames": 0,
        "frames_with_pose": 0, "frames_without_pose": 0,
        "dependency_import_seconds": import_seconds, "timings": timings,
    }
    write_json(metadata / "run_summary.json", summary)
    cap = detector = clock = None
    processing_started = None
    cleanup_error = None
    try:
        cap = cv2.VideoCapture(str(args.video))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {args.video}")
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        advertised_count = finite_or_none(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        expected_count = round(advertised_count) if advertised_count and advertised_count > 0 else None
        clock = FrameClock(fps)
        summary["input"].update({
            "fps": fps, "advertised_frame_count": expected_count,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "file_bytes": args.video.stat().st_size,
        })
        # Load bytes once; this also avoids native Windows non-ASCII path issues.
        model_bytes = args.model.read_bytes()
        summary["model"] = {"path": str(args.model), "bytes": len(model_bytes),
                            "sha256": hashlib.sha256(model_bytes).hexdigest()}
        vision = mp.tasks.vision
        options = vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_buffer=model_bytes, delegate=mp.tasks.BaseOptions.Delegate.CPU),
            running_mode=getattr(vision.RunningMode, args.running_mode),
            num_poses=1, min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5, min_tracking_confidence=0.5,
            output_segmentation_masks=False,
        )
        tick = time.perf_counter()
        detector = vision.PoseLandmarker.create_from_options(options)
        timings["model_initialization_seconds"] = time.perf_counter() - tick
        processing_started = time.perf_counter()
        while True:
            tick = time.perf_counter()
            ok, bgr = cap.read()
            timings["decode_seconds"] += time.perf_counter() - tick
            if not ok:
                break
            frame_index = summary["decoded_frames"]
            summary["decoded_frames"] += 1
            height, width = bgr.shape[:2]
            timestamp_ms, inference_ms, timestamp_source = clock.next(
                frame_index, float(cap.get(cv2.CAP_PROP_POS_MSEC)))
            tick = time.perf_counter()
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timings["image_conversion_seconds"] += time.perf_counter() - tick
            tick = time.perf_counter()
            if args.running_mode == "VIDEO":
                result = detector.detect_for_video(image, inference_ms)
            else:
                result = detector.detect(image)
            inference_seconds = time.perf_counter() - tick
            timings["inference_seconds"] += inference_seconds
            tick = time.perf_counter()
            people = serialize_people(result, width, height)
            payload = {
                "schema_version": SCHEMA_VERSION, "engine": summary["engine"],
                "source_video": args.video.name, "frame_index": frame_index,
                "timestamp_ms": timestamp_ms, "timestamp_source": timestamp_source,
                "inference_timestamp_ms": inference_ms if args.running_mode == "VIDEO" else None,
                "image_width": width, "image_height": height,
                "status": "detected" if people else "no_pose_detected",
                "inference_seconds": inference_seconds, "people": people,
            }
            filename = f"{args.video.stem}_{frame_index:012d}_keypoints.json"
            write_json(output / filename, payload, exclusive=True)
            timings["serialization_and_write_seconds"] += time.perf_counter() - tick
            summary["json_frames"] += 1
            summary["frames_with_pose" if people else "frames_without_pose"] += 1
        timings["processing_loop_seconds"] = time.perf_counter() - processing_started
        if summary["decoded_frames"] == 0:
            raise RuntimeError("Video opened but no frames could be decoded")
        if expected_count is not None and summary["decoded_frames"] != expected_count:
            raise RuntimeError(
                f"Frame-count mismatch: video advertised {expected_count}, "
                f"decoded {summary['decoded_frames']}; output is not accepted as complete")
        summary["status"] = "complete"
    except BaseException as exc:
        summary["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        summary["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        if processing_started is not None and "processing_loop_seconds" not in timings:
            timings["processing_loop_seconds"] = time.perf_counter() - processing_started
        tick = time.perf_counter()
        for resource, method in ((detector, "close"), (cap, "release")):
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception as exc:
                    cleanup_error = exc
                    summary["cleanup_error"] = str(exc)
        timings["cleanup_seconds"] = time.perf_counter() - tick
        if cleanup_error and summary["status"] == "complete":
            summary["status"] = "failed"
        summary["timestamp_fallback_frames"] = clock.fallbacks if clock else 0
        summary["inference_timestamp_adjustments"] = clock.inference_adjustments if clock else 0
        summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        timings["export_wall_seconds"] = time.perf_counter() - started
        timings["script_wall_seconds_before_final_summary"] = time.perf_counter() - SCRIPT_STARTED
        loop_seconds = timings.get("processing_loop_seconds", 0.0)
        summary["processing_fps"] = summary["json_frames"] / loop_seconds if loop_seconds > 0 else None
        write_json(metadata / "run_summary.json", summary)
    if cleanup_error:
        raise RuntimeError("Resource cleanup failed; see run summary") from cleanup_error
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tick = time.perf_counter()
    try:
        # MediaPipe imports matplotlib; keep its writable font cache project-local.
        if not os.environ.get("MPLCONFIGDIR"):
            cache_dir = Path(__file__).resolve().parents[1] / ".cache" / "matplotlib"
            cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ["MPLCONFIGDIR"] = str(cache_dir)
        import cv2
        import mediapipe as mp
        if not hasattr(mp, "tasks") or not hasattr(mp, "Image"):
            raise ImportError("Imported a source directory instead of an installed MediaPipe wheel")
    except ImportError as exc:
        print(f"Dependency error: {exc}\nInstall tools/requirements-mediapipe.txt in a virtual environment.",
              file=sys.stderr)
        return 2
    try:
        summary = export_video(args, mp, cv2, import_seconds=time.perf_counter() - tick)
    except KeyboardInterrupt:
        print("Interrupted; any partial output is marked in _meta/run_summary.json", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: summary[key] for key in (
        "status", "decoded_frames", "json_frames", "frames_with_pose",
        "frames_without_pose", "processing_fps", "output_directory", "timings",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
