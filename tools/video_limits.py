"""Validate video metadata before expensive pose extraction."""
import math


def inspect_video(path, cv2, *, max_duration_seconds, max_frames):
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("视频无法打开，请上传可播放的视频文件。")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not math.isfinite(fps) or not math.isfinite(frames) or fps <= 0 or frames < 1:
            raise ValueError("无法可靠读取视频时长，请重新导出视频后上传。")
        duration = frames / fps
        if duration > max_duration_seconds:
            raise ValueError(f"视频时长 {duration:.2f} 秒，超过 {max_duration_seconds} 秒上限，请先剪短。")
        if frames > max_frames:
            raise ValueError(f"视频帧数超过 {max_frames} 帧，请缩短视频或降低帧率。")
        return {"duration_seconds": duration, "fps": fps, "frames": math.ceil(frames)}
    finally:
        capture.release()
