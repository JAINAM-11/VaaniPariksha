/**
 * VaaniPariksha - Exam Interface (exam.js)
 * Handles: session management, Web Speech API STT, timer, lockdown,
 * question navigation, answer capture, confirmation, PDF submit.
 */

const API = '/api';
let SESSION_TOKEN = null;
let QUESTIONS = [];
let CURRENT_IDX = 0;
let TIMER_INTERVAL = null;
let TIME_REMAINING = 0;
let LISTENING = false;
let RECOGNITION = null;
let PENDING_ANSWER = null;
let PENDING_CONF = 0.0;
let SUBMITTED = false;
let SILENCE_HINT_TIMER = null;
let PENDING_SUBMIT = false;
let BARGE_IN_THRESHOLD = 0.02; // Hypersensitive for 2-way communication
let bargeInDetected = false;

/* ================================================================
   AUDIO EARCONS (Non-verbal feedback)
   ================================================================ */
const AudioEarcons = {
  ctx: null,
  init() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
  },
  play(type) {
    try {
      this.init();
      if (this.ctx.state === 'suspended') this.ctx.resume();
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.connect(gain);
      gain.connect(this.ctx.destination);

      const now = this.ctx.currentTime;
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(0.05, now + 0.01);

      if (type === 'mic_open') {
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
        osc.start(now); osc.stop(now + 0.15);
      } else if (type === 'processing') {
        osc.frequency.setValueAtTime(880, now);
        osc.frequency.exponentialRampToValueAtTime(440, now + 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
        osc.start(now); osc.stop(now + 0.15);
      } else if (type === 'success') {
        osc.frequency.setValueAtTime(660, now);
        osc.frequency.exponentialRampToValueAtTime(1320, now + 0.2);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
        osc.start(now); osc.stop(now + 0.25);
      }
    } catch(e) { console.error("Earcon failed", e); }
  }
};

let ONBOARDING_STEP = 'none'; // 'ask_name', 'confirm_name', 'ask_id', 'confirm_id', 'ask_start'
let TEMP_NAME = '';
let TEMP_ID = '';

/* ================================================================
   INIT
   ================================================================ */
document.addEventListener('DOMContentLoaded', async () => {
  // Restore exam state from localStorage
  const examId = localStorage.getItem('vp_exam_id');
  const existingToken = localStorage.getItem('vp_session_token');
  const studentName = localStorage.getItem('vp_student_name') || 'Anonymous';
  const studentId = localStorage.getItem('vp_student_id') || '';
  const title = localStorage.getItem('vp_exam_title') || 'Exam';

  document.getElementById('examTitleDisplay').textContent = title;

  if (!examId) {
    alert('No exam loaded. Please upload a PDF first.');
    window.location.href = '/';
    return;
  }

  // Attempt crash recovery if token exists
  if (existingToken) {
    const recovered = await tryRecover(existingToken);
    if (recovered) return;
  }

  initLockdown();
  // We wait for user engagement via startExamEngagement() to avoid autoplay blocks
});

let ENGAGEMENT_STARTED = false;

/* ================================================================
   USER ENGAGEMENT / ACCESSIBILITY START
   ================================================================ */
function startExamEngagement() {
  if (ENGAGEMENT_STARTED) return;
  ENGAGEMENT_STARTED = true;
  
  const overlay = document.getElementById('startOverlay');
  if (overlay) {
    overlay.style.opacity = '0';
    setTimeout(() => overlay.remove(), 500);
  }
  
  // Directly start onboarding
  startVoiceOnboarding();
}

// Global listeners for blind students: ANY interaction starts the audio engine
window.addEventListener('click', startExamEngagement, { once: true });
window.addEventListener('keydown', startExamEngagement, { once: true });

/* ================================================================
   SESSION START / RECOVERY
   ================================================================ */
/* ================================================================
   SESSION START / ONBOARDING
   ================================================================ */
function startVoiceOnboarding() {
  ONBOARDING_STEP = 'ask_id';
  TEMP_NAME = 'Student';

  document.getElementById('onboardingUI').style.display = 'flex';
  document.getElementById('examLayout').style.display = 'none';
  document.getElementById('idInputWrap').style.display = 'block';

  OnboardingVoiceIndicator.setState('idle');

  const msgEl = document.getElementById('onboardingMsg');
  if (msgEl) msgEl.textContent = 'Please say your Student ID.';

  // Speak and then start listening
  speakOnboarding('To start the exam, please say your Student I D.');
}

/* ── State flags ────────────────────────────────────────────── */
let PROCESSING_ONBOARDING = false;
let ONBOARDING_LOCKED     = false; // mic is deaf while TTS plays

/* ================================================================
   ONBOARDING TRANSCRIPT HANDLER
   ================================================================ */
async function handleOnboardingTranscript(transcript, _spokenMessage) {
  // Drop all input while TTS is playing OR a fetch is in-flight
  if (ONBOARDING_LOCKED || PROCESSING_ONBOARDING) {
    console.log(`[Onb] Ignored — locked:${ONBOARDING_LOCKED} processing:${PROCESSING_ONBOARDING}`);
    return;
  }

  const lower = transcript.toLowerCase().trim();
  console.log(`[Onb] step=${ONBOARDING_STEP} | heard="${transcript}"`);

  const msgEl         = document.getElementById('onboardingMsg');
  const idInput       = document.getElementById('manualIdInput');
  const submitBtn     = document.getElementById('manualIdSubmitBtn');

  /* ── STEP: ask_id ──────────────────────────────────────────── */
  if (ONBOARDING_STEP === 'ask_id') {
    PROCESSING_ONBOARDING = true;
    OnboardingVoiceIndicator.setState('processing');

    try {
      const resp = await fetch(`${API}/clean-id`, {
        method : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body   : JSON.stringify({ text: transcript }),
      });

      if (!resp.ok) throw new Error('clean-id endpoint error');
      const { id: cleanedId } = await resp.json();

      if (!cleanedId || cleanedId === 'INVALID') {
        // Only complain if the transcript was substantial
        const msg = transcript.length > 3
          ? 'I could not find a valid I D in what you said. Please try again.'
          : undefined;
        if (msg) speakOnboarding(msg);
        else { if (!LISTENING) toggleListening(); }
        return;
      }

      /* ── Valid ID captured ── */
      TEMP_ID = String(cleanedId).toUpperCase();

      // 1. Update text box immediately
      if (idInput) { idInput.value = TEMP_ID; }
      if (submitBtn) submitBtn.style.display = 'none'; // hide manual button during voice flow

      // 2. Move to confirmation
      ONBOARDING_STEP = 'confirm_id';
      if (msgEl) msgEl.textContent = `Student ID: "${TEMP_ID}" — Is this correct?`;

      // 3. Stop mic, clear buffer, then speak the ID back
      if (LISTENING) toggleListening();
      recordingChunks = [];

      const spokenId = TEMP_ID.split('').join(' '); // e.g. "A 1 2 3"
      speakOnboarding(`Your Student I D is ${spokenId}. Is that correct? Say yes to confirm or no to try again.`);

    } catch (err) {
      console.error('[Onb] ID fetch error:', err);
      speakOnboarding('Something went wrong. Please say your Student I D again.');
    } finally {
      PROCESSING_ONBOARDING = false;
      OnboardingVoiceIndicator.setState('idle');
    }
    return;
  }

  /* ── STEP: confirm_id ──────────────────────────────────────── */
  if (ONBOARDING_STEP === 'confirm_id') {
    const isYes = /\b(yes|correct|yeah|yep|yup|okay|ok|right|confirmed|that's it|it is correct)\b/.test(lower);
    const isNo  = /\b(no|nope|wrong|not right|incorrect|try again|change|different)\b/.test(lower);

    if (isYes) {
      console.log('[Onb] ID confirmed → asking to start');
      startFinalOnboarding();
      return;
    }

    if (isNo) {
      console.log('[Onb] ID rejected → re-collecting');
      ONBOARDING_STEP = 'ask_id';
      if (msgEl) msgEl.textContent = 'No problem. Please say your Student ID again.';
      speakOnboarding('No problem. Please say your Student I D again.');
      return;
    }

    // Ambiguous — re-ask for yes/no
    console.log('[Onb] Ambiguous confirmation response');
    speakOnboarding(`I heard "${transcript}". Please say yes to confirm the I D ${TEMP_ID}, or no to try again.`);
    return;
  }

  /* ── STEP: ask_start ───────────────────────────────────────── */
  if (ONBOARDING_STEP === 'ask_start') {
    const isStart = /\b(start|begin|go|ready|let's go|start exam|begin exam)\b/.test(lower);
    if (isStart) {
      console.log('[Onb] Start confirmed → finalStart()');
      finalStart();
    } else {
      speakOnboarding('Whenever you are ready, just say Start.');
    }
    return;
  }
}

/* ================================================================
   ONBOARDING TTS HELPER — locks mic while speaking
   ================================================================ */
function speakOnboarding(text) {
  ONBOARDING_LOCKED = true;
  recordingChunks   = [];          // discard any audio captured so far

  speakText(text, () => {
    console.log('[Onb] TTS done. Releasing lock.');
    ONBOARDING_LOCKED = false;
    recordingChunks   = [];        // discard noise recorded during speech
    if (!LISTENING) toggleListening();
  });
}

/* ================================================================
   MANUAL ID SUBMIT BUTTON VISIBILITY
   ================================================================ */
function toggleIdSubmitBtn() {
  const input    = document.getElementById('manualIdInput');
  const btn      = document.getElementById('manualIdSubmitBtn');
  const startBtn = document.getElementById('startExamBtn');

  if (!input || !btn) return;
  // Only show submit button when we are in the ask_id step and there is text
  const show = ONBOARDING_STEP === 'ask_id' && input.value.trim().length > 0;
  btn.style.display = show ? 'block' : 'none';
  if (startBtn) startBtn.style.display = 'none';
}

/* ================================================================
   MANUAL SUBMISSION (Option 2)
   ================================================================ */
async function submitManualId() {
  const input   = document.getElementById('manualIdInput');
  const typedId = (input?.value || '').trim().replace(/[^a-zA-Z0-9]/g, '').toUpperCase();

  if (!typedId) {
    showToast('Please enter a Student ID.', 'warning');
    return;
  }

  console.log('[Onb] Manual ID submitted:', typedId);
  TEMP_ID = typedId;

  // Go straight to the ready-to-start screen
  startFinalOnboarding();
}

/* ================================================================
   FINAL ONBOARDING — "Ready to Start?"
   ================================================================ */
function startFinalOnboarding() {
  const msgEl    = document.getElementById('onboardingMsg');
  const startBtn = document.getElementById('startExamBtn');
  const idForm   = document.querySelector('.registration-form');

  if (idForm) idForm.style.display = 'none';

  ONBOARDING_STEP = 'ask_start';
  if (msgEl) msgEl.textContent = "Ready to begin! Say 'Start' or click the button below.";
  if (startBtn) startBtn.style.display = 'block';

  speakOnboarding('Your Student I D has been set. Whenever you are ready, say Start to begin the exam.');
}

async function finalStart() {
  const examId = localStorage.getItem('vp_exam_id');
  document.getElementById('onboardingUI').style.display = 'none';
  document.getElementById('examLayout').style.display = ''; // Let CSS manage 'flex' vs 'grid'
  ONBOARDING_STEP = 'none';
  await startSession(examId, TEMP_NAME, TEMP_ID);
}

async function startSession(examId, name, sid) {
  try {
    const res = await fetch(`${API}/start-exam`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exam_id: parseInt(examId), student_name: name, student_id: sid }),
    });
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Failed to start exam', 'error'); return; }

    SESSION_TOKEN = data.session_token;
    TIME_REMAINING = data.duration_minutes * 60;
    localStorage.setItem('vp_session_token', SESSION_TOKEN);

    // Load all questions from status endpoint
    await loadCurrentState();
    startTimer();
    readQuestionAloud();
    VoiceIndicator.setState('idle');
  } catch (err) {
    showToast('Cannot connect to server. Check Flask is running.', 'error');
  }
}

async function tryRecover(token) {
  try {
    const res = await fetch(`${API}/status/${token}`);
    if (!res.ok) return false;
    const data = await res.json();
    SESSION_TOKEN = token;
    TIME_REMAINING = data.time_remaining_seconds || 3600;
    await loadCurrentState();
    startTimer();
    showToast('📂 Session recovered after crash!', 'success');
    return true;
  } catch {
    return false;
  }
}

async function loadCurrentState() {
  const res = await fetch(`${API}/get-question/${SESSION_TOKEN}`);
  const data = await res.json();
  if (!data.question) return;

  // Build questions list from progress
  const prog = data.progress;
  renderProgressSidebar(prog);
  renderQuestion(data.question, data.answer, data.status);
  updateProgressCounts(prog);
}

/* ================================================================
   QUESTION RENDERING
   ================================================================ */
function renderQuestion(q, answer, status) {
  if (!q) return;
  document.getElementById('qNumber').textContent = `Q${q.question_number}`;
  document.getElementById('qMarks').textContent = `${q.marks || 1} mark${q.marks === 1 ? '' : 's'}`;

  const typeBadge = document.getElementById('qTypeBadge');
  const typeMap = { mcq:'MCQ', true_false:'True/False', fill_blank:'Fill in Blank', short_answer:'Short Answer', long_answer:'Long Answer' };
  typeBadge.textContent = typeMap[q.question_type] || 'Short Answer';

  document.getElementById('qText').textContent = q.question_text || '';

  // MCQ options
  const optDiv = document.getElementById('qOptions');
  if (q.question_type === 'mcq' && q.options) {
    optDiv.style.display = 'grid';
    optDiv.innerHTML = Object.entries(q.options).map(([k, v]) =>
      `<div class="q-option" onclick="selectMCQOption('${k}', this)">
        <span class="option-key">${k}</span>
        <span>${escapeHtml(v)}</span>
      </div>`
    ).join('');
    // Highlight if already answered
    if (answer) {
      const all = optDiv.querySelectorAll('.q-option');
      all.forEach(el => { if (el.querySelector('.option-key').textContent === answer.toUpperCase()) el.classList.add('selected'); });
    }
  } else {
    optDiv.style.display = 'none';
    optDiv.innerHTML = '';
  }

  // Answer display
  const ansDisplay = document.getElementById('answerDisplay');
  if (answer) {
    ansDisplay.innerHTML = `<span style="color:var(--success)">${escapeHtml(answer)}</span>`;
  } else if (status === 'skipped') {
    ansDisplay.innerHTML = `<span style="color:var(--warning)">Skipped</span>`;
  } else {
    ansDisplay.innerHTML = `<span class="answer-placeholder">Speak or type your answer…</span>`;
  }

  // Update nav grid highlighting
  // Note: we might not have 'progress' here if called from some places, 
  // but usually it's updated via handleCommandResponse
}

function selectMCQOption(key, el) {
  document.querySelectorAll('.q-option').forEach(o => o.classList.remove('selected'));
  el.classList.add('selected');
  // Auto-save MCQ selection
  saveAnswerDirectly(`Option ${key}`, 1.0);
}

/* ================================================================
   PROGRESS SIDEBAR
   ================================================================ */
function renderProgressSidebar(progress) {
  const grid = document.getElementById('questionNav');
  if (!progress || !progress.total) return;
  grid.innerHTML = '';
  const statuses = progress.question_statuses || {};
  
  for (let i = 1; i <= progress.total; i++) {
    const btn = document.createElement('button');
    btn.className = 'q-nav-btn';
    const status = statuses[String(i)] || 'unanswered';
    if (status !== 'unanswered') btn.classList.add(status);
    
    btn.textContent = i;
    btn.setAttribute('id', `qnav-${i}`);
    btn.setAttribute('aria-label', `Go to question ${i}, status: ${status}`);
    btn.onclick = () => goToQuestion(String(i));
    grid.appendChild(btn);
  }
  if (progress.current_q_number) {
    const cur = document.getElementById(`qnav-${progress.current_q_number}`);
    if (cur) cur.classList.add('current');
  }
}

function updateNavGrid(progress) {
  if (!progress || !progress.question_statuses) return;
  const statuses = progress.question_statuses;
  const currentNum = progress.current_q_number;

  for (let i = 1; i <= progress.total; i++) {
    const btn = document.getElementById(`qnav-${i}`);
    if (btn) {
      btn.classList.remove('current', 'answered', 'skipped');
      const status = statuses[String(i)] || 'unanswered';
      if (status !== 'unanswered') btn.classList.add(status);
      if (String(i) === String(currentNum)) btn.classList.add('current');
    }
  }
}

function updateProgressCounts(p) {
  if (!p) return;
  // Desktop elements
  const ansEl = document.getElementById('countAnswered');
  const skipEl = document.getElementById('countSkipped');
  const remEl = document.getElementById('countRemaining');
  if (ansEl) ansEl.textContent = p.answered || 0;
  if (skipEl) skipEl.textContent = p.skipped || 0;
  if (remEl) remEl.textContent = p.unanswered || 0;

  // Mobile elements
  const mobAnsEl = document.getElementById('mobileCountAnswered');
  const mobSkipEl = document.getElementById('mobileCountSkipped');
  const mobRemEl = document.getElementById('mobileCountRemaining');
  if (mobAnsEl) mobAnsEl.textContent = p.answered || 0;
  if (mobSkipEl) mobSkipEl.textContent = p.skipped || 0;
  if (mobRemEl) mobRemEl.textContent = p.unanswered || 0;
}

/* ================================================================
   TIMER
   ================================================================ */
function startTimer() {
  if (TIMER_INTERVAL) clearInterval(TIMER_INTERVAL);
  TIMER_INTERVAL = setInterval(() => {
    TIME_REMAINING = Math.max(0, TIME_REMAINING - 1);
    const m = Math.floor(TIME_REMAINING / 60);
    const s = TIME_REMAINING % 60;
    const timeStr = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    
    // Desktop Timer
    const display = document.getElementById('timerDisplay');
    if (display) display.textContent = timeStr;
    const box = document.getElementById('timerBox');
    if (box && TIME_REMAINING < 300) { box.classList.add('warning'); }

    // Mobile Timer
    const mobileDisplay = document.getElementById('mobileTimerDisplay');
    if (mobileDisplay) mobileDisplay.textContent = timeStr;
    const mobileBox = document.getElementById('mobileTimerBox');
    if (mobileBox && TIME_REMAINING < 300) { mobileBox.classList.add('warning'); }

    if (TIME_REMAINING === 0 && !SUBMITTED) { submitExam(); }
  }, 1000);
}

/* ================================================================
   MICROPHONE CAPTURE (16kHz PCM WAV for backend Vosk STT)
   ================================================================ */
let audioContext = null;
let mediaStreamSource = null;
let scriptProcessor = null;
let recordingChunks = [];
let sourceSampleRate = 44100;

// VAD variables
let silenceStart = 0;
let hasSpoken = false;
const SILENCE_THRESHOLD = 0.004; // Slightly less sensitive to background noise for faster silence detection
const SILENCE_DURATION = 1000;  // Reduced to 1000ms (1 second) for snappier response
const SILENCE_HINT_DURATION = 12000; // 12s before hinting

async function initSpeechRecognition() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, echoCancellation: true, noiseSuppression: true });
    // Some browsers ignore sampleRate constraint, so we must record at native rate and resample later
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    sourceSampleRate = audioContext.sampleRate;
    mediaStreamSource = audioContext.createMediaStreamSource(stream);
    scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    
    scriptProcessor.onaudioprocess = (e) => {
      // Mute output to prevent mic echo
      const outData = e.outputBuffer.getChannelData(0);
      for (let i = 0; i < outData.length; i++) outData[i] = 0;

      if (!LISTENING) return;
      
      const channelData = e.inputBuffer.getChannelData(0);
      // Copy float32 array
      recordingChunks.push(new Float32Array(channelData));
      
      // Compute RMS for Silence Detection
      let sum = 0;
      for (let i = 0; i < channelData.length; i++) {
        sum += channelData[i] * channelData[i];
      }
      const rms = Math.sqrt(sum / channelData.length);
      
      // BARGE-IN: If student starts talking while Agent is speaking
      if (ONBOARDING_STEP === 'none' && window.speechSynthesis.speaking && rms > BARGE_IN_THRESHOLD) {
        window.speechSynthesis.cancel();
        VoiceIndicator.setState('idle');
        if (!LISTENING) {
          // Force start listening immediately to capture the interruption
          setTimeout(() => toggleListening(), 0);
        }
        hasSpoken = true;
      }

      if (rms > SILENCE_THRESHOLD) {
        hasSpoken = true;
        silenceStart = 0;
      } else {
        if (silenceStart === 0) {
          silenceStart = Date.now();
        } else if (hasSpoken && (Date.now() - silenceStart > SILENCE_DURATION)) {
          // Auto-stop after speaking
          setTimeout(() => { if(LISTENING) toggleListening(); }, 0);
        } else if (!hasSpoken && (Date.now() - silenceStart > 15000)) {
          // Silence hint for blind users
          if (!SILENCE_HINT_TIMER) {
            SILENCE_HINT_TIMER = setTimeout(() => {
              if (LISTENING && !hasSpoken) {
                speakText("Still there? You can say repeat or speak your answer.", () => { if(!LISTENING) toggleListening(); });
              }
              SILENCE_HINT_TIMER = null;
            }, 100);
          }
          silenceStart = Date.now(); // reset
        }
      }
    };

    mediaStreamSource.connect(scriptProcessor);
    scriptProcessor.connect(audioContext.destination);
  } catch (err) {
    showToast('⚠ Microphone access denied.', 'error');
  }
}

function toggleListening() {
  if (!audioContext) { 
    initSpeechRecognition().then(() => { if(audioContext) toggleListening(); }); 
    return; 
  }
  
  if (LISTENING) {
    LISTENING = false;
    AudioEarcons.play('processing');
    if (ONBOARDING_STEP !== 'none') OnboardingVoiceIndicator.setState('processing');
    else VoiceIndicator.setState('processing');
    processRecordedAudio();
  } else {
    recordingChunks = [];
    hasSpoken = false;
    silenceStart = Date.now();
    LISTENING = true;
    AudioEarcons.play('mic_open');
    if (ONBOARDING_STEP !== 'none') OnboardingVoiceIndicator.setState('listening');
    else VoiceIndicator.setState('listening');
  }
}

async function processRecordedAudio() {
  if (recordingChunks.length === 0) {
    VoiceIndicator.setState('idle');
    return;
  }
  
  // Merge chunks
  const totalLength = recordingChunks.reduce((acc, val) => acc + val.length, 0);
  const result = new Float32Array(totalLength);
  let offset = 0;
  for (let c of recordingChunks) {
    result.set(c, offset);
    offset += c.length;
  }
  
  // Resample to 16kHz using OfflineAudioContext (high quality)
  const targetSampleRate = 16000;
  const audioBuffer = audioContext.createBuffer(1, totalLength, sourceSampleRate);
  audioBuffer.copyToChannel(result, 0);

  const offlineCtx = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(
    1, Math.ceil(audioBuffer.duration * targetSampleRate), targetSampleRate
  );
  const source = offlineCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(offlineCtx.destination);
  source.start(0);

  let resampled;
  try {
    const resampledBuffer = await offlineCtx.startRendering();
    resampled = resampledBuffer.getChannelData(0);
  } catch (err) {
    console.error("Resampling failed:", err);
    VoiceIndicator.setState('idle');
    return;
  }
  
  // Convert float32 to int16
  const pcm16 = new Int16Array(resampled.length);
  for (let i = 0; i < resampled.length; i++) {
    let s = Math.max(-1, Math.min(1, resampled[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  
  const wavBlob = createWavBlob(pcm16, targetSampleRate);
  const formData = new FormData();
  formData.append('audio', wavBlob);
  
  if (ONBOARDING_STEP !== 'none') {
    try {
      const res = await fetch(`${API}/transcribe`, { method: 'POST', body: formData });
      const data = await res.json();
      if (data.transcript) {
        VoiceIndicator.showTranscript(data.transcript, data.confidence);
        // Leverage LLM-cleaned ID if appropriate
        handleOnboardingTranscript(data.transcript, data.spoken_message);
      } else {
        speakText("I didn't catch that. Please say that again.", () => { if(!LISTENING) toggleListening(); });
      }
    } catch(err) {
      VoiceIndicator.setState('idle');
    }
    return;
  }
  
  formData.append('session_token', SESSION_TOKEN);
  
  try {
    const res = await fetch(`${API}/voice-command-audio`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    
    if (data.heard) {
       VoiceIndicator.showTranscript(data.heard, data.confidence);
    } else {
       VoiceIndicator.showTranscript("...", 0);
       // Also tell user we didn't catch it
       speakText("I didn't catch that. Please say that again.", () => { if(!LISTENING) toggleListening(); });
       return;
    }
    handleCommandResponse(data, data.heard || "", data.confidence || 0);
  } catch (err) {
    showToast('Network error processing audio.', 'error');
    VoiceIndicator.setState('idle');
  }
}

function createWavBlob(pcm16Array, sampleRate) {
  const buffer = new ArrayBuffer(44 + pcm16Array.length * 2);
  const view = new DataView(buffer);
  
  const writeString = (view, offset, string) => {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
  };
  
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + pcm16Array.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); 
  view.setUint16(22, 1, true); 
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); 
  view.setUint16(32, 2, true); 
  view.setUint16(34, 16, true); 
  writeString(view, 36, 'data');
  view.setUint32(40, pcm16Array.length * 2, true);
  
  let offset = 44;
  for (let i = 0; i < pcm16Array.length; i++, offset += 2) {
    view.setInt16(offset, pcm16Array[i], true);
  }
  
  return new Blob([view], { type: 'audio/wav' });
}

/* ================================================================
   VOICE PROCESSING
   ================================================================ */
async function processVoiceInput(transcript, confidence) {
  if (!transcript || !SESSION_TOKEN) return;

  // Check for navigation/control keywords even if an answer is pending
  // This allows the user to say "repeat question" or "status" while confirming.
  const lower = transcript.toLowerCase();
  
  if (PENDING_SUBMIT) {
    if (/\b(confirm|yes|correct|okay|save|affirmative|submit)\b/.test(lower)) {
      PENDING_SUBMIT = false;
      submitExam();
    } else if (/\b(no|cancel|wrong|again|stop|go back|continue)\b/.test(lower)) {
      PENDING_SUBMIT = false;
      speakText("Submission cancelled. Continuing your exam.");
    }
    return;
  }

  // If we have a pending answer confirmation, we STILL send to backend.
  // The backend CommandProcessor will decide if it's a Confirm/Repeat or a new Nav command.
  
  try {
    AudioEarcons.play('processing');
    const res = await fetch(`${API}/voice-command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_token: SESSION_TOKEN, transcript, confidence }),
    });
    const data = await res.json();
    handleCommandResponse(data, transcript, confidence);
  } catch (err) {
    showToast('API error: ' + err.message, 'error');
    VoiceIndicator.setState('idle');
  }
}

function handleCommandResponse(data, transcript, conf) {
  VoiceIndicator.setState('idle');

  // Time alert
  if (data.alert) VoiceIndicator.showAlert(data.alert);

  // Progress update
  if (data.progress) {
    updateProgressCounts(data.progress);
    updateNavGrid(data.progress);
  }

  const mainMessage = data.spoken_message || data.message;

  switch (data.action) {
    case 'navigate':
      AudioEarcons.play('success');
      if (data.question) {
        const existAns = data.answer || null;
        renderQuestion(data.question, existAns, existAns ? 'answered' : 'unanswered');
      }
      if (mainMessage) {
        speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      }
      if (data.progress) updateProgressCounts(data.progress);
      break;
    case 'end':
      speakText(mainMessage || 'No more questions in that direction.',
                () => { if (!LISTENING) toggleListening(); });
      if (data.question) renderQuestion(data.question, data.answer || null, data.answer ? 'answered' : 'unanswered');
      break;
    case 'repeat':
      if (mainMessage) speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      break;
    case 'skip':
      if (data.question) {
        renderQuestion(data.question, null, 'unanswered');
        if (mainMessage) speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      }
      break;
    case 'status':
      speakText(mainMessage || '', () => { if (!LISTENING) toggleListening(); });
      break;
    case 'slow_speech': {
      const slider = document.getElementById('speedSlider');
      if (slider) {
        slider.value = '0.6';
        updateSpeed('0.6');
      }
      speakText('Speaking slower now.', () => { if (!LISTENING) toggleListening(); });
      break;
    }
    case 'fast_speech': {
      const slider = document.getElementById('speedSlider');
      if (slider) {
        slider.value = '1.4';
        updateSpeed('1.4');
      }
      speakText('Speaking faster now.', () => { if (!LISTENING) toggleListening(); });
      break;
    }
    case 'review':
      if (mainMessage) speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      break;
    case 'submit':
      confirmSubmit();
      break;
    case 'submit_pending':
      PENDING_SUBMIT = true;
      VoiceIndicator.showTranscript('Awaiting submission confirmation...', 0.8);
      if (mainMessage) speakText(mainMessage);
      break;
    case 'answer_pending': {
      const interpretedAns = data.text || transcript;
      PENDING_ANSWER = interpretedAns;
      PENDING_CONF = conf;
      const confirmMsg = data.prompt || mainMessage || `I heard: "${interpretedAns}". Is that correct?`;
      // Update answer display preview
      const displayEl = document.getElementById('answerDisplay');
      if (displayEl && interpretedAns) {
        displayEl.innerHTML = `<span style="color:var(--warning);font-style:italic">&#8220;${escapeHtml(interpretedAns)}&#8221; &mdash; awaiting confirmation</span>`;
      }
      showConfirmPrompt(confirmMsg);
      // Highlight MCQ option if present
      if (data.choice_letter) {
        document.querySelectorAll('.q-option').forEach(el => {
          el.classList.remove('selected');
          const keyEl = el.querySelector('.option-key');
          if (keyEl && keyEl.textContent.trim() === data.choice_letter) {
            el.classList.add('selected');
          }
        });
      }
      break;
    }
    case 'answer_saved':
      AudioEarcons.play('success');
      PENDING_ANSWER = null;
      document.getElementById('confirmPrompt').style.display = 'none';
      if (data.answer || data.text) {
        const disp = document.getElementById('answerDisplay');
        if (disp) disp.innerHTML = `<span style="color:var(--success)">&#10004; ${escapeHtml(data.answer || data.text)}</span>`;
      }
      if (mainMessage) speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      break;
    case 'control':
      if (mainMessage) speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      break;
    case 'provide_help':
      speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      break;
    case 'confirm':
      AudioEarcons.play('success');
      PENDING_ANSWER = null;
      document.getElementById('confirmPrompt').style.display = 'none';
      if (mainMessage) speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      break;
    case 'change_answer':
      // Student rejected the pending answer — discard and ask to re-answer
      PENDING_ANSWER = null;
      PENDING_CONF = 0;
      document.getElementById('confirmPrompt').style.display = 'none';
      document.getElementById('answerDisplay').innerHTML = `<span class="answer-placeholder">Please say your answer again…</span>`;
      speakText(mainMessage || 'Please tell me your answer again.', () => { if (!LISTENING) toggleListening(); });
      break;
    case 'repeat_input':
      if (mainMessage) speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
      else speakText('Please repeat your answer.', () => { if (!LISTENING) toggleListening(); });
      break;
  }
}

/* ================================================================
   ANSWER MANAGEMENT
   ================================================================ */
function showConfirmPrompt(msg) {
  const prompt = document.getElementById('confirmPrompt');
  const text = document.getElementById('confirmText');
  if (prompt && text) {
    text.textContent = msg;
    prompt.style.display = 'block';
  }
  speakText(msg);

  const display = document.getElementById('answerDisplay');
  if (display && PENDING_ANSWER) {
    display.innerHTML = `<span style="color:var(--warning);font-style:italic">“${escapeHtml(PENDING_ANSWER)}” — awaiting confirmation</span>`;
  }
}

async function confirmAnswer() {
  document.getElementById('confirmPrompt').style.display = 'none';
  if (!PENDING_ANSWER) return;
  const answerToSave = PENDING_ANSWER;
  PENDING_ANSWER = null;
  PENDING_CONF = 0;

  const res = await fetch(`${API}/confirm-answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_token: SESSION_TOKEN, action: 'confirm' }),
  });
  const data = await res.json();

  AudioEarcons.play('success');
  const mainMessage = data.spoken_message || data.message || 'Answer saved.';

  if (data.action === 'navigate' && data.question) {
    // MCQ/TF: advance to next question and speak it
    renderQuestion(data.question, null, 'unanswered');
    speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
  } else if (data.action === 'answer_saved') {
    // QA/Descriptive: stay on question, update display, ask for edits
    const display = document.getElementById('answerDisplay');
    if (display) display.innerHTML = `<span style="color:var(--success)">✔ ${escapeHtml(data.answer || answerToSave)}</span>`;
    speakText(mainMessage, () => { if (!LISTENING) toggleListening(); });
  } else if (data.action === 'confirm') {
    // Last question confirmed
    speakText(mainMessage);
  } else {
    speakText(mainMessage);
  }

  if (data.progress) {
    updateProgressCounts(data.progress);
    updateNavGrid(data.progress);
  }
}

async function repeatAnswer() {
  document.getElementById('confirmPrompt').style.display = 'none';
  PENDING_ANSWER = null; PENDING_CONF = 0;
  document.getElementById('answerDisplay').innerHTML = `<span class="answer-placeholder">Please say your answer again…</span>`;
  speakText('Please tell me your answer again.', () => { if (!LISTENING) toggleListening(); });
}

async function saveAnswerDirectly(answerText, confidence) {
  // Get current question id from display
  const qNum = document.getElementById('qNumber').textContent.replace('Q', '');
  try {
    // We need question_id — fetch from server
    const statusRes = await fetch(`${API}/get-question/${SESSION_TOKEN}`);
    const statusData = await statusRes.json();
    const questionId = statusData.question?.id;
    if (!questionId) return;

    await fetch(`${API}/save-answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_token: SESSION_TOKEN, question_id: questionId, answer_text: answerText, confidence }),
    });
    const resData = await res.json();
    if (resData.progress) {
      updateProgressCounts(resData.progress);
      updateNavGrid(resData.progress);
    }
    const display = document.getElementById('answerDisplay');
    if (display) display.innerHTML = `<span style="color:var(--success)">✔ ${escapeHtml(answerText)}</span>`;
  } catch {}
}

/* ================================================================
   NAVIGATION — buttons call /navigate directly (no LLM)
   ================================================================ */
async function navigateNext()  { await sendNavigate('next'); }
async function navigatePrev()  { await sendNavigate('previous'); }
async function skipQuestion()  { await sendNavigate('skip'); }
async function goToQuestion(num) { await sendNavigate('goto', num); }

async function sendNavigate(action, target = null) {
  if (!SESSION_TOKEN) return;
  try {
    const res = await fetch(`${API}/navigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_token: SESSION_TOKEN, action, target }),
    });
    const data = await res.json();
    if (data.error) { speakText(data.error); return; }
    handleCommandResponse(data, '', 0);
  } catch (err) {
    console.error('Navigate error:', err);
  }
}

/* For voice-based navigation (called from handleCommandResponse 'command' case) */
async function sendNavCommand(cmd) {
  if (!SESSION_TOKEN) return;
  await processVoiceInput(cmd, 1.0);
}

/* ================================================================
   TTS (browser Web Speech)
   ================================================================ */
function speakText(text, onEndCallback = null) {
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'en-IN'; u.rate = parseFloat(document.getElementById('speedSlider')?.value || 1.0);
  u.volume = 1.0;
  
  if (LISTENING) {
     LISTENING = false; 
     if (audioContext && audioContext.state === 'running') {
        // Just let onaudioprocess stop naturally or force it
     }
  }

  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
  if (ONBOARDING_STEP !== 'none') OnboardingVoiceIndicator.setState('speaking');
  else VoiceIndicator.setState('speaking');

  u.onend = () => {
    if (ONBOARDING_STEP !== 'none') OnboardingVoiceIndicator.setState('idle');
    else VoiceIndicator.setState('idle');
    
    if (onEndCallback) {
      onEndCallback();
    } else if (!SUBMITTED) {
      // Auto-listen after system speaks (hands-free loop)
      if (!LISTENING) toggleListening();
    }
  };
}

async function readQuestionAloud(q) {
  if (!q) {
    // Fetch current
    try {
      const res = await fetch(`${API}/get-question/${SESSION_TOKEN}`);
      const data = await res.json();
      q = data.question;
    } catch { return; }
  }
  if (!q) return;
  let text = `Question number ${q.question_number}. ${q.question_text}`;
  if (q.question_type === 'mcq' && q.options) {
    text += ' The options are: ';
    Object.entries(q.options).forEach(([k, v]) => { text += `Option ${k}: ${v}. `; });
  }
  if (q.question_type === 'true_false') text = `True or False. ${q.question_text}`;
  speakText(text);
}

function readBackAnswer() {
  const el = document.getElementById('answerDisplay');
  const text = el?.textContent || 'No answer stored.';
  speakText('Your current answer is: ' + text);
}

function updateSpeed(val) {
  const label = document.getElementById('speedLabel');
  if (label) label.textContent = parseFloat(val).toFixed(1) + 'x';
}

/* ================================================================
   KEYBOARD FALLBACK
   ================================================================ */
/* ================================================================
   KEYBOARD & SHORTCUTS
   ================================================================ */
document.addEventListener('keydown', (e) => {
  // Global shortcuts (only if not typing in a textarea/input)
  if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;

  if (e.code === 'Space') {
    e.preventDefault();
    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
      // Skip current system talking and start listening for student answer
      if (!LISTENING) toggleListening();
    } else {
      // Normal toggle if nothing is playing
      toggleListening();
    }
  }

  if (e.key.toLowerCase() === 'r') {
    readQuestionAloud();
  }
});

function toggleKeyboard() {
  const kbd = document.getElementById('keyboardAnswer');
  const btn = document.getElementById('keyboardToggle');
  const saveBtn = document.getElementById('saveKbdBtn');
  const badge = document.getElementById('answerMethodBadge');
  if (kbd.classList.contains('hidden')) {
    kbd.classList.remove('hidden'); btn.textContent = '🎙 Voice Instead';
    saveBtn.style.display = 'inline'; badge.textContent = '⌨️ Keyboard';
  } else {
    kbd.classList.add('hidden'); btn.textContent = '⌨️ Type Instead';
    saveBtn.style.display = 'none'; badge.textContent = '🎙 Voice';
  }
}

async function saveKeyboardAnswer() {
  const text = document.getElementById('keyboardAnswer')?.value?.trim();
  if (!text) { showToast('Please type an answer first', 'warning'); return; }
  await saveAnswerDirectly(text, 1.0);
  showToast('✅ Answer saved', 'success');
}

/* ================================================================
   SUBMIT
   ================================================================ */
function confirmSubmit() {
  fetch(`${API}/status/${SESSION_TOKEN}`)
    .then(r => r.json())
    .then(data => {
      const statsText = `You have answered ${data.answered} out of ${data.total} questions, and skipped ${data.skipped}. Are you sure you want to submit? Say yes to confirm or no to go back.`;
      speakText(statsText);
      const stats = document.getElementById('modalStats');
      if (stats) stats.innerHTML = `
        <div>Answered: <b>${data.answered}</b> / ${data.total}</div>
        <div>Skipped: <b>${data.skipped}</b></div>
        <div>Not answered: <b>${data.unanswered}</b></div>
      `;
      document.getElementById('submitModal').style.display = 'flex';
    })
    .catch(() => document.getElementById('submitModal').style.display = 'flex');
}

function closeModal() {
  document.getElementById('submitModal').style.display = 'none';
}

async function submitExam() {
  closeModal();
  if (SUBMITTED) return;
  SUBMITTED = true;
  LISTENING = false;
  if (TIMER_INTERVAL) clearInterval(TIMER_INTERVAL);
  
  document.getElementById('successOverlay').style.display = 'flex';
  document.getElementById('successMsg').textContent = 'Processing your answers and generating PDF…';

  try {
    const res = await fetch(`${API}/submit-exam`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_token: SESSION_TOKEN }),
    });
    const data = await res.json();

    if (data.pdf_ready) {
      document.getElementById('successMsg').textContent = '🎉 Exam submitted! Your answer PDF is ready.';
      const link = document.getElementById('downloadLink');
      link.href = `/api${data.pdf_download_url}`;
      document.getElementById('downloadActions').style.display = 'block';
    }
    localStorage.removeItem('vp_session_token');
    speakText('Exam submitted successfully. Please download your answer PDF.');
  } catch (err) {
    document.getElementById('successMsg').textContent = 'Submission error: ' + err.message;
  }
}

/* ================================================================
   LOCKDOWN MODE
   ================================================================ */
function initLockdown() {
  // Global Interruption Hotkey (Spacebar)
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space') {
      e.preventDefault();
      // Interrupt TTS
      if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
        VoiceIndicator.setState('idle');
      }
      // Toggle Mic
      if (!LISTENING) {
        toggleListening();
      }
    }
  });

  // Block context menu
  document.addEventListener('contextmenu', preventAction);
  // Detect visibility change (tab switch)
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && !SUBMITTED) {
      document.getElementById('lockdownOverlay').style.display = 'flex';
    }
  });
  // Block copy/cut
  document.addEventListener('copy', preventAction);
  document.addEventListener('cut', preventAction);
  // Warn on page unload
  window.addEventListener('beforeunload', (e) => {
    if (!SUBMITTED) {
      e.preventDefault();
      e.returnValue = 'Your exam is in progress. Are you sure you want to leave?';
    }
  });
}

function preventAction(e) {
  if (!SUBMITTED) { e.preventDefault(); return false; }
}

function dismissLockdown() {
  document.getElementById('lockdownOverlay').style.display = 'none';
}

/* ================================================================
   UTILITIES
   ================================================================ */
function showToast(msg, type = 'info') {
  const colors = { info:'rgba(79,142,247,0.15)', success:'rgba(16,185,129,0.12)', warning:'rgba(245,158,11,0.12)', error:'rgba(239,68,68,0.15)' };
  const bcolors = { info:'rgba(79,142,247,0.5)', success:'rgba(16,185,129,0.4)', warning:'rgba(245,158,11,0.4)', error:'rgba(239,68,68,0.5)' };
  const icons = { info:'ℹ', success:'✅', warning:'⚠️', error:'❌' };
  const el = document.createElement('div');
  el.style.cssText = `position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%);background:${colors[type]};border:1px solid ${bcolors[type]};color:var(--text);padding:0.7rem 1.5rem;border-radius:12px;font-size:0.88rem;z-index:9999;font-weight:500;backdrop-filter:blur(16px);max-width:400px;text-align:center;`;
  el.textContent = `${icons[type]} ${msg}`;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

/* ================================================================
   ONBOARDING VOICE INDICATOR (Helper for UI animations)
   ================================================================ */
const OnboardingVoiceIndicator = {
  orb: null,
  mic: null,
  status: null,
  init() {
    this.orb = document.getElementById('onboardingOrb');
    this.mic = this.orb?.querySelector('.voice-mic');
    this.status = document.getElementById('onboardingVoiceStatus');
  },
  setState(state) {
    if (!this.orb) this.init();
    if (!this.orb) return;
    this.orb.classList.remove('listening', 'processing');
    
    switch (state) {
      case 'listening':
        this.orb.classList.add('listening');
        if (this.mic) this.mic.textContent = '🔴';
        if (this.status) { this.status.textContent = 'Listening...'; this.status.style.color = 'var(--danger)'; }
        break;
      case 'processing':
        this.orb.classList.add('processing');
        if (this.mic) this.mic.textContent = '⚙️';
        if (this.status) { this.status.textContent = 'Processing...'; this.status.style.color = 'var(--success)'; }
        break;
      case 'speaking':
        if (this.mic) this.mic.textContent = '🔊';
        if (this.status) { this.status.textContent = 'Speaking...'; this.status.style.color = 'var(--primary-light)'; }
        break;
      default:
        if (this.mic) this.mic.textContent = '🎙';
        if (this.status) { this.status.textContent = 'Ready'; this.status.style.color = 'var(--text-sub)'; }
    }
  }
};
