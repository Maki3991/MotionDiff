#!/usr/bin/env python3
"""Compare OpenPose BODY_25 JSON sequences for the MotionDiff A/B/C/D probe.

This is an exploratory baseline, not a coaching or pass/fail model.  It keeps
the comparison interpretable: body-centred/torso-scaled 2D coordinates are
aligned by normalized action progress, then per-joint and simple angle
differences are reported.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from statistics import mean, median


JOINT_NAMES = [
    "nose", "neck", "right_shoulder", "right_elbow", "right_wrist",
    "left_shoulder", "left_elbow", "left_wrist", "mid_hip", "right_hip",
    "right_knee", "right_ankle", "left_hip", "left_knee", "left_ankle",
    "right_eye", "left_eye", "right_ear", "left_ear", "left_big_toe",
    "left_small_toe", "left_heel", "right_big_toe", "right_small_toe",
    "right_heel",
]

INDEX = {name: i for i, name in enumerate(JOINT_NAMES)}
FRAME_RE = re.compile(r"_(\d+)_keypoints\.json$")


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def parse_frame_number(path: Path) -> int:
    match = FRAME_RE.search(path.name)
    return int(match.group(1)) if match else len(path.name)


def load_sequence(directory: Path, confidence_threshold: float) -> dict:
    files = sorted(directory.glob("*_keypoints.json"), key=parse_frame_number)
    frames = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        people = payload.get("people") or []
        person = people[0] if people else None
        raw = (person or {}).get("pose_keypoints_2d") or []
        points = []
        for index in range(len(JOINT_NAMES)):
            offset = index * 3
            if offset + 2 >= len(raw):
                points.append(None)
                continue
            x, y, confidence = (float(raw[offset]), float(raw[offset + 1]), float(raw[offset + 2]))
            valid = confidence >= confidence_threshold and not (x == 0 and y == 0)
            points.append((x, y, confidence) if valid else None)
        frames.append({"frame_index": parse_frame_number(path), "points": points})

    # Convert each frame to body-centred coordinates.  These four probe clips
    # are upper-body clips, so use the neck and shoulder width first.  Mid-hip
    # is a fallback; it is often outside the frame in this recording.
    for frame in frames:
        points = frame["points"]
        neck = points[INDEX["neck"]]
        mid_hip = points[INDEX["mid_hip"]]
        shoulders = [points[INDEX[n]] for n in ("right_shoulder", "left_shoulder") if points[INDEX[n]]]
        if neck:
            center = (neck[0], neck[1])
        elif len(shoulders) == 2:
            center = (mean([p[0] for p in shoulders]), mean([p[1] for p in shoulders]))
        elif mid_hip:
            center = (mid_hip[0], mid_hip[1])
        else:
            hips = [points[INDEX[n]] for n in ("right_hip", "left_hip") if points[INDEX[n]]]
            center = (mean([p[0] for p in hips]), mean([p[1] for p in hips])) if hips else None
        if center is None:
            frame["normalized"] = [None] * len(JOINT_NAMES)
            continue
        if len(shoulders) == 2:
            scale = distance((shoulders[0][0], shoulders[0][1]), (shoulders[1][0], shoulders[1][1]))
        elif neck and mid_hip:
            scale = distance((neck[0], neck[1]), (mid_hip[0], mid_hip[1]))
        if scale < 1:
            valid_xy = [(p[0], p[1]) for p in points if p]
            scale = math.hypot(max(p[0] for p in valid_xy) - min(p[0] for p in valid_xy), max(p[1] for p in valid_xy) - min(p[1] for p in valid_xy)) if valid_xy else 0
        frame["normalized"] = [((p[0] - center[0]) / scale, (p[1] - center[1]) / scale) if p and scale >= 1 else None for p in points]

    return {"directory": str(directory), "files": files, "frames": frames, "confidence_threshold": confidence_threshold}


def series(sequence: dict, joint_index: int) -> list[tuple[float, tuple[float, float], float]]:
    frames = sequence["frames"]
    if not frames:
        return []
    last = max(1, len(frames) - 1)
    values = []
    for position, frame in enumerate(frames):
        point = frame["normalized"][joint_index]
        if point is not None:
            original = frame["points"][joint_index]
            values.append((position / last, point, original[2]))
    return values


def interpolate(values: list[tuple[float, tuple[float, float], float]], phase: float):
    if not values:
        return None
    for item in values:
        if abs(item[0] - phase) < 1e-9:
            return item[1], item[2]
    before = [item for item in values if item[0] < phase]
    after = [item for item in values if item[0] > phase]
    if not before or not after:
        return None
    left, right = before[-1], after[0]
    # Do not invent a trajectory across a long missing-keypoint gap.
    if right[0] - left[0] > 0.25:
        return None
    ratio = (phase - left[0]) / (right[0] - left[0])
    point = (left[1][0] + ratio * (right[1][0] - left[1][0]), left[1][1] + ratio * (right[1][1] - left[1][1]))
    return point, min(left[2], right[2])


def angle(a, b, c):
    if not a or not b or not c:
        return None
    ux, uy = a[0] - b[0], a[1] - b[1]
    vx, vy = c[0] - b[0], c[1] - b[1]
    denominator = math.hypot(ux, uy) * math.hypot(vx, vy)
    if denominator == 0:
        return None
    cosine = max(-1.0, min(1.0, (ux * vx + uy * vy) / denominator))
    return math.degrees(math.acos(cosine))


ANGLE_FEATURES = {
    "right_elbow_angle": ("right_shoulder", "right_elbow", "right_wrist"),
    "left_elbow_angle": ("left_shoulder", "left_elbow", "left_wrist"),
    "right_shoulder_angle": ("neck", "right_shoulder", "right_elbow"),
    "left_shoulder_angle": ("neck", "left_shoulder", "left_elbow"),
}


def feature_series(sequence: dict, feature: tuple[str, str, str]):
    indices = [INDEX[name] for name in feature]
    frames = sequence["frames"]
    last = max(1, len(frames) - 1)
    values = []
    for position, frame in enumerate(frames):
        points = frame["normalized"]
        value = angle(*(points[i] for i in indices))
        if value is not None:
            confidence = min(frame["points"][i][2] for i in indices)
            values.append((position / last, value, confidence))
    return values


def compare_joint(reference: dict, target: dict, joint_index: int, samples: int = 100):
    left, right = series(reference, joint_index), series(target, joint_index)
    errors, weights = [], []
    for step in range(samples):
        phase = step / max(1, samples - 1)
        a, b = interpolate(left, phase), interpolate(right, phase)
        if a is None or b is None:
            continue
        errors.append(distance(a[0], b[0]))
        weights.append(min(a[1], b[1]))
    return {"samples": len(errors), "coverage": len(errors) / samples, "mean_error": mean(errors) if errors else None, "median_error": median(errors) if errors else None, "p95_error": sorted(errors)[max(0, math.ceil(len(errors) * 0.95) - 1)] if errors else None, "mean_confidence": mean(weights) if weights else None}


def compare_angle(reference: dict, target: dict, feature: tuple[str, str, str], samples: int = 100):
    left, right = feature_series(reference, feature), feature_series(target, feature)
    errors, weights = [], []
    for step in range(samples):
        phase = step / max(1, samples - 1)
        a, b = interpolate_scalar(left, phase), interpolate_scalar(right, phase)
        if a is None or b is None:
            continue
        errors.append(abs(a[0] - b[0]))
        weights.append(min(a[1], b[1]))
    return {"samples": len(errors), "coverage": len(errors) / samples, "mean_abs_degrees": mean(errors) if errors else None, "p95_abs_degrees": sorted(errors)[max(0, math.ceil(len(errors) * 0.95) - 1)] if errors else None, "mean_confidence": mean(weights) if weights else None}


def interpolate_scalar(values, phase):
    if not values:
        return None
    exact = next((item for item in values if abs(item[0] - phase) < 1e-9), None)
    if exact:
        return exact[1], exact[2]
    before = [item for item in values if item[0] < phase]
    after = [item for item in values if item[0] > phase]
    if not before or not after:
        return None
    left, right = before[-1], after[0]
    if right[0] - left[0] > 0.25:
        return None
    ratio = (phase - left[0]) / (right[0] - left[0])
    return left[1] + ratio * (right[1] - left[1]), min(left[2], right[2])


def quality(sequence: dict):
    frames = sequence["frames"]
    return {
        "json_files": len(sequence["files"]),
        "frames_with_person": sum(bool(frame["points"]) and any(frame["points"]) for frame in frames),
        "joint_coverage": {
            name: sum(frame["points"][i] is not None for frame in frames) / len(frames) if frames else 0
            for i, name in enumerate(JOINT_NAMES)
        },
        "mean_detected_points": mean(sum(point is not None for point in frame["points"]) for frame in frames) if frames else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=Path("openPose/output_test1"))
    parser.add_argument("--output", type=Path, default=Path("MotionDiff/reports/pose_comparison_A_B_C_D.json"))
    parser.add_argument("--confidence-threshold", type=float, default=0.25)
    args = parser.parse_args()

    sequences = {label: load_sequence(args.input_root / label, args.confidence_threshold) for label in ("A", "B", "C", "D")}
    comparisons = {}
    for label in ("B", "C", "D"):
        comparisons[f"A-{label}"] = {
            "reference": "A",
            "target": label,
            "normalization": "neck_centered; shoulder_width_scale; normalized_progress_resampling",
            "joints": {name: compare_joint(sequences["A"], sequences[label], index) for index, name in enumerate(JOINT_NAMES)},
            "angles": {name: compare_angle(sequences["A"], sequences[label], feature) for name, feature in ANGLE_FEATURES.items()},
        }
    report = {
        "status": "exploratory_baseline",
        "not_a_score_or_coaching_model": True,
        "inputs": {label: {"directory": str(sequences[label]["directory"]), "json_files": len(sequences[label]["files"])} for label in sequences},
        "quality": {label: quality(sequence) for label, sequence in sequences.items()},
        "comparisons": comparisons,
        "interpretation": {
            "A-B": "same-camera repeat baseline",
            "A-C": "camera-height change probe",
            "A-D": "right-hand-raised action-change probe",
            "coordinate_error_unit": "torso lengths after normalization, not pixels",
            "angle_error_unit": "degrees",
            "missing_or_low_confidence": f"excluded below confidence {args.confidence_threshold}",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = [
        "# MotionDiff A/B/C/D baseline comparison",
        "",
        "本报告是可解释的探索性基线，不是合格判定、总分或动作建议。",
        "",
        "## 数据质量",
        "",
        "|视频|JSON 帧数|检测到人的帧数|平均有效关键点数|",
        "|---|---:|---:|---:|",
    ]
    for label in ("A", "B", "C", "D"):
        q = report["quality"][label]
        markdown.append(f"|{label}|{q['json_files']}|{q['frames_with_person']}|{q['mean_detected_points']:.2f}|")
    for pair in ("A-B", "A-C", "A-D"):
        data = comparisons[pair]
        markdown += ["", f"## {pair}", "", "坐标差异已按 Neck 居中、双肩距离缩放，并按视频进度对齐。单位是肩宽，不是像素；这是针对本次上半身视频的探索性归一化。", "", "### 关键点差异", "", "|关键点|平均差异|P95 差异|覆盖率|", "|---|---:|---:|---:|"]
        ranked = sorted(((name, values) for name, values in data["joints"].items() if values["mean_error"] is not None), key=lambda item: item[1]["mean_error"], reverse=True)
        for name, values in ranked:
            markdown.append(f"|{name}|{values['mean_error']:.3f}|{values['p95_error']:.3f}|{values['coverage']:.0%}|")
        markdown += ["", "### 关节角度差异", "", "|角度特征|平均绝对差异|P95 差异|覆盖率|", "|---|---:|---:|---:|"]
        for name, values in sorted(data["angles"].items(), key=lambda item: (item[1]["mean_abs_degrees"] is None, -(item[1]["mean_abs_degrees"] or 0))):
            if values["mean_abs_degrees"] is not None:
                markdown.append(f"|{name}|{values['mean_abs_degrees']:.2f}°|{values['p95_abs_degrees']:.2f}°|{values['coverage']:.0%}|")
    markdown += ["", "## 解释边界", "", "A-B 是重复动作基线，A-C 是机位降低的影响，A-D 是右手抬高的动作变化。当前报告不能证明任意机位下都能比较，也不定义合格阈值。"]
    md_path = args.output.with_suffix(".md")
    md_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
