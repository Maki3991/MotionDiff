"""Measured side-view squat evidence. No coaching text or correctness rules."""
from __future__ import annotations

import base64
import math
from statistics import median

from tools.ai_feedback import FeedbackError
from tools.compare_mediapipe_sequences import angle, finite, xy


VERSION = "motiondiff-squat-evidence/1.0"
CORE = ("shoulder", "hip", "knee", "ankle")
PHASE_LABELS = {"standing": "开始站立", "descent": "下蹲中段", "bottom": "最低位",
                "ascent": "起身中段", "finish": "结束站立"}


def usable(point):
    if not point or not xy(point):
        return False
    quality = [finite(point.get(key)) for key in ("visibility", "presence")]
    return all(value is not None and value >= .5 for value in quality)


def sample(frame: dict, side: str) -> dict | None:
    points = frame["points"]
    if frame["people"] != 1 or any(not usable(points.get(f"{side}_{name}")) for name in CORE):
        return None
    shoulder, hip, knee, ankle = [xy(points[f"{side}_{name}"]) for name in CORE]
    timestamp = finite(frame.get("timestamp_ms"))
    knee_angle = angle(hip, knee, ankle)
    femur = math.dist(hip, knee)
    if (timestamp is None or knee_angle is None or femur < 5 or
            math.dist(shoulder, hip) < 5 or math.dist(knee, ankle) < 5):
        return None
    # Pixel coordinates preserve the aspect ratio; normalized x/y alone do not.
    metrics = {
        "knee_angle_deg": knee_angle,
        "trunk_inclination_deg": math.degrees(math.atan2(abs(shoulder[0] - hip[0]), hip[1] - shoulder[1])),
        "hip_minus_knee_height_femur": (hip[1] - knee[1]) / femur,
        "thigh_angle_from_horizontal_deg": math.degrees(math.atan2(knee[1] - hip[1], abs(knee[0] - hip[0]))),
    }
    heel, toe = points.get(f"{side}_heel"), points.get(f"{side}_foot_index")
    direction = None
    if usable(heel) and usable(toe):
        heel, toe = xy(heel), xy(toe)
        foot_length = math.dist(heel, toe)
        if foot_length >= 5 and abs(toe[0] - heel[0]) >= foot_length * .5:
            direction = 1 if toe[0] > heel[0] else -1
            metrics["shin_forward_angle_deg"] = math.degrees(math.atan2(
                direction * (knee[0] - ankle[0]), ankle[1] - knee[1]))
    return {"frame_index": frame["frame_index"], "timestamp_ms": timestamp,
            "metrics": metrics, "foot_direction": direction,
            "quality": min(min(points[f"{side}_{name}"][key] for key in ("visibility", "presence")) for name in CORE)}


def side_samples(sequence, side):
    return [value for frame in sequence["frames"] if (value := sample(frame, side))]


def extract_clip(sequence: dict, side: str) -> dict:
    frames = sequence["frames"]
    samples = side_samples(sequence, side)
    coverage = len(samples) / max(1, len(frames))
    reasons = []
    if len(samples) < 12 or coverage < .6:
        return {"status": "insufficient_data", "side": side, "coverage": coverage,
                "reasons": ["肩、髋、膝、踝的同侧可靠数据不足，请完整露出身体并减少遮挡。"]}
    times = [s["timestamp_ms"] for s in samples]
    if any(b <= a for a, b in zip(times, times[1:])):
        return {"status": "insufficient_data", "reasons": ["视频时间信息不可用于动作分段。"]}
    span = times[-1] - times[0]
    interval = median(b - a for a, b in zip(times, times[1:]))
    directions = [s["foot_direction"] for s in samples if s["foot_direction"] is not None]
    if directions and max(directions.count(-1), directions.count(1))/len(directions) < .9:
        for value in samples:
            value["metrics"].pop("shin_forward_angle_deg", None)
    if span < 1000 or max(b - a for a, b in zip(times, times[1:])) > max(350, interval * 5):
        reasons.append("连续动作证据不足，请上传无遮挡的一次完整深蹲。")
    radius = max(1, round(120 / interval))
    smoothed = [median(s["metrics"]["knee_angle_deg"] for s in
                       samples[max(0, i-radius):i+radius+1]) for i in range(len(samples))]
    edge_count = max(3, min(len(samples)//5, round(400 / interval)))
    start_angle, finish_angle = median(smoothed[:edge_count]), median(smoothed[-edge_count:])
    standing_angle = min(start_angle, finish_angle)
    bottom_angle = min(smoothed)
    excursion = standing_angle - bottom_angle
    # Allow a shallow but complete squat; the evidence windows still require
    # a clear descent and ascent on both sides of the bottom.
    if standing_angle < 150 or excursion < 10:
        reasons.append("未确认站立→下蹲→起身的完整单次动作，请保留两端站立画面。")
    active_threshold = standing_angle - max(10, excursion * .35)
    active = [i for i, value in enumerate(smoothed) if value < active_threshold]
    groups = []
    for i in active:
        if not groups or times[i] - times[groups[-1][-1]] > 350:
            groups.append([i])
        else:
            groups[-1].append(i)
    groups = [group for group in groups if times[group[-1]] - times[group[0]] >= 200]
    if len(groups) != 1:
        reasons.append("未确认只有一次深蹲，请剪成一次完整动作后重试。")
    if reasons:
        return {"status": "insufficient_data", "side": side, "coverage": coverage, "reasons": reasons}
    active_start, active_end = groups[0][0], groups[0][-1]
    # Use a stable low-angle window, never an isolated deepest frame.
    bottom_indices = [i for i in groups[0] if smoothed[i] <= bottom_angle + 5]
    bottom_index = bottom_indices[len(bottom_indices)//2]
    if (bottom_index <= edge_count or bottom_index >= len(samples)-edge_count or
            times[bottom_index] - times[active_start] < 150 or
            times[active_end] - times[bottom_index] < 150):
        return {"status": "insufficient_data", "reasons": ["最低位两侧的下蹲和起身证据不完整，请保留整个动作。"]}
    halfway = (standing_angle + bottom_angle) / 2
    descent = min(range(edge_count, bottom_index), key=lambda i: abs(smoothed[i] - halfway))
    ascent = min(range(bottom_index+1, len(samples)-edge_count), key=lambda i: abs(smoothed[i] - halfway))
    anchors = {"standing": edge_count//2, "descent": descent, "bottom": bottom_index,
               "ascent": ascent, "finish": len(samples)-1-edge_count//2}
    windows = {}
    for phase, index in anchors.items():
        center = samples[index]["timestamp_ms"]
        values = [s for s in samples if abs(s["timestamp_ms"] - center) <= max(120, interval)]
        if len(values) < 3:
            return {"status": "insufficient_data", "reasons": ["动作阶段的连续有效帧不足，无法稳定提取证据。"]}
        metrics = {}
        for name in samples[index]["metrics"]:
            metric_values = [s["metrics"][name] for s in values if name in s["metrics"]]
            if len(metric_values) >= max(3, math.ceil(len(values)*.6)):
                metrics[name] = {"median": round(median(metric_values), 2),
                                 "min": round(min(metric_values), 2), "max": round(max(metric_values), 2)}
        windows[phase] = {"frame_index": samples[index]["frame_index"], "timestamp_ms": center,
                          "window_start_ms": values[0]["timestamp_ms"],
                          "window_end_ms": values[-1]["timestamp_ms"],
                          "samples": len(values), "metrics": metrics}
    return {"status": "complete", "side": side, "coverage": round(coverage, 3),
            "foot_coverage": round(sum("shin_forward_angle_deg" in s["metrics"] for s in samples)/len(samples), 3),
            "stage_method": "smoothed knee angle; single complete repetition; window medians",
            "windows": windows, "reasons": []}


def build_evidence(reference: dict, student: dict) -> dict:
    # High landmark confidence can still describe an occluded, nearly straight
    # leg. Prefer the same side with a clear squat excursion in both clips.
    sides = {side: min(sum(v["quality"] for v in side_samples(s, side))/max(1, len(s["frames"]))
                       for s in (reference, student)) for side in ("left", "right")}
    candidates = {side: {"reference": extract_clip(reference, side),
                         "student": extract_clip(student, side)} for side in sides}
    def side_score(side):
        pair = candidates[side]
        if any(clip["status"] != "complete" for clip in pair.values()):
            return (0, 0, sides[side])
        excursion = min(clip["windows"]["standing"]["metrics"]["knee_angle_deg"]["median"] -
                        clip["windows"]["bottom"]["metrics"]["knee_angle_deg"]["median"]
                        for clip in pair.values())
        return (1, excursion, sides[side])
    side = max(sides, key=side_score)
    clips = candidates[side]
    reasons = [f"{('参考' if name == 'reference' else '学员')}视频：{reason}"
               for name, clip in clips.items() for reason in clip["reasons"]]
    result = {"schema_version": VERSION, "action": "squat", "view": "single_side_expected",
              "status": "insufficient_data" if reasons else "complete", "reasons": reasons,
              "clips": clips, "evidence": [],
              "metric_definitions": {
                  "knee_angle_deg": "二维髋膝踝内角，角度小表示膝弯曲更多",
                  "shin_forward_angle_deg": "二维踝膝连线相对竖直角度，正为沿脚跟至脚尖方向前移；不是内扣外翻",
                  "hip_minus_knee_height_femur": "髋中心与膝中心的画面高度差/大腿段长度；正为髋更低；仅内部尺度",
                  "thigh_angle_from_horizontal_deg": "二维髋膝连线与水平夹角，正为髋中心高于膝；不是臀部边缘高度",
                  "trunk_inclination_deg": "二维肩髋连线相对竖直倾角；不是脊柱曲率",
              },
              "capture_limits": ["只比较相近侧面机位各一次完整深蹲。自动机位一致性识别尚未实现。",
                                 "角度为二维投影，身体比例和遮挡影响结果；不推断伤病和动作安全。",
                                 "左右是人体解剖左右，不是画面左右。"]}
    if reasons:
        return result
    for phase, label in PHASE_LABELS.items():
        pair = {name: clip["windows"][phase] for name, clip in clips.items()}
        common = pair["reference"]["metrics"].keys() & pair["student"]["metrics"].keys()
        dimensions = ["depth", "trunk_angle"]
        if "shin_forward_angle_deg" in common:
            dimensions.append("knee_trajectory")
        result["evidence"].append({"id": phase, "phase_label": label,
                                   "available_dimensions": dimensions, **pair,
                                   "student_minus_reference": {
                                       name: round(pair["student"]["metrics"][name]["median"]-
                                                   pair["reference"]["metrics"][name]["median"], 2)
                                       for name in sorted(common)}})
    return result


def evidence_images(evidence: dict, reference_path, student_path, cv2) -> list[dict]:
    """Four bounded JPEGs: paired descent and bottom evidence, not full videos."""
    images = []
    for name, path in (("reference", reference_path), ("student", student_path)):
        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                raise FeedbackError("images")
            for item in evidence["evidence"]:
                if item["id"] not in ("descent", "bottom"):
                    continue
                frame_index = item[name]["frame_index"]
                if not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
                    raise FeedbackError("images")
                ok, frame = capture.read()
                if not ok or abs(capture.get(cv2.CAP_PROP_POS_FRAMES) - (frame_index+1)) > 1:
                    raise FeedbackError("images")
                height, width = frame.shape[:2]
                scale = min(1., 640/max(height, width))
                if scale < 1:
                    frame = cv2.resize(frame, (round(width*scale), round(height*scale)))
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if not ok or len(encoded) > 200_000:
                    raise FeedbackError("images")
                images.append({"label": f"{name} {item['id']} timestamp_ms={item[name]['timestamp_ms']}",
                               "data_url": "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")})
        finally:
            capture.release()
    if len(images) != 4:
        raise FeedbackError("images")
    return images
