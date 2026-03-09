/**
 * VaaniPariksha - Admin Dashboard JavaScript
 */
const API = '/api';

async function loadDashboard() {
  try {
    const res = await fetch(`${API}/admin/dashboard`);
    const data = await res.json();
    renderSummary(data.summary);
    renderActiveSessions(data.active_sessions);
    renderSubmittedSessions(data.submitted_sessions);
    renderExams(data.exams);
  } catch (err) {
    console.error('Dashboard load failed:', err);
  }
}

function renderSummary(s) {
  document.getElementById('totalExams').textContent = s.total_exams || 0;
  document.getElementById('activeSessions').textContent = s.active_sessions || 0;
  document.getElementById('submittedSessions').textContent = s.submitted_sessions || 0;
  document.getElementById('crashedSessions').textContent = s.crashed_sessions || 0;
}

function renderActiveSessions(sessions) {
  const tbody = document.getElementById('activeTableBody');
  if (!sessions || sessions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="table-empty">No active sessions</td></tr>';
    return;
  }
  tbody.innerHTML = sessions.map(s => {
    const mins = s.time_remaining_seconds ? Math.floor(s.time_remaining_seconds / 60) : '—';
    const secs = s.time_remaining_seconds ? s.time_remaining_seconds % 60 : '';
    const timeStr = s.time_remaining_seconds ? `${mins}m ${secs}s` : '—';
    const saved = s.last_saved_at ? new Date(s.last_saved_at).toLocaleTimeString() : '—';
    return `<tr>
      <td><code style="font-size:0.8rem;color:var(--primary-light)">${s.session_token}</code></td>
      <td style="font-weight:600">${escapeHtml(s.student_id || '—')}</td>
      <td><code style="color:var(--text)">${escapeHtml(s.exam_code || s.exam_id)}</code></td>
      <td><b>Q${s.current_question || '?'}</b></td>
      <td style="color:${parseInt(mins) < 10 ? 'var(--danger)' : 'var(--success)'}">${timeStr}</td>
      <td style="font-size:0.8rem;color:var(--text-muted)">${saved}</td>
    </tr>`;
  }).join('');
}

function renderSubmittedSessions(sessions) {
  const tbody = document.getElementById('submittedTableBody');
  if (!sessions || sessions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="table-empty">No submitted sessions yet</td></tr>';
    return;
  }
  tbody.innerHTML = sessions.map(s => {
    const time = s.end_time ? new Date(s.end_time).toLocaleString() : '—';
    return `<tr>
      <td><code style="font-size:0.8rem;color:var(--primary-light)">${s.short_token}</code></td>
      <td style="font-weight:600">${escapeHtml(s.student_id || '—')}</td>
      <td><code style="color:var(--text)">${escapeHtml(s.exam_code || s.exam_id)}</code></td>
      <td style="font-size:0.8rem;color:var(--text-muted)">${time}</td>
      <td>
        ${s.pdf_ready 
          ? `<a href="/api/download-pdf/${s.session_token}" class="btn-primary btn-small" style="text-decoration:none" download>📄 Download PDF</a>`
          : '<span class="status-badge">Processing...</span>'}
      </td>
    </tr>`;
  }).join('');
}

function renderExams(exams) {
  const tbody = document.getElementById('examsTableBody');
  if (!exams || exams.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="table-empty">No exams uploaded yet</td></tr>';
    return;
  }
  tbody.innerHTML = exams.map(e => {
    const statusMap = {
      'pending': 'status-pending', 'active': 'status-active',
      'completed': 'status-submitted', 'archived': 'status-crashed'
    };
    const created = e.created_at ? new Date(e.created_at).toLocaleDateString() : '—';
    return `<tr>
      <td><code style="color:var(--primary-light)">${e.exam_code}</code></td>
      <td style="font-weight:600;color:var(--text)">${escapeHtml(e.title)}</td>
      <td>${e.total_questions}</td>
      <td>${e.duration_minutes}m</td>
      <td>${e.sessions_total || 0}</td>
      <td>${e.sessions_submitted || 0}</td>
      <td><span class="status-badge ${statusMap[e.status] || ''}">${e.status}</span></td>
      <td style="font-size:0.8rem;color:var(--text-muted)">${created}</td>
      <td>
        <div style="display:flex;gap:0.5rem">
          <button class="btn-text" onclick="editExam(${e.id}, '${escapeHtml(e.title)}', ${e.duration_minutes})" title="Edit Exam">✏️</button>
          <button class="btn-text" onclick="deleteExam(${e.id})" title="Delete Exam" style="color:var(--danger)">🗑️</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

let CURRENT_EDIT_ID = null;
let CURRENT_DELETE_ID = null;

function editExam(id, title, duration) {
  CURRENT_EDIT_ID = id;
  document.getElementById('editTitle').value = title;
  document.getElementById('editDuration').value = duration;
  document.getElementById('editModal').style.display = 'flex';
}

function closeEditModal() {
  document.getElementById('editModal').style.display = 'none';
  CURRENT_EDIT_ID = null;
}

async function submitEdit() {
  const newTitle = document.getElementById('editTitle').value.trim();
  const newDuration = document.getElementById('editDuration').value;
  
  if (!newTitle || !newDuration) {
    alert("Please fill all fields.");
    return;
  }

  try {
    const res = await fetch(`${API}/admin/exam/${CURRENT_EDIT_ID}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle, duration_minutes: parseInt(newDuration) })
    });
    if (res.ok) {
      closeEditModal();
      loadDashboard();
    } else {
      const data = await res.json();
      alert(data.error || "Failed to update exam.");
    }
  } catch (err) {
    console.error("Edit failed:", err);
  }
}

function deleteExam(id) {
  CURRENT_DELETE_ID = id;
  document.getElementById('deleteModal').style.display = 'flex';
  document.getElementById('confirmDeleteBtn').onclick = submitDelete;
}

function closeDeleteModal() {
  document.getElementById('deleteModal').style.display = 'none';
  CURRENT_DELETE_ID = null;
}

async function submitDelete() {
  try {
    const res = await fetch(`${API}/admin/exam/${CURRENT_DELETE_ID}`, { method: 'DELETE' });
    if (res.ok) {
      closeDeleteModal();
      loadDashboard();
    } else {
      alert("Failed to delete exam.");
    }
  } catch (err) {
    console.error("Delete failed:", err);
  }
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

// Auto-refresh every 10s
loadDashboard();
setInterval(loadDashboard, 10000);
