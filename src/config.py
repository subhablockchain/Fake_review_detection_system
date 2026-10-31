"""
Centralized configuration — single source of truth for values that were
previously scattered across files (confidence thresholds, cache
versioning, CORS). Change these here, not inline elsewhere.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Confidence-based human review
# ---------------------------------------------------------------------------
# >= HIGH_CONFIDENCE_THRESHOLD           -> "HIGH"
# MEDIUM_CONFIDENCE_THRESHOLD .. HIGH-1  -> "MEDIUM"
# < MEDIUM_CONFIDENCE_THRESHOLD          -> "LOW" (flagged for human review)

HIGH_CONFIDENCE_THRESHOLD = int(os.getenv("HIGH_CONFIDENCE_THRESHOLD", "80"))
MEDIUM_CONFIDENCE_THRESHOLD = int(os.getenv("MEDIUM_CONFIDENCE_THRESHOLD", "60"))


def get_confidence_level(confidence: int) -> str:
    """Maps a 0-100 confidence score to HIGH / MEDIUM / LOW."""
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return "HIGH"
    if confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def needs_human_review(confidence: int) -> bool:
    """LOW confidence predictions are flagged for human review.
    This does NOT mean the prediction is wrong — only that it warrants
    a second look before being treated as final."""
    return get_confidence_level(confidence) == "LOW"


# ---------------------------------------------------------------------------
# AI agent / cache versioning
# ---------------------------------------------------------------------------
# Bump these whenever the underlying model or the prompt template changes
# in a way that could change predictions. The cache key incorporates both,
# so old cached results automatically stop being served once either changes.

MODEL_VERSION = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v3-robust-classifier")


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Comma-separated list of allowed origins in production, e.g.:
#   ALLOWED_ORIGINS=https://myapp.com,https://www.myapp.com
# Falls back to "*" (all origins) for local development only.

_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]
CORS_IS_DEV_WILDCARD = ALLOWED_ORIGINS == ["*"]


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

MAX_BATCH_ROWS = int(os.getenv("MAX_BATCH_ROWS", "100000"))


# ---------------------------------------------------------------------------
# Review text limits
# ---------------------------------------------------------------------------

MIN_REVIEW_LENGTH = int(os.getenv("MIN_REVIEW_LENGTH", "10"))
MAX_REVIEW_LENGTH = int(os.getenv("MAX_REVIEW_LENGTH", "3000"))
