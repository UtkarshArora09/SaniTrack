async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

const webcamState = {
  attendance: { stream: null, blob: null },
  inspection: { stream: null, blob: null },
};

function statusClass(status) {
  const normalized = (status || 'Unknown').toLowerCase();
  if (normalized.includes('clean') && !normalized.includes('not')) return 'status-clean';
  if (normalized.includes('not') || normalized.includes('dirty')) return 'status-not-clean';
  return 'status-unknown';
}

function renderStats(overview) {
  const stats = [['Wards', overview.total_wards], ['Employees', overview.total_employees], ['Clean Inspections', overview.clean_inspections], ['Not Clean Inspections', overview.not_clean_inspections]];
  document.getElementById('statsGrid').innerHTML = stats.map(([label, value]) => `<article class="card stat-card"><div class="stat-value">${value}</div><div class="stat-label">${label}</div></article>`).join('');
}

function renderWards(wards) {
  const list = document.getElementById('wardsList');
  if (!wards.length) { list.innerHTML = '<div class="meta">No wards added yet.</div>'; return; }
  list.innerHTML = wards.map(ward => `<article class="ward-item"><div class="card-header"><strong>${ward.name}</strong><span class="status-chip ${statusClass(ward.latest_status)}">${ward.latest_status || 'Unknown'}</span></div><div class="meta">Location: ${ward.location || ward.name}</div><div class="meta">Assigned employee: ${ward.assigned_employee_key || 'Not assigned'}</div><div class="meta">Last inspection: ${ward.latest_inspection_at || 'No inspections yet'}</div><div class="meta">Latest object count: ${ward.latest_object_count ?? 0}</div></article>`).join('');
}

function renderHistory(history) {
  const timeline = document.getElementById('historyList');
  const merged = [...history.notifications.map(item => ({type: 'notification', ...item})), ...history.inspections.map(item => ({type: 'inspection', ...item})), ...history.attendance.map(item => ({type: 'attendance', ...item}))].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')).slice(0, 16);
  if (!merged.length) { timeline.innerHTML = '<div class="meta">No activity yet.</div>'; return; }
  timeline.innerHTML = merged.map(item => {
    if (item.type === 'inspection') return `<article class="timeline-item"><strong>Inspection · ${item.ward_name}</strong><div class="meta">${item.status} | objects: ${item.object_count}</div><small>${item.created_at}</small></article>`;
    if (item.type === 'attendance') return `<article class="timeline-item"><strong>Attendance · ${item.employee_key}</strong><div class="meta">Ward: ${item.ward_name}</div><small>${item.created_at}</small></article>`;
    return `<article class="timeline-item"><strong>Notification · ${item.ward_name}</strong><div class="meta">${item.message}</div><small>${item.created_at}</small></article>`;
  }).join('');
}

function renderFaceQuality(payload) {
  const root = document.getElementById('faceQuality');
  const rows = payload.report?.labels || [];
  if (!rows.length) {
    root.innerHTML = '<div class="meta">No face-quality report available yet.</div>';
    return;
  }
  root.innerHTML = rows.map(row => `
    <article class="timeline-item">
      <strong>${row.employee_key}</strong>
      <div class="meta">Samples: ${row.sample_count} | Accuracy: ${(row.leave_one_out_accuracy * 100).toFixed(1)}%</div>
      <div class="meta">Closest rival: ${row.closest_rival || 'None'} | Separation: ${row.closest_rival_distance ?? 'n/a'}</div>
      <span class="dataset-pill">${row.status}</span>
    </article>
  `).join('');
}

function setResult(el, payload) {
  el.textContent = JSON.stringify(payload, null, 2);
}

async function startCamera(kind) {
  const video = document.getElementById(`${kind}Video`);
  if (webcamState[kind].stream) return;
  const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  webcamState[kind].stream = stream;
  video.srcObject = stream;
}

function stopCamera(kind) {
  const stream = webcamState[kind].stream;
  if (!stream) return;
  stream.getTracks().forEach(track => track.stop());
  webcamState[kind].stream = null;
}

async function captureFrame(kind) {
  const video = document.getElementById(`${kind}Video`);
  const canvas = document.getElementById(`${kind}Canvas`);
  const ctx = canvas.getContext('2d');
  if (!video.srcObject) {
    await startCamera(kind);
    await new Promise(resolve => setTimeout(resolve, 800));
  }
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.classList.add('has-frame');
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92));
  webcamState[kind].blob = blob;
}

function clearCapture(kind) {
  webcamState[kind].blob = null;
  document.getElementById(`${kind}Canvas`).classList.remove('has-frame');
}

function appendImageToForm(formData, form, kind) {
  const fileInput = form.querySelector('input[type="file"][name="image"]');
  const file = fileInput?.files?.[0];
  if (file) {
    formData.set('image', file);
    return true;
  }
  const blob = webcamState[kind].blob;
  if (blob) {
    formData.set('image', blob, `${kind}_capture.jpg`);
    return true;
  }
  return false;
}

function wireWebcamButtons() {
  document.querySelectorAll('[data-start-camera]').forEach(button => {
    button.addEventListener('click', async () => startCamera(button.dataset.startCamera));
  });
  document.querySelectorAll('[data-capture-camera]').forEach(button => {
    button.addEventListener('click', async () => captureFrame(button.dataset.captureCamera));
  });
  document.querySelectorAll('[data-clear-capture]').forEach(button => {
    button.addEventListener('click', () => clearCapture(button.dataset.clearCapture));
  });
}

function attachForms() {
  document.getElementById('wardForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await fetchJSON('/api/wards', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(form.entries())) });
    event.currentTarget.reset();
    loadAll();
  });

  document.getElementById('employeeForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await fetchJSON('/api/employees', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(form.entries())) });
    event.currentTarget.reset();
    loadAll();
  });

  document.getElementById('attendanceForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    if (!appendImageToForm(formData, form, 'attendance')) throw new Error('Choose an image or capture a webcam frame first.');
    const result = await fetchJSON('/api/attendance/recognize', { method: 'POST', body: formData });
    setResult(document.getElementById('attendanceResult'), result);
    loadAll();
  });

  document.getElementById('inspectionForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    if (!appendImageToForm(formData, form, 'inspection')) throw new Error('Choose an image or capture a webcam frame first.');
    const result = await fetchJSON('/api/inspection/analyze', { method: 'POST', body: formData });
    const resultBox = document.getElementById('inspectionResult');
    setResult(resultBox, result);
    if (result.annotated_image) {
      const filename = result.annotated_image.split('\\').pop();
      resultBox.innerHTML += `\n\n<img class="preview-image" src="/inspections/${filename}" alt="inspection result" />`;
    }
    loadAll();
  });
}

async function loadFaceQuality() {
  const payload = await fetchJSON('/api/face/quality');
  renderFaceQuality(payload);
}

async function loadNotificationMode() {
  const payload = await fetchJSON('/api/config/notifications');
  document.getElementById('notificationMode').textContent = JSON.stringify(payload, null, 2);
}

async function loadAll() {
  const [overview, wards, history] = await Promise.all([fetchJSON('/api/overview'), fetchJSON('/api/wards'), fetchJSON('/api/history')]);
  renderStats(overview);
  renderWards(wards.wards);
  renderHistory(history);
  loadFaceQuality();
  loadNotificationMode();
}

wireWebcamButtons();
attachForms();
loadAll();
window.addEventListener('beforeunload', () => Object.keys(webcamState).forEach(stopCamera));
