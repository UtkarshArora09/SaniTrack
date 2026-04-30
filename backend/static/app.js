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

const appState = {
  employees: [],
  workers: [],
  wards: [],
};

function statusClass(status) {
  const normalized = (status || 'Unknown').toLowerCase();
  if (normalized.includes('clean') && !normalized.includes('not')) return 'status-clean';
  if (normalized.includes('not') || normalized.includes('dirty')) return 'status-not-clean';
  if (normalized.includes('mismatch') || normalized.includes('override')) return 'status-warning';
  return 'status-unknown';
}

function renderStats(overview) {
  const stats = [
    ['Wards', overview.total_wards],
    ['Employees', overview.total_employees],
    ['Clean', overview.clean_inspections],
    ['Not Clean', overview.not_clean_inspections],
    ['Attendance Mismatches', overview.attendance_mismatches],
    ['Overrides', overview.overrides],
  ];
  document.getElementById('statsGrid').innerHTML = stats.map(([label, value]) => `<article class="card stat-card"><div class="stat-value">${value}</div><div class="stat-label">${label}</div></article>`).join('');
}

function employeeOptions(selectedValue = '') {
  const options = ['<option value="">Unassigned</option>'];
  for (const employee of appState.employees) {
    const selected = employee.emp_key === selectedValue ? 'selected' : '';
    options.push(`<option value="${employee.emp_key}" ${selected}>${employee.name} (${employee.emp_key})</option>`);
  }
  return options.join('');
}

function renderWards(wards) {
  const list = document.getElementById('wardsList');
  if (!wards.length) {
    list.innerHTML = '<div class="meta">No wards added yet.</div>';
    return;
  }
  list.innerHTML = wards.map((ward) => {
    const image = ward.latest_annotated_image ? `/inspections/${ward.latest_annotated_image.split('\\').pop()}` : '';
    const latestObjectCount = ward.latest_object_count ?? 0;
    return `
      <article class="ward-item">
        <div class="card-header">
          <strong>${ward.name}</strong>
          <span class="status-chip ${statusClass(ward.latest_status)}">${ward.latest_status || 'Unknown'}</span>
        </div>
        <div class="meta">Location: ${ward.location || ward.name}</div>
        <div class="meta">Assigned worker: <span class="meta-strong">${ward.assigned_employee_name || ward.assigned_employee_key || 'Not assigned'}</span></div>
        <div class="meta">Latest inspection: ${ward.latest_inspection_at || 'No inspections yet'}</div>
        <div class="meta">Latest attendance: ${ward.latest_attendance_at || 'No attendance log'}</div>
        <div class="meta">Latest object count: ${latestObjectCount}</div>
        ${ward.overridden_status ? `<div class="meta">Override by ${ward.overridden_by || 'Admin'}: ${ward.overridden_status} ${ward.override_reason ? `| ${ward.override_reason}` : ''}</div>` : ''}
        <div class="inline-form">
          <select data-assign-select="${ward.id}">${employeeOptions(ward.assigned_employee_key || '')}</select>
          <div class="action-row">
            <button type="button" class="ghost" data-assign-ward="${ward.id}">Save Assignment</button>
            <button type="button" class="warn" data-alert-absence="${ward.id}">Send Absence Alert</button>
          </div>
        </div>
        ${ward.latest_inspection_id ? `
          <div class="divider"></div>
          <div class="inline-form">
            <select data-override-status="${ward.latest_inspection_id}">
              <option value="Clean">Override to Clean</option>
              <option value="Not Clean">Override to Not Clean</option>
            </select>
            <input data-override-reason="${ward.latest_inspection_id}" placeholder="Override reason" />
            <button type="button" class="danger" data-submit-override="${ward.latest_inspection_id}">Apply Override</button>
          </div>
        ` : ''}
        ${image ? `<img class="preview-image" src="${image}" alt="Latest ward inspection" />` : ''}
      </article>
    `;
  }).join('');
}

function renderHistory(history) {
  const timeline = document.getElementById('historyList');
  const merged = [
    ...history.notifications.map((item) => ({ type: 'notification', ...item })),
    ...history.inspections.map((item) => ({ type: 'inspection', ...item })),
    ...history.attendance.map((item) => ({ type: 'attendance', ...item })),
    ...history.confirmations.map((item) => ({ type: 'confirmation', ...item })),
  ].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')).slice(0, 18);

  if (!merged.length) {
    timeline.innerHTML = '<div class="meta">No activity yet.</div>';
    return;
  }

  timeline.innerHTML = merged.map((item) => {
    if (item.type === 'inspection') return `<article class="timeline-item"><strong>Inspection · ${item.ward_name}</strong><div class="meta">${item.status} | objects: ${item.object_count}</div><small>${item.created_at}</small></article>`;
    if (item.type === 'attendance') return `<article class="timeline-item"><strong>Attendance · ${item.employee_key}</strong><div class="meta">Ward: ${item.ward_name} | assigned match: ${item.assigned_match === 0 ? 'No' : 'Yes'}</div><small>${item.created_at}</small></article>`;
    if (item.type === 'confirmation') return `<article class="timeline-item"><strong>Worker Confirmation · ${item.employee_key}</strong><div class="meta">Ward: ${item.ward_name} | ${item.notes || ''}</div><small>${item.created_at}</small></article>`;
    return `<article class="timeline-item"><strong>Notification · ${item.ward_name}</strong><div class="meta">${item.message}</div><small>${item.created_at}</small></article>`;
  }).join('');
}

function renderWorkers(workers) {
  const root = document.getElementById('workersList');
  if (!workers.length) {
    root.innerHTML = '<div class="meta">No workers found.</div>';
    return;
  }
  root.innerHTML = workers.map((worker) => `
    <article class="timeline-item">
      <strong>${worker.name}</strong>
      <div class="meta">${worker.designation || 'Unknown role'} | ${worker.emp_key}</div>
      <div class="meta">Assigned wards: ${worker.assigned_ward_count}</div>
      <div class="meta">Last attendance: ${worker.last_attendance_at || 'No record yet'}</div>
      <div class="meta">Last confirmation: ${worker.last_confirmation_at || 'No confirmation yet'}</div>
      <div class="action-row">
        <a class="ghost" href="/worker/${worker.emp_key}" target="_blank">Open Worker Page</a>
      </div>
    </article>
  `).join('');
}

function populateWorkerSelector() {
  const selector = document.getElementById('workerSelector');
  selector.innerHTML = appState.workers.map((worker) => `<option value="${worker.emp_key}">${worker.name} (${worker.emp_key})</option>`).join('');
}

function renderWorkerPanel(payload) {
  const root = document.getElementById('workerPanel');
  if (!payload || !payload.worker) {
    root.innerHTML = '<div class="meta">Choose a worker to load assigned wards.</div>';
    return;
  }
  const cards = payload.assigned_wards.map((ward) => `
    <article class="timeline-item">
      <strong>${ward.name}</strong>
      <div class="meta">Status: ${ward.latest_status || 'No inspection yet'}</div>
      <div class="meta">Last attendance: ${ward.latest_attendance_at || 'No record'}</div>
      <div class="meta">Last confirmation: ${ward.last_confirmation_at || 'No confirmation'}</div>
      <div class="meta">Objects detected: ${ward.latest_object_count ?? 0}</div>
      <button type="button" class="ghost" data-confirm-task="${ward.name}" data-confirm-worker="${payload.worker.emp_key}">Confirm Cleaning Complete</button>
    </article>
  `).join('');
  root.innerHTML = `
    <article class="timeline-item">
      <strong>${payload.worker.name}</strong>
      <div class="meta">${payload.worker.designation || 'Unknown role'} | ${payload.worker.emp_key}</div>
      <div class="meta">Assigned wards: ${payload.assigned_wards.length}</div>
    </article>
    ${cards || '<div class="meta">This worker has no assigned wards.</div>'}
  `;
}

function renderFaceQuality(payload) {
  const root = document.getElementById('faceQuality');
  const rows = payload.report?.labels || [];
  if (!rows.length) {
    root.innerHTML = '<div class="meta">No face-quality report available yet.</div>';
    return;
  }
  root.innerHTML = rows.map((row) => `
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
  stream.getTracks().forEach((track) => track.stop());
  webcamState[kind].stream = null;
}

async function captureFrame(kind) {
  const video = document.getElementById(`${kind}Video`);
  const canvas = document.getElementById(`${kind}Canvas`);
  const ctx = canvas.getContext('2d');
  if (!video.srcObject) {
    await startCamera(kind);
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.classList.add('has-frame');
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
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
  document.querySelectorAll('[data-start-camera]').forEach((button) => {
    button.addEventListener('click', async () => startCamera(button.dataset.startCamera));
  });
  document.querySelectorAll('[data-capture-camera]').forEach((button) => {
    button.addEventListener('click', async () => captureFrame(button.dataset.captureCamera));
  });
  document.querySelectorAll('[data-clear-capture]').forEach((button) => {
    button.addEventListener('click', () => clearCapture(button.dataset.clearCapture));
  });
}

async function loadWorkerDashboard(empKey) {
  if (!empKey) {
    renderWorkerPanel(null);
    return;
  }
  const payload = await fetchJSON(`/api/workers/${empKey}/dashboard`);
  renderWorkerPanel(payload);
}

function attachForms() {
  document.getElementById('wardForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await fetchJSON('/api/wards', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(form.entries())) });
    event.currentTarget.reset();
    loadAll();
  });

  document.getElementById('employeeForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await fetchJSON('/api/employees', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(form.entries())) });
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

  document.getElementById('loadWorkerBtn').addEventListener('click', async () => {
    await loadWorkerDashboard(document.getElementById('workerSelector').value);
  });
}

function wireDelegatedActions() {
  document.addEventListener('click', async (event) => {
    const assignWardId = event.target.dataset.assignWard;
    const alertWardId = event.target.dataset.alertAbsence;
    const overrideId = event.target.dataset.submitOverride;
    const confirmWard = event.target.dataset.confirmTask;

    if (assignWardId) {
      const selector = document.querySelector(`[data-assign-select="${assignWardId}"]`);
      await fetchJSON(`/api/wards/${assignWardId}/assign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employee_key: selector.value, admin_name: 'Dashboard Admin' }),
      });
      loadAll();
    }

    if (alertWardId) {
      await fetchJSON(`/api/wards/${alertWardId}/alert-absence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Assigned worker absent from ward check.' }),
      });
      loadAll();
    }

    if (overrideId) {
      const status = document.querySelector(`[data-override-status="${overrideId}"]`).value;
      const reason = document.querySelector(`[data-override-reason="${overrideId}"]`).value;
      await fetchJSON(`/api/inspection/${overrideId}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, reason, admin_name: 'Dashboard Admin' }),
      });
      loadAll();
    }

    if (confirmWard) {
      const employeeKey = event.target.dataset.confirmWorker;
      const notes = window.prompt(`Add an optional note for ${confirmWard}:`, 'Cleaning completed and ready for inspection.') || 'Cleaning completed and ready for inspection.';
      await fetchJSON('/api/tasks/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ward_name: confirmWard, employee_key: employeeKey, notes }),
      });
      loadAll();
      await loadWorkerDashboard(employeeKey);
    }
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
  const [overview, wardsPayload, history, employeesPayload, workersPayload] = await Promise.all([
    fetchJSON('/api/overview'),
    fetchJSON('/api/wards'),
    fetchJSON('/api/history'),
    fetchJSON('/api/employees'),
    fetchJSON('/api/workers'),
  ]);
  appState.wards = wardsPayload.wards;
  appState.employees = employeesPayload.employees;
  appState.workers = workersPayload.workers;
  renderStats(overview);
  renderWards(appState.wards);
  renderHistory(history);
  renderWorkers(appState.workers);
  populateWorkerSelector();
  await loadFaceQuality();
  await loadNotificationMode();
}

wireWebcamButtons();
attachForms();
wireDelegatedActions();
loadAll().catch((error) => {
  console.error(error);
  document.getElementById('notificationMode').textContent = `Dashboard load failed: ${error.message}`;
});
window.addEventListener('beforeunload', () => Object.keys(webcamState).forEach(stopCamera));
