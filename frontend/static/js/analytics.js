'use strict';

const analyticsPage = {
  async init() {
    const container = document.getElementById('analytics-content');
    try {
      const [statsRes, graphsRes, feedbackRes] = await Promise.all([
        fetch('/analytics/stats', { credentials: 'include' }),
        fetch('/analytics/graphs', { credentials: 'include' }),
        fetch('/feedback/list', { credentials: 'include' }),
      ]);

      const statsData = await analyticsPage.readJson(statsRes, 'analytics stats');
      const graphsData = await analyticsPage.readJson(graphsRes, 'analytics charts');
      const feedbackData = await analyticsPage.readJson(feedbackRes, 'feedback history');

      if (!statsRes.ok) {
        throw new Error(statsData.error || 'Failed to load analytics stats');
      }
      if (!graphsRes.ok) {
        throw new Error(graphsData.error || 'Failed to load analytics charts');
      }
      if (!feedbackRes.ok) {
        throw new Error(feedbackData.error || 'Failed to load feedback history');
      }

      container.innerHTML = analyticsPage.render(statsData, graphsData, feedbackData);
      analyticsPage.renderTopicPlot(graphsData.topic_plot);
    } catch (err) {
      container.innerHTML = `<div class="loading-spinner">❌ ${err.message}</div>`;
      console.error('Analytics page error:', err);
    }
  },

  async readJson(response, label) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return response.json();
    }

    const text = await response.text();
    const detail = text.trim().startsWith('<')
      ? 'server returned an HTML error page'
      : text.slice(0, 120);
    throw new Error(`Failed to load ${label}: ${detail}`);
  },

  renderTopicPlot(plotData) {
    const target = document.getElementById('topic-plot');
    if (!target || !plotData) return;

    if (!window.Plotly) {
      target.innerHTML = '<div class="feedback-empty">Interactive topic chart is unavailable.</div>';
      return;
    }

    window.Plotly.newPlot(target, plotData.data, plotData.layout, {
      displayModeBar: false,
      responsive: true,
    });
  },

  escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value ?? '';
    return div.innerHTML;
  },

  render(stats, graphs, feedbackData) {
    const messageFeedback = feedbackData.feedback || [];
    const logoutFeedback = feedbackData.logout_feedback || [];

    return `
      <div class="analytics-panel">
        <div class="stat-card">
          <h4>Total Messages</h4>
          <div class="stat-value">${stats.total_messages || 0}</div>
          <div class="stat-sub">${stats.user_messages || 0} sent · ${stats.assistant_messages || 0} received</div>
        </div>
        <div class="stat-card">
          <h4>Sessions</h4>
          <div class="stat-value">${stats.total_sessions || 0}</div>
          <div class="stat-sub">${stats.messages_last_7_days || 0} messages last 7 days</div>
        </div>
        <div class="stat-card">
          <h4>Average Rating</h4>
          <div class="stat-value">${stats.avg_rating ?? '—'} ⭐</div>
          <div class="stat-sub">${stats.total_feedback || 0} feedback entries</div>
        </div>
        <div class="stat-card">
          <h4>Top Topic</h4>
          <div class="stat-value stat-value-text">${analyticsPage.escapeHtml(stats.top_topic || 'No topic data')}</div>
          <div class="stat-sub">${stats.avg_messages_per_session || 0} avg messages per session</div>
        </div>

        <div class="analytics-charts">
          <div>
            <p style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">Daily Activity</p>
            <img class="chart-img" src="${graphs.daily_activity}" alt="Daily Activity" />
          </div>
          <div>
            <p style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">Response Correctness</p>
            <img class="chart-img" src="${graphs.correctness_pie}" alt="Correctness" />
          </div>
          <div>
            <p style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">Rating Distribution</p>
            <img class="chart-img" src="${graphs.rating_dist}" alt="Rating Distribution" />
          </div>
          <div class="plotly-card">
            <p style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">Topic Classification</p>
            <div id="topic-plot" class="topic-plot"></div>
          </div>
        </div>
      </div>

      <section class="feedback-history">
        <h2>All submitted feedback</h2>
        <div class="feedback-grid">
          <div class="feedback-block">
            <h3>Message Feedback</h3>
            ${messageFeedback.length ? messageFeedback.map(entry => analyticsPage.renderMessageFeedback(entry)).join('') : '<div class="feedback-empty">No message feedback submitted yet.</div>'}
          </div>
          <div class="feedback-block">
            <h3>Logout Feedback</h3>
            ${logoutFeedback.length ? logoutFeedback.map(entry => analyticsPage.renderLogoutFeedback(entry)).join('') : '<div class="feedback-empty">No logout feedback yet.</div>'}
          </div>
        </div>
      </section>
    `;
  },

  renderMessageFeedback(entry) {
    const comment = entry.comment ? analyticsPage.escapeHtml(entry.comment) : '<em>No comment</em>';

    return `
      <div class="feedback-row">
        <div class="feedback-meta"><strong>${entry.rating} ⭐</strong> • ${entry.correctness.replace('_', ' ')} • ${entry.length_rating.replace('_', ' ')}</div>
        <div class="feedback-text">${comment}</div>
        <div class="feedback-ts">${new Date(entry.submitted_at).toLocaleString()}</div>
      </div>
    `;
  },

  renderLogoutFeedback(entry) {
    const comment = entry.comment ? analyticsPage.escapeHtml(entry.comment) : '<em>No comment</em>';

    return `
      <div class="feedback-row">
        <div class="feedback-meta"><strong>${entry.rating} ⭐</strong></div>
        <div class="feedback-text">${comment}</div>
        <div class="feedback-ts">${new Date(entry.submitted_at).toLocaleString()}</div>
      </div>
    `;
  },
};

document.addEventListener('DOMContentLoaded', () => analyticsPage.init());
