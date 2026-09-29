const express = require('express');
const cors = require('cors');
const { execFile } = require('child_process');
const path = require('path');

const app = express();
const PORT = 3000;
const SCRIPT = path.join(__dirname, '../ml_engine/launch_planner.py');

app.use(cors());
app.use(express.json({ limit: '50kb' }));

// Runs the Launch Planner script with arguments passed directly (no shell), so user
// input can never be interpreted as a command.
function runPlanner(args, res, errorMessage) {
    execFile('python3', [SCRIPT, ...args], { maxBuffer: 5 * 1024 * 1024 }, (error, stdout, stderr) => {
        if (error) {
            console.error('launch_planner.py failed:', stderr || error.message);
            return res.status(500).json({ error: errorMessage });
        }
        try {
            const data = JSON.parse(stdout);
            if (data.error) return res.status(400).json(data);
            res.json(data);
        } catch (parseError) {
            console.error('launch_planner.py returned invalid JSON:', stdout);
            res.status(500).json({ error: 'Invalid data received from the Python script.' });
        }
    });
}

// Form options and the models' measured accuracy
app.get('/api/options', (req, res) => runPlanner(['options'], res, 'Failed to load options.'));

// Estimates for a game that has not been released yet
app.post('/api/estimate', (req, res) => {
    runPlanner(['estimate', JSON.stringify(req.body || {})], res, 'Estimate failed.');
});

// Steam market statistics
app.get('/api/market', (req, res) => runPlanner(['market'], res, 'Failed to load market statistics.'));

app.listen(PORT, () => {
    console.log(`GamePulse API running on http://localhost:${PORT}`);
});
