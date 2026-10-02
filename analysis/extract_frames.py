"""Extract every Nth video frame for faster pose inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Input video path")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New or empty directory for sampled JPEG frames")
    parser.add_argument("--every", type=int, default=4,
                        help="Keep one frame out of every N frames (default: 4)")
    parser.add_argument("--offset", type=int, default=0,
                        help="First frame index to keep, from 0 to N-1 (default: 0)")
    args = parser.parse_args()
    if args.every < 1:
        parser.error("--every must be at least 1")
    if args.offset < 0 or args.offset >= args.every:
        parser.error("--offset must be in [0, every)")
    if not args.video.is_file():
        parser.error(f"Video does not exist: {args.video}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        parser.error(f"Output directory must be empty: {output_dir}")

    cap = cv2.VideoCapture(str(args.video.resolve()))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    samples = []
    frame_index = 0
    while True:
        ok, image = cap.read()
        if not ok:
            break
        if frame_index >= args.offset and (frame_index - args.offset) % args.every == 0:
            filename = f"frame_{frame_index:012d}.jpg"
            if not cv2.imwrite(str(output_dir / filename), image):
                cap.release()
                raise RuntimeError(f"Could not write sampled frame: {output_dir / filename}")
            samples.append({
                "source_frame_index": frame_index,
                "timestamp_ms": round(frame_index * 1000 / fps, 3) if fps > 0 else None,
                "image": filename,
            })
        frame_index += 1
    cap.release()

    manifest = {
        "source_video": str(args.video.resolve()),
        "fps": fps,
        "source_frame_count": frame_count,
        "decoded_frame_count": frame_index,
        "width": width,
        "height": height,
        "sample_every": args.every,
        "sample_offset": args.offset,
        "sampled_frame_count": len(samples),
        "frames": samples,
    }
    (output_dir / "sampling_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Extracted {len(samples)} of {frame_index} frames into {output_dir}")


if __name__ == "__main__":
    main()
