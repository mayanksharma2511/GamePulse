document.addEventListener('DOMContentLoaded', () => {
    // --- LOAD DASHBOARD DATA ---
    async function loadDashboard() {
        try {
            const response = await fetch('http://localhost:3000/api/dashboard-stats');
            const data = await response.json();
            if (data.error) {
                console.error("Backend Error:", data.error);
                document.getElementById('dash-metrics').innerHTML = `<p style="color:red; padding: 20px;">Server Error: ${data.error}</p>`;
                return; // Stop the function here so the rest of the page doesn't break
            }

            // Populate top cards
            document.getElementById('dash-metrics').innerHTML = `
                <div class="card">Games in Dataset<br><strong style="color: #8b5cf6">${data.metrics.total_games}</strong></div>
                <div class="card">Average Rating<br><strong style="color: #10b981">${data.metrics.average_rating}/10</strong></div>
                <div class="card">Most Common Genre<br><strong>${data.metrics.top_genre}</strong></div>
                <div class="card">Average Price<br><strong>${data.metrics.average_price}</strong></div>
            `;

            // Draw Genre Bar Chart
            new Chart(document.getElementById('genreChart').getContext('2d'), {
                type: 'bar',
                data: {
                    labels: data.genre_distribution.labels,
                    datasets: [{
                        label: 'Total Games',
                        data: data.genre_distribution.data,
                        backgroundColor: '#8b5cf6',
                        borderRadius: 4
                    }]
                },
                options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } }, x: { grid: { display: false }, ticks: { color: '#94a3b8' } } } }
            });

            // Draw Pricing Line Chart
            new Chart(document.getElementById('pricingChart').getContext('2d'), {
                type: 'line',
                data: {
                    labels: data.pricing_trends.labels,
                    datasets: [{
                        label: 'Average Price (USD)',
                        data: data.pricing_trends.data,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } }, x: { grid: { display: false }, ticks: { color: '#94a3b8' } } } }
            });

        } catch (error) {
            console.error('Dashboard load failed:', error);
        }
    }
    
    loadDashboard(); // Fire function on page load

    // --- PREDICTION FORM OPTIONS (from the trained model) ---
    async function loadModelInfo() {
        try {
            const response = await fetch('http://localhost:3000/api/model-info');
            const info = await response.json();
            if (info.error) throw new Error(info.error);
            document.getElementById('pred-genre').innerHTML = info.genre_groups
                .map(g => `<option value="${g}">${g}</option>`).join('');
            document.getElementById('publisher-list').innerHTML = info.publishers
                .map(p => `<option value="${p}"></option>`).join('');
        } catch (error) {
            console.error('Model info load failed:', error);
        }
    }
    loadModelInfo();
    
    // --- NAVIGATION LOGIC ---
    const navItems = document.querySelectorAll('.nav-links li');
    const views = document.querySelectorAll('.view');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove active states
            navItems.forEach(nav => nav.classList.remove('active'));
            views.forEach(view => {
                view.classList.remove('active-view');
                view.classList.add('hidden-view');
            });

            // Set new active state
            item.classList.add('active');
            const targetId = item.getAttribute('data-target');
            const targetView = document.getElementById(targetId);
            targetView.classList.remove('hidden-view');
            targetView.classList.add('active-view');
        });
    });

    // --- SIMILARITY SEARCH LOGIC ---
    const searchBtn = document.getElementById('searchBtn');
    const searchInput = document.getElementById('gameSearchInput');
    const resultsContainer = document.getElementById('results-container');

    searchBtn.addEventListener('click', async () => {
        const gameName = searchInput.value.trim();
        if (!gameName) return alert('Please enter a game name');

        resultsContainer.innerHTML = '<p>Analyzing market data...</p>';

        try {
            // Fetch data from your Node.js backend
            const response = await fetch('http://localhost:3000/api/recommend', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gameName })
            });

            const data = await response.json();

            if (data.error) {
                resultsContainer.innerHTML = `<p style="color: red;">Error: ${data.error}</p>`;
                return;
            }

            // Render the cards dynamically
            resultsContainer.innerHTML = '';
            data.forEach(game => {
                const card = document.createElement('div');
                card.className = 'result-card';
                // Generate HTML for the NLP tags
                const tagsHtml = (game.tags || []).map(tag => 
                    `<span style="background: rgba(139, 92, 246, 0.15); color: #a78bfa; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; margin-right: 6px; display: inline-block; margin-top: 10px; border: 1px solid rgba(139, 92, 246, 0.3);">${tag}</span>`
                ).join('');

                card.innerHTML = `
                    <h3>${game.title}</h3>
                    <p style="color: #94a3b8; margin-top: 10px; font-size: 0.9rem;">🏢 ${game.publisher}</p>
                    <p style="color: #94a3b8; margin-top: 5px;">🎮 ${game.genre} &nbsp;|&nbsp; ⭐ ${game.rating}/10</p>
                    <p style="color: #10b981; margin-top: 5px; font-weight: bold;">💰 ${game.price}</p>
                    <div>${tagsHtml}</div>
                `;
                resultsContainer.appendChild(card);
            });

        } catch (error) {
            console.error('Fetch error:', error);
            resultsContainer.innerHTML = '<p style="color: red;">Failed to connect to the server.</p>';
        }
    });
    // --- RATING ESTIMATE LOGIC ---
    const predictBtn = document.getElementById('predictBtn');
    const resultPanel = document.getElementById('prediction-result');

    if (predictBtn) {
        predictBtn.addEventListener('click', async () => {
            const genreGroup = document.getElementById('pred-genre').value;
            const publisher = document.getElementById('pred-publisher').value;
            const price = document.getElementById('pred-price').value;
            const releaseDate = document.getElementById('pred-date').value;

            resultPanel.innerHTML = '<p>Calculating...</p>';

            try {
                const response = await fetch('http://localhost:3000/api/predict', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ genreGroup, publisher, price, releaseDate })
                });
                const data = await response.json();
                if (data.error) throw new Error(data.error);

                const factorRows = data.factors.map(f => `
                    <tr>
                        <td style="text-align: left; padding: 4px 8px;">${f.factor}</td>
                        <td style="text-align: right; padding: 4px 8px; color: ${f.effect >= 0 ? '#10b981' : '#f87171'}">
                            ${f.effect >= 0 ? '+' : ''}${f.effect.toFixed(2)}
                        </td>
                    </tr>`).join('');

                resultPanel.innerHTML = `
                    <h2 style="color: #94a3b8">Estimated Rating</h2>
                    <div class="success-score">${data.estimate.toFixed(1)}<span style="font-size: 1.5rem; color: #94a3b8">/10</span></div>
                    <p>${Math.round(data.coverage * 100)}% range: <strong>${data.range_low.toFixed(1)} – ${data.range_high.toFixed(1)}</strong></p>
                    <table style="margin-top: 15px; color: #cbd5e1; font-size: 0.9rem; border-collapse: collapse;">
                        <tr><td style="text-align: left; padding: 4px 8px; color: #94a3b8">Average game</td>
                            <td style="text-align: right; padding: 4px 8px; color: #94a3b8">${data.average_game.toFixed(2)}</td></tr>
                        ${factorRows}
                    </table>
                    <p style="margin-top: 15px; color: #64748b; font-size: 0.85rem">
                        Model trained on ${data.model}. When the same method was tested on ${data.tested_on}, the range
                        contained the real rating ${(data.tested_coverage * 100).toFixed(1)}% of the time, and the estimate was only
                        modestly more accurate than always guessing the average.
                        See analysis/EVALUATION.md and analysis/INTERVALS.md.
                    </p>
                `;
            } catch (err) {
                resultPanel.innerHTML = `<p style="color: red;">Error: ${err.message}</p>`;
            }
        });
    }

    // --- MARKET TRENDS LOGIC (CHART.JS) ---
    // We trigger this when they click the "Market Trends" tab
    const trendsTab = document.querySelector('[data-target="trends-view"]');
    let chartLoaded = false;

    if(trendsTab) {
        trendsTab.addEventListener('click', async () => {
            if(chartLoaded) return; // Don't reload if already loaded
            
            try {
                const response = await fetch('http://localhost:3000/api/dashboard-stats');
                const data = await response.json();

                // 1. Populate Metric Cards
                document.getElementById('trend-metrics').innerHTML = `
                    <div class="card">Average Price Change<br><strong style="color: #10b981">${data.metrics.avg_price_change}</strong></div>
                    <div class="card">Average Price<br><strong>${data.metrics.average_price}</strong></div>
                    <div class="card">Most Common Genre<br><strong>${data.metrics.top_genre}</strong></div>
                `;

                // 2. Render Chart.js
                const ctx = document.getElementById('trendsChart').getContext('2d');
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.chart_data.labels,
                        datasets: [
                        {
                            label: data.chart_data.genre1_name, // Dynamic!
                            data: data.chart_data.genre1_data,
                            borderColor: '#8b5cf6',
                            tension: 0.4
                        },
                        {
                            label: data.chart_data.genre2_name, // Dynamic!
                            data: data.chart_data.genre2_data,
                            borderColor: '#10b981',
                            tension: 0.4
                        }
                    ]
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { labels: { color: 'white' } } },
                        scales: {
                            y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
                            x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } }
                        }
                    }
                });
                chartLoaded = true;
            } catch (err) {
                console.error("Failed to load chart data", err);
            }
        });
    }
});