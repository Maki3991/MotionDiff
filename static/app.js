const ACTION_CATALOG = [
  {
    id: 'strength',
    name: '力量 / 体能基础',
    shortName: '力量与体能',
    description: '建立全身力量与基础动作控制。',
    tone: 'teal',
    actions: [
      { id: 'squat', name: '深蹲', description: '比较下肢轨迹与身体控制', available: true },
      { id: 'lunge', name: '弓步蹲' },
      { id: 'push-up', name: '俯卧撑' },
      { id: 'plank', name: '平板支撑' },
      { id: 'pull-up', name: '引体向上' },
      { id: 'deadlift', name: '硬拉姿势' },
    ],
  },
  {
    id: 'football', name: '足球', description: '从脚下触球到完整射门动作。', tone: 'green',
    actions: [{ id: 'shooting', name: '射门', detail: '正脚背 / 内脚背' }, { id: 'passing', name: '传球' }, { id: 'juggling', name: '颠球' }, { id: 'free-kick', name: '任意球' }],
  },
  {
    id: 'basketball', name: '篮球', description: '拆解投篮、上篮与控球基础。', tone: 'orange',
    actions: [{ id: 'shooting-free-throw', name: '投篮 / 罚球' }, { id: 'layup', name: '上篮' }, { id: 'stationary-dribble', name: '原地运球' }],
  },
  {
    id: 'school-sports', name: '中考体育全套', description: '覆盖常见中考体育项目的动作准备。', tone: 'blue',
    actions: [{ id: 'standing-long-jump', name: '立定跳远' }, { id: 'medicine-ball', name: '实心球' }, { id: 'jump-rope', name: '跳绳' }, { id: 'sit-up', name: '仰卧起坐' }, { id: 'volleyball-pass', name: '排球垫球' }, { id: 'running', name: '跑姿' }],
  },
  {
    id: 'racket', name: '挥拍基础', description: '羽毛球、乒乓球和网球的挥拍动作。', tone: 'purple',
    actions: [{ id: 'badminton-clear', name: '羽毛球高远球' }, { id: 'table-tennis-forehand', name: '乒乓正手攻球' }, { id: 'tennis-serve', name: '网球发球' }],
  },
];

const form = document.querySelector('#analysis-form');
const statusPanel = document.querySelector('#status-panel');
const statusLabel = document.querySelector('#status-label');
const statusPercent = document.querySelector('#status-percent');
const progressBar = document.querySelector('#progress-bar');
const statusMessage = document.querySelector('#status-message');
const results = document.querySelector('#results');
const analyzeButton = document.querySelector('#analyze-button');
const retryStatus = document.querySelector('#retry-status');
let activeRun = null;

const views = {
  catalog: document.querySelector('#catalog-view'),
  actions: document.querySelector('#action-view'),
  coming: document.querySelector('#coming-view'),
  analysis: document.querySelector('#analysis-view'),
};
let selectedCategory = ACTION_CATALOG[0];

function findCategory(categoryId) {
  return ACTION_CATALOG.find((category) => category.id === categoryId) || ACTION_CATALOG[0];
}

function showView(name) {
  Object.entries(views).forEach(([key, view]) => { view.hidden = key !== name; });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderCategoryCards() {
  document.querySelector('#category-grid').innerHTML = ACTION_CATALOG.map((category, index) => `
    <button class="category-card ${category.tone}" type="button" data-category-id="${category.id}">
      <span class="card-index">0${index + 1}</span>
      <span class="category-name">${category.name}</span>
      <span class="category-description">${category.description}</span>
      <span class="category-footer"><span>${category.actions.length} 个动作</span><span class="card-arrow" aria-hidden="true">↗</span></span>
    </button>`).join('');
  document.querySelectorAll('[data-category-id]').forEach((button) => {
    button.addEventListener('click', () => { window.location.hash = `actions/${button.dataset.categoryId}`; });
  });
}

function renderActionCards(category) {
  selectedCategory = category;
  document.querySelector('#action-eyebrow').textContent = category.name;
  document.querySelector('#action-title').textContent = `${category.shortName || category.name}动作`;
  document.querySelector('#action-count').textContent = String(category.actions.length).padStart(2, '0');
  document.querySelector('#action-grid').innerHTML = category.actions.map((action, index) => `
    <button class="action-card ${action.available ? 'available' : ''}" type="button" data-action-id="${action.id}">
      <span class="action-number">${String(index + 1).padStart(2, '0')}</span>
      <span class="action-name">${action.name}</span>
      <span class="action-detail">${action.description || action.detail || '动作分析功能正在准备中'}</span>
      <span class="action-status">${action.available ? '进入视频分析 ↗' : '敬请期待 · 正在开发'}</span>
    </button>`).join('');
  document.querySelectorAll('[data-action-id]').forEach((button) => {
    button.addEventListener('click', () => {
      const action = category.actions.find((item) => item.id === button.dataset.actionId);
      window.location.hash = action.available ? `analyze/${category.id}/${action.id}` : `coming/${category.id}/${action.id}`;
    });
  });
}

function findAction(category, actionId) {
  return category.actions.find((action) => action.id === actionId) || category.actions[0];
}

function routeFromHash() {
  const parts = window.location.hash.replace(/^#/, '').split('/').filter(Boolean);
  if (parts[0] === 'actions') {
    const category = findCategory(parts[1]);
    renderActionCards(category);
    showView('actions');
    return;
  }
  if (parts[0] === 'coming') {
    const category = findCategory(parts[1]);
    const action = findAction(category, parts[2]);
    selectedCategory = category;
    document.querySelector('#coming-category').textContent = category.name;
    document.querySelector('#coming-title').textContent = `${action.name}正在开发`;
    document.querySelector('#coming-description').textContent = `我们正在为${action.name}准备采集规范、姿态指标和对比报告，敬请期待。`;
    showView('coming');
    return;
  }
  if (parts[0] === 'analyze') {
    const category = findCategory(parts[1]);
    const action = findAction(category, parts[2]);
    if (!action.available) {
      window.location.hash = `coming/${category.id}/${action.id}`;
      return;
    }
    renderActionCards(category);
    showView('analysis');
    return;
  }
  showView('catalog');
}

renderCategoryCards();
window.addEventListener('hashchange', routeFromHash);

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
  const totalSeconds = Math.max(0, Number(milliseconds) / 1000);
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${(totalSeconds % 60).toFixed(2).padStart(5, '0')}`;
}

function seekVideo(videoId, milliseconds) {
  const video = document.querySelector(`#${videoId}`);
  const seconds = Number(milliseconds) / 1000;
  if (!Number.isFinite(seconds)) return;
  video.currentTime = Math.max(0, seconds);
  video.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function renderStudentFeedback(feedback) {
  const content = document.querySelector('#student-feedback-content');
  content.replaceChildren();
  document.querySelector('#ai-review-status').textContent = feedback?.status === 'complete' ? '待核对' : '';
  const add = (parent, tag, text, className) => {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    parent.append(node);
    return node;
  };
  if (feedback?.status !== 'complete') {
    add(content, 'p', feedback?.message || '本次没有 AI 建议。', 'ai-state');
    return;
  }
  add(content, 'p', feedback.summary, 'ai-summary');
  (feedback.suggestions || []).forEach((item) => {
    const article = add(content, 'article', '', 'ai-suggestion');
    add(article, 'h4', item.title);
    add(article, 'p', item.observation);
    add(article, 'p', item.adjustment, 'ai-adjustment');
    (item.evidence || []).forEach((evidence) => {
      const button = add(article, 'button', `回看${evidence.phase_label} · A ${formatTime(evidence.reference.timestamp_ms)} / B ${formatTime(evidence.student.timestamp_ms)}`, 'finding-seek ai-seek');
      button.type = 'button';
      button.addEventListener('click', () => {
        seekVideo('reference-video', evidence.reference.timestamp_ms);
        seekVideo('student-video', evidence.student.timestamp_ms);
      });
    });
  });
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
  renderStudentFeedback(report.ai_feedback);
  document.querySelector('#findings').innerHTML = (report.findings || []).map((item) => `
    <div class="finding">
      <div class="finding-title"><span class="finding-chip">${item.joint_label}</span><span>${item.direction}</span></div>
      <p>${item.message} 对齐覆盖 ${(item.coverage * 100).toFixed(0)}%，P90 位置差指数 ${format(item.p90_delta, 3)}。</p>
      <button class="finding-seek" type="button" data-reference-ms="${item.peak_reference_timestamp_ms ?? ''}" data-student-ms="${item.peak_target_timestamp_ms ?? ''}">定位 A ${formatTime(item.peak_reference_timestamp_ms)} / B ${formatTime(item.peak_target_timestamp_ms)}</button>
    </div>`).join('') || '<p class="format-note">当前有效关键点不足，无法生成可解释差异。</p>';
  document.querySelectorAll('#findings .finding-seek').forEach((button) => {
    button.addEventListener('click', () => {
      seekVideo('reference-video', button.dataset.referenceMs);
      seekVideo('student-video', button.dataset.studentMs);
    });
  });
  const phaseRows = unjudgeable ? '<tr><td colspan="3">有效姿态数据不足，无法判断</td></tr>' : (report.phases || []).map((phase) => {
    const candidates = Object.entries(phase.joints || {}).filter(([, value]) => value.mean != null).sort((a, b) => b[1].mean - a[1].mean);
    const top = candidates[0];
    const labels = {left_wrist:'左手腕',right_wrist:'右手腕',left_elbow:'左肘',right_elbow:'右肘',left_shoulder:'左肩',right_shoulder:'右肩',left_hip:'左髋',right_hip:'右髋',left_knee:'左膝',right_knee:'右膝',left_ankle:'左踝',right_ankle:'右踝'};
    return `<tr><td>${phase.phase}</td><td>${top ? (labels[top[0]] || top[0]) : '—'}</td><td>${top ? Number(top[1].mean).toFixed(3) : '—'}</td></tr>`;
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

async function poll(runId, retries = 0) {
  if (runId !== activeRun) return;
  let data;
  try {
    const response = await fetch(`/api/status/${runId}`, { signal: AbortSignal.timeout(15000) });
    if (response.status === 404) {
      setStatus('failed', 100, '本次任务不存在，服务可能已重启，请重新上传。');
      analyzeButton.disabled = false;
      analyzeButton.textContent = '重新分析';
      rememberRun(null);
      return;
    }
    if (!response.ok) throw new Error('status unavailable');
    data = await response.json();
  } catch (error) {
    if (runId !== activeRun) return;
    statusMessage.textContent = retries < 5 ? '暂时无法获取进度，正在重连…' : '连接中断，恢复网络后可继续获取本次报告。';
    retryStatus.hidden = retries < 5;
    if (retries < 5) window.setTimeout(() => poll(runId, retries + 1), Math.min(5000, 1000 * (retries + 1)));
    return;
  }
  if (runId !== activeRun) return;
  retryStatus.hidden = true;
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

function rememberRun(runId) {
  try {
    if (runId) sessionStorage.setItem('motiondiff-run', runId);
    else sessionStorage.removeItem('motiondiff-run');
  } catch (error) { /* Storage may be disabled in private browser sessions. */ }
}

retryStatus.addEventListener('click', () => {
  retryStatus.hidden = true;
  if (activeRun) poll(activeRun);
});

function readVideoDuration(file) {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video');
    const url = URL.createObjectURL(file);
    const finish = (error, duration) => {
      window.clearTimeout(timer);
      video.onloadedmetadata = video.onerror = null;
      video.removeAttribute('src');
      video.load();
      URL.revokeObjectURL(url);
      error ? reject(error) : resolve(duration);
    };
    const timer = window.setTimeout(() => finish(new Error('读取视频时长超时，请重新导出视频后重试。')), 15000);
    video.preload = 'metadata';
    video.onloadedmetadata = () => {
      const duration = video.duration;
      finish(Number.isFinite(duration) && duration > 0 ? null : new Error('无法读取视频时长，请重新导出视频后重试。'), duration);
    };
    video.onerror = () => finish(new Error('浏览器无法读取这个视频，请转换为 MP4 后重试。'));
    video.src = url;
  });
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const reference = document.querySelector('#reference-file').files[0];
  const student = document.querySelector('#student-file').files[0];
  if (!reference || !student) return;
  results.hidden = true;
  retryStatus.hidden = true;
  analyzeButton.disabled = true;
  analyzeButton.textContent = '处理中…';
  setStatus('queued', 0, '正在检查两段视频');
  const data = new FormData();
  data.append('reference', reference);
  data.append('student', student);
  data.append('action', 'squat');
  try {
    const limitsResponse = await fetch('/api/limits');
    if (!limitsResponse.ok) throw new Error('无法读取上传限制，请稍后重试。');
    const limits = await limitsResponse.json();
    for (const [label, file] of [['参考', reference], ['学员', student]]) {
      if (file.size > limits.max_video_bytes) {
        throw new Error(`${label}视频不能超过 ${(limits.max_video_bytes / 1024 / 1024).toFixed(0)} MB，请压缩后上传。`);
      }
      const duration = await readVideoDuration(file);
      if (duration > limits.max_video_seconds) {
        throw new Error(`${label}视频长 ${duration.toFixed(2)} 秒，最多允许 ${limits.max_video_seconds} 秒，请先剪短。`);
      }
    }
    setStatus('queued', 0, '正在上传两段视频');
    const response = await fetch('/api/analyze', { method: 'POST', body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || '上传失败');
    activeRun = payload.run_id;
    rememberRun(activeRun);
    await poll(activeRun);
  } catch (error) {
    analyzeButton.disabled = false;
    analyzeButton.textContent = '重新尝试';
    setStatus('failed', 100, error.message);
  }
});

document.querySelector('#new-analysis').addEventListener('click', () => {
  activeRun = null;
  rememberRun(null);
  retryStatus.hidden = true;
  results.hidden = true;
  statusPanel.hidden = true;
  form.reset();
  document.querySelector('#reference-name').textContent = '选择视频文件';
  document.querySelector('#student-name').textContent = '选择视频文件';
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

document.querySelector('#back-to-catalog').addEventListener('click', () => { window.location.hash = 'library'; });
document.querySelector('#back-to-actions').addEventListener('click', () => { window.location.hash = `actions/${selectedCategory.id}`; });
document.querySelector('#back-to-catalog-from-coming').addEventListener('click', () => { window.location.hash = 'library'; });
document.querySelector('#coming-back-action').addEventListener('click', () => { window.location.hash = `actions/${selectedCategory.id}`; });
document.querySelector('#coming-back-library').addEventListener('click', () => { window.location.hash = 'library'; });
document.querySelector('#back-to-actions-from-analysis').addEventListener('click', () => { window.location.hash = `actions/${selectedCategory.id}`; });

routeFromHash();
try {
  const savedRun = sessionStorage.getItem('motiondiff-run');
  if (/^[a-f0-9]{32}$/.test(savedRun || '') && window.location.hash.startsWith('#analyze/')) {
    activeRun = savedRun;
    analyzeButton.disabled = true;
    setStatus('processing', 0, '恢复本次分析报告');
    poll(savedRun);
  }
} catch (error) { /* Continue without report restoration when storage is unavailable. */ }
