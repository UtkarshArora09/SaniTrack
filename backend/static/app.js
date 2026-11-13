async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  let data;
  if (contentType.includes('application/json')) {
    data = await response.json();
  } else {
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status}: ${text.slice(0, 80)}`);
    }
    try {
      data = JSON.parse(text);
    } catch (e) {
      throw new Error(`Unexpected server response (HTTP ${response.status})`);
    }
  }
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

const webcamState = {
  attendance: { stream: null, blob: null },
  inspection: { stream: null, blob: null },
  liveWard: { stream: null, isPresent: false },
};

const appState = {
  employees: [],
  wards: [],
  selectedWardId: null,
};

// 1. Render Top Metrics
function renderMetrics(overview) {
  const row = document.getElementById('metricsRow');
  const cleanCount = overview.clean_inspections || 0;
  const notCleanCount = overview.not_clean_inspections || 0;
  const totalInspections = cleanCount + notCleanCount;
  const hygieneScore = totalInspections > 0 ? Math.round((cleanCount / totalInspections) * 100) : 100;

  row.innerHTML = `
    <div class="metric-box">
      <div class="metric-value">${overview.total_wards || 0}</div>
      <div class="metric-label">Hospital Wards Monitored</div>
    </div>
    <div class="metric-box">
      <div class="metric-value" style="color: var(--success);">${cleanCount}</div>
      <div class="metric-label">Clean Verified Wards</div>
    </div>
    <div class="metric-box">
      <div class="metric-value">${overview.total_employees || 0}</div>
      <div class="metric-label">Enrolled Cleaning Personnel</div>
    </div>
    <div class="metric-box">
      <div class="metric-value" style="color: ${hygieneScore >= 80 ? 'var(--success)' : 'var(--danger)'};">${hygieneScore}%</div>
      <div class="metric-label">Hospital Hygiene Pass Rate</div>
    </div>
  `;
}

// 2. Populate Dropdowns across Steps
function populateDropdowns(wards, employees) {
  const attendanceSelect = document.getElementById('attendanceWardSelect');
  const assignWardSelect = document.getElementById('quickAssignWardSelect');
  const assignEmpSelect = document.getElementById('quickAssignEmployeeSelect');
  const liveWardSelect = document.getElementById('liveViewWardSelect');
  const inspectionSelect = document.getElementById('inspectionWardSelect');

  const wardOpts = '<option value="">Select Ward</option>' + 
    wards.map(w => `<option value="${w.id}" data-name="${w.name}">${w.name} (${w.location || 'Wing'})</option>`).join('');

  const empOpts = '<option value="">Select Staff</option>' + 
    employees.map(e => `<option value="${e.emp_key}">${e.name} (${e.designation || 'Staff'})</option>`).join('');

  if (attendanceSelect) attendanceSelect.innerHTML = wardOpts;
  if (assignWardSelect) assignWardSelect.innerHTML = wardOpts;
  if (liveWardSelect) liveWardSelect.innerHTML = wardOpts;
  if (inspectionSelect) inspectionSelect.innerHTML = wardOpts;
  if (assignEmpSelect) assignEmpSelect.innerHTML = empOpts;
}

// 3. Render Wards Overview Grid
function renderWardsGrid(wards) {
  const container = document.getElementById('wardsList');
  if (!wards.length) {
    container.innerHTML = '<div class="meta">No wards configured yet.</div>';
    return;
  }

  container.innerHTML = wards.map(w => {
    const isClean = (w.latest_status || '').toLowerCase().includes('clean') && !w.latest_status.toLowerCase().includes('not');
    const isDirty = (w.latest_status || '').toLowerCase().includes('not') || (w.latest_status || '').toLowerCase().includes('dirty');
    const statusClass = isClean ? 'clean' : (isDirty ? 'dirty' : 'pending');
    const statusLabel = w.latest_status || 'Pending Check';

    const hasWorker = Boolean(w.assigned_employee_key && w.assigned_employee_name);
    const presenceLower = (w.worker_presence || '').toLowerCase();
    const isWorking = hasWorker && (presenceLower.startsWith('active') || presenceLower.includes('working')) && !presenceLower.includes('inactive');

    let presenceHTML = '';
    if (!hasWorker) {
      presenceHTML = '<span style="color: var(--text-muted); font-weight: 600;">⚪ Unassigned (No Staff)</span>';
    } else if (isWorking) {
      presenceHTML = '<span style="color: var(--success); font-weight: 700;">🟢 Working in Ward</span>';
    } else {
      presenceHTML = '<span style="color: var(--danger); font-weight: 700;">🔴 Away / Inactive</span>';
    }

    const image = w.latest_annotated_image ? `/inspections/${w.latest_annotated_image.split('\\').pop().split('/').pop()}` : '';

    return `
      <div class="ward-card">
        <div class="ward-card-header">
          <div>
            <div class="ward-name">${w.name}</div>
            <div class="ward-loc">${w.location || w.name}</div>
          </div>
          <span class="status-pill ${statusClass}">${statusLabel}</span>
        </div>

        <div class="ward-info-row">
          <span>Assigned Staff:</span>
          <strong>${w.assigned_employee_name || 'Unassigned'}</strong>
        </div>

        <div class="ward-info-row">
          <span>Worker Presence:</span>
          ${presenceHTML}
        </div>

        <div class="ward-info-row">
          <span>Last Inspection:</span>
          <span>${w.latest_inspection_at ? w.latest_inspection_at.split('T')[0] : 'None'}</span>
        </div>

        ${image ? `<img src="${image}" class="ward-preview-img" alt="Floor preview" />` : ''}

        <div class="btn-group" style="margin-top: auto; padding-top: 8px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="selectWardForLive('${w.id}')">Watch Live</button>
          <button type="button" class="btn btn-outline btn-sm" onclick="quickAlertAbsence('${w.id}')">Alert Absence</button>
          ${w.latest_inspection_id ? `
            <button type="button" class="btn btn-outline btn-sm" onclick="quickOverride('${w.latest_inspection_id}', '${isClean ? 'Not Clean' : 'Clean'}')">
              Override
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

// 4. Render Collapsible History & IoT
function renderHistoryAndTelemetry(history, telemetry, employees) {
  const histBody = document.getElementById('inspectionHistoryBody');
  if (histBody && history.inspections) {
    histBody.innerHTML = history.inspections.slice(0, 10).map(i => `
      <tr>
        <td><strong>${i.ward_name}</strong></td>
        <td>${i.employee_key || 'Staff'}</td>
        <td><span class="status-pill ${i.status.toLowerCase().includes('clean') && !i.status.toLowerCase().includes('not') ? 'clean' : 'dirty'}">${i.overridden_status || i.status}</span></td>
        <td>${i.object_count} (${i.raw_label || 'None'})</td>
        <td>${i.confidence ? (i.confidence * 100).toFixed(1) + '%' : 'N/A'}</td>
        <td>${i.overridden_status ? 'Yes' : 'No'}</td>
        <td>${i.created_at.replace('T', ' ').split('.')[0]}</td>
      </tr>
    `).join('');
  }

  const iotContainer = document.getElementById('iotGaugesList');
  if (iotContainer && telemetry.summary) {
    iotContainer.innerHTML = telemetry.summary.map(s => `
      <div class="iot-box">
        <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 13px;">
          <span>${s.ward_name} (${s.sensor_type.replace('_', ' ').toUpperCase()})</span>
          <span>${s.metric_value.toFixed(1)} ${s.unit}</span>
        </div>
        <div class="meter-bar">
          <div class="meter-fill ${s.metric_value >= 80 ? 'danger' : ''}" style="width: ${Math.min(s.metric_value, 100)}%;"></div>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">Status: ${s.status}</div>
      </div>
    `).join('');
  }

  const chipsContainer = document.getElementById('workerLinksList');
  if (chipsContainer) {
    if (!employees || employees.length === 0) {
      chipsContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; padding: 8px 0;">Zero workers registered. Run <code>python scripts\\enroll_face.py</code> to record new face biometrics.</div>';
    } else {
      chipsContainer.innerHTML = employees.map(e => `
        <div style="display: inline-flex; align-items: center; gap: 8px; background: #fff; padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px; margin: 4px;">
          <a href="/worker/${e.emp_key}" target="_blank" style="text-decoration: none; color: var(--primary); font-weight: 600; font-size: 13px;">
            📱 ${e.name} (${e.designation || 'Staff'})
          </a>
          <button onclick="deleteWorker('${e.emp_key}')" style="background: none; border: none; cursor: pointer; color: var(--danger); font-size: 14px; padding: 0 4px;" title="Delete worker & face data">✕</button>
        </div>
      `).join('');
    }
  }
}

// 5. STEP 1: Attendance Verification
document.getElementById('attendanceForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const resBox = document.getElementById('attendanceResult');
  const select = document.getElementById('attendanceWardSelect');
  const wardName = select.options[select.selectedIndex]?.dataset?.name || select.value;

  const formData = new FormData(e.target);
  formData.set('ward_name', wardName);
  if (webcamState.attendance.blob) {
    formData.set('image', webcamState.attendance.blob, 'face.jpg');
  }

  resBox.innerHTML = '<div class="spinner">Scanning facial biometric features...</div>';
  try {
    const res = await fetchJSON('/api/attendance/recognize', { method: 'POST', body: formData });
    if (res.matched) {
      resBox.innerHTML = `
<strong style="color: var(--success);">✅ Verified: ${res.name}</strong>
Role: ${res.designation || 'Staff'} | Confidence: ${(res.confidence * 100).toFixed(1)}%
Status: Clocked in for ${wardName}
      `;
      // Pre-select staff in Step 2
      const quickEmpSelect = document.getElementById('quickAssignEmployeeSelect');
      if (quickEmpSelect) quickEmpSelect.value = res.employee_key;
    } else {
      let extraHelp = '';
      if ((res.message || '').includes('No enrolled face samples')) {
        extraHelp = '<br><span style="font-size: 12px; color: var(--text-muted); font-weight: 500;">Register staff with a face photo below under <strong>"👥 Staff Registry"</strong> to activate biometrics.</span>';
      }
      resBox.innerHTML = `<strong style="color: var(--danger);">❌ Verification Failed:</strong> ${res.message}${extraHelp}`;
    }
    loadAll();
  } catch (err) {
    resBox.innerHTML = `<span style="color: var(--danger);">Error: ${err.message}</span>`;
  }
});

// 6. STEP 2: Quick Assignment
document.getElementById('quickAssignForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const resBox = document.getElementById('assignResult');
  const empKey = document.getElementById('quickAssignEmployeeSelect').value;
  const wardSelect = document.getElementById('quickAssignWardSelect');
  const wardId = wardSelect.value;
  const wardName = wardSelect.options[wardSelect.selectedIndex]?.dataset?.name || 'Selected Ward';

  if (!empKey || !wardId) {
    alert('Please select both staff member and target ward');
    return;
  }

  resBox.innerHTML = '<div class="spinner">Assigning ward & sending WhatsApp notification...</div>';
  try {
    const res = await fetchJSON(`/api/wards/${wardId}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ employee_key: empKey, admin_name: 'Hospital Admin' })
    });

    resBox.innerHTML = `
<strong style="color: var(--success);">✅ Assignment Complete!</strong>
Staff: <strong>${empKey}</strong> assigned to <strong>${wardName}</strong>.
WhatsApp alert dispatched. Status set to: "Cleaning In Progress".
    `;
    
    // Automatically switch Step 3 to watch this newly assigned ward!
    selectWardForLive(wardId);
    loadAll();
  } catch (err) {
    resBox.innerHTML = `<span style="color: var(--danger);">Assignment error: ${err.message}</span>`;
  }
});

// 7. STEP 3: Live Ward Surveillance & Automated Real-Time Presence
let livePresenceTrackerTimer = null;
let isProbingPresence = false;

function startLivePresenceTracker() {
  if (livePresenceTrackerTimer) clearInterval(livePresenceTrackerTimer);

  livePresenceTrackerTimer = setInterval(async () => {
    const select = document.getElementById('liveViewWardSelect');
    const wardId = select ? select.value : null;
    const video = document.getElementById('liveWardVideo');
    if (!wardId || !video || video.readyState < 2 || isProbingPresence) return;

    isProbingPresence = true;
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 320;
      canvas.height = 240;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, 320, 240);

      canvas.toBlob(async (blob) => {
        if (!blob) {
          isProbingPresence = false;
          return;
        }

        const formData = new FormData();
        formData.append('frame', blob, 'frame.jpg');

        try {
          const res = await fetchJSON(`/api/wards/${wardId}/detect-presence`, {
            method: 'POST',
            body: formData
          });

          const badge = document.getElementById('presenceBadge');
          const details = document.getElementById('livePresenceDetails');

          if (badge) {
            if (res.is_present) {
              badge.className = 'presence-badge presence-active';
              badge.textContent = res.worker_match
                ? `🟢 ACTIVE: ${res.recognized_name || 'Worker'} Present in Ward`
                : '🟢 ACTIVE: Worker Present in Ward';
            } else {
              badge.className = 'presence-badge presence-away';
              badge.textContent = '🔴 AWAY: Ward Unattended (Worker Not in Frame)';
            }
          }

          if (details) {
            details.innerHTML = `
Ward: <strong>${res.ward_name}</strong> &bull; Assigned: <strong>${res.assigned_employee_name || 'None'}</strong><br>
Status: <strong style="color: ${res.is_present ? 'var(--success)' : 'var(--danger)'};">${res.is_present ? 'Active Cleaning in Progress' : 'No Worker Detected in Frame'}</strong><br>
Real-Time AI Surveillance: <em>${res.is_present ? (res.worker_match ? 'Assigned Worker Verified in Frame' : 'Person Detected on Camera') : 'Camera Active — Worker Out of View'}</em>
            `;
          }

          const w = appState.wards.find(item => String(item.id) === String(wardId));
          if (w) {
            w.worker_presence = res.worker_presence;
            w.last_presence_at = res.last_presence_at;
          }
        } catch (apiErr) {
          // Frame drop ignored
        } finally {
          isProbingPresence = false;
        }
      }, 'image/jpeg', 0.65);
    } catch (err) {
      isProbingPresence = false;
    }
  }, 1200);
}

function selectWardForLive(wardId) {
  const select = document.getElementById('liveViewWardSelect');
  if (select) select.value = wardId;
  updateLiveWardPresenceView();
}

async function updateLiveWardPresenceView() {
  const select = document.getElementById('liveViewWardSelect');
  const wardId = select.value;
  const badge = document.getElementById('presenceBadge');
  const details = document.getElementById('livePresenceDetails');

  if (!wardId) {
    badge.className = 'presence-badge';
    badge.textContent = 'Select ward to monitor';
    details.innerHTML = 'Worker Presence: <strong>Not Connected</strong>';
    return;
  }

  const ward = appState.wards.find(w => String(w.id) === String(wardId));
  if (!ward) return;

  const hasWorker = Boolean(ward.assigned_employee_key && ward.assigned_employee_name);
  const presenceLower = (ward.worker_presence || '').toLowerCase();
  const isWorking = hasWorker && (presenceLower.startsWith('active') || presenceLower.includes('working')) && !presenceLower.includes('inactive');

  if (!hasWorker) {
    badge.className = 'presence-badge presence-away';
    badge.textContent = '⚪ UNASSIGNED: No Staff Assigned';
  } else if (isWorking) {
    badge.className = 'presence-badge presence-active';
    badge.textContent = '🟢 ACTIVE: Worker Present in Ward';
  } else {
    badge.className = 'presence-badge presence-away';
    badge.textContent = '🔴 AWAY: Ward Unattended';
  }

  details.innerHTML = `
Ward: <strong>${ward.name}</strong> &bull; Assigned: <strong>${ward.assigned_employee_name || 'Unassigned'}</strong><br>
Status: <strong style="color: ${hasWorker ? (isWorking ? 'var(--success)' : 'var(--danger)') : 'var(--text-muted)'};">
  ${hasWorker ? (isWorking ? 'Active Cleaning in Progress' : 'No Worker Detected in Ward') : 'No Staff Assigned to this Ward'}
</strong><br>
Last Activity Log: ${ward.last_presence_at ? ward.last_presence_at.replace('T', ' ').split('.')[0] : 'None recorded'}
  `;
}

document.getElementById('liveViewWardSelect').addEventListener('change', () => {
  updateLiveWardPresenceView();
  if (webcamState.liveWard.stream) {
    startLivePresenceTracker();
  }
});

document.getElementById('btnStartLiveWard').addEventListener('click', async () => {
  const video = document.getElementById('liveWardVideo');
  const btn = document.getElementById('btnStartLiveWard');

  if (webcamState.liveWard.stream) {
    webcamState.liveWard.stream.getTracks().forEach(t => t.stop());
    webcamState.liveWard.stream = null;
    video.srcObject = null;
    if (livePresenceTrackerTimer) clearInterval(livePresenceTrackerTimer);
    btn.textContent = 'Open Camera';
    updateLiveWardPresenceView();
    return;
  }

  try {
    webcamState.liveWard.stream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = webcamState.liveWard.stream;
    btn.textContent = '🟢 Camera Streaming (Live AI)';
    startLivePresenceTracker();
  } catch (e) {
    alert(`Camera permission denied: ${e.message}`);
  }
});

document.getElementById('btnSimulatePresence').addEventListener('click', async () => {
  const select = document.getElementById('liveViewWardSelect');
  const wardId = select.value;
  if (!wardId) return alert('Select a ward first');

  webcamState.liveWard.isPresent = !webcamState.liveWard.isPresent;
  const res = await fetchJSON(`/api/wards/${wardId}/presence`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_present: webcamState.liveWard.isPresent })
  });

  const ward = appState.wards.find(w => String(w.id) === String(wardId));
  if (ward) {
    ward.worker_presence = res.worker_presence;
  }
  updateLiveWardPresenceView();
});

// 8. STEP 4: Asynchronous Floor Inspection (Clean/Not Clean)
document.getElementById('inspectionForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const resBox = document.getElementById('inspectionResult');
  const submitBtn = document.getElementById('btnSubmitInspection');
  const select = document.getElementById('inspectionWardSelect');
  const wardName = select.options[select.selectedIndex]?.dataset?.name || select.value;

  const formData = new FormData(e.target);
  formData.set('ward_name', wardName);

  // If camera is streaming and user hasn't explicitly clicked Snap Floor, auto-capture current frame
  if (!webcamState.inspection.blob && webcamState.inspection.stream) {
    const video = document.getElementById('inspectionVideo');
    const canvas = document.getElementById('inspectionCanvas');
    if (video && canvas) {
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.classList.add('has-frame');
      const blobPromise = new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
      webcamState.inspection.blob = await blobPromise;
    }
  }

  const fileInput = e.target.querySelector('input[type="file"][name="image"]');
  const hasFile = fileInput && fileInput.files && fileInput.files.length > 0;
  if (!webcamState.inspection.blob && !hasFile) {
    resBox.innerHTML = '<div style="color: var(--danger); font-size: 13px; font-weight: 600;">⚠️ Please start the camera and point it at the floor, or choose an image file to inspect.</div>';
    return;
  }

  if (webcamState.inspection.blob) {
    formData.set('image', webcamState.inspection.blob, 'floor.jpg');
  }

  try {
    submitBtn.disabled = true;
    resBox.innerHTML = '<div class="spinner">Scanning floor for waste & contaminants (YOLOv8)...</div>';

    // 1. Submit (Immediate 202 Accepted)
    const initial = await fetchJSON('/api/inspection/analyze', { method: 'POST', body: formData });
    const inspectionId = initial.inspection_id;

    // 2. Poll until background forward-pass completes
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetchJSON(`/api/inspection/${inspectionId}/status`);
        if (res.complete) {
          clearInterval(pollInterval);
          submitBtn.disabled = false;

          const isClean = res.status === 'Clean';
          resBox.innerHTML = `
<div style="font-size: 14px; font-weight: 800; color: ${isClean ? 'var(--success)' : 'var(--danger)'};">
  ${isClean ? '✅ PASSED: Floor Clean & Sanitary' : '❌ UNCLEAN: Waste / Debris Localized'}
</div>
<div style="margin-top: 4px; color: var(--text-muted);">
  Findings: ${res.object_found ? `${res.object_count} item(s) (${res.raw_label})` : 'Zero Contaminants Found'}<br>
  Confidence: ${res.confidence ? (res.confidence * 100).toFixed(1) + '%' : '100% Floor Clarity'}<br>
  Audit ID: #${res.inspection_id} &bull; Timestamp: ${res.created_at.split('T')[1].slice(0, 5)}
</div>
${res.annotated_image_url ? `<img src="${res.annotated_image_url}" style="width: 100%; border-radius: 8px; margin-top: 8px;" />` : ''}
          `;
          loadAll();
        }
      } catch (pollErr) {
        clearInterval(pollInterval);
        submitBtn.disabled = false;
        resBox.textContent = `Polling error: ${pollErr.message}`;
      }
    }, 800);

  } catch (err) {
    submitBtn.disabled = false;
    resBox.textContent = `Inspection error: ${err.message}`;
  }
});

// Quick Action Helpers
async function quickAlertAbsence(wardId) {
  if (!confirm('Dispatch absence alert for this ward?')) return;
  await fetchJSON(`/api/wards/${wardId}/alert-absence`, { method: 'POST' });
  alert('Absence notification dispatched to worker and supervisor.');
  loadAll();
}

async function quickOverride(inspectionId, newStatus) {
  const reason = prompt(`Enter supervisor rationale to override status to ${newStatus}:`, 'Visual supervisor confirmation');
  if (!reason) return;
  await fetchJSON(`/api/inspection/${inspectionId}/override`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: newStatus, reason: reason, admin_name: 'Lead Supervisor' })
  });
  loadAll();
}

async function triggerIoTSimulation(sensorType) {
  await fetchJSON('/api/iot/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sensor_type: sensorType, ward_name: 'Emergency' })
  });
  alert(`Simulated ${sensorType} sensor event transmitted!`);
  loadAll();
}

async function deleteWorker(empKey) {
  if (!confirm(`Are you sure you want to delete worker "${empKey}" and their biometric face data?`)) return;
  try {
    await fetchJSON(`/api/employees/${empKey}`, { method: 'DELETE' });
    alert(`Worker "${empKey}" deleted successfully.`);
    loadAll();
  } catch (err) {
    alert(`Error deleting worker: ${err.message}`);
  }
}
window.deleteWorker = deleteWorker;

// Live Toast Poller
async function pollToast() {
  try {
    const data = await fetchJSON('/api/notifications/live');
    if (data.feed && data.feed.length > 0) {
      const top = data.feed[0];
      const toastEl = document.getElementById('liveToastText');
      if (toastEl) toastEl.textContent = `[${top.ward_name}] ${top.message}`;
    }
  } catch (e) {}
}
setInterval(pollToast, 3000);

// Camera Setup
function setupWebcam(type) {
  const video = document.getElementById(`${type}Video`);
  const canvas = document.getElementById(`${type}Canvas`);
  if (!video || !canvas) return;

  const startBtn = document.querySelector(`[data-start-camera="${type}"]`);
  const snapBtn = document.querySelector(`[data-capture-camera="${type}"]`);

  if (startBtn) {
    startBtn.onclick = async () => {
      try {
        webcamState[type].stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = webcamState[type].stream;
      } catch (e) {
        alert(`Camera access denied: ${e.message}`);
      }
    };
  }

  if (snapBtn) {
    snapBtn.onclick = () => {
      if (!webcamState[type].stream) return alert('Please start camera first');
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.classList.add('has-frame');
      canvas.toBlob((blob) => {
        webcamState[type].blob = blob;
      }, 'image/jpeg');
    };
  }
}

// Main Loader
async function loadAll() {
  try {
    const [overview, wards, employees, history, telemetry] = await Promise.all([
      fetchJSON('/api/overview'),
      fetchJSON('/api/wards'),
      fetchJSON('/api/employees'),
      fetchJSON('/api/history'),
      fetchJSON('/api/iot/summary'),
    ]);

    appState.employees = employees.employees;
    appState.wards = wards.wards;

    renderMetrics(overview);
    populateDropdowns(wards.wards, employees.employees);
    renderWardsGrid(wards.wards);
    renderHistoryAndTelemetry(history, telemetry, employees.employees);
  } catch (err) {
    console.error('Failed to load dashboard:', err);
  }
}

// Setup Form Listeners for Add Ward & Add Employee
document.getElementById('wardForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  await fetchJSON('/api/wards', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.fromEntries(formData.entries()))
  });
  e.target.reset();
  alert('Ward added successfully!');
  loadAll();
});

// Show upload button if file is chosen manually
const fileInput = document.getElementById('enrollPhotoInput');
if (fileInput) {
  fileInput.addEventListener('change', () => {
    const btn = document.getElementById('btnSubmitFileEnroll');
    if (btn) btn.style.display = fileInput.files.length > 0 ? 'inline-block' : 'none';
  });
}

// 80-Frame Biometric Capture Studio
const btnStart80 = document.getElementById('btnStart80FrameCapture');
if (btnStart80) {
  btnStart80.addEventListener('click', async () => {
    const nameInput = document.getElementById('enrollNameInput');
    const roleInput = document.getElementById('enrollRoleInput');
    const phoneInput = document.getElementById('enrollPhoneInput');
    const feedback = document.getElementById('enrollFeedback');
    const progressContainer = document.getElementById('enrollProgressContainer');
    const progressBar = document.getElementById('enrollProgressBar');
    const progressStatus = document.getElementById('enrollProgressStatus');
    const progressPercent = document.getElementById('enrollProgressPercent');
    const video = document.getElementById('enrollWebcamVideo');
    const canvas = document.getElementById('enrollWebcamCanvas');
    const guideText = document.getElementById('enrollGuideText');

    const name = (nameInput.value || '').trim();
    if (!name) {
      alert('Please enter the full name of the staff member first.');
      nameInput.focus();
      return;
    }

    btnStart80.disabled = true;
    feedback.textContent = '';
    progressContainer.style.display = 'block';

    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' }
      });
      video.srcObject = stream;
      await new Promise(r => video.onloadedmetadata = r);
      video.play();
    } catch (camErr) {
      btnStart80.disabled = false;
      progressContainer.style.display = 'none';
      alert(`Camera access error: ${camErr.message}. You can still upload a photo below.`);
      return;
    }

    const TARGET_FRAMES = 80;
    const capturedBlobs = [];
    canvas.width = 320;
    canvas.height = 240;
    const ctx = canvas.getContext('2d');

    const prompts = [
      { at: 0, text: 'Look directly at the camera...' },
      { at: 20, text: 'Turn face slightly to the left...' },
      { at: 40, text: 'Turn face slightly to the right...' },
      { at: 60, text: 'Tilt chin slightly up and down...' }
    ];

    let currentFrame = 0;

    await new Promise((resolve) => {
      const interval = setInterval(() => {
        if (currentFrame >= TARGET_FRAMES) {
          clearInterval(interval);
          resolve();
          return;
        }

        ctx.drawImage(video, 0, 0, 320, 240);
        canvas.toBlob((blob) => {
          if (blob) capturedBlobs.push(blob);
        }, 'image/jpeg', 0.65);

        currentFrame++;
        const pct = Math.round((currentFrame / TARGET_FRAMES) * 100);
        progressBar.style.width = `${pct}%`;
        progressPercent.textContent = `${pct}%`;

        const activePrompt = [...prompts].reverse().find(p => currentFrame >= p.at);
        const text = activePrompt ? activePrompt.text : 'Hold still...';
        progressStatus.textContent = `${text} (${currentFrame}/${TARGET_FRAMES})`;
        if (guideText) guideText.textContent = `${currentFrame}/${TARGET_FRAMES}`;
      }, 65);
    });

    stream.getTracks().forEach(t => t.stop());
    video.srcObject = null;
    if (guideText) guideText.textContent = 'Capture Complete!';

    progressStatus.textContent = 'Compiling 80 biometric feature vectors (KNN)...';
    feedback.innerHTML = '<span style="color: var(--primary);">Uploading 80 clips & training facial vector space...</span>';

    try {
      const formData = new FormData();
      formData.append('name', name);
      formData.append('designation', (roleInput.value || 'Sanitation Staff').trim());
      formData.append('phone', (phoneInput.value || '').trim());

      capturedBlobs.forEach((blob, idx) => {
        formData.append('images', blob, `frame_${idx}.jpg`);
      });

      const res = await fetchJSON('/api/employees/enroll-web', {
        method: 'POST',
        body: formData
      });

      feedback.innerHTML = `<span style="color: var(--success); font-weight: 700;">🎉 Success: Enrolled ${res.name} with ${res.samples_captured} biometric vector samples!</span>`;
      alert(`Success: ${res.name} successfully registered with ${res.samples_captured} biometric frames!\nThey can now clock in at Step 1.`);

      nameInput.value = '';
      roleInput.value = '';
      phoneInput.value = '';
      progressContainer.style.display = 'none';
      progressBar.style.width = '0%';
      loadAll();
    } catch (err) {
      feedback.innerHTML = `<span style="color: var(--danger);">Enrollment error: ${err.message}</span>`;
      alert(`Enrollment failed: ${err.message}`);
    } finally {
      btnStart80.disabled = false;
    }
  });
}

// Fallback manual form submit (for file uploads)
document.getElementById('employeeForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const feedback = document.getElementById('enrollFeedback');
  const submitBtn = e.target.querySelector('button[type="submit"]');
  const formData = new FormData(e.target);
  const fileInput = document.getElementById('enrollPhotoInput');
  const hasFiles = fileInput && fileInput.files && fileInput.files.length > 0;

  submitBtn.disabled = true;
  if (feedback) feedback.textContent = hasFiles ? 'Analyzing face & extracting biometric vectors...' : 'Saving staff profile...';

  try {
    if (hasFiles) {
      const res = await fetchJSON('/api/employees/enroll-web', {
        method: 'POST',
        body: formData
      });
      alert(`Success: Enrolled ${res.name} with ${res.samples_captured} facial vector samples!`);
    } else {
      await fetchJSON('/api/employees', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.fromEntries(formData.entries()))
      });
      alert('Staff registered! Note: Use 80-Frame Capture or upload a photo to enable biometrics.');
    }
    e.target.reset();
    if (feedback) feedback.textContent = '';
    loadAll();
  } catch (err) {
    if (feedback) feedback.innerHTML = `<span style="color: var(--danger);">Enrollment failed: ${err.message}</span>`;
  } finally {
    submitBtn.disabled = false;
  }
});

// Initialize
setupWebcam('attendance');
setupWebcam('inspection');
loadAll();
