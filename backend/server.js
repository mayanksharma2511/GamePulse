const express = require('express');
const cors = require('cors');
const { exec } = require('child_process');
const path = require('path');

const app = express();
const PORT = 3000;

app.use(cors());
app.use(express.json());

// API Route: Similarity Analysis (User Story 1)
app.post('/api/recommend', (req, res) => {
    const targetGame = req.body.gameName;

    if (!targetGame) {
        return res.status(400).json({ error: "Please provide a game name." });
    }

    const scriptPath = path.join(__dirname, '../ml_engine/recommend.py');

    // Execute Python script
    exec(`python3 "${scriptPath}" "${targetGame}"`, (error, stdout, stderr) => {
        if (error) {
            console.error(`Execution Error:`, error);
            return res.status(500).json({ error: "Failed to generate recommendations." });
        }
        try {
            const recommendations = JSON.parse(stdout);
            res.json(recommendations);
        } catch (parseError) {
            console.error(`Parse Error:`, parseError);
            res.status(500).json({ error: "Invalid data received from ML engine." });
        }
    });
});
// API Route: Success Prediction (User Story 2)
app.post('/api/predict', (req, res) => {
    // Added releaseDate here
    const { genre, price, platform, releaseDate } = req.body;

    if (!genre || !price || !platform || !releaseDate) {
        return res.status(400).json({ error: "Missing game details." });
    }

    const scriptPath = path.join(__dirname, '../ml_engine/predict.py');

    // Passing 4 variables to Python now
    exec(`python3 "${scriptPath}" "${genre}" "${price}" "${platform}" "${releaseDate}"`, (error, stdout, stderr) => {
        if (error) return res.status(500).json({ error: "Prediction failed." });
        try { res.json(JSON.parse(stdout)); } 
        catch (e) { res.status(500).json({ error: "Invalid prediction data." }); }
    });
});

// API Route: Market Trends (User Story 3)
app.get('/api/dashboard-stats', (req, res) => {
    const scriptPath = path.join(__dirname, '../ml_engine/dashboard.py');

    exec(`python3 "${scriptPath}"`, (error, stdout, stderr) => {
        console.log("--- PYTHON OUTPUT ---");
        console.log("STDOUT:", stdout);
        console.log("STDERR:", stderr);
        if (error) return res.status(500).json({ error: "Failed to fetch stats." });
        try { res.json(JSON.parse(stdout)); } 
        catch (e) { res.status(500).json({ error: "Invalid stats data." }); }
    });
});

app.listen(PORT, () => {
    console.log(`🚀 GamePulse API running on http://localhost:${PORT}`);
});