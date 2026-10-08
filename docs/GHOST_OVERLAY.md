# Ghost 骨架叠加回放

在学员视频上叠加半透明琥珀色的「参考骨架幽灵」，随播放逐帧跟随，与学员自己的实线青色骨架同屏对比。对齐关系复用对比引擎的 DTW 结果，空间对齐复用对比引擎的归一化锚点约定（双肩中点 + 肩宽），因此**不修改 `compare_mediapipe_sequences.py`**。

## 数据链路

```
pose/reference/*.json ─┐
                       ├─→ tools/ghost_data.py ─→ GET /api/ghost/<run_id> ─→ 前端 canvas 覆盖层
pose/student/*.json ───┤         （+ report/comparison.json 的 alignment_rows）
report/comparison.json ┘
```

1. `tools/ghost_data.py` 的 `build_ghost_payload(run_dir)` 汇总双路骨架帧 + DTW 对齐对，输出一份紧凑 JSON（schema `motiondiff-ghost/1.0`）。
2. `app.py` 提供 `GET /api/ghost/<run_id>`（`STORE.touch` 刷新临时运行的 TTL；数据直接从磁盘读，所以演示脚本生成的 run 也能访问）；分析完成的 result 里带 `ghost_url`。
3. 前端 `static/app.js` 按 `video.currentTime` 二分查找学员帧，经 pairs 映射找到参考帧，在 `<canvas id="student-ghost">` 上重绘；`index.html` 提供开关（默认开）。

## Payload Schema（motiondiff-ghost/1.0）

```json
{
  "schema_version": "motiondiff-ghost/1.0",
  "joints": ["left_shoulder", "...", "right_ear"],
  "bones":  [[0, 1], [0, 2], "..."],
  "anchor": {"center": "shoulder midpoint", "scale": "shoulder distance",
             "quality_threshold": 0.5},
  "reference": {"width": 1280, "height": 720,
    "frames": [{"i": 0, "t": 0.0, "k": [["x", "y", "q"]], "a": ["cx", "cy", "w"]}]},
  "student":  {},
  "pairs": [[0, 0]]
}
```

- `k`：14 个关节的 `[x, y, q]`（原始像素坐标；`q = min(visibility, presence)` 保留两位）。无人或关键点缺失为 `null`。
- `a`：锚点 `[双肩中点x, 双肩中点y, 肩宽]`；任一侧肩点质量 < 0.5 时为 `null`。
- 无人帧保留为 `k: null, a: null`，**不缩短时间线**（延续导出器「不静默丢帧」原则，前端可可靠按时间戳查帧）。

## 锚点变换（前端）

参考帧骨架映射到学员坐标系：

```
p′ = a_student + (p − a_reference) × (a_student.w / a_reference.w)
```

即双肩中点对齐 + 按肩宽比例缩放，天然抗拍摄远近、站位偏移。验证：合成数据中学员比例 0.85、偏移 (60, 40)，变换后 ghost 关键点与学员关键点逐像素重合。任一帧锚点为 `null`（肩部置信度不足）时回退为只画学员骨架。

## 回退与边界

- 报告缺失或 `alignment_rows` 为空 → API 返回 400 及原因。
- run 目录不存在（含临时运行被清理）→ 404。
- 前端拉取 ghost 数据失败 → 静默不画，不影响报告展示。

## 联调 / 演示

无需摄像头：

```bash
python app.py --port 8770          # 先启动服务
python tools/make_demo_run.py      # 再生成合成 run（含真实 DTW 结果）
# curl http://127.0.0.1:8770/api/ghost/a1b2c3d4e5f60718293a4b5c6d7e8f90
```

注意：app 启动时会清理「孤儿」run 目录（`clear_orphaned_runs_on_start`），服务重启后需重新运行演示脚本。

测试：`python -m unittest discover -s tools/tests`（`test_ghost_data.py` 4 个用例：结构/锚点/pairs、低质量肩部 → 锚点 null、缺报告/空 rows 报错、未知帧号跳过）。

## 已知瑕疵

- 视频控件条占的高度（约 30px）计入 `video.clientHeight`，骨架有轻微纵向偏移；修复方向是用 `getBoundingClientRect` 扣除控件高度或按视频内容区比例计算 scaleY。
- 幽灵只画单人的第一个 person（与对比引擎一致）。
