async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function statusClass(status) {
  const normalized = (status || 'Unknown').toLowerCase();
  if (normalized.includes('clean') && !normalized.includes('not')) return 'status-clean';
  if (normalized.includes('not') || normalized.includes('dirty')) return 'status-not-clean';
  return 'status-unknown';
}

function renderWorker(payload) {
  const summary = document.getElementById('workerSummary');
  summary.textContent = JSON.stringify(payload.worker, null, 2);

  const tasks = document.getElementById('workerTasks');
  if (!payload.assigned_wards.length) {
    tasks.innerHTML = '<div class="meta">No wards are currently assigned to you.</div>';
  } else {
    tasks.innerHTML = payload.assigned_wards.map((ward) => `
      <article class="timeline-item">
        <div class="card-header">
          <strong>${ward.name}</strong>
          <span class="status-chip ${statusClass(ward.latest_status)}">${ward.latest_status || 'Pending'}</span>
        </div>
        <div class="meta">Location: ${ward.location || ward.name}</div>
        <div class="meta">Latest inspection: ${ward.latest_inspection_at || 'No inspection yet'}</div>
        <div class="meta">Objects detected: ${ward.latest_object_count ?? 0}</div>
        <div class="meta">Last attendance: ${ward.latest_attendance_at || 'No attendance yet'}</div>
        <div class="meta">Last confirmation: ${ward.last_confirmation_at || 'No confirmation yet'}</div>
        ${ward.override_reason ? `<div class="meta">Override reason: ${ward.override_reason}</div>` : ''}
        <button type="button" class="ghost" data-worker-confirm="${ward.name}">Confirm Cleaning Complete</button>
      </article>
    `).join('');
  }

  const notifications = document.getElementById('workerNotifications');
  if (!payload.notifications.length) {
    notifications.innerHTML = '<div class="meta">No notifications yet.</div>';
  } else {
    notifications.innerHTML = payload.notifications.map((item) => `
      <article class="timeline-item">
        <strong>${item.ward_name}</strong>
        <div class="meta">${item.message}</div>
        <small>${item.created_at}</small>
      </article>
    `).join('');
  }
}

async function loadWorkerPage() {
  const payload = await fetchJSON(`/api/workers/${window.SANITRACK_WORKER_KEY}/dashboard`);
  renderWorker(payload);
}

document.addEventListener('click', async (event) => {
  const wardName = event.target.dataset.workerConfirm;
  if (!wardName) return;
  const notes = window.prompt(`Add an optional note for ${wardName}:`, 'Cleaning completed and ready for inspection.') || 'Cleaning completed and ready for inspection.';
  await fetchJSON('/api/tasks/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ward_name: wardName, employee_key: window.SANITRACK_WORKER_KEY, notes }),
  });
  await loadWorkerPage();
});

document.getElementById('refreshWorkerPage').addEventListener('click', loadWorkerPage);
loadWorkerPage().catch((error) => {
  console.error(error);
  document.getElementById('workerSummary').textContent = `Worker page load failed: ${error.message}`;
});
