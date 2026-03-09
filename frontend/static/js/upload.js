/**
 * VaaniPariksha - Upload Page JavaScript
 */
let selectedFile = null;
let examData = null;

/* --- Drag & drop --- */
function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('uploadZone').classList.add('drag-over');
}
function handleDragLeave(e) {
  document.getElementById('uploadZone').classList.remove('drag-over');
}
function handleDrop(e) {
  e.preventDefault();
  document.getElementById('uploadZone').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) processFile(file);
}
function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) processFile(file);
}

function processFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showError('Only PDF files are accepted.'); return;
  }
  if (file.size > 50 * 1024 * 1024) {
    showError('File exceeds 50MB limit.'); return;
  }
  selectedFile = file;
  document.getElementById('uploadForm').style.display = 'block';
  document.getElementById('filePreview').innerHTML = `
    <span>📄</span>
    <div>
      <div style="font-weight:600">${file.name}</div>
      <div style="font-size:0.8rem;color:var(--text-muted)">${file.size < 1024 * 1024 ? (file.size/1024).toFixed(1) + ' KB' : (file.size/1024/1024).toFixed(2) + ' MB'}</div>
    </div>
  `;
  // Pre-fill title from filename
  const titleInput = document.getElementById('examTitle');
  if (!titleInput.value) {
    titleInput.value = file.name.replace('.pdf','').replace(/[-_]/g,' ');
  }
}

async function uploadPDF() {
  if (!selectedFile) { showError('Please select a PDF first.'); return; }

  const title = document.getElementById('examTitle').value.trim() || selectedFile.name;
  const duration = parseInt(document.getElementById('examDuration').value) || 60;

  // Show progress
  document.getElementById('uploadProgress').style.display = 'block';
  document.getElementById('uploadBtn').disabled = true;
  animateProgress();

  const formData = new FormData();
  formData.append('pdf', selectedFile);
  formData.append('title', title);
  formData.append('duration', duration);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok) {
      document.getElementById('uploadProgress').style.display = 'none';
      document.getElementById('uploadBtn').disabled = false;
      showError(data.error || 'Upload failed.');
      return;
    }

    // Direct Success
    finishProgress();
    
    // Store exam data
    examData = data;
    localStorage.setItem('vp_exam_id', data.exam_id);
    localStorage.setItem('vp_exam_title', data.title);
    localStorage.setItem('vp_exam_duration', data.duration_minutes || duration);

    showResult(data);
    showToast(`Exam "${data.title}" uploaded successfully!`, 'success');
    loadExams(); // Refresh list
  } catch (err) {
    // We don't hide the progress bar yet! We keep it visible while polling.
    console.error("Upload error (likely timeout):", err);
    
    const label = document.getElementById('progressLabel');
    const bar = document.getElementById('progressBar');
    label.textContent = 'Processing large file... please wait...';
    bar.style.width = '98%'; 
    
    let attempts = 0;
    const checkInterval = setInterval(async () => {
      attempts++;
      try {
        const checkRes = await fetch('/api/exams');
        const checkData = await checkRes.json();
        if (checkData.success && checkData.exams) {
            const found = checkData.exams.find(ex => ex.title === title);
            if (found || attempts > 12) {
                clearInterval(checkInterval);
                if (found) {
                  finishProgress();
                  showToast('Exam successfully saved! You can now start the test.', 'success');
                  loadExams();
                } else {
                  document.getElementById('uploadProgress').style.display = 'none';
                  document.getElementById('uploadBtn').disabled = false;
                  showToast('The upload might have failed. Please try again or refresh the page.', 'error');
                }
            }
        }
      } catch(e) { /* ignore polling errors */ }
    }, 3000);
  }
}

function finishProgress() {
  const bar = document.getElementById('progressBar');
  const label = document.getElementById('progressLabel');
  bar.style.width = '100%';
  label.textContent = 'Complete!';
  setTimeout(() => {
    document.getElementById('uploadProgress').style.display = 'none';
    document.getElementById('uploadBtn').disabled = false;
  }, 800);
}

function showResult(data) {
  document.getElementById('uploadForm').style.display = 'none';
  const rc = document.getElementById('resultCard');
  rc.style.display = 'block';
  document.getElementById('resultTitle').textContent = `✅ "${data.title}" Uploaded`;
  document.getElementById('resultSub').textContent =
    `${data.total_questions} questions detected across ${data.page_count || '?'} pages`;

  // Show preview of first 5 questions
  const preview = document.getElementById('questionPreview');
  if (data.questions && data.questions.length > 0) {
    preview.innerHTML = data.questions.slice(0, 5).map(q => `
      <div class="q-preview-item">
        <span class="q-preview-num">Q${q.question_number}</span>
        <span style="font-size:0.78rem;color:var(--text-muted);margin-right:0.5rem">[${q.question_type}]</span>
        ${escapeHtml((q.question_text || '').substring(0, 100))}${q.question_text?.length > 100 ? '…' : ''}
      </div>
    `).join('');
    if (data.total_questions > 5) {
      preview.innerHTML += `<div style="text-align:center;color:var(--text-muted);font-size:0.82rem;padding:0.5rem">+ ${data.total_questions - 5} more questions</div>`;
    }
  }
}

function goToExam() {
  if (examData) {
    // Clear old student details so exam page can voice onboard
    localStorage.removeItem('vp_student_name');
    localStorage.removeItem('vp_student_id');
  }
  window.location.href = '/exam';
}

function resetUpload() {
  selectedFile = null; examData = null;
  document.getElementById('resultCard').style.display = 'none';
  document.getElementById('uploadForm').style.display = 'none';
  document.getElementById('filePreview').innerHTML = '';
  document.getElementById('examTitle').value = '';
  document.getElementById('pdfInput').value = '';
}

function showError(msg) {
  showToast(msg, 'error');
}

function showToast(msg, type = 'error') {
  const el = document.createElement('div');
  let bg = '#7f1d1d'; // default error (dark red)
  let border = '#ef4444';
  let icon = '⚠';

  if (type === 'success') {
    bg = '#064e3b'; // dark green
    border = '#10b981';
    icon = '✅';
  } else if (type === 'info') {
    bg = '#1e3a8a'; // dark blue
    border = '#3b82f6';
    icon = 'ℹ';
  }

  el.style.cssText = `position:fixed;top:1rem;left:50%;transform:translateX(-50%);background:${bg};border:1px solid ${border};color:#fff;padding:0.8rem 1.5rem;border-radius:12px;font-size:0.9rem;z-index:9999;font-weight:500;box-shadow:0 10px 15px -3px rgba(0,0,0,0.3);`;
  el.textContent = icon + ' ' + msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

function animateProgress() {
  let pct = 0;
  const bar = document.getElementById('progressBar');
  const label = document.getElementById('progressLabel');
  const stages = [
    [30, 'Uploading PDF...'],
    [60, 'Extracting text...'],
    [85, 'Classifying questions...'],
    [95, 'Saving to database...'],
  ];
  stages.forEach(([target, text], i) => {
    setTimeout(() => {
      pct = target;
      bar.style.width = pct + '%';
      label.textContent = text;
    }, i * 800);
  });
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

/* --- Existing Exams List --- */
document.addEventListener('DOMContentLoaded', loadExams);

async function loadExams() {
  try {
    const res = await fetch('/api/exams');
    const data = await res.json();
    if (data.success && data.exams && data.exams.length > 0) {
      document.getElementById('availableExamsContainer').style.display = 'block';
      const list = document.getElementById('examsList');
      list.innerHTML = data.exams.map(ex => `
        <div class="exam-list-item" style="display:flex; justify-content:space-between; align-items:center; background:var(--bg-layer); padding:1rem; border-radius:8px; border:1px solid var(--border); transition:all 0.2s;">
          <div>
            <div style="font-weight:600; font-size:1.05rem;">${escapeHtml(ex.title)}</div>
            <div style="font-size:0.85rem; color:var(--text-muted); margin-top:0.25rem;">
              ${ex.total_questions} questions · ${ex.duration_minutes} mins · Added ${new Date(ex.created_at).toLocaleDateString()}
            </div>
          </div>
          <button class="btn-primary" style="padding:0.5rem 1rem; font-size:0.9rem;" onclick="selectExistingExam(${ex.id}, '${escapeHtml(ex.title.replace(/'/g, "\\'"))}', ${ex.duration_minutes})">
            Take Exam
          </button>
        </div>
      `).join('');
    }
  } catch(err) {
    console.error("Failed to load existing exams:", err);
  }
}

function selectExistingExam(id, title, duration) {
  localStorage.setItem('vp_exam_id', id);
  localStorage.setItem('vp_exam_title', title);
  localStorage.setItem('vp_exam_duration', duration);
  
  // Clear old student details
  localStorage.removeItem('vp_student_name');
  localStorage.removeItem('vp_student_id');
  
  window.location.href = '/exam';
}

