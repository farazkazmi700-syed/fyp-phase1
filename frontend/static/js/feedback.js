'use strict';

const feedbackPage = {
  currentMessageId: null,
  currentSessionId: null,
  selectedRating: 0,
  selectedCorrectness: null,
  selectedLength: null,

  init() {
    const params = new URLSearchParams(window.location.search);
    feedbackPage.currentMessageId = params.get('message_id');
    feedbackPage.currentSessionId = params.get('session_id');

    const errorEl = document.getElementById('feedback-error');
    const statusEl = document.getElementById('feedback-status');
    const panel = document.getElementById('feedback-panel');

    if (!feedbackPage.currentMessageId) {
      errorEl.textContent = 'Open this feedback page by clicking Rate on an AI response in the chat page.';
      panel.style.opacity = '0.5';
      panel.style.pointerEvents = 'none';
      document.getElementById('btn-submit-feedback').disabled = true;
      return;
    }

    errorEl.textContent = '';
    panel.style.opacity = '1';
    panel.style.pointerEvents = 'auto';

    document.querySelectorAll('.star').forEach(star => {
      star.addEventListener('click', () => {
        feedbackPage.setRating(parseInt(star.dataset.value, 10));
      });
    });

    document.querySelectorAll('#correctness-group .toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#correctness-group .toggle-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        feedbackPage.selectedCorrectness = btn.dataset.value;
      });
    });

    document.querySelectorAll('#length-group .toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#length-group .toggle-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        feedbackPage.selectedLength = btn.dataset.value;
      });
    });

    document.getElementById('btn-submit-feedback').addEventListener('click', async () => {
      await feedbackPage.submit();
    });
  },

  setRating(value) {
    feedbackPage.selectedRating = value;
    document.querySelectorAll('.star').forEach(star => {
      star.classList.toggle('active', parseInt(star.dataset.value, 10) <= value);
    });
  },

  async submit() {
    const statusEl = document.getElementById('feedback-status');
    statusEl.textContent = '';
    statusEl.className = 'feedback-status';

    if (!feedbackPage.selectedRating) {
      statusEl.textContent = 'Please select a star rating.';
      statusEl.className = 'feedback-status error';
      return;
    }
    if (!feedbackPage.selectedCorrectness) {
      statusEl.textContent = 'Please select a correctness option.';
      statusEl.className = 'feedback-status error';
      return;
    }
    if (!feedbackPage.selectedLength) {
      statusEl.textContent = 'Please select a length option.';
      statusEl.className = 'feedback-status error';
      return;
    }

    const payload = {
      message_id: feedbackPage.currentMessageId,
      session_id: feedbackPage.currentSessionId || null,
      rating: feedbackPage.selectedRating,
      correctness: feedbackPage.selectedCorrectness,
      length_rating: feedbackPage.selectedLength,
      comment: document.getElementById('feedback-comment').value.trim() || null,
    };

    try {
      const res = await fetch('/feedback/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      statusEl.textContent = '✅ Feedback saved. Thank you!';
      statusEl.className = 'feedback-status';
    } catch (err) {
      statusEl.textContent = `❌ ${err.message}`;
      statusEl.className = 'feedback-status error';
    }
  },
};

document.addEventListener('DOMContentLoaded', () => feedbackPage.init());
