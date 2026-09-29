const API = 'http://localhost:3000/api';
let OPTIONS = null;

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (x, digits = 1) => `${(x * 100).toFixed(digits)}%`;
const fmtInt = (n) => Number(n).toLocaleString('en-US');

async function getJSON(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (data.error) throw new Error(data.error);
    return data;
}

// ---------- Navigation ----------
const views = document.querySelectorAll('.view');
document.querySelectorAll('.nav-links li').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.nav-links li').forEach(n => n.classList.remove('active'));
        views.forEach(v => { v.classList.remove('active-view'); v.classList.add('hidden-view'); });
        item.classList.add('active');
        const target = document.getElementById(item.dataset.target);
        target.classList.remove('hidden-view');
        target.classList.add('active-view');
        if (item.dataset.target === 'market-view') loadMarket();
    });
});

// ---------- Form options ----------
function chips(containerId, values, preselected) {
    const box = document.getElementById(containerId);
    box.innerHTML = values.map(v =>
        `<span class="chip${preselected.includes(v) ? ' selected' : ''}" data-value="${escapeHtml(v)}">${escapeHtml(v)}</span>`).join('');
    box.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => c.classList.toggle('selected')));
}
const selected = (containerId) =>
    [...document.querySelectorAll(`#${containerId} .chip.selected`)].map(c => c.dataset.value);

async function loadOptions() {
    try {
        OPTIONS = await getJSON(`${API}/options`);
        chips('genre-options', OPTIONS.genres, ['Indie', 'Simulation']);
        chips('category-options', OPTIONS.categories, ['Single-player', 'Steam Achievements']);
        document.getElementById('month').innerHTML = OPTIONS.months
            .map((m, i) => `<option value="${i + 1}"${i === 9 ? ' selected' : ''}>${m}</option>`).join('');
        renderMethod();
    } catch (err) {
        document.getElementById('results').innerHTML =
            `<div class="card error">Could not reach the API: ${escapeHtml(err.message)}. Is the server running?</div>`;
    }
}

// ---------- Estimate ----------
function factorRows(factors) {
    const maxAbs = Math.max(...factors.map(f => Math.abs(f.effect)), 0.01);
    return factors.map(f => {
        const width = (Math.abs(f.effect) / maxAbs) * 50;
        return `<div class="factor">
            <span>${escapeHtml(f.factor)}</span>
            <div class="bar-track"><div class="bar ${f.effect >= 0 ? 'up' : 'down'}" style="width:${width}%"></div></div>
        </div>`;
    }).join('');
}

function reviewsText(n, isTop) {
    return isTop ? `${fmtInt(n)}+` : fmtInt(n);
}

function renderResults(d) {
    const c = d.checks;
    const r = d.reach;
    const studioLine = (s, role) => s.known
        ? `${escapeHtml(s.name)}: ${s.games} earlier game${s.games === 1 ? '' : 's'} in the data`
        : `${escapeHtml(s.name)}: no earlier games in the data, so the average ${role} record is used`;

    document.getElementById('results').innerHTML = `
        <div class="card">
            <h3>Chance of Very Positive reviews</h3>
            <div class="big-number">${Math.round(d.reception.probability * 100)}%</div>
            <p class="muted">Very Positive = at least 80% positive reviews (among games that reach 50+ reviews).</p>
            <p class="muted" style="margin-top:12px">What moved this estimate, compared with an average game</p>
            ${factorRows(d.reception.factors)}
            <p class="note">Checked on ${fmtInt(c.reception_test_games)} games released in 2018: AUC ${c.reception_auc.toFixed(3)};
            ${pct(c.reception_top20)} of the games it rated in its top 20% were Very Positive, against ${pct(c.reception_test_rate)} of all of them.
            Its probabilities ran slightly low that year (average ${pct(c.reception_mean_prob_after)}).</p>
        </div>
        <div class="card">
            <h3>Expected reach</h3>
            <div class="big-number">${r.estimate}<span style="font-size:1.2rem;color:var(--muted)">th percentile</span></div>
            <p class="range">${Math.round(d.coverage * 100)}% range: <strong>${r.low}–${r.high}</strong></p>
            <div class="reach-scale">
                <div class="reach-range" style="left:${r.low}%;width:${r.high - r.low}%"></div>
                <div class="reach-point" style="left:calc(${r.estimate}% - 2px)"></div>
            </div>
            <div class="scale-labels"><span>fewest reviews</span><span>most reviews</span></div>
            <p class="note">More reviews than about ${r.estimate}% of games released the same month. For reference, 2017 games at that level
            had about ${reviewsText(r.reviews_estimate, r.estimate >= 95)} reviews by May 2019
            (range ${reviewsText(r.reviews_low, false)}–${reviewsText(r.reviews_high, r.high >= 95)}).
            In a check on ${fmtInt(c.reach_test_games)} games from 2018, ${pct(c.reach_coverage)} fell inside their range.</p>
        </div>
        <div class="card">
            <h3>Track record used</h3>
            <p class="muted">Developer — ${studioLine(d.studios.developer, 'developer')}</p>
            <p class="muted">Publisher — ${studioLine(d.studios.publisher, 'publisher')}</p>
        </div>`;

    const rows = d.comparables.map(g => `
        <tr>
            <td><a href="${escapeHtml(g.url)}" target="_blank" rel="noopener">${escapeHtml(g.name)}</a><br>
                ${g.tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</td>
            <td>${g.year}</td>
            <td>${g.price === 0 ? 'Free' : '$' + g.price.toFixed(2)}</td>
            <td>${g.positive_share}%</td>
            <td>${fmtInt(g.reviews)}</td>
            <td>${escapeHtml(g.owners.split('-').map(fmtInt).join('–'))}</td>
        </tr>`).join('');
    document.getElementById('comparables-table').innerHTML = `
        <tr><th>Game</th><th>Released</th><th>Price</th><th>Positive reviews</th><th>Reviews</th><th>Estimated owners</th></tr>${rows}`;
    document.getElementById('comparables-card').hidden = false;
}

document.getElementById('planner-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('estimateBtn');
    const payload = {
        description: document.getElementById('desc').value,
        genres: selected('genre-options'),
        categories: selected('category-options'),
        price: document.getElementById('price').value,
        releaseMonth: document.getElementById('month').value,
        developer: document.getElementById('developer').value,
        publisher: document.getElementById('publisher').value,
        mac: document.getElementById('mac').checked,
        linux: document.getElementById('linux').checked,
        ageRestricted: document.getElementById('age').checked,
    };
    btn.disabled = true;
    btn.textContent = 'Estimating...';
    try {
        renderResults(await getJSON(`${API}/estimate`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        }));
    } catch (err) {
        document.getElementById('results').innerHTML = `<div class="card error">${escapeHtml(err.message)}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Estimate';
    }
});

// ---------- Market overview ----------
let marketLoaded = false;
const axis = { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } };

async function loadMarket() {
    if (marketLoaded) return;
    try {
        const m = await getJSON(`${API}/market`);
        document.getElementById('market-metrics').innerHTML = `
            <div class="card">Steam games in the data<strong>${m.metrics.games_total}</strong></div>
            <div class="card">Released 2014–2018<strong>${m.metrics.games_study}</strong></div>
            <div class="card">Very Positive (50+ reviews)<strong>${m.metrics.very_positive_rate}</strong></div>
            <div class="card">Median price of paid games<strong>${m.metrics.median_paid_price}</strong></div>`;
        new Chart(document.getElementById('yearChart'), {
            type: 'bar',
            data: { labels: m.per_year.labels, datasets: [{ data: m.per_year.data, backgroundColor: '#8b5cf6' }] },
            options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: axis, y: axis } },
        });
        new Chart(document.getElementById('priceChart'), {
            type: 'bar',
            data: { labels: m.price_vp.labels, datasets: [{ data: m.price_vp.data, backgroundColor: '#10b981' }] },
            options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: axis, y: { ...axis, title: { display: true, text: '% Very Positive', color: '#94a3b8' } } } },
        });
        new Chart(document.getElementById('genreChart'), {
            type: 'bar',
            data: { labels: m.genre_vp.labels, datasets: [{ data: m.genre_vp.data, backgroundColor: '#8b5cf6' }] },
            options: { maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { ...axis, title: { display: true, text: '% Very Positive', color: '#94a3b8' } }, y: axis } },
        });
        marketLoaded = true;
    } catch (err) {
        document.getElementById('market-metrics').innerHTML = `<div class="card error">${escapeHtml(err.message)}</div>`;
    }
}

async function loadDataNote() {
    try {
        const m = await getJSON(`${API}/market`);
        document.getElementById('data-note').textContent = `Built on ${m.metrics.games_total} Steam games (data up to May 2019).`;
    } catch (err) { /* the note is optional */ }
}

// ---------- How it works ----------
function renderMethod() {
    const c = OPTIONS.checks;
    document.getElementById('method-content').innerHTML = `
        <p>GamePulse estimates how a Steam game might be received before it is released, using only information a
        publisher has at that point: price, platforms, genres, store features, release month, the store description, and
        the developer's and publisher's earlier games. The models are trained on ${escapeHtml(OPTIONS.trained_on)}.</p>

        <h3>What is estimated</h3>
        <ul>
            <li><strong>Chance of Very Positive reviews</strong> (80%+ positive): logistic regression, recalibrated on the most recent year.</li>
            <li><strong>Reach</strong>: rank by number of reviews among games released the same month, a rough stand-in for sales.
            Gradient boosting, with an ${Math.round(OPTIONS.coverage * 100)}% range from conformal prediction.</li>
            <li><strong>Comparable games</strong>: the closest store descriptions (TF-IDF, cosine similarity).</li>
        </ul>

        <h3>How accurate it was on games it had not seen</h3>
        <p>Each method was fitted on 2014–2016, calibrated on 2017, and tested on 2018:</p>
        <table class="table">
            <tr><th>Check</th><th>Result</th></tr>
            <tr><td>Reception: AUC (0.5 = chance, 1 = perfect)</td><td>${c.reception_auc.toFixed(3)}</td></tr>
            <tr><td>Reception: Very Positive among the model's top 20%</td><td>${pct(c.reception_top20)} (all games: ${pct(c.reception_test_rate)})</td></tr>
            <tr><td>Reception: calibration error before / after recalibration</td><td>${c.reception_calibration_error_before.toFixed(3)} / ${c.reception_calibration_error_after.toFixed(3)}</td></tr>
            <tr><td>Reach: games inside their ${Math.round(OPTIONS.coverage * 100)}% range</td><td>${pct(c.reach_coverage)} (range ± ${c.reach_half_width.toFixed(1)} percentile points)</td></tr>
            <tr><td>Reach: mean absolute error</td><td>${c.reach_mae.toFixed(1)} percentile points</td></tr>
            <tr><td>Comparable games sharing a genre (vs. random games)</td><td>${pct(c.comparables_share_genre)} (vs. ${pct(c.comparables_share_genre_random)})</td></tr>
        </table>

        <h3>Limitations</h3>
        <ul>
            <li>The data ends in May 2019, so the models describe the Steam market of 2014–2018.</li>
            <li>Reviews are a rough stand-in for sales; the data has no sales figures.</li>
            <li>The Very Positive rate rose over time, so probabilities ran a little low on the newest games.</li>
            <li>The reach range has the same width for every game, so it holds on average, not for every kind of game.</li>
            <li>These are estimates from past games, not guarantees. Use them alongside other research.</li>
        </ul>
        <p class="muted">Full details: steam_analysis/DATA_AUDIT.md, EVALUATION.md and MODELS.md in the repository.</p>`;
}

loadOptions();
loadDataNote();
