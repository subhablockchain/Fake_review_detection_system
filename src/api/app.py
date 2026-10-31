"""
Backend API — Fake Review Detection (AI Agent based)
------------------------------------------------------
Multi-user system with JWT auth, per-user history, batch CSV
classification, rate limiting, version-aware result caching, confidence-
based human review flagging, real-data analytics, and Excel/PDF export.
"""

import base64
import csv
import hashlib
import io
import json
import logging
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import (
    MODEL_VERSION, PROMPT_VERSION, ALLOWED_ORIGINS, CORS_IS_DEV_WILDCARD,
    MAX_BATCH_ROWS, MIN_REVIEW_LENGTH, MAX_REVIEW_LENGTH,
)
from src.agent.classifier import classify_review, AgentResponseError
from database.db import (
    save_review, get_history, get_review_by_id, delete_review,
    get_stats, get_trend, get_confidence_distribution,
    create_user, get_user_by_username,
    get_cached_result, save_cache_result,
)
from auth.security import hash_password, verify_password, create_access_token
from src.auth.dependencies import get_current_user, get_current_user_optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fake-review-api")

if CORS_IS_DEV_WILDCARD:
    logger.warning(
        "CORS is set to allow all origins ('*'). This is fine for local "
        "development but should NOT be used in production — set the "
        "ALLOWED_ORIGINS environment variable to a comma-separated list "
        "of your real frontend origins."
    )

BASE_DIR = Path(__file__).resolve().parent.parent.parent

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Fake Review Detection System",
    description=(
        "An AI-agent-powered API that classifies reviews as Fake or Genuine "
        "using an LLM reasoning agent (no trained ML model). Includes "
        "confidence-based human-review flagging, result caching, batch "
        "processing, and analytics — all backed by real stored data."
    ),
    version="4.0.0",
    contact={"name": "Fake Review Detection System"},
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

MIN_USERNAME_LENGTH = 3
MIN_PASSWORD_LENGTH = 8


class ReviewRequest(BaseModel):
    review_text: str = Field(..., description="The review text to analyze", examples=["This product works great, used it for two weeks now."])
    rating: int | None = Field(None, ge=1, le=5, description="Star rating, 1-5 (optional)")

    @field_validator("review_text")
    @classmethod
    def validate_review_text(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < MIN_REVIEW_LENGTH:
            raise ValueError(f"Review must be at least {MIN_REVIEW_LENGTH} characters long.")
        if len(cleaned) > MAX_REVIEW_LENGTH:
            raise ValueError(f"Review must not exceed {MAX_REVIEW_LENGTH} characters.")
        return cleaned


class ReviewResponse(BaseModel):
    label: str = Field(..., description="'Fake' or 'Genuine'")
    confidence: int = Field(..., description="0-100 confidence score from the AI agent")
    confidence_level: str = Field(..., description="HIGH (>=80), MEDIUM (60-79), or LOW (<60)")
    needs_human_review: bool = Field(..., description="True when confidence is LOW — flagged for manual review")
    reasoning: str = Field(..., description="Short natural-language explanation from the agent")
    indicators: list[str] = Field(default_factory=list, description="Short phrases naming the specific signals detected")
    cached: bool = Field(False, description="True if this result was served from cache (no LLM call made)")


class SignupRequest(BaseModel):
    username: str = Field(..., min_length=MIN_USERNAME_LENGTH, max_length=50)
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


def _review_hash(review_text: str, rating: int | None) -> str:
    """Stable cache key for a (review_text, rating) pair — versioned by the
    current MODEL_VERSION and PROMPT_VERSION, so changing either
    automatically invalidates old cached results (cache MISS) without
    needing to clear the table."""
    normalized = review_text.strip().lower()
    key = f"{normalized}|{rating if rating is not None else ''}|{MODEL_VERSION}|{PROMPT_VERSION}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Centralized error handling — never leak internals to the client
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. Please try again."})


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------

@app.get("/", tags=["Pages"], include_in_schema=False)
def serve_homepage():
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/dashboard", tags=["Pages"], include_in_schema=False)
def serve_dashboard():
    return FileResponse(BASE_DIR / "templates" / "dashboard.html")


@app.get("/login", tags=["Pages"], include_in_schema=False)
def serve_login():
    return FileResponse(BASE_DIR / "templates" / "auth.html")


@app.get("/batch", tags=["Pages"], include_in_schema=False)
def serve_batch():
    return FileResponse(BASE_DIR / "templates" / "batch.html")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.post("/auth/signup", response_model=TokenResponse, tags=["Auth"], summary="Create a new account")
def signup(payload: SignupRequest):
    """Creates a new user account and returns a JWT for immediate use."""
    if get_user_by_username(payload.username):
        raise HTTPException(status_code=409, detail="Username already taken.")

    hashed = hash_password(payload.password)
    try:
        user_id = create_user(payload.username, hashed)
    except Exception:
        logger.exception("Signup failed")
        raise HTTPException(status_code=503, detail="Could not create account. Please try again.")

    token = create_access_token({"sub": str(user_id)})
    return {"access_token": token, "username": payload.username}


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"], summary="Log in")
def login(payload: LoginRequest):
    """Authenticates a user and returns a JWT. Send it as
    `Authorization: Bearer <token>` on subsequent requests."""
    user = get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = create_access_token({"sub": str(user["id"])})
    return {"access_token": token, "username": user["username"]}


@app.get("/auth/me", tags=["Auth"], summary="Current authenticated user")
def whoami(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["id"], "username": current_user["username"]}


# ---------------------------------------------------------------------------
# Prediction routes
# ---------------------------------------------------------------------------

@app.post(
    "/predict", response_model=ReviewResponse, tags=["Prediction"],
    summary="Classify a single review",
    description=(
        "Runs the review through the AI reasoning agent (or returns a "
        "cached result if this exact review + rating was analyzed before "
        "under the same model/prompt version). Works without login; if a "
        "Bearer token is sent, the result is attached to that account. "
        "Rate limited to 10 requests/minute per client."
    ),
)
@limiter.limit("10/minute")
def predict(
    request: Request,
    payload: ReviewRequest,
    current_user: dict | None = Depends(get_current_user_optional),
):
    review_hash = _review_hash(payload.review_text, payload.rating)
    cached = get_cached_result(review_hash)

    if cached:
        from config import get_confidence_level, needs_human_review as needs_review_fn
        confidence = cached["confidence"]
        result = {
            "label": cached["predicted_label"],
            "confidence": confidence,
            "confidence_level": get_confidence_level(confidence),
            "needs_human_review": needs_review_fn(confidence),
            "reasoning": cached["reasoning"],
            "indicators": cached.get("indicators", []),
        }
        was_cached = True
    else:
        try:
            result = classify_review(payload.review_text, payload.rating)
        except AgentResponseError as e:
            logger.warning("Agent response validation failed: %s", e)
            raise HTTPException(status_code=502, detail="The AI agent returned an invalid response. Please try again.")
        except Exception:
            logger.exception("Agent call failed")
            raise HTTPException(status_code=503, detail="The AI service is temporarily unavailable. Please try again shortly.")

        try:
            save_cache_result(
                review_hash, result["label"], result["confidence"], result["reasoning"],
                indicators=result.get("indicators", []),
                model_version=MODEL_VERSION, prompt_version=PROMPT_VERSION,
            )
        except Exception as e:
            logger.warning("Failed to write cache entry: %s", e)
        was_cached = False

    try:
        save_review(
            review_text=payload.review_text,
            rating=payload.rating,
            label=result["label"],
            confidence=result["confidence"],
            confidence_level=result["confidence_level"],
            needs_human_review=result["needs_human_review"],
            reasoning=result["reasoning"],
            indicators=result.get("indicators", []),
            was_cached=was_cached,
            user_id=current_user["id"] if current_user else None,
        )
    except Exception as e:
        # A persistence failure should not block returning the prediction itself.
        logger.error("Failed to persist review: %s", e)

    return {**result, "cached": was_cached}


@app.post(
    "/predict/batch", tags=["Prediction"], summary="Classify reviews from a CSV file",
    description=(
        "Upload a CSV with a 'review_text' column (optional 'rating' "
        "column). Returns a results CSV as the response body, with a "
        "base64-encoded JSON summary in the X-Batch-Summary header "
        "(total rows, cache hits, LLM calls, human-review flags, errors). "
        f"Capped at {MAX_BATCH_ROWS} rows, rate limited to 3 requests/minute."
    ),
)
@limiter.limit("3/minute")
async def predict_batch(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict | None = Depends(get_current_user_optional),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(text))
    if "review_text" not in (reader.fieldnames or []):
        raise HTTPException(status_code=400, detail="CSV must contain a 'review_text' column.")

    rows = list(reader)
    if len(rows) == 0:
        raise HTTPException(status_code=400, detail="CSV file is empty.")
    if len(rows) > MAX_BATCH_ROWS:
        raise HTTPException(status_code=400, detail=f"Batch limited to {MAX_BATCH_ROWS} rows per upload.")

    output_rows = []
    summary = {
        "total_rows": len(rows),
        "processed": 0,
        "cache_hits": 0,
        "llm_calls": 0,
        "needs_human_review": 0,
        "errors": 0,
        "skipped": 0,
    }

    for row in rows:
        review_text = (row.get("review_text") or "").strip()
        rating_raw = row.get("rating")
        rating = int(rating_raw) if rating_raw and rating_raw.strip().isdigit() else None

        if len(review_text) < MIN_REVIEW_LENGTH:
            output_rows.append({**row, "predicted_label": "SKIPPED", "confidence": "", "confidence_level": "", "needs_human_review": "", "reasoning": "Review too short."})
            summary["skipped"] += 1
            continue

        review_hash = _review_hash(review_text, rating)
        cached = get_cached_result(review_hash)

        try:
            if cached:
                from config import get_confidence_level, needs_human_review as needs_review_fn
                confidence = cached["confidence"]
                result = {
                    "label": cached["predicted_label"], "confidence": confidence,
                    "confidence_level": get_confidence_level(confidence),
                    "needs_human_review": needs_review_fn(confidence),
                    "reasoning": cached["reasoning"], "indicators": cached.get("indicators", []),
                }
                summary["cache_hits"] += 1
            else:
                result = classify_review(review_text, rating)
                save_cache_result(
                    review_hash, result["label"], result["confidence"], result["reasoning"],
                    indicators=result.get("indicators", []),
                    model_version=MODEL_VERSION, prompt_version=PROMPT_VERSION,
                )
                summary["llm_calls"] += 1

            save_review(
                review_text=review_text, rating=rating,
                label=result["label"], confidence=result["confidence"],
                confidence_level=result["confidence_level"], needs_human_review=result["needs_human_review"],
                reasoning=result["reasoning"], indicators=result.get("indicators", []),
                was_cached=bool(cached),
                user_id=current_user["id"] if current_user else None,
            )
            if result["needs_human_review"]:
                summary["needs_human_review"] += 1

            output_rows.append({
                **row, "predicted_label": result["label"], "confidence": result["confidence"],
                "confidence_level": result["confidence_level"],
                "needs_human_review": result["needs_human_review"], "reasoning": result["reasoning"],
            })
            summary["processed"] += 1
        except Exception as e:
            # A single bad row must not fail the whole batch.
            output_rows.append({**row, "predicted_label": "ERROR", "confidence": "", "confidence_level": "", "needs_human_review": "", "reasoning": str(e)})
            summary["errors"] += 1

        if not cached:
            time.sleep(0.2)  # gentle pacing to avoid hammering the LLM API on real (non-cached) calls

    buffer = io.StringIO()
    fieldnames = list(dict.fromkeys(
        list(rows[0].keys()) + ["predicted_label", "confidence", "confidence_level", "needs_human_review", "reasoning"]
    ))
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(output_rows)
    buffer.seek(0)

    summary_header = base64.b64encode(json.dumps(summary).encode("utf-8")).decode("ascii")

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=batch_results.csv",
            "X-Batch-Summary": summary_header,
            "Access-Control-Expose-Headers": "X-Batch-Summary",
        },
    )


# ---------------------------------------------------------------------------
# History / CRUD — PRIVATE. Require a valid Bearer token; every query is
# scoped to the authenticated user's own id. Guests get 401, not
# unscoped/global data — this is the fix for the IDOR/data-leak issue
# where an unauthenticated request previously fell through to
# user_id=None and received unfiltered (all-users) results.
# ---------------------------------------------------------------------------

@app.get("/history", tags=["History"], summary="Recent predictions (auth required)")
def history(limit: int = 20, current_user: dict = Depends(get_current_user)):
    """Returns the authenticated caller's own recent predictions only."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200.")
    try:
        return get_history(limit=limit, user_id=current_user["id"])
    except Exception:
        logger.exception("Failed to fetch history")
        raise HTTPException(status_code=503, detail="Could not reach the database.")


@app.get("/reviews/{review_id}", tags=["History"], summary="Fetch one review (auth required)")
def get_single_review(review_id: int, current_user: dict = Depends(get_current_user)):
    review = get_review_by_id(review_id, user_id=current_user["id"])
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    return review


@app.delete("/reviews/{review_id}", tags=["History"], summary="Delete a review (auth required)")
def remove_review(review_id: int, current_user: dict = Depends(get_current_user)):
    deleted = delete_review(review_id, user_id=current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Review not found.")
    return {"status": "deleted", "id": review_id}


# ---------------------------------------------------------------------------
# Analytics — PRIVATE, scoped to the authenticated user. All values are
# computed from real stored data (see src/database/db.py).
# ---------------------------------------------------------------------------

@app.get("/stats", tags=["Analytics"], summary="Aggregate counts (auth required)")
def stats(current_user: dict = Depends(get_current_user)):
    try:
        return get_stats(user_id=current_user["id"])
    except Exception:
        logger.exception("Failed to compute stats")
        raise HTTPException(status_code=503, detail="Could not reach the database.")


@app.get("/stats/trend", tags=["Analytics"], summary="Daily Fake/Genuine/human-review trend (auth required)")
def stats_trend(days: int = 14, current_user: dict = Depends(get_current_user)):
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be between 1 and 90.")
    try:
        return get_trend(days=days, user_id=current_user["id"])
    except Exception:
        logger.exception("Failed to compute trend")
        raise HTTPException(status_code=503, detail="Could not reach the database.")


@app.get("/stats/confidence-distribution", tags=["Analytics"], summary="HIGH/MEDIUM/LOW confidence counts (auth required)")
def stats_confidence_distribution(current_user: dict = Depends(get_current_user)):
    try:
        return get_confidence_distribution(user_id=current_user["id"])
    except Exception:
        logger.exception("Failed to compute confidence distribution")
        raise HTTPException(status_code=503, detail="Could not reach the database.")


# ---------------------------------------------------------------------------
# Export (Excel / PDF) — PRIVATE, scoped to the authenticated user.
# ---------------------------------------------------------------------------

@app.get("/export/excel", tags=["Export"], summary="Download history as Excel (auth required)")
def export_excel(limit: int = 200, current_user: dict = Depends(get_current_user)):
    from api.export import build_excel
    rows = get_history(limit=min(limit, 1000), user_id=current_user["id"])
    if not rows:
        raise HTTPException(status_code=404, detail="No history to export yet.")

    file_bytes = build_excel(rows)
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=review_history.xlsx"},
    )


@app.get("/export/pdf", tags=["Export"], summary="Download history as PDF (auth required)")
def export_pdf(limit: int = 200, current_user: dict = Depends(get_current_user)):
    from api.export import build_pdf
    rows = get_history(limit=min(limit, 1000), user_id=current_user["id"])
    if not rows:
        raise HTTPException(status_code=404, detail="No history to export yet.")

    file_bytes = build_pdf(rows)
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=review_history.pdf"},
    )


@app.get("/health", tags=["System"], summary="Health check")
def health_check():
    return {"status": "ok", "model_version": MODEL_VERSION, "prompt_version": PROMPT_VERSION}


# Serve static frontend assets (CSS/JS)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
