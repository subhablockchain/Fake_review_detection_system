# Week 6 — Testing & Deployment Preparation Checklist

## Automated Tests
- [x] Unit tests for agent prompt building and response parsing (`tests/test_agent.py`)
- [x] Integration tests for API validation, /predict, /history, /reviews CRUD (`tests/test_api.py`)
- Run locally: `pytest tests/ -v`

## Manual Functional Testing
- [ ] Submit a clearly fake review (excessive superlatives) → verify label = Fake
- [ ] Submit a realistic, detailed review → verify label = Genuine
- [ ] Submit a review under 10 characters → verify 422 validation error shown in UI
- [ ] Submit a review over 3000 characters → verify 422 validation error
- [ ] Submit with an invalid rating (0 or 6) → verify 422 validation error
- [ ] Check /dashboard loads stats and history correctly after several predictions
- [ ] Delete a review from the dashboard → verify it disappears and stats update
- [ ] Kill the database connection and submit a review → verify prediction still
      returns to the user (persistence failure should not block the response)
- [ ] Submit a review with the AI provider API key removed → verify a clean
      503 error is shown instead of a raw stack trace

## Cross-Browser / Responsive Testing
- [ ] Chrome desktop
- [ ] Firefox desktop
- [ ] Mobile viewport (< 640px) — dashboard table remains scrollable, form usable

## Performance Testing
- [ ] Measure /predict response time under normal conditions (target: under
      3-4 seconds, dependent on LLM API latency)
- [ ] Run `src/agent/evaluate.py` against `data/sample_reviews.csv` and confirm
      accuracy is reported without crashing on any row

## Security & Basic Hardening
- [x] Input length limits enforced server-side (not just client-side)
- [x] Rating constrained to 1–5 via Pydantic validation
- [x] Database credentials and API keys loaded from `.env`, never hardcoded
- [x] Generic 500 response for unhandled exceptions (no internal details leaked)
- [ ] Confirm `.env` is excluded from version control (see `.gitignore`)

## Bug Log
| # | Issue | Status |
|---|-------|--------|
| — | (log issues found during manual testing here) | — |
