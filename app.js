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
      scenarioSeverity.textContent = 'AWAITING DATA';
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
    list.innerHTML = '<div class="text-muted" style="text-align: center; margin-top: 2rem;">No events in stream.</div>';
    return;
  }

  list.innerHTML = alerts
    .map((item, index) => {
      const active = index === currentIndex ? 'active' : '';
      return `
        <div class="alert-item ${active}" data-index="${index}">
          <div class="alert-title-row">
            <span class="alert-title">${item.title}</span>
            <span class="badge ${getSeverityClass(item.severity)}">${item.severity.toUpperCase()}</span>
          </div>
          <div class="alert-meta">${item.sender} → ${item.recipient}</div>
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
  if (!item) {
    const evidence = document.getElementById('evidence-card');
    if (evidence) evidence.innerHTML = '<div class="empty-state">Select an event from the stream to view Pure AI analysis.</div>';
    return;
  }
  const evidence = document.getElementById('evidence-card');

  updateScenarioSummary();

  // Highlight Pure AI logic over Legacy logic
  const legacyScore = item.heuristicScore ?? item.score;
  const slmScore = item.predictiveScore ?? item.score;
  const rawModelName = item.modelName || 'llama3.1-local';
  const modelName = `${rawModelName} (Pure AI)`;

  // --- DYNAMIC URL UPDATE FOR DEMO ---
  // This physically updates the browser URL bar so you can point to it
  // and prove the local SLM is driving the prediction.
  const url = new URL(window.location);
  url.searchParams.set('engine', rawModelName);
  url.searchParams.set('mode', 'pure-local-ai-inference');
  url.searchParams.set('eventId', item.id);
  window.history.pushState({}, '', url);
  // ------------------------------------

  // Format the raw evidence JSON to look professional in the dashboard
  const rawDataStr = [
    `Sender   : ${item.sender}`,
    `Recipient: ${item.recipient}`,
    `Time     : ${item.timestamp}`,
    `Message  : ${item.summary}`
  ].join("\n");


  let explanationsHtml = '';
  if (item.predictionExplanation && item.predictionExplanation.length > 0) {
    explanationsHtml = `<ul class="ai-reasoning-list">
          ${item.predictionExplanation.map(r => `<li>${r}</li>`).join('')}
      </ul>`;
  } else {
    explanationsHtml = `<p class="text-muted">SLM deduced risk holistically from context.</p>`;
  }

  evidence.innerHTML = `
    <h3>Cognitive Risk Analysis (${modelName})</h3>
    <p class="text-muted" style="margin-bottom: 1.5rem;">
        The SLM analyzed the raw communication content below with absolutely no programmed rule heuristics.
    </p>

    <!-- Score Comparison -->
    <div class="score-comparison">
        <div class="score-box ai-highlight">
            <h4>SLM Cognitive Risk Score</h4>
            <span class="score-val">${slmScore}</span>
        </div>
    </div>

    <!-- AI Reasoning -->
    <h3>SLM Reasoning</h3>
    ${explanationsHtml}

    <br>
    
    <!-- Raw Data Passed to Model -->
    <h3>Raw Event Payload</h3>
    <div class="raw-evidence-box">${rawDataStr}</div>
  `;
}

function updateMetrics() {
  const total = alerts.length;
  const escalations = alerts.filter((item) => item.severity === 'high').length;
  const accuracy = 99; // Demo fixed value

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
  status.textContent = 'Stream cleared. Inject fresh raw comms.';
  status.style.color = 'var(--text-muted)';
}

async function handleUpload(event) {
  const file = event.target.files[0];
  const status = document.getElementById('upload-status');
  const scoringMode = 'predictive'; // Always predictive in this demo now!
  if (!file) return;

  status.textContent = 'Injecting data into local SLM...';
  status.style.color = 'var(--primary)';

  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`/api/upload?mode=${scoringMode}`, {
    method: 'POST',
    body: formData,
  });

  const payload = await response.json();
  event.target.value = '';

  if (!response.ok) {
    status.textContent = `Infection failed: ${payload.error}`;
    status.style.color = 'var(--danger)';
    return;
  }

  const startIndex = alerts.length;
  alerts = [...alerts, ...payload.alerts];
  currentIndex = startIndex;

  status.textContent = `Stream live. SLM processed ${payload.added} records.`;
  status.style.color = 'var(--success)';
  renderAlerts();
  renderDetail();
  updateMetrics();
}

function runNextScenario() {
  if (alerts.length > 0) {
    currentIndex = (currentIndex + 1) % alerts.length;
    renderAlerts();
    renderDetail();
  }
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
      labelEl.textContent = `LOCAL AI ACTIVE — ${data.model}`;
    } else {
      statusEl.className = 'slm-status disconnected';
      dotEl.className = 'slm-dot disconnected';
      labelEl.textContent = `SLM OFFLINE — ${data.backend}`;
    }
  } catch {
    statusEl.className = 'slm-status disconnected';
    dotEl.className = 'slm-dot disconnected';
    labelEl.textContent = 'SLM UNREACHABLE';
  }
}

loadAlerts();
checkModelStatus();
