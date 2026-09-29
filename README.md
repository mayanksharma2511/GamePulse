# GamePulse

GamePulse is a market-analytics dashboard for video game publishers. It uses a dataset of 1,271 games released between 2017 and 2023 to show market trends, find comparable titles, and estimate how a proposed game might be rated, with a range that shows how uncertain that estimate is.

## Project history

- **Version 1 (course project).** Built by a team of three for a semester-long Software Engineering and Project Management course, using sprints and user stories. It estimated success with a hand-written rule. The submitted version is preserved at the tag [`v1-course-submission`](https://github.com/mayanksharma2511/GamePulse/tree/v1-course-submission).
- **Version 2 (independent extension).** After the course, I (Mayank Sharma) went back to test whether that rule actually worked. I audited the data, evaluated the rule against simple baselines and learned models on games released later, and replaced it with the best model, together with prediction ranges that were checked on unseen games. This work is in `analysis/`.

## What I found

1. **About a quarter of the data was filled in.** 345 ratings (27%) and 327 prices (26%) have values like 7.333950 or 23.586207, matching the overall or publisher averages rather than real scores and store prices. 154 ratings equal the dataset's average rating exactly. See [`analysis/DATA_AUDIT.md`](analysis/DATA_AUDIT.md).
2. **The original rule did not predict ratings.** Tested on 375 games released in 2020–2023, its score had essentially no relationship with the real ratings (Spearman ρ = −0.05), and its error was larger than simply guessing the average rating every time.
3. **Genre, price and release month carried little signal.** Models using only these inputs were not clearly better than guessing the average.
4. **The publisher's track record did help, modestly.** Adding each publisher's average rating from earlier games reduced the error by 0.07 points (95% interval 0.03–0.11) and gave ρ = 0.33.
5. **Honest ranges are wide.** An 80% range needs to be about ±1.4–1.6 rating points. On unseen games, the range contained the real rating 81.3% of the time.

## Evaluation

Methods learned from 544 games released 2017–2019 and were tested on 375 games released 2020–2023, using only games with an original (not filled-in) rating. Full details: [`analysis/EVALUATION.md`](analysis/EVALUATION.md).

| Method | Mean absolute error (out of 10) | Spearman ρ | Error vs. guessing the average (95% interval) |
|---|---|---|---|
| Guess the overall average | 0.962 | — | — |
| Genre-group average | 0.977 | 0.08 | +0.015 (−0.018 to +0.048) |
| Original GamePulse rule (score ÷ 10) | 1.569 | −0.05 | +0.624 (+0.510 to +0.738) |
| Ridge regression: genre group, month, price | 0.937 | 0.19 | −0.025 (−0.058 to +0.009) |
| Gradient boosting: genre group, month, price | 0.958 | 0.19 | −0.004 (−0.051 to +0.038) |
| **Ridge regression: + publisher history** | **0.894** | **0.33** | **−0.068 (−0.108 to −0.029)** |
| Gradient boosting: + publisher history | 0.895 | 0.34 | −0.067 (−0.109 to −0.022) |

The original rule could score 351 of the 375 test games (the others had a genre that did not appear in the training years).

## Prediction ranges

Each estimate comes with an 80% range built with split conformal prediction: the model is fitted on one set of games, and the size of its errors on a later, separate set decides how wide the range must be. Full details: [`analysis/INTERVALS.md`](analysis/INTERVALS.md).

| Check (fit 2017–2018, calibrate 2019, test 2020–2023) | Result |
|---|---|
| Range | estimate ± 1.42 |
| Test games whose real rating fell inside the range | 81.3% (target 80%) |
| Publishers with 3+ earlier rated games | 82.7% (133 games) |
| Other publishers | 80.6% (242 games) |

The model in the app is built the same way on more recent data (fitted on 708 games from 2017–2020, calibrated on 211 games from 2021–2023), which gives a range of ± 1.56.

## Features

| Page | What it does |
|---|---|
| **Dashboard** | Number of games, average rating and average price (original values only), most common genre, genre distribution, and average price by release year |
| **Rating Estimate** | Choose a genre group, publisher, price and release date to get an estimated rating out of 10, an 80% range, and how much each input moved the estimate compared with an average game |
| **Market Trends** | Average price change over the years with enough games, and how many games of the two most common genres the dataset has per year |
| **Similarity Analysis** | Enter a game from the dataset to see the highest-rated games in the same genre, with price, publisher and descriptive tags |

**Descriptive tags.** For each game, GamePulse reads its plot description, drops common filler words, and uses the three most frequent remaining words as tags.

## Limitations

- The ratings come from a single scraped dataset, and the filled-in values were identified by a rule (more than two decimal places), not by labels in the data.
- The inputs explain only a small part of how a game is rated. Quality, reviews and marketing are not in the data, so even the best model is only modestly better than guessing the average.
- The range has the same width for every game, so the 80% holds on average, not separately for every kind of game.
- The dataset has few games from 2022–2023, and the model assumes future games resemble past ones.
- Rating is not the same as commercial success; the data has no sales figures.

## Reproducing the analysis

You need Python 3.

```bash
pip3 install -r analysis/requirements.txt
python3 analysis/data_audit.py    # writes analysis/clean_games.csv and DATA_AUDIT.md
python3 analysis/evaluate.py      # writes analysis/results.csv and EVALUATION.md
python3 analysis/train_model.py   # writes ml_engine/model.json, interval_results.csv and INTERVALS.md
```

## Running the app

You need Node.js and Python 3.

```bash
pip3 install -r ml_engine/requirements.txt
cd backend
npm install
node server.js        # runs on http://localhost:3000
```

Then open `frontend/index.html` in a browser.

## Architecture

```
Browser (HTML, CSS, JavaScript, Chart.js)
        │  fetch()
        ▼
Node.js / Express API (port 3000)
        │  runs Python scripts with execFile, returns JSON
        ▼
Python + pandas ──► ml_engine/finalData.csv (1,271 games)
                └─► ml_engine/model.json (model exported by analysis/train_model.py)
```

| Endpoint | Method | Python script |
|---|---|---|
| `/api/dashboard-stats` | GET | `ml_engine/dashboard.py` |
| `/api/model-info` | GET | `ml_engine/model_info.py` |
| `/api/predict` | POST | `ml_engine/predict.py` |
| `/api/recommend` | POST | `ml_engine/recommend.py` |

## Repository structure

```
analysis/     data audit, evaluation and model training (version 2)
backend/      Express API
frontend/     dashboard (HTML, CSS, JavaScript)
ml_engine/    dataset, exported model and the Python scripts the API runs
```

## Tech stack

Python (pandas, NumPy, SciPy, scikit-learn), Node.js, Express, JavaScript, Chart.js.
