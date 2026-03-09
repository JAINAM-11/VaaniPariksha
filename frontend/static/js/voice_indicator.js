/**
 * VaaniPariksha - Voice Indicator Animation
 * Handles the voice orb visual states.
 */

const VoiceIndicator = {
  orb: null,
  mic: null,
  status: null,

  init() {
    this.orb = document.getElementById('voiceOrb');
    this.mic = document.getElementById('voiceMic');
    this.status = document.getElementById('voiceStatus');
  },

  setState(state) {
    // state: 'idle' | 'listening' | 'processing' | 'speaking'
    if (!this.orb) return;
    this.orb.classList.remove('listening', 'processing');

    switch (state) {
      case 'listening':
        this.orb.classList.add('listening');
        this.mic.textContent = '🔴';
        this.status.textContent = 'Listening…';
        this.status.style.color = 'var(--danger)';
        break;
      case 'processing':
        this.orb.classList.add('processing');
        this.mic.textContent = '⚙️';
        this.status.textContent = 'Processing…';
        this.status.style.color = 'var(--success)';
        break;
      case 'speaking':
        this.mic.textContent = '🔊';
        this.status.textContent = 'Speaking…';
        this.status.style.color = 'var(--primary-light)';
        break;
      default:
        this.mic.textContent = '🎙';
        this.status.textContent = 'Click to speak';
        this.status.style.color = 'var(--text-sub)';
    }
  },

  showTranscript(text, confidence) {
    const el = document.getElementById('voiceTranscript');
    const wrap = document.getElementById('confidenceWrap');
    const bar = document.getElementById('confidenceBar');
    const label = document.getElementById('confidenceLabel');

    if (el) el.textContent = text || '—';
    if (wrap && confidence !== undefined) {
      wrap.style.display = 'block';
      const pct = Math.round(confidence * 100);
      bar.style.width = pct + '%';
      bar.style.background = pct >= 75 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)';
      label.textContent = `Confidence: ${pct}%`;
    } else if (wrap) {
      wrap.style.display = 'none';
    }
  },

  showAlert(msg) {
    const el = document.createElement('div');
    el.style.cssText = 'position:fixed;top:5rem;left:50%;transform:translateX(-50%);background:rgba(245,158,11,0.15);border:1px solid rgba(245,158,11,0.5);color:#f59e0b;padding:0.7rem 1.5rem;border-radius:12px;font-size:0.9rem;z-index:999;font-weight:600;text-align:center;max-width:400px;';
    el.textContent = '⏰ ' + msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 6000);
  },
};

window.VoiceIndicator = VoiceIndicator;
document.addEventListener('DOMContentLoaded', () => VoiceIndicator.init());
