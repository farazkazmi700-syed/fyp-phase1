'use strict';

const api = {
  async sendMessage(content, sessionId) {
    const res = await fetch('/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ content, session_id: sessionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async getSessions() {
    const res = await fetch('/chat/sessions', { credentials: 'include' });
    if (!res.ok) throw new Error('Failed to load sessions');
    return res.json();
  },

  async getHistory(sessionId) {
    const res = await fetch(`/chat/history/${sessionId}`, { credentials: 'include' });
    if (!res.ok) throw new Error('Failed to load history');
    return res.json();
  },

  async deleteSession(sessionId) {
    const res = await fetch(`/chat/session/${sessionId}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    if (!res.ok) throw new Error('Failed to delete session');
    return res.json();
  },

  async submitLogoutFeedback(payload) {
    const res = await fetch('/feedback/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Logout feedback failed');
    }
    return res.json();
  },

  async checkHealth() {
    const res = await fetch('/analytics/health', { credentials: 'include' });
    return res.json();
  },
};

const ui = {
  escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  },

  formatTime(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  },

  renderSessions(sessions = []) {
    const list = document.getElementById('session-list');
    if (!sessions.length) {
      list.innerHTML = '<div class="empty-sessions">No chats yet. Start a new one!</div>';
      return;
    }

    list.innerHTML = sessions.map(session => `
      <div class="session-item ${session.session_id === app.currentSessionId ? 'active' : ''}" data-id="${session.session_id}">
        <div class="session-info">
          <div class="session-title">${ui.escapeHtml(session.title || 'New Chat')}</div>
          <div class="session-meta">${session.message_count || 0} messages</div>
        </div>
        <button class="session-delete" title="Delete chat">x</button>
      </div>
    `).join('');

    list.querySelectorAll('.session-item').forEach(item => {
      item.addEventListener('click', () => app.loadSession(item.dataset.id));
      item.querySelector('.session-delete').addEventListener('click', event => {
        event.stopPropagation();
        app.deleteSession(item.dataset.id);
      });
    });
  },

  appendMessage(role, content, messageId, timestamp) {
    const welcome = document.getElementById('welcome-message');
    if (welcome) welcome.remove();

    const container = document.getElementById('messages-container');
    const message = document.createElement('div');
    message.className = `message ${role}`;
    if (messageId) message.dataset.msgId = messageId;

    const isAssistant = role === 'assistant';
    message.innerHTML = `
      <div class="msg-avatar">${isAssistant ? 'AI' : 'You'}</div>
      <div class="msg-content">
        <div class="msg-bubble">${ui.escapeHtml(content).replaceAll('\n', '<br>')}</div>
        <div class="msg-meta">
          <span>${ui.formatTime(timestamp)}</span>
          ${isAssistant && messageId ? `<button class="btn-feedback-trigger" data-id="${messageId}">Feedback</button>` : ''}
        </div>
      </div>
    `;

    const feedbackBtn = message.querySelector('.btn-feedback-trigger');
    if (feedbackBtn) {
      feedbackBtn.addEventListener('click', () => feedback.open(feedbackBtn.dataset.id));
    }

    container.appendChild(message);
    container.scrollTop = container.scrollHeight;
  },

  showTyping() {
    const container = document.getElementById('messages-container');
    const typing = document.createElement('div');
    typing.className = 'message assistant typing-indicator';
    typing.id = 'typing-indicator';
    typing.innerHTML = `
      <div class="msg-avatar">AI</div>
      <div class="msg-content">
        <div class="msg-bubble">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    `;
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
  },

  hideTyping() {
    document.getElementById('typing-indicator')?.remove();
  },

  setTitle(title) {
    document.getElementById('current-session-title').textContent = title || 'New Chat';
  },

  setConnectionStatus(online, text) {
    const dot = document.querySelector('.status-dot');
    const label = document.querySelector('.status-text');
    dot.className = `status-dot ${online ? 'online' : 'offline'}`;
    label.textContent = text;
  },
};

const feedback = {
  open(messageId) {
    const sessionParam = app.currentSessionId ? `&session_id=${encodeURIComponent(app.currentSessionId)}` : '';
    window.location.href = `/feedback?message_id=${encodeURIComponent(messageId)}${sessionParam}`;
  },
};

const app = {
  currentSessionId: null,
  isLoading: false,
  logoutRating: 0,

  async init() {
    app.bindEvents();
    await app.loadSessions();
    await app.checkConnection();
    app.autoResizeInput();
  },

  bindEvents() {
    document.getElementById('btn-send').addEventListener('click', app.handleSend);
    document.getElementById('btn-new-chat').addEventListener('click', app.startNewChat);
    document.getElementById('btn-sidebar-toggle').addEventListener('click', () => {
      document.getElementById('sidebar').classList.toggle('collapsed');
    });

    document.getElementById('message-input').addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        app.handleSend();
      }
    });

    document.getElementById('btn-logout')?.addEventListener('click', app.handleLogoutPrompt);
    document.getElementById('logout-submit-feedback')?.addEventListener('click', app.handleLogoutSubmit);
    document.getElementById('logout-skip')?.addEventListener('click', app.handleLogoutSkip);
    document.getElementById('logout-modal-close')?.addEventListener('click', app.closeLogoutModal);

    document.querySelectorAll('#logout-star-rating .star').forEach(star => {
      star.addEventListener('click', () => app.setLogoutRating(Number(star.dataset.value)));
    });
  },

  autoResizeInput() {
    const input = document.getElementById('message-input');
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
    });
  },

  async handleSend() {
    const input = document.getElementById('message-input');
    const content = input.value.trim();
    if (!content || app.isLoading) return;

    app.isLoading = true;
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('btn-send').disabled = true;
    ui.appendMessage('user', content, null, new Date().toISOString());
    ui.showTyping();

    try {
      const result = await api.sendMessage(content, app.currentSessionId);
      app.currentSessionId = result.session_id;
      ui.hideTyping();
      ui.appendMessage('assistant', result.response, result.message_id, result.timestamp);
      await app.loadSessions();
    } catch (err) {
      ui.hideTyping();
      ui.appendMessage('assistant', `Error: ${err.message}. Please try again.`, null, new Date().toISOString());
    } finally {
      app.isLoading = false;
      document.getElementById('btn-send').disabled = false;
      input.focus();
    }
  },

  async loadSessions() {
    try {
      const data = await api.getSessions();
      ui.renderSessions(data.sessions || []);
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  },

  async loadSession(sessionId) {
    if (sessionId === app.currentSessionId) return;

    try {
      const data = await api.getHistory(sessionId);
      app.currentSessionId = sessionId;

      const container = document.getElementById('messages-container');
      container.innerHTML = '';
      (data.messages || []).forEach(msg => {
        ui.appendMessage(msg.role, msg.content, msg.id, msg.timestamp);
      });

      const sessionData = await api.getSessions();
      const session = (sessionData.sessions || []).find(item => item.session_id === sessionId);
      ui.setTitle(session?.title || 'Chat');
      ui.renderSessions(sessionData.sessions || []);
    } catch (err) {
      console.error('Failed to load session:', err);
    }
  },

  startNewChat() {
    app.currentSessionId = null;
    document.getElementById('messages-container').innerHTML = `
      <div class="welcome-message" id="welcome-message">
        <div class="welcome-icon">AI</div>
        <h2>New Chat</h2>
        <p>Ask me anything - I will remember the conversation.</p>
        <div class="suggestion-chips">
          <button class="chip" onclick="app.sendSuggestion('Explain machine learning in simple terms')">Machine learning</button>
          <button class="chip" onclick="app.sendSuggestion('Write a Python hello world program')">Python code</button>
          <button class="chip" onclick="app.sendSuggestion('Give me 3 tips for better writing')">Writing tips</button>
        </div>
      </div>
    `;
    ui.setTitle('New Chat');
    app.loadSessions();
    document.getElementById('message-input').focus();
  },

  async deleteSession(sessionId) {
    if (!confirm('Delete this conversation? This cannot be undone.')) return;
    try {
      await api.deleteSession(sessionId);
      if (app.currentSessionId === sessionId) app.startNewChat();
      await app.loadSessions();
    } catch (err) {
      alert(`Failed to delete: ${err.message}`);
    }
  },

  sendSuggestion(text) {
    document.getElementById('message-input').value = text;
    app.handleSend();
  },

  async checkConnection() {
    try {
      const result = await api.checkHealth();
      ui.setConnectionStatus(result.status === 'ok', result.status === 'ok' ? 'Connected' : 'AI Offline');
    } catch {
      ui.setConnectionStatus(false, 'No Connection');
    }
  },

  handleLogoutPrompt(event) {
    event.preventDefault();
    app.openLogoutModal();
  },

  openLogoutModal() {
    const modal = document.getElementById('logout-feedback-modal');
    modal.classList.add('visible');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    app.setLogoutRating(0);
    document.getElementById('logout-feedback-comment').value = '';
    document.getElementById('logout-feedback-status').textContent = '';
  },

  closeLogoutModal() {
    const modal = document.getElementById('logout-feedback-modal');
    modal.classList.remove('visible');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  },

  setLogoutRating(value) {
    app.logoutRating = value;
    document.querySelectorAll('#logout-star-rating .star').forEach(star => {
      star.classList.toggle('active', Number(star.dataset.value) <= value);
    });
  },

  async handleLogoutSubmit() {
    const status = document.getElementById('logout-feedback-status');
    status.textContent = '';
    status.className = 'feedback-status';

    if (!app.logoutRating) {
      status.textContent = 'Please select a rating before submitting.';
      status.className = 'feedback-status error';
      return;
    }

    try {
      await api.submitLogoutFeedback({
        rating: app.logoutRating,
        comment: document.getElementById('logout-feedback-comment').value.trim() || null,
      });
      status.textContent = 'Thanks for your feedback. Logging out...';
      setTimeout(() => {
        window.location.href = '/auth/logout';
      }, 500);
    } catch (err) {
      status.textContent = err.message;
      status.className = 'feedback-status error';
    }
  },

  handleLogoutSkip(event) {
    event.preventDefault();
    window.location.href = '/auth/logout';
  },
};

window.app = app;

document.addEventListener('DOMContentLoaded', () => app.init());
