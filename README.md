# Fake Review Detection System (AI Agent Based)


Hey !!
check https://github.com/Worldofsadan/fake-review-agent

live: [https://fake-review-agent.onrender.com](https://fake-review-agent.onrender.com)



An AI-agent-powered system that classifies product/service reviews as
**Fake** or **Genuine**. The system does **not** train a Machine Learning
model on a labeled dataset — it uses a (Claude API) as a reasoning
agent that evaluates each review against a defined set of linguistic red
flags and returns a structured judgment with an explanation.

Now a full multi-user system with authentication, batch processing,
rate limiting, and two frontends (plain HTML/JS and React + Tailwind).

---

## How It Works

```
User -> Frontend (review form) -> Backend API (/predict)
     -> AI Agent (LLM call with structured, few-shot prompt)
     -> JSON classification (label, confidence, reasoning)
     -> Stored in MySQL (scoped to user, if logged in) -> Returned to Frontend
```

---

## Project Structure

```
fake-review-agent/
├── src/
│   ├── agent/
│   │   ├── classifier.py       # AI agent — builds prompt, calls LLM, parses response
│   │   ├── evaluate.py         # Batch accuracy evaluation against labeled data
│   │   └── system_prompt.txt   # Few-shot prompt defining the agent's reasoning criteria
│   ├── api/
│   │   ├── app.py              # FastAPI app — auth, /predict, /predict/batch, CRUD, cache, trend, analytics
│   │   └── export.py           # Excel (.xlsx) and PDF report builders
│   ├── auth/
│   │   ├── security.py         # Password hashing + JWT create/verify
│   │   └── dependencies.py     # FastAPI auth dependencies (required / optional user)
│   ├── config.py               # Centralized thresholds, model/prompt versioning, CORS config
│   └── database/
│       └── db.py               # SQLite helpers — users, reviews, cache (scoped per user, real analytics)
├── static/                     # plain frontend assets
│   ├── style.css
│   ├── script.js               # review form logic
│   ├── dashboard.js            # dashboard/history logic
│   ├── auth.js                 # login/signup logic
│   └── batch.js                # batch upload logic
├── templates/                  # plain frontend pages
│   ├── index.html
│   ├── dashboard.html
│   ├── auth.html
│   └── batch.html
├── frontend-react/             # alternative polished UI (React + Tailwind, CDN-based)
│   ├── index.html
│   └── README.md
├── database/
│   ├── schema.sql               # users + reviews (confidence level, human review, cache) + versioned cache
│   └── migrations/
│       └── 001_confidence_and_cache_versioning.sql   # ALTER TABLE script for existing DBs
├── data/
│   └── sample_reviews.csv
├── tests/
│   ├── test_agent.py
│   ├── test_api.py
│   ├── test_evaluate.py
│   └── WEEK6_QA_CHECKLIST.md
├── requirements.txt
├── .env.example
├── .gitignore
├── Procfile
├── Dockerfile
├── docker-compose.yml           # app + MySQL together for local dev
├── .github/workflows/ci.yml     # GitHub Actions — install deps, syntax check, run tests
├── LIVE_TESTING.md              # how to test with a real API key, step by step
└── README.md
```

---

## Run locally in Google Antigravity (macOS)

This project currently uses **SQLite** in `src/database/db.py`; you do not need to install or start MySQL for local development. The `DB_*` values in `.env.example` are legacy settings and are not used by this SQLite database layer.

1. Extract this ZIP and open the extracted folder in Antigravity.
2. Open Antigravity's Terminal and run:
   ```bash
   python3 --version
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   cp .env.example .env
   ```
3. Keep `DEMO_MODE=true` in `.env` for a free offline demo. No Claude API key is needed. For real Claude analysis, set `DEMO_MODE=false` and add your own `ANTHROPIC_API_KEY`.
4. Start the server:
   ```bash
   uvicorn src.api.app:app --reload
   ```
5. Open `http://127.0.0.1:8000` in your browser. API documentation: `http://127.0.0.1:8000/docs`.
6. Stop the server with `Control + C`.

## Setup

1. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Fill in ANTHROPIC_API_KEY, DB credentials, and JWT_SECRET_KEY
   ```

3. **Set up the database**
   ```bash
   
   ```

4. **Run the backend**
   ```bash
   uvicorn src.api.app:app --reload
   ```
   - `http://127.0.0.1:8000` — review checker
   - `http://127.0.0.1:8000/dashboard` — history & stats
   - `http://127.0.0.1:8000/login` — sign up / log in
   - `http://127.0.0.1:8000/batch` — batch CSV checker

5. **Or use the React/Tailwind frontend** — see `frontend-react/README.md`.

6. **Run tests**
   ```bash
   pytest tests/ -v
   ```

7. **Test with a real API key, step by step** — see `LIVE_TESTING.md`.

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup` | — | Create an account, returns a JWT |
| POST | `/auth/login` | — | Log in, returns a JWT |
| GET | `/auth/me` | required | Current user info |
| POST | `/predict` | optional | Classify a review (10/minute rate limit; version-aware cache). Guests allowed. |
| POST | `/predict/batch` | optional | Upload a CSV, get predictions CSV back + `X-Batch-Summary` header (3/minute, max 100,000 rows). Guests allowed. |
| GET | `/history?limit=20` | **required** | Caller's own recent predictions |
| GET | `/reviews/{id}` | **required** | Fetch a single stored review (own only) |
| DELETE | `/reviews/{id}` | **required** | Delete a stored review (own only) |
| GET | `/stats` | **required** | Totals, %, cache hits, LLM calls, human-review count (own only) |
| GET | `/stats/trend?days=14` | **required** | Per-day Fake/Genuine/human-review counts (own only) |
| GET | `/stats/confidence-distribution` | **required** | HIGH/MEDIUM/LOW counts (own only) |
| GET | `/export/excel?limit=200` | **required** | Download history as .xlsx (own only) |
| GET | `/export/pdf?limit=200` | **required** | Download history as .pdf (own only) |
| GET | `/health` | — | Health check (also reports active model/prompt version) |

`/predict` and `/predict/batch` are the only guest-accessible endpoints —
by design, guests can get predictions but have no private data to protect.
Every other data/analytics/export endpoint **requires** a Bearer token and
returns `401` without one; each query is additionally scoped to the
authenticated user's own `id`, so one user can never read, delete, or
export another user's data. See Security Notes below.

**Example — POST /predict**
```json
{ "review_text": "This product is amazing, best ever!!!", "rating": 5 }
```
```json
{
  "label": "Fake",
  "confidence": 82,
  "confidence_level": "HIGH",
  "needs_human_review": false,
  "reasoning": "Generic superlative language with no specific product details.",
  "indicators": ["excessive superlatives", "no specific detail"],
  "cached": false
}
```
- `confidence_level` is HIGH (>=80) / MEDIUM (60-79) / LOW (<60) — thresholds
  configurable via `HIGH_CONFIDENCE_THRESHOLD` / `MEDIUM_CONFIDENCE_THRESHOLD`.
- `needs_human_review` is `true` for LOW confidence — a signal for extra
  scrutiny, not a claim that the prediction is wrong.
- `cached` is `true` if this exact review+rating was analyzed before under
  the same model/prompt version — no LLM call was made.

**Example — POST /predict/batch summary (decoded from X-Batch-Summary header)**
```json
{ "total_rows": 100, "processed": 92, "cache_hits": 31, "llm_calls": 61, "needs_human_review": 18, "skipped": 5, "errors": 3 }
```

**Example — POST /predict/batch**
```bash
curl -X POST http://127.0.0.1:8000/predict/batch \
  -H "Authorization: Bearer <token>" \
  -F "file=@data/sample_reviews.csv" \
  -o results.csv
```

---

## Deployment

**Option A — Render/Heroku (Procfile)**
```
web: uvicorn src.api.app:app --host 0.0.0.0 --port $PORT
```
Set `ANTHROPIC_API_KEY`, `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`,
`JWT_SECRET_KEY` as environment variables in the platform dashboard.

**Option B — Docker**
```bash
docker build -t fake-review-agent .
docker run -p 8000:8000 --env-file .env fake-review-agent
```

**Option C — Docker Compose (local dev, app + MySQL together)**
```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY at minimum
docker compose up --build
```
This starts MySQL (with `database/schema.sql` auto-applied on first run)
and the FastAPI app with hot-reload, both networked together — no local
MySQL install needed. Visit `http://127.0.0.1:8000`.

Use a managed MySQL instance (PlanetScale, Railway, RDS) in production.

---

## Project Timeline

| Week | Focus |
|---|---|
| 1 | Planning & research — requirements, dataset study, architecture |
| 2 | Foundation setup — backend/frontend/DB skeleton, AI agent design |
| 3 | Agent evaluation — batch accuracy testing, few-shot prompt refinement |
| 4 | Complete integration — dashboard, CRUD endpoints, full data flow |
| 5 | Features & optimization — server-side validation, centralized error handling |
| 6 | Testing — unit/integration test suite, manual QA checklist |
| 7 | Deployment — Docker, Procfile, production-readiness pass |
| 8 | Hardening — JWT auth & multi-user support, batch CSV processing, rate limiting, React/Tailwind frontend |
| 9 | Polish — result caching, analytics trend chart, Excel/PDF export, Docker Compose for local dev, dark mode UI |
| 10 | Reliability — confidence-based human review, strict AI output validation, version-aware cache, real analytics (%, cache efficiency, confidence distribution), Precision/Recall/F1/confusion matrix, configurable CORS, GitHub Actions CI, batch summary reporting |

---

## Security Notes

- Passwords are hashed with bcrypt (`passlib`), never stored in plain text.
- JWTs expire after `JWT_EXPIRE_MINUTES` (default 60) — set a long random
  `JWT_SECRET_KEY` in production, never the placeholder from `.env.example`.
- CORS origins are configurable via `ALLOWED_ORIGINS` (comma-separated).
  Defaults to `*` for local development, with a startup log warning — set
  real origins before deploying publicly.
- `/predict` is rate-limited per IP (10/minute); `/predict/batch` is more
  restrictive (3/minute, 100-row cap) since it fans out into many LLM calls.
- All database credentials, JWT secret, and the LLM API key are loaded
  from `.env`, excluded from version control via `.gitignore`. No secrets
  are logged or returned in API responses.
- **Multi-user isolation**: `/history`, `/reviews/{id}`, `DELETE /reviews/{id}`,
  `/stats`, `/stats/trend`, `/stats/confidence-distribution`, `/export/excel`,
  and `/export/pdf` all **require** a valid Bearer token (`get_current_user`)
  — a guest request gets a clean 401, not unfiltered data. Only `/predict`
  and `/predict/batch` are guest-accessible, matching the "prediction only"
  design intent. *(Earlier drafts of these endpoints used optional auth,
  which meant an unauthenticated request fell through to `user_id=None` and
  the DB layer returned unfiltered/global data — this was fixed and is now
  covered by dedicated 401 tests in `tests/test_api.py`.)* Every private
  query is additionally scoped to the authenticated user's own `id` (see
  `src/database/db.py`), so User A can never read, delete, or export User
  B's data even with a valid token of their own.

## AI Reliability Notes

- **Strict output validation** (`src/agent/classifier.py::validate_agent_output`):
  label must be exactly "Fake"/"Genuine", confidence must be numeric 0-100,
  reasoning must be a non-empty string, indicators must be a list of
  strings. Malformed LLM output raises `AgentResponseError` and is never
  silently persisted.
- **Confidence-based human review** (`src/config.py`): HIGH (>=80) /
  MEDIUM (60-79) / LOW (<60, flagged `needs_human_review: true`).
  Thresholds are environment-configurable, not hardcoded inline.
- **Version-aware caching**: the cache key hashes `review + rating +
  MODEL_VERSION + PROMPT_VERSION`, so changing the model or prompt
  automatically invalidates stale cached predictions (cache MISS)
  without manually clearing the table.

## Notes

- The agent's accuracy depends entirely on prompt quality — refine
  `src/agent/system_prompt.txt` based on `evaluate.py` results, not on retraining.
- `data/sample_reviews.csv` is a small hand-labeled set for local testing.
  For a fuller benchmark, source a larger labeled dataset (e.g. the Kaggle
  Fake Reviews Dataset) and point `evaluate.py --file` at it — `evaluate.py`
  now reports Accuracy, Precision, Recall, F1, and a confusion matrix, and
  explicitly warns when the sample is too small (<30 rows) to be reliable.
- Existing databases created before this upgrade need
  `database/migrations/001_confidence_and_cache_versioning.sql` run against
  them to add the new columns (fresh installs just use `schema.sql`).
