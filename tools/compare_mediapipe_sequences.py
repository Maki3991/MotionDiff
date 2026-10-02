#!/usr/bin/env python3
"""Compare two MotionDiff MediaPipe Pose Landmarker frame directories.

The comparison is intentionally descriptive. It produces evidence that can be
shown in the UI; it is not a calibrated coaching or pass/fail model.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


FRAME_RE = re.compile(r"_(\d+)_keypoints\.json$")
REQUIRED_JOINTS = (
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)
ANGLE_FEATURES = {
    "left_elbow_angle": ("left_shoulder", "left_elbow", "left_wrist"),
    "right_elbow_angle": ("right_shoulder", "right_elbow", "right_wrist"),
    "left_shoulder_angle": ("left_ear", "left_shoulder", "left_elbow"),
    "right_shoulder_angle": ("right_ear", "right_shoulder", "right_elbow"),
    "left_knee_angle": ("left_hip", "left_knee", "left_ankle"),
    "right_knee_angle": ("right_hip", "right_knee", "right_ankle"),
    "left_hip_angle": ("left_shoulder", "left_hip", "left_knee"),
    "right_hip_angle": ("right_shoulder", "right_hip", "right_knee"),
}
JOINT_LABELS = {
    "left_shoulder": "左肩", "right_shoulder": "右肩",
    "left_elbow": "左肘", "right_elbow": "右肘",
    "left_wrist": "左手腕", "right_wrist": "右手腕",
    "left_hip": "左髋", "right_hip": "右髋",
    "left_knee": "左膝", "right_knee": "右膝",
    "left_ankle": "左踝", "right_ankle": "右踝",
}
QUALITY_THRESHOLD = 0.5
MIN_VALID_FRAME_COVERAGE = 0.5
MIN_COMPARABLE_PATH_COVERAGE = 0.5
MIN_VALID_JOINT_PAIRS = 4


def finite(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def frame_index(path: Path) -> int:
    match = FRAME_RE.search(path.name)
    return int(match.group(1)) if match else 10**12


def point_from_person(person: dict, name: str) -> dict | None:
    for point in person.get("keypoints", []):
        if point.get("name") == name:
            return point
    return None


def point_quality(point: dict | None) -> float:
    if not point:
        return 0.0
    values = [finite(point.get(key)) for key in ("visibility", "presence")]
    values = [value for value in values if value is not None]
    return min(values) if values else 1.0


def load_sequence(directory: Path) -> dict:
    paths = sorted(directory.glob("*_keypoints.json"), key=frame_index)
    if not paths:
        raise ValueError(f"No MediaPipe frame JSON files found in {directory}")
    frames = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        people = payload.get("people") or []
        person = people[0] if people else None
        points = {}
        if person:
            for name in REQUIRED_JOINTS + ("left_ear", "right_ear"):
                points[name] = point_from_person(person, name)
        frames.append({
            "frame_index": int(payload.get("frame_index", frame_index(path))),
            "timestamp_ms": finite(payload.get("timestamp_ms")),
            "status": payload.get("status", "unknown"),
            "points": points,
            "people": len(people),
        })
    return {"directory": str(directory), "frames": frames, "files": len(paths)}


def xy(point: dict | None) -> tuple[float, float] | None:
    if not point:
        return None
    x, y = finite(point.get("x")), finite(point.get("y"))
    return (x, y) if x is not None and y is not None else None


def normalize_frame(frame: dict) -> dict:
    points = frame["points"]
    left_shoulder = xy(points.get("left_shoulder"))
    right_shoulder = xy(points.get("right_shoulder"))
    if not left_shoulder or not right_shoulder:
        return {"valid": False, "points": {}, "scale": None}
    center = ((left_shoulder[0] + right_shoulder[0]) / 2,
              (left_shoulder[1] + right_shoulder[1]) / 2)
    scale = math.hypot(left_shoulder[0] - right_shoulder[0],
                       left_shoulder[1] - right_shoulder[1])
    if scale < 1:
        return {"valid": False, "points": {}, "scale": scale}
    normalized = {}
    for name, point in points.items():
        value = xy(point)
        if value and point_quality(point) >= QUALITY_THRESHOLD:
            normalized[name] = ((value[0] - center[0]) / scale,
                                (value[1] - center[1]) / scale)
    return {"valid": len(normalized) >= 4, "points": normalized, "scale": scale}


def enrich(sequence: dict) -> None:
    for frame in sequence["frames"]:
        frame["normalized"] = normalize_frame(frame)


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def local_cost(reference: dict, target: dict) -> float:
    values = [
        distance(reference["normalized"]["points"][name], target["normalized"]["points"][name])
        for name in REQUIRED_JOINTS
        if name in reference["normalized"]["points"] and name in target["normalized"]["points"]
    ]
    return mean(values) if len(values) >= 4 else 1.0


def dtw_path(reference: list[dict], target: list[dict]) -> tuple[list[tuple[int, int]], float]:
    """Align two clips while allowing different speeds and frame counts."""
    n, m = len(reference), len(target)
    costs = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    paths = [[None] * (m + 1) for _ in range(n + 1)]
    costs[0][0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = local_cost(reference[i - 1], target[j - 1])
            predecessor = min((costs[i - 1][j], (i - 1, j)),
                              (costs[i][j - 1], (i, j - 1)),
                              (costs[i - 1][j - 1], (i - 1, j - 1)),
                              key=lambda item: item[0])
            costs[i][j] = cost + predecessor[0]
            paths[i][j] = predecessor[1]
    if not math.isfinite(costs[n][m]):
        return [], 0.0
    path = []
    cursor = (n, m)
    while cursor != (0, 0):
        i, j = cursor
        path.append((i - 1, j - 1))
        cursor = paths[i][j]
    path.reverse()
    return path, costs[n][m] / max(1, len(path))


def angle(a: tuple[float, float] | None, b: tuple[float, float] | None,
          c: tuple[float, float] | None) -> float | None:
    if not a or not b or not c:
        return None
    ux, uy = a[0] - b[0], a[1] - b[1]
    vx, vy = c[0] - b[0], c[1] - b[1]
    denominator = math.hypot(ux, uy) * math.hypot(vx, vy)
    if denominator <= 1e-9:
        return None
    cosine = max(-1.0, min(1.0, (ux * vx + uy * vy) / denominator))
    return math.degrees(math.acos(cosine))


def summarize(values: list[float]) -> dict:
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return {"samples": 0, "mean": None, "median": None, "p90": None}
    ordered = sorted(values)
    return {
        "samples": len(values),
        "mean": mean(values),
        "median": median(values),
        "p90": ordered[max(0, math.ceil(len(ordered) * 0.9) - 1)],
    }


def quality_summary(sequence: dict) -> dict:
    frames = sequence["frames"]
    pose_frames = sum(frame["people"] > 0 for frame in frames)
    joint_coverage = {}
    for name in REQUIRED_JOINTS:
        joint_coverage[name] = sum(
            name in frame["normalized"]["points"] for frame in frames
        ) / len(frames) if frames else 0.0
    valid_normalized_frames = sum(frame["normalized"]["valid"] for frame in frames)
    return {
        "json_frames": len(frames),
        "frames_with_pose": pose_frames,
        "pose_frame_coverage": pose_frames / len(frames) if frames else 0.0,
        "joint_coverage": joint_coverage,
        "valid_normalized_frames": valid_normalized_frames,
        "valid_normalized_frame_coverage": valid_normalized_frames / len(frames) if frames else 0.0,
    }


def phase_name(progress: float) -> str:
    if progress < 0.25:
        return "0-25%"
    if progress < 0.5:
        return "25-50%"
    if progress < 0.75:
        return "50-75%"
    return "75-100%"


def compare(reference: dict, target: dict, *, reference_label: str = "参考视频 A",
            target_label: str = "学员视频 B") -> dict:
    enrich(reference)
    enrich(target)
    ref_frames, target_frames = reference["frames"], target["frames"]
    path, dtw_cost = dtw_path(ref_frames, target_frames)
    joint_values = {name: [] for name in REQUIRED_JOINTS}
    joint_vectors = {name: [] for name in REQUIRED_JOINTS}
    angles = {name: [] for name in ANGLE_FEATURES}
    phase_joint_values = {(phase, name): [] for phase in ("0-25%", "25-50%", "50-75%", "75-100%")
                          for name in REQUIRED_JOINTS}
    aligned_rows = []
    comparable_path_rows = 0
    for ref_index, target_index in path:
        ref_frame, target_frame = ref_frames[ref_index], target_frames[target_index]
        ref_points = ref_frame["normalized"]["points"]
        target_points = target_frame["normalized"]["points"]
        progress = ref_index / max(1, len(ref_frames) - 1)
        phase = phase_name(progress)
        row = {
            "reference_frame_index": ref_frame["frame_index"],
            "target_frame_index": target_frame["frame_index"],
            "reference_timestamp_ms": ref_frame["timestamp_ms"],
            "target_timestamp_ms": target_frame["timestamp_ms"],
            "reference_progress": progress,
            "phase": phase,
            "joints": {},
        }
        for name in REQUIRED_JOINTS:
            a, b = ref_points.get(name), target_points.get(name)
            if a and b:
                dx, dy = b[0] - a[0], b[1] - a[1]
                delta = math.hypot(dx, dy)
                joint_values[name].append(delta)
                joint_vectors[name].append((dx, dy))
                phase_joint_values[(phase, name)].append(delta)
                row["joints"][name] = {"delta": delta, "dx": dx, "dy": dy}
        if len(row["joints"]) >= MIN_VALID_JOINT_PAIRS:
            comparable_path_rows += 1
        for feature_name, feature in ANGLE_FEATURES.items():
            a = angle(*(ref_points.get(name) for name in feature))
            b = angle(*(target_points.get(name) for name in feature))
            if a is not None and b is not None:
                angles[feature_name].append(abs(b - a))
                row.setdefault("angles", {})[feature_name] = {
                    "reference": a, "target": b, "absolute_delta": abs(b - a)
                }
        aligned_rows.append(row)

    joint_metrics = {}
    findings = []
    for name in REQUIRED_JOINTS:
        metric = summarize(joint_values[name])
        vectors = joint_vectors[name]
        metric["mean_dx"] = mean(value[0] for value in vectors) if vectors else None
        metric["mean_dy"] = mean(value[1] for value in vectors) if vectors else None
        metric["coverage"] = len(joint_values[name]) / max(1, len(path))
        joint_metrics[name] = metric
        if metric["mean"] is not None and metric["mean"] >= 0.05:
            direction = []
            phase_means = {
                phase: summarize(phase_joint_values[(phase, name)])["mean"]
                for phase in ("0-25%", "25-50%", "50-75%", "75-100%")
            }
            peak_row = max(
                (row for row in aligned_rows if name in row["joints"]),
                key=lambda row: row["joints"][name]["delta"], default=None
            )
            if peak_row:
                peak_delta = peak_row["joints"][name]
                if abs(peak_delta["dy"]) >= 0.05:
                    direction.append("更高" if peak_delta["dy"] < 0 else "更低")
                if abs(peak_delta["dx"]) >= 0.05:
                    direction.append("更靠画面右侧" if peak_delta["dx"] > 0 else "更靠画面左侧")
            direction_text = "、".join(direction) if direction else "存在位置差异"
            peak_phase = peak_row["phase"] if peak_row else max(
                ((phase, value) for phase, value in phase_means.items() if value is not None),
                key=lambda item: item[1], default=(None, None)
            )[0]
            findings.append({
                    "joint": name, "joint_label": JOINT_LABELS[name],
                    "mean_delta": metric["mean"], "p90_delta": metric["p90"],
                    "coverage": metric["coverage"], "mean_dx": metric["mean_dx"],
                    "mean_dy": metric["mean_dy"], "direction": direction_text,
                    "peak_phase": peak_phase,
                    "peak_reference_frame_index": peak_row["reference_frame_index"] if peak_row else None,
                    "peak_target_frame_index": peak_row["target_frame_index"] if peak_row else None,
                    "peak_reference_timestamp_ms": peak_row["reference_timestamp_ms"] if peak_row else None,
                    "peak_target_timestamp_ms": peak_row["target_timestamp_ms"] if peak_row else None,
                    "message": f"{JOINT_LABELS[name]}相对参考位置{direction_text}，"
                               f"该关节平均位置差为 {metric['mean']:.3f} 个肩宽，峰值出现在动作进度 {peak_phase or '未知'}；"
                               "建议回看对应片段并尝试向参考位置靠近。",
                })
    findings.sort(key=lambda item: item["mean_delta"], reverse=True)
    angle_metrics = {name: summarize(values) for name, values in angles.items()}
    mean_delta_values = [value for values in joint_values.values() for value in values]
    overall_delta = mean(mean_delta_values) if mean_delta_values else None
    similarity = max(0.0, min(100.0, 100.0 * (1.0 - overall_delta / 0.5))) if overall_delta is not None else None
    phases = []
    for phase in ("0-25%", "25-50%", "50-75%", "75-100%"):
        phase_values = {name: summarize(phase_joint_values[(phase, name)]) for name in REQUIRED_JOINTS}
        phases.append({"phase": phase, "joints": phase_values})
    reference_quality = quality_summary(reference)
    target_quality = quality_summary(target)
    comparable_path_coverage = comparable_path_rows / len(path) if path else 0.0
    status_reasons = []
    for label, quality in (("参考视频", reference_quality), ("学员视频", target_quality)):
        coverage = quality["valid_normalized_frame_coverage"]
        if coverage < MIN_VALID_FRAME_COVERAGE:
            status_reasons.append(
                f"{label}有效姿态帧覆盖仅 {coverage:.0%}，低于当前最低要求 {MIN_VALID_FRAME_COVERAGE:.0%}。"
            )
    if len(path) < 2:
        status_reasons.append("可用于时间对齐的帧数不足。")
    if comparable_path_coverage < MIN_COMPARABLE_PATH_COVERAGE:
        status_reasons.append(
            f"对齐路径中同时具备至少 {MIN_VALID_JOINT_PAIRS} 个有效关键点的帧仅占 "
            f"{comparable_path_coverage:.0%}，不足以可靠比较。"
        )
    usable = not status_reasons and len(mean_delta_values) >= MIN_VALID_JOINT_PAIRS
    if not usable and not status_reasons:
        status_reasons.append("两段视频没有足够的成对有效关键点。")
    if not usable:
        findings = []
        similarity = None
        overall_delta = None
    return {
        "schema_version": "motiondiff-comparison/1.0",
        "status": "complete" if usable else "insufficient_data",
        "status_reasons": status_reasons,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_label": reference_label, "target_label": target_label,
        "method": {
            "normalization": "每帧以双肩中点居中，以双肩距离缩放；保留画面坐标轴方向",
            "temporal_alignment": "DTW over valid upper- and lower-body normalized coordinates",
            "quality_threshold": QUALITY_THRESHOLD,
            "minimum_valid_frame_coverage": MIN_VALID_FRAME_COVERAGE,
            "minimum_comparable_path_coverage": MIN_COMPARABLE_PATH_COVERAGE,
            "distance_unit": "shoulder_widths",
            "score": "un-calibrated similarity index = max(0, 100 * (1 - mean_delta / 0.5))",
        },
        "reference_quality": reference_quality,
        "target_quality": target_quality,
        "alignment": {"path_length": len(path), "reference_frames": len(ref_frames),
                      "target_frames": len(target_frames), "mean_dtw_cost": dtw_cost,
                      "coverage_reference": len({row[0] for row in path}) / max(1, len(ref_frames)),
                      "coverage_target": len({row[1] for row in path}) / max(1, len(target_frames)),
                      "comparable_path_coverage": comparable_path_coverage},
        "summary": {"mean_position_delta_shoulder_widths": overall_delta,
                    "similarity_index": similarity,
                    "finding_count": len(findings)},
        "joints": joint_metrics,
        "angles": angle_metrics,
        "findings": findings[:6],
        "phases": phases,
        "alignment_rows": aligned_rows,
        "limitations": [
            "相似度指数尚未用多组人工标注样本校准，不能解释为合格线。",
            "结果依赖参考与学员采用相近的正面拍摄方向；二维单目数据不能消除任意机位差异。",
            "改进提示表示向参考视频靠近，不等同于安全、专业或医学建议。",
        ],
    }


def write_report(result: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# MotionDiff 两视频动作比较报告", "",
        f"状态：`{result['status']}`。本报告用于展示可追查的相对差异，不是已校准的合格判定。", "",
        "## 输入与质量", "",
        f"- 参考视频：{result['reference_label']}，JSON 帧数 {result['reference_quality']['json_frames']}。",
        f"- 学员视频：{result['target_label']}，JSON 帧数 {result['target_quality']['json_frames']}。",
        f"- DTW 对齐帧数：{result['alignment']['path_length']}；平均对齐代价：{result['alignment']['mean_dtw_cost']:.4f}。",
        f"- 对齐路径中有足够成对关键点的帧：{result['alignment']['comparable_path_coverage']:.0%}。",
        f"- 平均位置差：{result['summary']['mean_position_delta_shoulder_widths']:.4f} 个肩宽。" if result['summary']['mean_position_delta_shoulder_widths'] is not None else "- 平均位置差：无法计算。",
        f"- 未校准相似度指数：{result['summary']['similarity_index']:.1f}/100。" if result['summary']['similarity_index'] is not None else "- 未校准相似度指数：无法计算。",
    ]
    if result.get("status_reasons"):
        md += ["", "## 无法判断原因", ""]
        md += [f"- {reason}" for reason in result["status_reasons"]]
    md += ["", "## 主要差异", ""]
    if result["findings"]:
        for finding in result["findings"]:
            reference_time = finding.get("peak_reference_timestamp_ms")
            target_time = finding.get("peak_target_timestamp_ms")
            evidence = ""
            if reference_time is not None and target_time is not None:
                evidence = (f"（参考 A {reference_time / 1000:.2f}s / 第 {finding['peak_reference_frame_index']} 帧；"
                            f"学员 B {target_time / 1000:.2f}s / 第 {finding['peak_target_frame_index']} 帧）")
            md.append(f"- {finding['message']}{evidence}")
    else:
        md.append("- 没有足够有效关键点生成差异提示。")
    md += ["", "## 关节角度", "", "|指标|平均绝对差异|P90|样本数|", "|---|---:|---:|---:|"]
    for name, metric in result["angles"].items():
        if metric["mean"] is not None:
            md.append(f"|{name}|{metric['mean']:.2f}°|{metric['p90']:.2f}°|{metric['samples']}|")
    md += ["", "## 限制", ""] + [f"- {item}" for item in result["limitations"]]
    run = result.get("run")
    if run:
        md += ["", "## 本次运行耗时", "",
               f"- 应用端到端耗时：{run.get('elapsed_seconds', 0):.2f} 秒（保存视频、两段逐帧 JSON 和比较）。"]
        for label, display in (("reference_export", "参考视频 MediaPipe 导出"),
                               ("student_export", "学员视频 MediaPipe 导出")):
            summary = run.get(label) or {}
            timings = summary.get("timings") or {}
            if timings.get("export_wall_seconds") is not None:
                md.append(f"- {display}脚本耗时：{timings['export_wall_seconds']:.2f} 秒，"
                          f"处理循环：{timings.get('processing_loop_seconds', 0):.2f} 秒。")
    output.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(load_sequence(args.reference), load_sequence(args.target))
    write_report(result, args.output)
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "findings": len(result["findings"]),
                      "similarity_index": result["summary"]["similarity_index"]},
                     ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
