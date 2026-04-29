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
                <div class="card">Total Games Analyzed<br><strong style="color: #8b5cf6">${data.metrics.total_games}</strong></div>
                <div class="card">Average Market Rating<br><strong style="color: #10b981">${data.metrics.average_rating}</strong></div>
                <div class="card">Trending Genre<br><strong>${data.metrics.top_genre}</strong></div>
                <div class="card">Risk Indicator<br><strong style="color: #f59e0b">${data.metrics.risk_indicator}</strong></div>
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
                const tagsHtml = game.tags.map(tag => 
                    `<span style="background: rgba(139, 92, 246, 0.15); color: #a78bfa; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; margin-right: 6px; display: inline-block; margin-top: 10px; border: 1px solid rgba(139, 92, 246, 0.3);">${tag}</span>`
                ).join('');

                card.innerHTML = `
                    <div class="match-pill">${game.match}</div>
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
    // --- SUCCESS PREDICTION LOGIC ---
    const predictBtn = document.getElementById('predictBtn');
    const resultPanel = document.getElementById('prediction-result');

    if(predictBtn) {
        predictBtn.addEventListener('click', async () => {
            const genre = document.getElementById('pred-genre').value;
            const price = document.getElementById('pred-price').value;
            const platform = document.getElementById('pred-platform').value;
            const releaseDate = document.getElementById('pred-date').value; // Grab date

            resultPanel.innerHTML = '<p>Running ML Model...</p>';

            try {
                const response = await fetch('http://localhost:3000/api/predict', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ genre, price, platform, releaseDate })
                });
                const data = await response.json();

                if(data.error) throw new Error(data.error);

                resultPanel.innerHTML = `
                    <h2 style="color: #94a3b8">Predicted Success</h2>
                    <div class="success-score">${data.success_probability}</div>
                    <p>Risk Level: <strong style="color: ${data.risk_level === 'Low' ? '#10b981' : '#f59e0b'}">${data.risk_level}</strong></p>
                    <p style="margin-top: 15px; color: #94a3b8">${data.recommendation}</p>
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
                    <div class="card">Market Growth<br><strong style="color: #10b981">${data.metrics.market_growth}</strong></div>
                    <div class="card">Avg Price<br><strong>${data.metrics.average_price}</strong></div>
                    <div class="card">Top Genre<br><strong>${data.metrics.top_genre}</strong></div>
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