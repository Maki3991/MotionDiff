const form = document.querySelector('#analysis-form');
const statusPanel = document.querySelector('#status-panel');
const statusLabel = document.querySelector('#status-label');
const statusPercent = document.querySelector('#status-percent');
const progressBar = document.querySelector('#progress-bar');
const statusMessage = document.querySelector('#status-message');
const results = document.querySelector('#results');
const analyzeButton = document.querySelector('#analyze-button');
let activeRun = null;

function bindFileName(inputId, outputId) {
  document.querySelector(`#${inputId}`).addEventListener('change', (event) => {
    const file = event.target.files[0];
    document.querySelector(`#${outputId}`).textContent = file ? file.name : '选择视频文件';
  });
}
bindFileName('reference-file', 'reference-name');
bindFileName('student-file', 'student-name');

function setStatus(status, progress, message) {
  statusPanel.hidden = false;
  const labels = { queued: '排队中', processing: '处理中', complete: '已完成', failed: '失败' };
  statusLabel.textContent = labels[status] || status;
  statusPercent.textContent = `${Math.round(progress || 0)}%`;
  progressBar.style.width = `${Math.max(0, Math.min(100, progress || 0))}%`;
  statusMessage.textContent = message || '';
}

function format(value, digits = 3) {
  return value === null || value === undefined || Number.isNaN(value) ? '—' : Number(value).toFixed(digits);
}

function formatTime(milliseconds) {
  if (milliseconds === null || milliseconds === undefined || !Number.isFinite(Number(milliseconds))) return '未知';
  const totalSeconds = Math.max(0, Math.floor(Number(milliseconds) / 1000));
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`;
}

function seekVideo(videoId, milliseconds) {
  const video = document.querySelector(`#${videoId}`);
  const seconds = Number(milliseconds) / 1000;
  if (!Number.isFinite(seconds)) return;
  video.currentTime = Math.max(0, seconds);
  video.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function renderResult(payload) {
  const report = payload.comparison;
  const summary = report.summary || {};
  const alignment = report.alignment || {};
  const run = report.run || {};
  const unjudgeable = report.status !== 'complete';
  const judgementNote = document.querySelector('#judgement-note');
  judgementNote.hidden = !unjudgeable;
  judgementNote.textContent = unjudgeable
    ? `无法判断：${(report.status_reasons || []).join(' ') || '有效关键点不足，不能可靠比较。'}`
    : '';
  document.querySelector('#metric-score').textContent = unjudgeable || summary.similarity_index == null ? '无法判断' : `${Number(summary.similarity_index).toFixed(1)}`;
  document.querySelector('#metric-delta').textContent = unjudgeable || summary.mean_position_delta_shoulder_widths == null ? '无法判断' : format(summary.mean_position_delta_shoulder_widths, 3);
  document.querySelector('#metric-coverage').textContent = `${Math.round((alignment.coverage_reference || 0) * 100)}% / ${Math.round((alignment.coverage_target || 0) * 100)}%`;
  document.querySelector('#metric-time').textContent = run.elapsed_seconds == null ? '—' : `${Number(run.elapsed_seconds).toFixed(1)}s`;
  document.querySelector('#finding-count').textContent = (report.findings || []).length;
  document.querySelector('#report-link').href = payload.report_url || '#';
  const refVideo = document.querySelector('#reference-video');
  const studentVideo = document.querySelector('#student-video');
  refVideo.src = payload.video_urls.reference;
  studentVideo.src = payload.video_urls.student;
  document.querySelector('#reference-video-name').textContent = '参考动作';
  document.querySelector('#student-video-name').textContent = '学员动作';
  document.querySelector('#findings').innerHTML = (report.findings || []).map((item) => `
    <div class="finding">
      <div class="finding-title"><span class="finding-chip">${item.joint_label}</span><span>${item.direction}</span></div>
      <p>${item.message} 对齐覆盖 ${(item.coverage * 100).toFixed(0)}%，P90 差异 ${format(item.p90_delta, 3)} 个肩宽。</p>
      <button class="finding-seek" type="button" data-reference-ms="${item.peak_reference_timestamp_ms ?? ''}" data-student-ms="${item.peak_target_timestamp_ms ?? ''}">定位 A ${formatTime(item.peak_reference_timestamp_ms)} / B ${formatTime(item.peak_target_timestamp_ms)}</button>
    </div>`).join('') || '<p class="format-note">当前有效关键点不足，无法生成可解释差异。</p>';
  document.querySelectorAll('.finding-seek').forEach((button) => {
    button.addEventListener('click', () => {
      seekVideo('reference-video', button.dataset.referenceMs);
      seekVideo('student-video', button.dataset.studentMs);
    });
  });
  const phaseRows = unjudgeable ? '<tr><td colspan="3">有效姿态数据不足，无法判断</td></tr>' : (report.phases || []).map((phase) => {
    const candidates = Object.entries(phase.joints || {}).filter(([, value]) => value.mean != null).sort((a, b) => b[1].mean - a[1].mean);
    const top = candidates[0];
    const labels = {left_wrist:'左手腕',right_wrist:'右手腕',left_elbow:'左肘',right_elbow:'右肘',left_shoulder:'左肩',right_shoulder:'右肩',left_hip:'左髋',right_hip:'右髋',left_knee:'左膝',right_knee:'右膝',left_ankle:'左踝',right_ankle:'右踝'};
    return `<tr><td>${phase.phase}</td><td>${top ? (labels[top[0]] || top[0]) : '—'}</td><td>${top ? `${Number(top[1].mean).toFixed(3)} 个肩宽` : '—'}</td></tr>`;
  }).join('');
  document.querySelector('#phase-table').innerHTML = phaseRows;
  document.querySelector('#limitations').innerHTML = `<p>结果边界</p><ul>${(report.limitations || []).map((item) => `<li>${item}</li>`).join('')}</ul>`;
  ['reference-pose', 'student-pose'].forEach((id) => {
    const canvas = document.querySelector(`#${id}`);
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
  });
  if (report.visualization && !unjudgeable) {
    drawPose('reference-pose', report.visualization.reference, '#61d8c6');
    drawPose('student-pose', report.visualization.student, '#f0b15a');
  }
  results.hidden = false;
  results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

const POSE_EDGES = [['left_shoulder','right_shoulder'],['left_shoulder','left_elbow'],['left_elbow','left_wrist'],['right_shoulder','right_elbow'],['right_elbow','right_wrist'],['left_shoulder','left_hip'],['right_shoulder','right_hip'],['left_hip','right_hip'],['left_hip','left_knee'],['left_knee','left_ankle'],['right_hip','right_knee'],['right_knee','right_ankle']];
async function drawPose(canvasId, url, color) {
  const canvas = document.querySelector(`#${canvasId}`);
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);
  try {
    const payload = await (await fetch(url)).json();
    const person = (payload.people || [])[0];
    const points = Object.fromEntries((person?.keypoints || []).map((point) => [point.name, point]));
    const xy = (name) => { const point = points[name]; return point && point.x != null && point.y != null ? [point.x, point.y] : null; };
    const values = Object.values(points).filter((point) => point.x != null && point.y != null);
    if (!values.length) return;
    const maxX = Math.max(...values.map((point) => point.x), 1); const maxY = Math.max(...values.map((point) => point.y), 1);
    const scale = Math.min((canvas.width - 30) / maxX, (canvas.height - 30) / maxY);
    const project = (name) => { const value = xy(name); return value ? [15 + value[0] * scale, 15 + value[1] * scale] : null; };
    context.lineWidth = 4; context.lineCap = 'round'; context.strokeStyle = color;
    POSE_EDGES.forEach(([a, b]) => { const from = project(a); const to = project(b); if (!from || !to) return; context.beginPath(); context.moveTo(...from); context.lineTo(...to); context.stroke(); });
    context.fillStyle = '#f3f8f7'; Object.keys(points).forEach((name) => { const point = project(name); if (!point) return; context.beginPath(); context.arc(point[0], point[1], 4, 0, Math.PI * 2); context.fill(); });
  } catch (error) { context.fillStyle = '#9fb2b4'; context.font = '13px Segoe UI'; context.fillText('关键点预览不可用', 18, 28); }
}

async function poll(runId) {
  const response = await fetch(`/api/status/${runId}`);
  const data = await response.json();
  setStatus(data.status, data.progress, data.message || data.error);
  if (data.status === 'complete') {
    analyzeButton.disabled = false;
    analyzeButton.innerHTML = '开始分析 <span aria-hidden="true">→</span>';
    renderResult(data.result);
    return;
  }
  if (data.status === 'failed') {
    analyzeButton.disabled = false;
    analyzeButton.innerHTML = '重新尝试 <span aria-hidden="true">↻</span>';
    statusMessage.textContent = data.error || '分析失败';
    return;
  }
  window.setTimeout(() => poll(runId), 700);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const reference = document.querySelector('#reference-file').files[0];
  const student = document.querySelector('#student-file').files[0];
  if (!reference || !student) return;
  results.hidden = true;
  analyzeButton.disabled = true;
  analyzeButton.textContent = '处理中…';
  setStatus('queued', 0, '正在上传两段视频');
  const data = new FormData();
  data.append('reference', reference);
  data.append('student', student);
  try {
    const response = await fetch('/api/analyze', { method: 'POST', body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || '上传失败');
    activeRun = payload.run_id;
    await poll(activeRun);
  } catch (error) {
    analyzeButton.disabled = false;
    analyzeButton.textContent = '重新尝试';
    setStatus('failed', 100, error.message);
  }
});

document.querySelector('#new-analysis').addEventListener('click', () => {
  results.hidden = true;
  statusPanel.hidden = true;
  form.reset();
  document.querySelector('#reference-name').textContent = '选择视频文件';
  document.querySelector('#student-name').textContent = '选择视频文件';
  window.scrollTo({ top: 0, behavior: 'smooth' });
});
