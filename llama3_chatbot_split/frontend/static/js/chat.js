let currentSessionId = null;

const messages = document.getElementById('messages');
const form = document.getElementById('chatForm');
const input = document.getElementById('messageInput');
const newChatBtn = document.getElementById('newChatBtn');

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = `${role}: ${content}`;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

async function loadSessions() {
  const res = await fetch('/chat/sessions');
  const data = await res.json();
  const box = document.getElementById('sessions');
  box.innerHTML = '';
  data.sessions.forEach(s => {
    const btn = document.createElement('button');
    btn.textContent = s.title;
    btn.onclick = () => loadHistory(s.session_id);
    box.appendChild(btn);
  });
}

async function loadHistory(sessionId) {
  currentSessionId = sessionId;
  messages.innerHTML = '';
  const res = await fetch(`/chat/history/${sessionId}`);
  const data = await res.json();
  data.messages.forEach(m => addMessage(m.role, m.content));
}

newChatBtn.onclick = () => {
  currentSessionId = null;
  messages.innerHTML = '';
};

form.onsubmit = async (e) => {
  e.preventDefault();
  const content = input.value.trim();
  if (!content) return;

  addMessage('user', content);
  input.value = '';

  const res = await fetch('/chat/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, session_id: currentSessionId })
  });
  const data = await res.json();
  if (data.error) {
    addMessage('assistant', data.error);
    return;
  }
  currentSessionId = data.session_id;
  addMessage('assistant', data.response);
  loadSessions();
};

loadSessions();
