'use strict';

const analyticsPage = {
  topicPlotData: null,

  async init() {
    const container = document.getElementById('analytics-content');
    analyticsPage.bindGraphZoom();
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
      analyticsPage.topicPlotData = graphsData.topic_plot;
      analyticsPage.renderTopicPlot(graphsData.topic_plot);
      analyticsPage.bindChartCards();
    } catch (err) {
      container.innerHTML = `
        <div class="analytics-empty-state">
          <strong>Analytics could not be loaded</strong>
          <span>${analyticsPage.escapeHtml(err.message)}</span>
        </div>
      `;
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

  bindGraphZoom() {
    const overlay = document.getElementById('graph-zoom-overlay');
    const closeBtn = document.getElementById('graph-zoom-close');
    if (!overlay || !closeBtn) return;

    closeBtn.addEventListener('click', analyticsPage.closeGraphZoom);
    overlay.addEventListener('click', event => {
      if (event.target === overlay) {
        analyticsPage.closeGraphZoom();
      }
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && overlay.classList.contains('visible')) {
        analyticsPage.closeGraphZoom();
      }
    });
  },

  bindChartCards() {
    document.querySelectorAll('.chart-card').forEach(card => {
      card.addEventListener('click', () => analyticsPage.openGraphZoom(card));
      card.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          analyticsPage.openGraphZoom(card);
        }
      });
    });
  },

  openGraphZoom(card) {
    const overlay = document.getElementById('graph-zoom-overlay');
    const body = document.getElementById('graph-zoom-body');
    const title = document.getElementById('graph-zoom-title');
    if (!overlay || !body || !title) return;

    const chartTitle = card.dataset.chartTitle || 'Graph Preview';
    title.textContent = chartTitle;
    body.innerHTML = '';

    if (card.dataset.chartType === 'plotly') {
      const plotTarget = document.createElement('div');
      plotTarget.className = 'graph-zoom-plot';
      body.appendChild(plotTarget);
      overlay.classList.add('visible');
      overlay.setAttribute('aria-hidden', 'false');

      if (window.Plotly && analyticsPage.topicPlotData) {
        const layout = {
          ...analyticsPage.topicPlotData.layout,
          height: 520,
          margin: { l: 56, r: 28, t: 24, b: 56 },
        };
        window.Plotly.newPlot(plotTarget, analyticsPage.topicPlotData.data, layout, {
          displayModeBar: false,
          responsive: true,
        });
      }
      return;
    }

    const img = card.querySelector('.chart-img');
    if (!img) return;

    const zoomImg = document.createElement('img');
    zoomImg.src = img.src;
    zoomImg.alt = img.alt;
    zoomImg.className = 'graph-zoom-img';
    body.appendChild(zoomImg);
    overlay.classList.add('visible');
    overlay.setAttribute('aria-hidden', 'false');
  },

  closeGraphZoom() {
    const overlay = document.getElementById('graph-zoom-overlay');
    const body = document.getElementById('graph-zoom-body');
    if (!overlay || !body) return;

    overlay.classList.remove('visible');
    overlay.setAttribute('aria-hidden', 'true');
    body.innerHTML = '';
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
      <section class="analytics-panel" aria-label="Analytics summary">
        <div class="stat-card stat-card-featured">
          <div class="stat-icon">01</div>
          <h4>Total Messages</h4>
          <div class="stat-value">${stats.total_messages || 0}</div>
          <div class="stat-sub">${stats.user_messages || 0} sent / ${stats.assistant_messages || 0} received</div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">02</div>
          <h4>Sessions</h4>
          <div class="stat-value">${stats.total_sessions || 0}</div>
          <div class="stat-sub">${stats.messages_last_7_days || 0} messages last 7 days</div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">03</div>
          <h4>Average Rating</h4>
          <div class="stat-value">${stats.avg_rating ?? '--'} / 5</div>
          <div class="stat-sub">${stats.total_feedback || 0} feedback entries</div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">04</div>
          <h4>Top Topic</h4>
          <div class="stat-value stat-value-text">${analyticsPage.escapeHtml(stats.top_topic || 'No topic data')}</div>
          <div class="stat-sub">${stats.avg_messages_per_session || 0} avg messages per session</div>
        </div>
      </section>

      <section class="analytics-section">
        <div class="section-heading">
          <span>Visual insights</span>
          <h2>Conversation Trends</h2>
        </div>
        <div class="analytics-charts">
          <article class="chart-card" role="button" tabindex="0" data-chart-title="Daily Activity">
            <p>Daily Activity</p>
            <img class="chart-img" src="${graphs.daily_activity}" alt="Daily Activity" />
            <span class="chart-action">Click to zoom</span>
          </article>
          <article class="chart-card" role="button" tabindex="0" data-chart-title="Response Correctness">
            <p>Response Correctness</p>
            <img class="chart-img" src="${graphs.correctness_pie}" alt="Correctness" />
            <span class="chart-action">Click to zoom</span>
          </article>
          <article class="chart-card" role="button" tabindex="0" data-chart-title="Rating Distribution">
            <p>Rating Distribution</p>
            <img class="chart-img" src="${graphs.rating_dist}" alt="Rating Distribution" />
            <span class="chart-action">Click to zoom</span>
          </article>
          <article class="chart-card plotly-card" role="button" tabindex="0" data-chart-title="Topic Classification" data-chart-type="plotly">
            <p>Topic Classification</p>
            <div id="topic-plot" class="topic-plot"></div>
            <span class="chart-action">Click to zoom</span>
          </article>
        </div>
      </section>

      <section class="feedback-history analytics-section">
        <div class="section-heading">
          <span>Quality signals</span>
          <h2>Submitted Feedback</h2>
        </div>
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
        <div class="feedback-meta"><strong>${entry.rating} / 5</strong> - ${entry.correctness.replace('_', ' ')} - ${entry.length_rating.replace('_', ' ')}</div>
        <div class="feedback-text">${comment}</div>
        <div class="feedback-ts">${new Date(entry.submitted_at).toLocaleString()}</div>
      </div>
    `;
  },

  renderLogoutFeedback(entry) {
    const comment = entry.comment ? analyticsPage.escapeHtml(entry.comment) : '<em>No comment</em>';

    return `
      <div class="feedback-row">
        <div class="feedback-meta"><strong>${entry.rating} / 5</strong></div>
        <div class="feedback-text">${comment}</div>
        <div class="feedback-ts">${new Date(entry.submitted_at).toLocaleString()}</div>
      </div>
    `;
  },
};

document.addEventListener('DOMContentLoaded', () => analyticsPage.init());
