let alerts = [];
let currentIndex = 0;

async function loadAlerts() {
  const response = await fetch('/api/alerts');
  alerts = await response.json();
  renderAlerts();
  renderDetail();
  updateMetrics();
}

function getSeverityClass(level) {
  if (level === 'high') return 'high';
  if (level === 'medium') return 'medium';
  return 'low';
}

function updateScenarioSummary() {
  const scenarioCount = document.getElementById('scenario-count');
  const scenarioSeverity = document.getElementById('scenario-severity');

  if (!alerts.length) {
    if (scenarioCount) scenarioCount.textContent = 'Case 0 of 0';
    if (scenarioSeverity) {
      scenarioSeverity.textContent = 'LOW';
      scenarioSeverity.className = 'badge low';
    }
    return;
  }

  const item = alerts[currentIndex];
  if (!item) return;

  if (scenarioCount) scenarioCount.textContent = `Case ${currentIndex + 1} of ${alerts.length}`;
  if (scenarioSeverity) {
    scenarioSeverity.textContent = item.severity.toUpperCase();
    scenarioSeverity.className = `badge ${getSeverityClass(item.severity)}`;
  }
}

function renderAlerts() {
  const list = document.getElementById('alert-list');
  if (!alerts.length) {
    list.innerHTML = '<div class="summary">Loading risk alerts...</div>';
    return;
  }

  list.innerHTML = alerts
    .map((item, index) => {
      const active = index === currentIndex ? 'active' : '';
      return `
        <div class="alert-item ${active}" data-index="${index}">
          <div class="alert-title">
            <strong>${item.title}</strong>
            <span class="badge ${getSeverityClass(item.severity)}">${item.severity.toUpperCase()}</span>
          </div>
          <div class="alert-meta">${item.sender} → ${item.recipient} • ${item.timestamp}</div>
          <div class="summary">${item.summary}</div>
        </div>
      `;
    })
    .join('');

  list.querySelectorAll('.alert-item').forEach((item) => {
    item.addEventListener('click', () => {
      currentIndex = Number(item.dataset.index);
      renderAlerts();
      renderDetail();
    });
  });
}

function renderDetail() {
  const item = alerts[currentIndex];
  if (!item) return;
  const evidence = document.getElementById('evidence-card');
  const action = document.getElementById('action-card');

  updateScenarioSummary();

  const heuristicScore = item.heuristicScore ?? item.score;
  const predictiveScore = item.predictiveScore ?? item.score;
  const delta = predictiveScore - heuristicScore;
  const deltaText = delta >= 0 ? `+${delta}` : `${delta}`;
  const modelLabel = item.modelName ? `${item.modelName} (${item.modelVersion || 'v1'})` : 'Rule-based demo';

  evidence.innerHTML = `
    <h3>${item.title}</h3>
    <p class="summary">${item.summary}</p>
    <div class="comparison-card">
      <div class="comparison-score">
        <span class="comparison-label">Heuristic</span>
        <strong>${heuristicScore}/100</strong>
      </div>
      <div class="comparison-score comparison-highlight">
        <span class="comparison-label">Predictive</span>
        <strong>${predictiveScore}/100</strong>
      </div>
      <div class="comparison-delta ${delta >= 0 ? 'delta-up' : 'delta-down'}">
        <span>Delta</span>
        <strong>${deltaText}</strong>
      </div>
    </div>
    <div class="details-row">
      <span class="meta-pill">Department: ${item.department || 'Compliance'}</span>
      <span class="score-pill">${item.scoringMode === 'predictive' ? 'Active mode: Predictive' : 'Active mode: Heuristic'}</span>
      <span class="meta-pill">Model: ${modelLabel}</span>
    </div>
    ${item.predictionExplanation ? `
      <div class="explanation-box">
        <h3>Why the predictive score changed</h3>
        <ul>
          ${item.predictionExplanation.map((reason) => `<li>${reason}</li>`).join('')}
        </ul>
      </div>
    ` : ''}
    <ul>
      ${item.reasons.map((reason) => `<li>${reason}</li>`).join('')}
    </ul>
  `;

  action.innerHTML = `
    <h3>Recommended response</h3>
    <ul>
      ${item.recommendedActions.map((actionItem) => `<li>${actionItem}</li>`).join('')}
    </ul>
    <h3>Evidence captured</h3>
    <ul>
      ${item.evidence.map((entry) => `<li>${entry}</li>`).join('')}
    </ul>
  `;
}

function updateMetrics() {
  const total = alerts.length;
  const escalations = alerts.filter((item) => item.severity === 'high').length;
  const accuracy = 96;

  document.getElementById('active-alerts').textContent = total;
  document.getElementById('escalations').textContent = escalations;
  document.getElementById('accuracy').textContent = `${accuracy}%`;
  updateScenarioSummary();
}

function clearDashboard() {
  alerts = [];
  currentIndex = 0;
  renderAlerts();
  renderDetail();
  updateMetrics();
  const status = document.getElementById('upload-status');
  status.textContent = 'Dashboard cleared. Upload a new JSON to start a fresh demo.';
  status.classList.remove('upload-error');
}

async function handleUpload(event) {
  const file = event.target.files[0];
  const status = document.getElementById('upload-status');
  const scoringMode = document.getElementById('scoring-mode')?.value || 'heuristic';
  if (!file) return;

  status.textContent = 'Uploading sample data...';
  status.classList.remove('upload-error');
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`/api/upload?mode=${encodeURIComponent(scoringMode)}`, {
    method: 'POST',
    body: formData,
  });

  const payload = await response.json();
  event.target.value = '';

  if (!response.ok) {
    status.textContent = `Upload failed: ${payload.error}`;
    status.classList.add('upload-error');
    return;
  }

  const startIndex = alerts.length;
  alerts = [...alerts, ...payload.alerts];
  currentIndex = startIndex;

  status.textContent = `Upload complete — ${payload.added} ${scoringMode} alerts generated.`;
  status.classList.remove('upload-error');
  renderAlerts();
  renderDetail();
  updateMetrics();
}

function runNextScenario() {
  currentIndex = (currentIndex + 1) % alerts.length;
  renderAlerts();
  renderDetail();
}

document.getElementById('demo-button').addEventListener('click', runNextScenario);
document.getElementById('clean-button').addEventListener('click', clearDashboard);

const uploadInput = document.getElementById('file-upload');
if (uploadInput) {
  uploadInput.addEventListener('change', handleUpload);
}

async function checkModelStatus() {
  const statusEl = document.getElementById('slm-status');
  const labelEl = document.getElementById('slm-label');
  const dotEl = statusEl?.querySelector('.slm-dot');
  if (!statusEl || !labelEl || !dotEl) return;

  try {
    const resp = await fetch('/api/model-status');
    const data = await resp.json();

    if (data.available) {
      statusEl.className = 'slm-status connected';
      dotEl.className = 'slm-dot connected';
      labelEl.textContent = `SLM connected — ${data.model} (${data.backend})`;
    } else {
      statusEl.className = 'slm-status disconnected';
      dotEl.className = 'slm-dot disconnected';
      labelEl.textContent = `SLM offline — using ${data.backend} scoring`;
    }
  } catch {
    statusEl.className = 'slm-status disconnected';
    dotEl.className = 'slm-dot disconnected';
    labelEl.textContent = 'SLM unreachable — using fallback scoring';
  }
}

loadAlerts();
checkModelStatus();
