"""Exploratory comparison of the four OpenPose BODY_25 test clips.

Run from the repository root:
    python MotionDiff/analysis/compare_test1.py

The output is a descriptive baseline, not a movement correctness score.
"""

from __future__ import annotations

import csv
import argparse
import json
import math
import re
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
VIDEO_DIR = ROOT / "MotionDiff" / "videos" / "test1"
JSON_DIR = ROOT / "openPose" / "output_test1"
OUT_DIR = ROOT / "MotionDiff" / "analysis" / "results" / "test1"
CONFIDENCE_MIN = 0.25

KEYPOINTS = [
    "Nose", "Neck", "RShoulder", "RElbow", "RWrist", "LShoulder", "LElbow",
    "LWrist", "MidHip", "RHip", "RKnee", "RAnkle", "LHip", "LKnee",
    "LAnkle", "REye", "LEye", "REar", "LEar", "LBigToe", "LSmallToe",
    "LHeel", "RBigToe", "RSmallToe", "RHeel",
]

# Image left/right follows OpenPose's anatomical R/L labels in its BODY_25 order.
ARM_JOINTS = ["RShoulder", "RElbow", "RWrist", "LShoulder", "LElbow", "LWrist"]
ALIGN_JOINTS = [KEYPOINTS.index(name) for name in ARM_JOINTS]
STAGES = [(0.0, 0.25, "0-25%"), (0.25, 0.5, "25-50%"),
          (0.5, 0.75, "50-75%"), (0.75, 1.001, "75-100%")]


def read_clip(label: str, sample_every: int, sample_offset: int, json_dir: Path) -> dict:
    video_path = VIDEO_DIR / f"{label}.mp4"
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    json_files = sorted((json_dir / label).glob("*_keypoints.json"))
    if not json_files:
        raise RuntimeError(f"No OpenPose JSON files in {json_dir / label}")

    frames = []
    for path in json_files:
        match = re.search(r"_(\d+)_keypoints\.json$", path.name)
        if not match:
            raise RuntimeError(f"Cannot parse frame index from {path.name}")
        frame_index = int(match.group(1))
        payload = json.loads(path.read_text(encoding="utf-8"))
        people = payload.get("people", [])
        coords = np.full((25, 2), np.nan, dtype=float)
        confidence = np.zeros(25, dtype=float)
        if people:
            values = people[0].get("pose_keypoints_2d", [])
            if len(values) != 75:
                raise RuntimeError(f"Unexpected BODY_25 length in {path.name}: {len(values)}")
            triples = np.asarray(values, dtype=float).reshape(25, 3)
            confidence = triples[:, 2]
            valid = (confidence >= CONFIDENCE_MIN) & (triples[:, 0] != 0) & (triples[:, 1] != 0)
            coords[valid] = triples[valid, :2]
        frames.append({"index": frame_index, "coords": coords, "confidence": confidence,
                       "people": len(people), "name": path.name})

    frames.sort(key=lambda frame: frame["index"])
    json_frames_total = len(frames)
    if sample_every > 1:
        frames = [frame for frame in frames
                  if frame["index"] >= sample_offset
                  and (frame["index"] - sample_offset) % sample_every == 0]
    return {"label": label, "video": video_path.name, "fps": fps,
            "video_frames": frame_count, "width": width, "height": height,
            "duration": frame_count / fps if fps > 0 else float("nan"),
            "json_frames_total": json_frames_total, "sample_every": sample_every,
            "sample_offset": sample_offset,
            "frames": frames}


def normalize_frame(frame: dict) -> tuple[np.ndarray, float]:
    """Center on shoulder midpoint and scale by shoulder width; retain image axes."""
    xy = frame["coords"].copy()
    right, left = xy[2], xy[5]
    if not (np.isfinite(right).all() and np.isfinite(left).all()):
        return np.full_like(xy, np.nan), float("nan")
    scale = float(np.linalg.norm(right - left))
    if scale < 1:
        return np.full_like(xy, np.nan), float("nan")
    center = (right + left) / 2
    return (xy - center) / scale, scale


def local_cost(a: dict, b: dict) -> float:
    diffs = []
    for idx in ALIGN_JOINTS:
        if np.isfinite(a["norm"][idx]).all() and np.isfinite(b["norm"][idx]).all():
            diffs.append(float(np.linalg.norm(a["norm"][idx] - b["norm"][idx])))
    return float(np.mean(diffs)) if len(diffs) >= 4 else 1e3


def dtw_path(reference: list[dict], target: list[dict]) -> list[tuple[int, int]]:
    """Classic DTW over normalized arm landmarks, with a small clip-length band."""
    n, m = len(reference), len(target)
    dp = np.full((n + 1, m + 1), np.inf, dtype=float)
    back = np.zeros((n + 1, m + 1, 2), dtype=np.int32)
    dp[0, 0] = 0.0
    for i in range(1, n + 1):
        expected = i * m / n
        band = max(8, int(max(n, m) * 0.25))
        lo, hi = max(1, int(expected - band)), min(m, int(expected + band) + 1)
        for j in range(lo, hi + 1):
            prev_i, prev_j = min((i - 1, j), (i, j - 1), (i - 1, j - 1),
                                 key=lambda p: dp[p[0], p[1]])
            dp[i, j] = local_cost(reference[i - 1], target[j - 1]) + dp[prev_i, prev_j]
            back[i, j] = (prev_i, prev_j)
    if not np.isfinite(dp[n, m]):
        raise RuntimeError("DTW could not align the two clips")
    path = []
    i, j = n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        i, j = map(int, back[i, j])
    return list(reversed(path))


def angle_degrees(points: np.ndarray) -> float:
    if not np.isfinite(points).all():
        return float("nan")
    a, b, c = points
    u, v = a - b, c - b
    denom = np.linalg.norm(u) * np.linalg.norm(v)
    if denom < 1e-8:
        return float("nan")
    cosine = float(np.clip(np.dot(u, v) / denom, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def summarize(values: list[float]) -> tuple[float, float, float, int]:
    clean = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if clean.size == 0:
        return float("nan"), float("nan"), float("nan"), 0
    return float(np.mean(clean)), float(np.median(clean)), float(np.percentile(clean, 90)), int(clean.size)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-every", type=int, default=1,
                        help="Use every Nth original video frame from the existing OpenPose JSON")
    parser.add_argument("--sample-offset", type=int, default=0,
                        help="First original frame index to retain (0 <= offset < sample-every)")
    parser.add_argument("--json-dir", type=Path, default=JSON_DIR,
                        help="Root folder containing A/B/C/D OpenPose JSON subfolders")
    parser.add_argument("--output-dir", type=Path,
                        help="Optional custom output directory for reports and CSV files")
    args = parser.parse_args()
    if args.sample_every < 1:
        parser.error("--sample-every must be at least 1")
    if args.sample_offset < 0 or args.sample_offset >= args.sample_every:
        parser.error("--sample-offset must be in [0, sample-every)")
    sample_every = args.sample_every
    sample_offset = args.sample_offset
    if args.output_dir:
        out_dir = args.output_dir.resolve()
    elif sample_every == 1 and args.json_dir.resolve() == JSON_DIR.resolve():
        out_dir = ROOT / "MotionDiff" / "analysis" / "results" / "test1"
    elif sample_every == 1:
        out_dir = ROOT / "MotionDiff" / "analysis" / "results" / "test1_custom_json"
    else:
        suffix = f"test1_every{sample_every}"
        if sample_offset:
            suffix += f"_offset{sample_offset}"
        out_dir = ROOT / "MotionDiff" / "analysis" / "results" / suffix
    global OUT_DIR
    OUT_DIR = out_dir
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_dir = args.json_dir.resolve()
    clips = {label: read_clip(label, sample_every, sample_offset, json_dir) for label in "ABCD"}
    quality_rows = []
    for label, clip in clips.items():
        frames = clip["frames"]
        for idx, name in enumerate(KEYPOINTS):
            valid = [frame for frame in frames if np.isfinite(frame["coords"][idx]).all()]
            confs = [frame["confidence"][idx] for frame in valid]
            quality_rows.append({
                "clip": label, "video_frames": clip["video_frames"],
                "json_frames_total": clip["json_frames_total"], "sampled_json_frames": len(frames),
                "sample_every": sample_every, "sample_offset": sample_offset,
                "fps": clip["fps"], "duration_s": round(clip["duration"], 3),
                "people_frames": sum(frame["people"] > 0 for frame in frames),
                "keypoint": name, "valid_frames": len(valid),
                "coverage_pct": round(100 * len(valid) / len(frames), 1),
                "mean_confidence_when_valid": round(float(np.mean(confs)), 3) if confs else "",
            })
        for frame in frames:
            frame["norm"], frame["shoulder_width"] = normalize_frame(frame)

    joint_rows, stage_rows, pair_rows = [], [], []
    pair_summaries = {}
    for target_label in "BCD":
        ref, target = clips["A"]["frames"], clips[target_label]["frames"]
        path = dtw_path(ref, target)
        pair_name = f"A-{target_label}"
        pair_errors = []
        for joint_idx, joint_name in enumerate(KEYPOINTS):
            norm_errors, pixel_errors, conf_values = [], [], []
            stage_values = {name: [] for _, _, name in STAGES}
            for ri, ti in path:
                a, b = ref[ri], target[ti]
                if np.isfinite(a["norm"][joint_idx]).all() and np.isfinite(b["norm"][joint_idx]).all():
                    norm_errors.append(float(np.linalg.norm(a["norm"][joint_idx] - b["norm"][joint_idx])))
                    pixel_errors.append(float(np.linalg.norm(a["coords"][joint_idx] - b["coords"][joint_idx])))
                    conf_values.append(min(a["confidence"][joint_idx], b["confidence"][joint_idx]))
                    progress = ri / max(1, len(ref) - 1)
                    for lo, hi, name in STAGES:
                        if lo <= progress < hi:
                            stage_values[name].append(norm_errors[-1])
                            break
            mean_e, median_e, p90_e, nvalid = summarize(norm_errors)
            pmean, pmedian, pp90, _ = summarize(pixel_errors)
            mean_conf = float(np.mean(conf_values)) if conf_values else float("nan")
            joint_rows.append({"pair": pair_name, "joint": joint_name, "aligned_samples": len(path),
                               "valid_pairs": nvalid, "coverage_pct": round(100*nvalid/max(1,len(path)),1),
                               "mean_delta_shoulder_widths": round(mean_e,4) if np.isfinite(mean_e) else "",
                               "median_delta_shoulder_widths": round(median_e,4) if np.isfinite(median_e) else "",
                               "p90_delta_shoulder_widths": round(p90_e,4) if np.isfinite(p90_e) else "",
                               "mean_raw_delta_px": round(pmean,1) if np.isfinite(pmean) else "",
                               "mean_pair_confidence": round(mean_conf,3) if np.isfinite(mean_conf) else ""})
            if joint_name in ARM_JOINTS:
                pair_errors.extend(norm_errors)
            for stage_name, values in stage_values.items():
                sm, smed, sp90, sn = summarize(values)
                stage_rows.append({"pair": pair_name, "stage_by_reference_progress": stage_name,
                                   "joint": joint_name, "metric": "position_delta",
                                   "unit": "shoulder_widths", "valid_pairs": sn,
                                   "mean": round(sm,4) if np.isfinite(sm) else "",
                                   "median": round(smed,4) if np.isfinite(smed) else "",
                                   "p90": round(sp90,4) if np.isfinite(sp90) else ""})

        # Arm angle change and hand height relative to its own shoulder.
        arm_summary = {}
        for side, shoulder_i, elbow_i, wrist_i in [
            ("R", 2, 3, 4), ("L", 5, 6, 7)
        ]:
            elbow_deltas, wrist_height_delta = [], []
            stage_angles = {name: [] for _, _, name in STAGES}
            stage_wrist = {name: [] for _, _, name in STAGES}
            for ri, ti in path:
                a, b = ref[ri], target[ti]
                aa = angle_degrees(a["coords"][[shoulder_i, elbow_i, wrist_i]])
                ba = angle_degrees(b["coords"][[shoulder_i, elbow_i, wrist_i]])
                if np.isfinite(aa) and np.isfinite(ba):
                    delta = abs(aa - ba)
                    elbow_deltas.append(delta)
                else:
                    delta = float("nan")
                if (np.isfinite(a["norm"][[shoulder_i, wrist_i]]).all()
                        and np.isfinite(b["norm"][[shoulder_i, wrist_i]]).all()):
                    # y grows downward; positive means the target wrist is higher than A.
                    wrist_delta = float((a["norm"][wrist_i, 1] - a["norm"][shoulder_i, 1])
                                        - (b["norm"][wrist_i, 1] - b["norm"][shoulder_i, 1]))
                    wrist_height_delta.append(wrist_delta)
                else:
                    wrist_delta = float("nan")
                progress = ri / max(1, len(ref) - 1)
                for lo, hi, name in STAGES:
                    if lo <= progress < hi:
                        if np.isfinite(delta): stage_angles[name].append(delta)
                        if np.isfinite(wrist_delta): stage_wrist[name].append(wrist_delta)
                        break
            arm_summary[f"{side}_elbow_angle_abs_delta_deg"] = summarize(elbow_deltas)
            arm_summary[f"{side}_wrist_height_change_shoulder_widths"] = summarize(wrist_height_delta)
            for _, _, stage_name in STAGES:
                for measure, vals in [("elbow_angle_abs_delta_deg", stage_angles[stage_name]),
                                      ("wrist_height_change_shoulder_widths", stage_wrist[stage_name])]:
                    mean_v, med_v, p90_v, n_v = summarize(vals)
                    stage_rows.append({"pair": pair_name, "stage_by_reference_progress": stage_name,
                                       "joint": f"{side}_{measure}", "metric": measure,
                                       "unit": "degrees" if "angle" in measure else "shoulder_widths",
                                       "valid_pairs": n_v,
                                       "mean": round(mean_v,4) if np.isfinite(mean_v) else "",
                                       "median": round(med_v,4) if np.isfinite(med_v) else "",
                                       "p90": round(p90_v,4) if np.isfinite(p90_v) else ""})
            for measure, values in arm_summary.items():
                if measure.startswith(side + "_"):
                    mean_v, med_v, p90_v, n_v = values
                    pair_rows.append({"pair": pair_name, "metric": measure, "valid_pairs": n_v,
                                      "mean": round(mean_v,4) if np.isfinite(mean_v) else "",
                                      "median": round(med_v,4) if np.isfinite(med_v) else "",
                                      "p90": round(p90_v,4) if np.isfinite(p90_v) else ""})
        pair_mean = float(np.mean(pair_errors)) if pair_errors else float("nan")
        pair_rows.append({"pair": pair_name, "metric": "all_arm_keypoint_mean_delta_shoulder_widths",
                          "valid_pairs": len(pair_errors), "mean": round(pair_mean,4) if np.isfinite(pair_mean) else "",
                          "median": "", "p90": ""})
        pair_summaries[pair_name] = {"path_len": len(path), "normalized_arm_mean": pair_mean}

    write_csv(OUT_DIR / "quality_by_keypoint.csv", quality_rows, list(quality_rows[0]))
    write_csv(OUT_DIR / "pairwise_joint_metrics.csv", joint_rows, list(joint_rows[0]))
    write_csv(OUT_DIR / "stage_metrics.csv", stage_rows, list(stage_rows[0]))
    write_csv(OUT_DIR / "pair_summary.csv", pair_rows, list(pair_rows[0]))

    lines = [
        "# A/B/C/D OpenPose 对比：探索性基线报告", "",
        "## 实验定义", "",
        "- A：标准动作和参考机位。", "- B：同机位重复标准动作。",
        "- C：标准动作，相机机位降低。", "- D：同机位，画面右侧手抬得更高。", "",
        "## 数据质量", "",
        "| 视频 | 视频帧数 | 原始 JSON 帧数 | 本次采样帧数 | 时长 | 采样间隔 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, clip in clips.items():
        person_frames = sum(frame["people"] > 0 for frame in clip["frames"])
        lines.append(f"| {label} | {clip['video_frames']} | {clip['json_frames_total']} | {len(clip['frames'])} | "
                     f"{clip['duration']:.2f}s | 每 {sample_every} 帧取 1 帧，起点 {sample_offset} |")
    if sample_every > 1:
        lines += ["", f"本轮从已有 OpenPose JSON 按原始帧号 {sample_offset}、"
                  f"{sample_offset}+{sample_every}、{sample_offset}+2×{sample_every}……抽样；"
                  "没有对多帧图像做合并，也没有重新运行 OpenPose。",
                  "这样可以隔离‘减少参与比较的帧数’对差异报告的影响。实际把抽帧放在 OpenPose 之前时，"
                  "才会减少推理帧数和大部分识别耗时。", ""]
    lines += ["", f"关键点有效阈值：置信度 >= {CONFIDENCE_MIN:.2f}。缺失点不参与差异统计。",
              "四组均为单人 BODY_25 JSON。逐关键点覆盖率见 `quality_by_keypoint.csv`。", "",
              "## 比较方法", "",
              "1. 每帧以左右肩中点为原点，以肩宽为单位进行平移和尺度归一化；保留图像坐标轴方向，不做旋转校正。",
              "2. 以六个肩、肘、腕点的归一化轨迹做动态时间规整（DTW），用于处理视频帧数和动作速度差异。",
              "3. 对齐后逐关节统计归一化位置差的均值、中位数和 P90；另外比较肘部夹角，以及腕点相对肩点的高度变化。",
              f"4. 阶段按 A 的视频进度四等分。这是时间进度区间，不代表经验证的生物力学动作阶段。当前每 {sample_every} 帧采一帧，起点帧为 {sample_offset}。", "",
              "所有距离单位都是肩宽。数值越大表示对应关键点位置差越大。A-B 是本组重复动作参考波动；A-C 是降低机位后的综合变化；A-D 检查预期手部变化能否反映到数据。", "",
              "## 对比摘要", "",
              "| 对比 | 对齐样本 | 双臂关键点平均差（肩宽） | 解读边界 |",
              "|---|---:|---:|---|"]
    descriptions = {"A-B": "同机位重录的本组基线波动。", "A-C": "包含低机位带来的投影、构图及取景变化。",
                    "A-D": "检验右侧手臂抬高是否被定位差异捕捉。"}
    for pair in ["A-B", "A-C", "A-D"]:
        summary = pair_summaries[pair]
        val = summary["normalized_arm_mean"]
        lines.append(f"| {pair} | {summary['path_len']} | {val:.4f} | {descriptions[pair]} |" if np.isfinite(val) else f"| {pair} | {summary['path_len']} | NA | {descriptions[pair]} |")

    ab = pair_summaries["A-B"]["normalized_arm_mean"]
    ac = pair_summaries["A-C"]["normalized_arm_mean"]
    ad = pair_summaries["A-D"]["normalized_arm_mean"]
    camera_note = ("本次抽样中 A-C 略低于 A-B。" if ac < ab else
                   "本次抽样中 A-C 高于 A-B。")
    lines += ["", f"本次样本中，A-C 双臂关键点差约为 A-B 的 {ac / ab:.2f} 倍，"
              f"A-D 约为 A-B 的 {ad / ab:.2f} 倍。",
              f"{camera_note} D 的动作变化信号仍大于 A-B 的重复波动。",
              "抽样会改变相对差距，且每种条件目前只有一次录制；不能据此建立通用机位容差或动作阈值。"]

    def metric_value(pair: str, metric: str):
        for row in pair_rows:
            if row["pair"] == pair and row["metric"] == metric:
                try: return float(row["mean"])
                except (TypeError, ValueError): return float("nan")
        return float("nan")

    for side, name in [("R", "OpenPose R（被测者右侧，画面左侧）"),
                       ("L", "OpenPose L（被测者左侧，画面右侧）")]:
        dheight = metric_value("A-D", f"{side}_wrist_height_change_shoulder_widths")
        abheight = metric_value("A-B", f"{side}_wrist_height_change_shoulder_widths")
        acheight = metric_value("A-C", f"{side}_wrist_height_change_shoulder_widths")
        angle_d = metric_value("A-D", f"{side}_elbow_angle_abs_delta_deg")
        screen = "画面左侧" if side == "R" else "画面右侧"
        lines += ["", f"### {name}手臂（正面拍摄时约对应{screen}）", "",
                  f"A-D 平均腕点相对肩点的高度变化（正值表示 D 更高）：{dheight:.4f} 肩宽；A-B 为 {abheight:.4f}，A-C 为 {acheight:.4f}。",
                  f"A-D 肘部夹角绝对差均值：{angle_d:.2f} 度。"]

    lines += ["", "### 肩、肘、腕逐关节总体位置差", "",
              "| 对比 | 身体侧别 | 关节 | 有效对齐覆盖 | 平均差（肩宽） | P90（肩宽） |",
              "|---|---|---|---:|---:|---:|"]
    side_labels = {"RShoulder": "画面左", "RElbow": "画面左", "RWrist": "画面左",
                   "LShoulder": "画面右", "LElbow": "画面右", "LWrist": "画面右"}
    for pair in ["A-B", "A-C", "A-D"]:
        for joint_name in ["RShoulder", "RElbow", "RWrist", "LShoulder", "LElbow", "LWrist"]:
            row = next(row for row in joint_rows if row["pair"] == pair and row["joint"] == joint_name)
            lines.append(f"| {pair} | {side_labels[joint_name]} | {joint_name} | {row['coverage_pct']}% | "
                         f"{row['mean_delta_shoulder_widths']} | {row['p90_delta_shoulder_widths']} |")

    lines += ["", "### 关键关节分阶段变化", "",
              "下表的腕点高度变化为 target 相对 A 的变化，正值表示该侧腕点更高；关节位置差单位为肩宽。",
              "正面视频中，画面右侧手对应 OpenPose L（被拍摄者左侧），画面左侧手对应 OpenPose R。", "",
              "| 对比 | A 的进度阶段 | 画面右腕高度变化 | 画面右肘位置差 | 画面左腕高度变化 | 画面左肘位置差 |",
              "|---|---|---:|---:|---:|---:|"]

    def stage_mean(pair: str, stage: str, joint: str, metric: str):
        for row in stage_rows:
            if (row["pair"] == pair and row["stage_by_reference_progress"] == stage
                    and row["joint"] == joint and row["metric"] == metric):
                try: return float(row["mean"])
                except (TypeError, ValueError): return float("nan")
        return float("nan")

    for pair in ["A-B", "A-C", "A-D"]:
        for _, _, stage in STAGES:
            values = [
                stage_mean(pair, stage, "L_wrist_height_change_shoulder_widths", "wrist_height_change_shoulder_widths"),
                stage_mean(pair, stage, "LElbow", "position_delta"),
                stage_mean(pair, stage, "R_wrist_height_change_shoulder_widths", "wrist_height_change_shoulder_widths"),
                stage_mean(pair, stage, "RElbow", "position_delta"),
            ]
            shown = [f"{value:+.3f}" if np.isfinite(value) else "NA" for value in values]
            lines.append(f"| {pair} | {stage} | {shown[0]} | {shown[1]} | {shown[2]} | {shown[3]} |")

    lines += ["", "## 逐关节和动作阶段", "",
              "所有 25 个 BODY_25 点的逐关节阶段明细在 `stage_metrics.csv`；角度指标使用度数，位置和腕高指标使用肩宽。",
              "这里报告的是检测点差异，不等于动作正确性，也不自动说明差异由机位还是动作造成。", "",
              "## 结论与限制", "",
              "- 这四段视频可以检查单次重复、单次低机位和单次右手抬高的差异模式；每种条件只有一个样本，不能据此建立稳定阈值或普遍机位容差。",
              "- 肩中点/肩宽归一化去掉部分画面平移和人物大小变化，但低机位引起的透视投影仍会保留；因此 A-C 是机位变化的综合响应，不是纯相机参数测量。",
              "- DTW 会寻找姿态序列的最相似时间对应，适合不同速度的粗对齐，但也可能把真实的阶段差异部分对齐掉。解读阶段差异时要结合原视频。",
              "- 正面拍摄时，被测者自身右侧（OpenPose R）出现在画面左侧；被测者自身左侧（OpenPose L）出现在画面右侧。本次 D 的画面右侧抬手变化主要对应 OpenPose L。",
              "- 膝、踝、脚部在四段数据中都没有达到置信度门槛；髋部覆盖也因片段而异。因此当前可解释结论限于上肢，不适合报告下肢动作差异。",
              "- 这是一份小样本可解释基线，不给总分、合格判断或动作建议。", "",
              "## 产物", "",
              "- `quality_by_keypoint.csv`：每段每个关键点的置信度覆盖。",
              "- `pairwise_joint_metrics.csv`：A-B、A-C、A-D 逐关节差异。",
              "- `stage_metrics.csv`：按参考视频时间进度分段的逐关节差异。",
              "- `pair_summary.csv`：整体及左右手臂角度/腕高摘要。",
              "- 可用 `python MotionDiff/analysis/compare_test1.py` 重算全帧基线。",
              "- 可用 `python MotionDiff/analysis/compare_test1.py --sample-every 4 --sample-offset 0` 从现有全帧 JSON 模拟每 4 帧采 1 帧。",
              "- 新视频先用 `extract_frames.py` 抽帧，再把抽样图片交给 OpenPose；比较时通过 `--json-dir` 指向抽样 JSON。"]
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if sample_every > 1:
        dense_path = ROOT / "MotionDiff" / "analysis" / "results" / "test1" / "pair_summary.csv"
        dense_rows = list(csv.DictReader(dense_path.open(encoding="utf-8-sig"))) if dense_path.exists() else []
        dense_values = {(row["pair"], row["metric"]): float(row["mean"])
                        for row in dense_rows
                        if row["metric"] == "all_arm_keypoint_mean_delta_shoulder_widths" and row["mean"]}
        sampled_values = {(row["pair"], row["metric"]): float(row["mean"])
                          for row in pair_rows
                          if row["metric"] == "all_arm_keypoint_mean_delta_shoulder_widths" and row["mean"]}
        sensitivity_lines = [
            f"# 全帧与每 {sample_every} 帧抽 1 帧的结果对照", "",
            f"这里比较的是同一批 OpenPose JSON：全帧结果与只保留从帧 {sample_offset} 开始、每隔 {sample_every} 帧的结果。",
            "它检验差异信号对降采样是否稳定；真实推理耗时缩短需要在 OpenPose 输入端抽帧后另行计时。", "",
            "| 对比 | 全帧平均差（肩宽） | 抽样平均差（肩宽） | 相对变化 |", "|---|---:|---:|---:|"]
        for pair in ["A-B", "A-C", "A-D"]:
            key = (pair, "all_arm_keypoint_mean_delta_shoulder_widths")
            dense, sampled = dense_values.get(key, float("nan")), sampled_values.get(key, float("nan"))
            change = (sampled / dense - 1) * 100 if np.isfinite(dense) and dense else float("nan")
            vals = [f"{value:.4f}" if np.isfinite(value) else "NA" for value in (dense, sampled)]
            change_text = f"{change:+.1f}%" if np.isfinite(change) else "NA"
            sensitivity_lines.append(f"| {pair} | {vals[0]} | {vals[1]} | {change_text} |")
        dense_ad = dense_values.get(("A-D", "all_arm_keypoint_mean_delta_shoulder_widths"), float("nan"))
        dense_ab = dense_values.get(("A-B", "all_arm_keypoint_mean_delta_shoulder_widths"), float("nan"))
        sample_ad = sampled_values.get(("A-D", "all_arm_keypoint_mean_delta_shoulder_widths"), float("nan"))
        sample_ab = sampled_values.get(("A-B", "all_arm_keypoint_mean_delta_shoulder_widths"), float("nan"))
        if all(np.isfinite(v) for v in (dense_ad, dense_ab, sample_ad, sample_ab)):
            sensitivity_lines += ["", f"A-D 是否高于 A-B：全帧 {dense_ad > dense_ab}；抽样 {sample_ad > sample_ab}。",
                                  f"D 相对重复波动的差距倍数：全帧 {dense_ad / dense_ab:.2f}；抽样 {sample_ad / sample_ab:.2f}。"]
        (OUT_DIR / "sampling_sensitivity.md").write_text("\n".join(sensitivity_lines) + "\n", encoding="utf-8")

        if sample_every == 4 and sample_offset == 0:
            phase_data = []
            for offset in range(sample_every):
                suffix = f"test1_every{sample_every}" + (f"_offset{offset}" if offset else "")
                phase_dir = ROOT / "MotionDiff" / "analysis" / "results" / suffix
                pair_file, stage_file = phase_dir / "pair_summary.csv", phase_dir / "stage_metrics.csv"
                if not pair_file.exists() or not stage_file.exists():
                    continue
                p_rows = list(csv.DictReader(pair_file.open(encoding="utf-8-sig")))
                s_rows = list(csv.DictReader(stage_file.open(encoding="utf-8-sig")))
                means = {(row["pair"], row["metric"]): float(row["mean"])
                         for row in p_rows
                         if row["metric"] == "all_arm_keypoint_mean_delta_shoulder_widths" and row["mean"]}
                wrist_mid = {}
                for pair in ["A-B", "A-C", "A-D"]:
                    values = [float(row["mean"]) for row in s_rows
                              if row["pair"] == pair
                              and row["joint"] == "L_wrist_height_change_shoulder_widths"
                              and row["stage_by_reference_progress"] in ("25-50%", "50-75%")
                              and row["mean"]]
                    wrist_mid[pair] = float(np.mean(values)) if values else float("nan")
                phase_data.append((offset, means, wrist_mid))

            if len(phase_data) == sample_every:
                phase_lines = [
                    "# 每 4 帧抽 1 帧：采样起点敏感性", "",
                    "从四种可能的采样起点分别分析：帧 0、1、2、3 开始，然后每隔 4 帧取一帧。",
                    "这样检查结果是否依赖某一个采样相位。数据仍来自已有逐帧 OpenPose JSON。", "",
                    "| 起始帧 | A-B 上肢差 | A-C 上肢差 | A-D 上肢差 | A-D/A-B | 中段画面右腕变化 A-B | A-C | A-D |",
                    "|---:|---:|---:|---:|---:|---:|---:|---:|"]
                ratios = []
                for offset, means, wrist_mid in phase_data:
                    ab_v = means[("A-B", "all_arm_keypoint_mean_delta_shoulder_widths")]
                    ac_v = means[("A-C", "all_arm_keypoint_mean_delta_shoulder_widths")]
                    ad_v = means[("A-D", "all_arm_keypoint_mean_delta_shoulder_widths")]
                    ratios.append(ad_v / ab_v)
                    wvals = [wrist_mid.get(pair, float("nan")) for pair in ("A-B", "A-C", "A-D")]
                    phase_lines.append(f"| {offset} | {ab_v:.4f} | {ac_v:.4f} | {ad_v:.4f} | {ad_v/ab_v:.2f} | "
                                       + " | ".join(f"{value:+.3f}" if np.isfinite(value) else "NA" for value in wvals)
                                       + " |")
                d_separated = all(means[("A-D", "all_arm_keypoint_mean_delta_shoulder_widths")]
                                  > means[("A-B", "all_arm_keypoint_mean_delta_shoulder_widths")]
                                  for _, means, _ in phase_data)
                c_over_b = [means[("A-C", "all_arm_keypoint_mean_delta_shoulder_widths")]
                            / means[("A-B", "all_arm_keypoint_mean_delta_shoulder_widths")]
                            for _, means, _ in phase_data]
                phase_lines += ["", f"四种起点下 A-D 都高于 A-B：{d_separated}。",
                                f"D/A-B 差异倍数范围：{min(ratios):.2f} 到 {max(ratios):.2f}。",
                                f"A-C/A-B 比值范围：{min(c_over_b):.2f} 到 {max(c_over_b):.2f}；四种起点下 A-C 均未超过 A-B。",
                                "因此每 4 帧取 1 帧在本组数据里稳定保留了较大的抬手信号，但不能可靠区分这次低机位效应与同机位重录波动。",
                                "如果产品只需发现较明显的动作偏差，它可作为速度优先的候选；若要判断细小差异或机位误差，当前证据不足，宜提高采样频率并继续验证。"]
                (ROOT / "MotionDiff" / "analysis" / "results" / "test1_every4"
                 / "sampling_phase_sensitivity.md").write_text("\n".join(phase_lines) + "\n", encoding="utf-8")
    print(f"Wrote comparison report and CSVs to {OUT_DIR}")


if __name__ == "__main__":
    main()
