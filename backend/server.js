const express = require('express');
const cors = require('cors');
const { execFile } = require('child_process');
const path = require('path');

const app = express();
const PORT = 3000;
const ML_DIR = path.join(__dirname, '../ml_engine');

app.use(cors());
app.use(express.json());

// Runs a Python script with arguments passed directly (no shell), so user input
// can never be interpreted as a command.
function runPython(script, args, res, errorMessage) {
    execFile('python3', [path.join(ML_DIR, script), ...args], (error, stdout, stderr) => {
        if (error) {
            console.error(`${script} failed:`, stderr || error.message);
            return res.status(500).json({ error: errorMessage });
        }
        try {
            res.json(JSON.parse(stdout));
        } catch (parseError) {
            console.error(`${script} returned invalid JSON:`, stdout);
            res.status(500).json({ error: 'Invalid data received from the Python script.' });
        }
    });
}

// Similarity Analysis (User Story 1)
app.post('/api/recommend', (req, res) => {
    const gameName = req.body.gameName;
    if (!gameName) {
        return res.status(400).json({ error: 'Please provide a game name.' });
    }
    runPython('recommend.py', [String(gameName)], res, 'Failed to find similar games.');
});

// Rating estimate (User Story 2)
app.post('/api/predict', (req, res) => {
    const { genre, price, releaseDate } = req.body;
    if (!genre || price === undefined || price === '' || !releaseDate) {
        return res.status(400).json({ error: 'Please provide a genre, price and release date.' });
    }
    runPython('predict.py', [String(genre), String(price), String(releaseDate)], res, 'Prediction failed.');
});

// Dashboard and market trends (User Story 3)
app.get('/api/dashboard-stats', (req, res) => {
    runPython('dashboard.py', [], res, 'Failed to load dashboard statistics.');
});

app.listen(PORT, () => {
    console.log(`GamePulse API running on http://localhost:${PORT}`);
});
