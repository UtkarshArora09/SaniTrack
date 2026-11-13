async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function getStatusPill(status) {
  const normalized = (status || 'Pending').toLowerCase();
  if (normalized.includes('clean') && !normalized.includes('not')) {
    return '<span class="status-pill clean">✓ Clean</span>';
  }
  if (normalized.includes('not') || normalized.includes('dirty')) {
    return '<span class="status-pill not-clean">✕ Needs Cleaning</span>';
  }
  return '<span class="status-pill pending">⏳ Pending Check</span>';
}

function formatDate(isoStr) {
  if (!isoStr) return 'None recorded';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return isoStr;
  }
}

function renderWorker(payload) {
  // Update Telegram connection status
  if (payload.worker) {
    const tgLink = document.getElementById('tgConnectLink');
    const tgDesc = document.getElementById('tgStatusDesc');
    const tgTitle = document.getElementById('tgStatusTitle');
    const tgBanner = document.getElementById('telegramConnectBanner');
    if (payload.worker.telegram_chat_id) {
      if (tgTitle) tgTitle.textContent = '✅ Telegram Alerts Active';
      if (tgDesc) tgDesc.textContent = `Connected! You will receive task dispatches and emergency ward alerts on Telegram.`;
      if (tgLink) {
        tgLink.innerHTML = '<span>💬 Open SaniTrack Bot</span>';
        tgLink.href = 'https://t.me/SaniTrackBot';
        tgLink.className = 'btn btn-sm btn-secondary';
      }
      if (tgBanner) {
        tgBanner.style.background = '#f0fdf4';
        tgBanner.style.borderColor = '#86efac';
      }
    } else {
      if (tgTitle) tgTitle.textContent = 'Instant Telegram Alerts';
      if (tgDesc) tgDesc.textContent = 'Tap Connect to receive cleaning duties and supervisor notices directly on your phone.';
      if (tgLink) {
        tgLink.innerHTML = '<span>📲 Connect Telegram</span>';
        tgLink.href = `https://t.me/SaniTrackBot?start=emp_${window.SANITRACK_WORKER_KEY}`;
        tgLink.className = 'btn btn-sm btn-primary';
      }
    }
  }

  const tasks = document.getElementById('workerTasks');
  if (!tasks) return;

  if (!payload.assigned_wards || !payload.assigned_wards.length) {
    tasks.innerHTML = `
      <div class="card" style="text-align: center; padding: 36px 20px; color: var(--text-muted);">
        <div style="font-size: 36px; margin-bottom: 8px;">📋</div>
        <strong style="color: var(--text-main); font-size: 15px; display: block;">No Wards Assigned Currently</strong>
        <p style="margin: 6px 0 0; font-size: 13px;">Your supervisor has not assigned any active wards to your shift.</p>
      </div>`;
  } else {
    tasks.innerHTML = payload.assigned_wards.map((ward) => `
      <article class="task-card">
        <div class="task-header">
          <div>
            <div class="task-ward-title">${ward.name}</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 3px;">📍 ${ward.location || ward.name}</div>
          </div>
          <div>${getStatusPill(ward.latest_status)}</div>
        </div>

        <div class="task-meta-grid">
          <div class="task-meta-item">Latest Inspection: <strong>${formatDate(ward.latest_inspection_at)}</strong></div>
          <div class="task-meta-item">Floor Objects: <strong>${ward.latest_object_count ?? 0} items detected</strong></div>
          <div class="task-meta-item">Last Attendance Log: <strong>${formatDate(ward.latest_attendance_at)}</strong></div>
          <div class="task-meta-item">Last Confirmation: <strong>${ward.last_confirmation_at ? formatDate(ward.last_confirmation_at) : 'Not confirmed yet'}</strong></div>
        </div>

        ${ward.override_reason ? `
          <div style="margin-bottom: 14px; font-size: 12px; background: #f8fafc; border-left: 3px solid var(--primary); padding: 8px 12px; border-radius: 4px;">
            <strong>Supervisor Note:</strong> ${ward.override_reason}
          </div>
        ` : ''}

        <button type="button" class="btn btn-success btn-block" data-worker-confirm="${ward.name}">
          ✓ Mark Cleaning Complete for ${ward.name}
        </button>
      </article>
    `).join('');
  }

  const notifications = document.getElementById('workerNotifications');
  if (!notifications) return;

  if (!payload.notifications || !payload.notifications.length) {
    notifications.innerHTML = `
      <div class="card" style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 13px;">
        No recent notifications or urgent alerts for your assigned wards.
      </div>`;
  } else {
    notifications.innerHTML = payload.notifications.map((item) => {
      const isUrgent = (item.message || '').toLowerCase().includes('not clean') || (item.message || '').toLowerCase().includes('urgent');
      return `
        <div class="notification-card ${isUrgent ? 'alert' : ''}">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <strong style="color: ${isUrgent ? 'var(--danger)' : 'var(--primary)'}; font-size: 13px;">
              ${item.ward_name || 'Ward Update'}
            </strong>
            <span class="notification-time">${formatDate(item.created_at)}</span>
          </div>
          <div style="color: var(--text-main); font-size: 13px; line-height: 1.4;">${item.message}</div>
        </div>
      `;
    }).join('');
  }
}

async function loadWorkerPage() {
  const tasks = document.getElementById('workerTasks');
  if (tasks && !tasks.innerHTML.trim()) {
    tasks.innerHTML = '<div class="spinner">Loading your assigned duties...</div>';
  }
  try {
    const payload = await fetchJSON(`/api/workers/${window.SANITRACK_WORKER_KEY}/dashboard`);
    renderWorker(payload);
  } catch (error) {
    console.error(error);
    if (tasks) {
      tasks.innerHTML = `<div class="card" style="padding: 18px; color: var(--danger); font-size: 13px;">Failed to load assignments: ${error.message}</div>`;
    }
  }
}

document.addEventListener('click', async (event) => {
  const target = event.target.closest('[data-worker-confirm]');
  if (!target) return;
  const wardName = target.dataset.workerConfirm;
  const originalText = target.innerHTML;

  const notes = window.prompt(`Confirm cleaning for ${wardName}?\nAdd optional comments (e.g. "Floors mopped, trash cleared"):`, 'Cleaning completed and sanitized.') || 'Cleaning completed and sanitized.';

  try {
    target.disabled = true;
    target.textContent = 'Submitting confirmation...';
    await fetchJSON('/api/tasks/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ward_name: wardName, employee_key: window.SANITRACK_WORKER_KEY, notes }),
    });
    alert(`Success: Cleaning completion confirmed for ${wardName}. Supervisor has been notified.`);
    await loadWorkerPage();
  } catch (err) {
    alert(`Failed to confirm cleaning: ${err.message}`);
    target.disabled = false;
    target.innerHTML = originalText;
  }
});

const refreshBtn = document.getElementById('refreshWorkerPage');
if (refreshBtn) {
  refreshBtn.addEventListener('click', async () => {
    refreshBtn.disabled = true;
    const oldText = refreshBtn.textContent;
    refreshBtn.textContent = 'Refreshing...';
    try {
      await loadWorkerPage();
    } finally {
      refreshBtn.disabled = false;
      refreshBtn.textContent = oldText;
    }
  });
}

// Initial Load
loadWorkerPage();

// Progressive Web App (PWA) Service Worker Registration
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js').catch(err => {
      console.debug('SW registration skipped:', err);
    });
  });
}

// PWA Install Prompt Banner Event Handling
let deferredPrompt = null;
const pwaBanner = document.getElementById('pwaInstallBanner');
const btnPwaInstall = document.getElementById('btnPwaInstall');

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  if (pwaBanner) pwaBanner.style.display = 'flex';
});

if (btnPwaInstall) {
  btnPwaInstall.addEventListener('click', async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted' && pwaBanner) {
      pwaBanner.style.display = 'none';
    }
    deferredPrompt = null;
  });
}

window.addEventListener('appinstalled', () => {
  if (pwaBanner) pwaBanner.style.display = 'none';
});


