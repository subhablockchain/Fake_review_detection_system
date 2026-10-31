# Live Testing Guide

This sandbox environment has no internet access, so the AI agent
couldn't be exercised against the real Anthropic API while building this
project — everything above was verified with syntax checks and mocked
unit/integration tests instead. Here's how to run it live in your own
environment.

## 1. Get an API key
Sign up at https://console.anthropic.com and generate an API key.

## 2. Configure `.env`
```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
AGENT_MODEL=claude-sonnet-4-6
```

## 3. Smoke-test the agent in isolation (fastest feedback loop)
```bash
python src/agent/classifier.py
```
This runs one hardcoded sample review through the agent and prints the
JSON result. If this works, your API key and prompt are wired correctly.

## 4. Run the accuracy evaluation
```bash
python -m src.agent.evaluate --file data/sample_reviews.csv --delay 0.5
```
- `--delay 0.5` adds a short pause between calls to stay comfortably
  under API rate limits while testing.
- The report now includes **Accuracy, Precision, Recall, F1, and a
  confusion matrix** — computed from real predictions, not fabricated.
  With fewer than 30 labeled rows it will print an explicit limitation
  warning; treat those numbers as a smoke test, not a real benchmark.
- Read the misclassified rows printed at the end — if the same *type* of
  mistake shows up repeatedly, add a short rule or another few-shot
  example to `src/agent/system_prompt.txt`, bump `PROMPT_VERSION` in
  `.env` (so old cached results don't mask the change), and re-run.

## 5. Start the full stack and test end-to-end
```bash
mysql -u root -p < database/schema.sql
uvicorn src.api.app:app --reload
```
Then:
- Visit `http://127.0.0.1:8000` and submit a few real reviews as a guest
  (no login) — this should work fine (`/predict` is guest-accessible).
- Visit `http://127.0.0.1:8000/dashboard` while logged out — you should
  see a "log in to view your dashboard" message, not any data. This
  confirms the security fix: `/history`, `/stats`, and friends now
  require auth and never leak data to unauthenticated requests.
- Visit `http://127.0.0.1:8000/login`, create an account, log in, submit
  a review while logged in, and confirm the dashboard now shows only
  *your* reviews (your earlier guest predictions stay separate, with
  `user_id = NULL`, and are not visible to anyone since no history
  endpoint is guest-accessible anymore).
- Create a second account (User B) in a different browser/incognito
  window, submit different reviews, and confirm User B's dashboard never
  shows User A's reviews — try guessing a review id from User A's
  dashboard and calling `GET /reviews/{id}` or `DELETE /reviews/{id}` as
  User B; both should return 404 (not found for you), never User A's data.
- Visit `http://127.0.0.1:8000/batch` and upload `data/sample_reviews.csv`
  (rename the `true_label` column or just leave it — extra columns are
  passed through untouched) to confirm the batch pipeline works.

## 6. Run the offline automated test suite
```bash
pytest tests/ -v
```
These use mocked API calls, so they don't need a real key or network
access — good for CI or a quick regression check after any change.

## 7. Rate limiting sanity check
Hit `/predict` more than 10 times in a minute from the same client and
confirm you get an HTTP 429 with a rate-limit message instead of the
request hanging or erroring oddly.

## 8. Confidence & human-review sanity check
- Submit a review you'd expect the agent to be very sure about (e.g. an
  extreme, obviously bulk-generated review) and confirm `confidence_level`
  comes back `HIGH` with `needs_human_review: false`.
- Submit an ambiguous, short, neutral review and see if it lands in
  `MEDIUM` or `LOW` — a `LOW` result should show `needs_human_review: true`
  in the response and the ⚠️ banner in the UI.

## 9. Cache versioning sanity check
- Submit the same review twice — the second response should have
  `"cached": true` and return near-instantly.
- Change `PROMPT_VERSION` in `.env` (or `AGENT_MODEL`), restart the
  server, and submit the exact same review again — it should now be a
  cache **MISS** (a fresh LLM call), proving the cache doesn't serve
  stale predictions after a prompt/model change.
