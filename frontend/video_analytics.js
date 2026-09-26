// Video Analytics - renders views, engagement, reach and SEO for a video
// as a Word-style report, from /api/video-info (see backend/analytics.py).

const analyticsEls = {
    urlInput: document.getElementById('analyticsUrlInput'),
    analyzeBtn: document.getElementById('analyzeBtn'),
    printBtn: document.getElementById('printReportBtn'),
    report: document.getElementById('analyticsReport'),
    seoBox: document.getElementById('seoScoreBox'),
    glanceBox: document.getElementById('glanceBox'),
    keywordsBox: document.getElementById('keywordsBox')
};

const STATUS_LABELS = {
    good: { icon: '✔', text: 'Above typical', cls: 'status-good' },
    ok: { icon: '●', text: 'Typical', cls: 'status-ok' },
    low: { icon: '▲', text: 'Below typical', cls: 'status-low' },
    unknown: { icon: '–', text: 'Not available', cls: 'status-unknown' }
};

document.addEventListener('DOMContentLoaded', () => {
    analyticsEls.analyzeBtn.addEventListener('click', () => fetchVideoInfo(getSharedUrl(), { force: true }));
    analyticsEls.urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') fetchVideoInfo(getSharedUrl(), { force: true });
    });
    analyticsEls.printBtn.addEventListener('click', () => {
        document.body.classList.add('printing-report');
        window.print();
        document.body.classList.remove('printing-report');
    });
});

// ---------- Formatting ----------

function formatCount(n) {
    if (n === null || n === undefined) return '—';
    return Number(n).toLocaleString();
}

function formatCompact(n) {
    if (n === null || n === undefined) return '—';
    return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(n);
}

function formatPercent(n) {
    if (n === null || n === undefined) return '—';
    return (n < 0.1 ? n.toFixed(3) : n.toFixed(2)) + '%';
}

function formatDuration(seconds) {
    if (!seconds) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

function statusBadge(status) {
    const s = STATUS_LABELS[status] || STATUS_LABELS.unknown;
    return `<span class="status-badge ${s.cls}"><span aria-hidden="true">${s.icon}</span> ${s.text}</span>`;
}

function seoGrade(score) {
    if (score >= 80) return { label: 'Strong', cls: 'status-good', icon: '✔' };
    if (score >= 55) return { label: 'Needs work', cls: 'status-ok', icon: '●' };
    return { label: 'Weak', cls: 'status-low', icon: '▲' };
}

// ---------- Rendering ----------

function renderAnalytics(data) {
    const { video, metrics, engagement, reach, seo } = data;
    analyticsEls.printBtn.disabled = false;

    renderSidebar(data);

    const meta = [
        video.channel && `${escapeHtml(video.channel)}${video.verified ? ' ✔' : ''}`,
        video.published && `Published ${escapeHtml(video.published)}`,
        `Duration ${formatDuration(video.duration)}${video.is_short ? ' (Short)' : ''}`,
        video.categories.length && escapeHtml(video.categories.join(', '))
    ].filter(Boolean).join(' · ');

    const tiles = [
        ['Views', formatCount(metrics.views)],
        ['Likes', formatCount(metrics.likes)],
        ['Comments', formatCount(metrics.comments)],
        ['Subscribers', formatCount(metrics.subscribers)],
        ['Views per day', formatCount(metrics.views_per_day)],
        ['Days live', formatCount(metrics.days_live)]
    ].map(([label, value]) => `
        <div class="stat-tile">
            <div class="stat-label">${label}</div>
            <div class="stat-value">${value}</div>
        </div>`).join('');

    const engagementRows = [
        ['Like rate', 'Likes ÷ views', engagement.like_rate, engagement.benchmarks.like_rate, engagement.like_rate_status],
        ['Comment rate', 'Comments ÷ views', engagement.comment_rate, engagement.benchmarks.comment_rate, engagement.comment_rate_status],
        ['Engagement rate', '(Likes + comments) ÷ views', engagement.engagement_rate, engagement.benchmarks.engagement_rate, engagement.engagement_status]
    ].map(([label, formula, value, band, status]) => `
        <tr>
            <td><strong>${label}</strong><div class="cell-note">${formula}</div></td>
            <td class="num">${formatPercent(value)}</td>
            <td>${rateBar(value, band, label)}</td>
            <td>${statusBadge(status)}</td>
        </tr>`).join('');

    const seoRows = seo.checks.map(c => `
        <tr>
            <td class="check-cell ${c.passed ? 'status-good' : 'status-low'}" aria-label="${c.passed ? 'Passed' : 'Failed'}">${c.passed ? '✔' : '✖'}</td>
            <td><strong>${escapeHtml(c.label)}</strong></td>
            <td>${escapeHtml(c.detail)}</td>
            <td class="cell-note">${escapeHtml(c.tip) || 'Looks good'}</td>
        </tr>`).join('');

    const maxKeyword = Math.max(1, ...seo.keywords.map(k => k.score));
    const keywordRows = seo.keywords.slice(0, 10).map(k => `
        <tr>
            <td>${escapeHtml(k.word)}</td>
            <td class="bar-cell">
                <div class="bar-track" title="${escapeHtml(k.word)}: weight ${k.score}">
                    <div class="bar-fill" style="width: ${(k.score / maxKeyword * 100).toFixed(1)}%"></div>
                </div>
            </td>
            <td class="num">${k.score}</td>
        </tr>`).join('');

    const tags = video.tags.length
        ? video.tags.map(t => `<span class="tag-chip">${escapeHtml(t)}</span>`).join(' ')
        : '<span class="placeholder-text">No public tags on this video</span>';

    const grade = seoGrade(seo.score);

    analyticsEls.report.innerHTML = `
        <div class="title-editor">${escapeHtml(video.title || 'Video Analytics Report')}</div>
        <div class="report-body">
            <p class="report-meta">${meta}</p>

            <h3 class="section-heading">1. Performance</h3>
            <div class="stat-grid">${tiles}</div>

            <h3 class="section-heading">2. Engagement</h3>
            <table class="word-table">
                <thead><tr><th>Metric</th><th>Value</th><th>Compared with typical range (shaded)</th><th>Status</th></tr></thead>
                <tbody>${engagementRows}</tbody>
            </table>

            <h3 class="section-heading">3. Reach</h3>
            <table class="word-table">
                <tbody>
                    <tr><td><strong>Views ÷ subscribers</strong></td><td class="num">${reach.views_to_subscribers ?? '—'}×</td></tr>
                    <tr><td><strong>Reach level</strong></td><td>${escapeHtml(reach.tier)}</td></tr>
                    <tr><td><strong>Average views per day</strong></td><td class="num">${formatCount(metrics.views_per_day)}</td></tr>
                </tbody>
            </table>
            <p class="doc-hint">A ratio above 1× means the video reached people beyond the channel's subscribers,
            usually through search, Browse or Suggested videos. Impressions, click-through rate and watch time
            are private to the channel owner and only available in YouTube Studio.</p>

            <h3 class="section-heading">4. SEO Checklist — ${seo.score}/100 <span class="status-badge ${grade.cls}"><span aria-hidden="true">${grade.icon}</span> ${grade.label}</span></h3>
            <table class="word-table">
                <thead><tr><th></th><th>Check</th><th>Finding</th><th>Recommendation</th></tr></thead>
                <tbody>${seoRows}</tbody>
            </table>

            <h3 class="section-heading">5. Keywords &amp; Tags</h3>
            <table class="word-table keyword-table">
                <thead><tr><th>Keyword</th><th>Weight (tags ×3, title ×2, description ×1)</th><th>Score</th></tr></thead>
                <tbody>${keywordRows || '<tr><td colspan="3" class="placeholder-text">No keywords found</td></tr>'}</tbody>
            </table>
            <p class="report-subheading">Tags</p>
            <div class="tag-list">${tags}</div>
        </div>`;

    statusText.textContent = `Analytics ready - SEO score ${seo.score}/100`;
}

// Single-series bar with the typical range shaded behind it
function rateBar(value, band, label) {
    const [low, high] = band;
    const max = Math.max(high * 1.5, value || 0);
    const pct = v => (v / max * 100).toFixed(1);
    const fill = value === null || value === undefined ? '' :
        `<div class="bar-fill" style="width: ${pct(value)}%"></div>`;
    return `
        <div class="bar-track" title="${label}: ${formatPercent(value)} (typical ${low}–${high}%)">
            <div class="bar-band" style="left: ${pct(low)}%; width: ${pct(high - low)}%"></div>
            ${fill}
        </div>
        <div class="cell-note">Typical: ${low}–${high}%</div>`;
}

function renderSidebar({ metrics, reach, seo }) {
    const grade = seoGrade(seo.score);
    analyticsEls.seoBox.innerHTML = `
        <div class="seo-score">
            <span class="seo-score-value">${seo.score}</span><span class="seo-score-max">/100</span>
        </div>
        <div class="seo-score-grade"><span class="status-badge ${grade.cls}"><span aria-hidden="true">${grade.icon}</span> ${grade.label}</span></div>
        <div class="meter" title="SEO score ${seo.score} of 100"><div class="meter-fill" style="width: ${seo.score}%"></div></div>
        <p class="cell-note">${seo.checks.filter(c => c.passed).length} of ${seo.checks.length} checks passed</p>`;

    const rows = [
        ['Views', formatCompact(metrics.views)],
        ['Subscribers', formatCompact(metrics.subscribers)],
        ['Views/day', formatCompact(metrics.views_per_day)],
        ['Reach', reach.views_to_subscribers !== null ? `${reach.views_to_subscribers}× subs` : '—']
    ];
    analyticsEls.glanceBox.innerHTML = rows.map(([k, v]) =>
        `<div class="glance-row"><span>${k}</span><strong>${v}</strong></div>`).join('');

    analyticsEls.keywordsBox.innerHTML = seo.keywords.length
        ? seo.keywords.map(k => `<span class="tag-chip">${escapeHtml(k.word)}</span>`).join(' ')
        : '<p class="placeholder-text">No keywords found</p>';
}
