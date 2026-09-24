# GamePulse

GamePulse is a market-intelligence dashboard for video game publishers. It uses a dataset of 1,271 historical games to show market trends, find comparable titles, and give a rough success score for a proposed game before it is built.

It was built as a semester-long Software Engineering and Project Management project, using sprints and user stories.

![Dashboard](screenshots/dashboard.png)

## Features

| Page | What it does |
|---|---|
| **Dashboard** | Headline market metrics (total games, average rating, top genre, average price), genre distribution, and average price by release year |
| **Similarity Analysis** | Enter a game and get comparable titles from the same genre, ranked by rating, with price, publisher and descriptive tags |
| **Success Prediction** | Enter a genre, price, platform and release date and get a success score (15–98%) with a risk level and a short explanation |
| **Market Trends** | How many games the two most common genres released each year over the last six years |

### Descriptive tags

For each similar game, GamePulse reads its plot description, drops common filler words (for example "the", "game" or "player"), and uses the three most frequent remaining words as tags. The tags summarise a game at a glance, so users don't have to read the full description.

## How the success score works

The score is a rule-based heuristic built from historical games in the chosen genre (`ml_engine/predict.py`):

1. **Base score:** the genre's average rating, scaled to a percentage: `(average rating ÷ 10) × 100`
2. **Price adjustment**, comparing your price with the genre's average price:
   - at or below the average: **+10**
   - more than 1.5× the average: **−20**
   - otherwise: a gradual penalty of `−((your price − average) ÷ average) × 15`
3. **Release-month adjustment:** **+5** if games in that genre historically rated above the genre average in that month, otherwise **−5**. The adjustment is skipped if the genre has no past releases in that month.
4. **Capped** between 15% and 98%, then labelled **Low** risk (above 75%), **Medium** (51–75%) or **High** (50% or below).

### Limitations

The adjustments (+10, −20, ±5 and so on) are fixed rules, not values learned from the data. The month adjustment treats a month with two past releases the same as one with two hundred, and the final percentage is a score, not a calibrated probability. A natural next step would be to estimate these effects statistically and attach a measure of uncertainty to the score.

## Architecture

```
Browser (HTML, CSS, Vanilla JS, Chart.js)
        │  fetch()
        ▼
Node.js / Express API (port 3000)
        │  runs Python scripts, returns JSON
        ▼
Python + pandas  ──►  finalData.csv (1,271 games)
```

| Endpoint | Method | Python script |
|---|---|---|
| `/api/dashboard-stats` | GET | `ml_engine/dashboard.py` |
| `/api/recommend` | POST | `ml_engine/recommend.py` |
| `/api/predict` | POST | `ml_engine/predict.py` |

## Tech stack

- **Frontend:** HTML, CSS, Vanilla JavaScript, Chart.js
- **Backend:** Node.js, Express
- **Data processing:** Python 3, pandas
- **Data:** `ml_engine/finalData.csv`, with title, genre, developer, publisher, release date, plot, price and rating for each game

## Running locally

You need **Node.js** and **Python 3**.

```bash
# 1. Install the Python dependency
pip3 install -r ml_engine/requirements.txt

# 2. Install and start the API
cd backend
npm install
node server.js        # runs on http://localhost:3000
```

3. Open `frontend/index.html` in your browser.

## Screenshots

| Similarity Analysis | Success Prediction |
|---|---|
| ![Similarity](screenshots/similarity.png) | ![Prediction](screenshots/prediction.png) |
