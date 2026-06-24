# EPLPredict — Football Predictions App

A dissertation project: React + Flask + MongoDB for Premier League predictions and analytics.

---

## Project Structure

```
Disertatie/
├── backend/
│   ├── app.py              # Flask entry point
│   ├── config.py           # Config & env vars
│   ├── database.py         # MongoDB connection (draft — toggle MONGO_ENABLED)
│   ├── requirements.txt
│   ├── .env.example        # Copy to .env and fill values
│   └── routes/
│       ├── auth.py         # POST /api/auth/login|register|logout
│       ├── results.py      # GET  /api/results/
│       ├── predictions.py  # GET/POST /api/predictions/
│       └── standings.py    # GET  /api/standings/
└── frontend/
    ├── index.html
    ├── vite.config.js
    ├── package.json
    └── src/
        ├── App.jsx          # Router + layout
        ├── main.jsx
        ├── index.css        # Global dark theme
        ├── api/api.js       # Axios instance
        ├── context/AuthContext.jsx
        ├── components/
        │   ├── Navbar.jsx
        │   └── Navbar.module.css
        └── pages/
            ├── Home.jsx
            ├── Login.jsx
            ├── Register.jsx
            ├── Standings.jsx
            ├── Results.jsx
            ├── Predictions.jsx
            └── About.jsx
```

---

## Getting Started

### Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # then edit .env
python app.py            # runs on http://localhost:5000
```

### Frontend

```bash
cd frontend
npm install
npm run dev              # runs on http://localhost:5173
```

The Vite dev server proxies `/api/*` → `http://localhost:5000` automatically.

---

## Pages

| Route          | Description                              |
|----------------|------------------------------------------|
| `/`            | Home dashboard with recent results       |
| `/standings`   | 2024/25 Premier League table             |
| `/results`     | Historical match results with search     |
| `/predictions` | Submit score predictions for fixtures    |
| `/login`       | Login form (demo: demo@epl.com/demo1234) |
| `/register`    | Registration form                        |
| `/about`       | Tech stack, dataset info, roadmap        |

---

## Recommended Kaggle Dataset

**English Premier League Results (1993–2023)**  
`https://www.kaggle.com/datasets/saife245/english-premier-league`

Columns: `season`, `date`, `HomeTeam`, `AwayTeam`, `FTHG` (full-time home goals),
`FTAG` (full-time away goals), `FTR` (H/D/A), shots, corners, cards, referee.

### Import to MongoDB

```bash
mongoimport --db football_predictions \
            --collection results \
            --type csv \
            --headerline \
            --file EPL_results.csv
```

Then set `MONGO_ENABLED = True` in `backend/database.py` and update the
route queries to use `mongo.db.results.find(...)` instead of `MOCK_RESULTS`.

---

## Next Steps

- [x] Enable MongoDB and seed the EPL dataset
- [x] Replace mock auth with proper bcrypt + JWT
- [x] Add pagination & season filter to Results page
- [x] ML model (PyTorch) for outcome + exact-score prediction
- [ ] Prediction scoring & leaderboard
- [ ] Charts with match statistics (recharts / Chart.js)

---

## Machine Learning pipeline (PyTorch)

The model is a multi-task feedforward network: a shared trunk feeds an outcome
head (Home/Draw/Away, softmax) and a Poisson goals head (expected home & away
goals). Run from the `backend/` folder with the venv active:

```bash
python -m ml.download_data   # download EPL CSVs (1993–2023) -> ml/data/epl_matches.csv
python -m scripts.seed_db    # load matches into MongoDB
python -m ml.train           # train + save ml/artifacts/{model.pt, scaler.pkl, metrics.json}
```

The 15-feature vector (rolling form, dynamic Elo, season table, head-to-head)
is built leak-free in `ml/features.py`. Flask loads the trained model once via
`ml/predict.py` and serves predictions at `POST /api/predictions/predict`.

### Run everything

```bash
# Terminal 1 — backend
cd backend
venv\Scripts\activate
python app.py            # http://localhost:5000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev              # http://localhost:5173
```
