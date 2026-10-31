"""
API integration tests using FastAPI's TestClient with the AI agent and
database mocked out, so tests run fast and offline. Covers validation,
CRUD, caching behavior, analytics, and multi-user data isolation.

Run with: pytest tests/test_api.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_predict_rejects_too_short_review():
    res = client.post("/predict", json={"review_text": "bad", "rating": 5})
    assert res.status_code == 422


def test_predict_rejects_invalid_rating():
    res = client.post("/predict", json={"review_text": "This is a long enough review.", "rating": 9})
    assert res.status_code == 422


@patch("src.api.app.save_review")
@patch("src.api.app.save_cache_result")
@patch("src.api.app.get_cached_result")
@patch("src.api.app.classify_review")
def test_predict_success_includes_confidence_level(mock_classify, mock_get_cache, mock_save_cache, mock_save):
    mock_classify.return_value = {
        "label": "Genuine", "confidence": 85, "confidence_level": "HIGH",
        "needs_human_review": False, "reasoning": "Looks authentic.", "indicators": ["specific detail"],
    }
    mock_get_cache.return_value = None
    mock_save_cache.return_value = None
    mock_save.return_value = None

    res = client.post("/predict", json={"review_text": "This product works well for daily use.", "rating": 4})
    assert res.status_code == 200
    body = res.json()
    assert body["label"] == "Genuine"
    assert body["confidence_level"] == "HIGH"
    assert body["needs_human_review"] is False
    assert body["cached"] is False
    assert "indicators" in body


@patch("src.api.app.save_review")
@patch("src.api.app.classify_review")
def test_predict_low_confidence_flags_human_review(mock_classify, mock_save):
    mock_classify.return_value = {
        "label": "Fake", "confidence": 45, "confidence_level": "LOW",
        "needs_human_review": True, "reasoning": "Ambiguous signals.", "indicators": [],
    }
    mock_save.return_value = None

    with patch("src.api.app.get_cached_result", return_value=None), \
         patch("src.api.app.save_cache_result", return_value=None):
        res = client.post("/predict", json={"review_text": "This product works fine I guess maybe.", "rating": 3})

    assert res.status_code == 200
    body = res.json()
    assert body["needs_human_review"] is True
    assert body["confidence_level"] == "LOW"


@patch("src.api.app.save_review")
def test_predict_uses_cache_and_recomputes_confidence_level(mock_save):
    mock_save.return_value = None
    with patch("src.api.app.get_cached_result", return_value={
        "predicted_label": "Fake", "confidence": 91, "reasoning": "Cached result.", "indicators": ["too generic"],
    }):
        res = client.post("/predict", json={"review_text": "This product works well for daily use.", "rating": 4})

    assert res.status_code == 200
    body = res.json()
    assert body["label"] == "Fake"
    assert body["cached"] is True
    assert body["confidence_level"] == "HIGH"  # recomputed from cached confidence, not stored redundantly


def test_agent_error_returns_502_not_stack_trace():
    from src.agent.classifier import AgentResponseError
    with patch("src.api.app.get_cached_result", return_value=None), \
         patch("src.api.app.classify_review", side_effect=AgentResponseError("bad json")):
        res = client.post("/predict", json={"review_text": "This is a fine review of reasonable length."})

    assert res.status_code == 502
    assert "AI agent" in res.json()["detail"]
    assert "bad json" not in res.json()["detail"]  # internal error detail must not leak


# ---------------------------------------------------------------------------
# CRITICAL SECURITY FIX: private endpoints must require auth.
#
# Previously these endpoints used get_current_user_optional, so an
# unauthenticated request fell through to user_id=None, which the DB
# layer treats as "no filter" — meaning a guest could read/export ALL
# users' history and delete ANY review by guessing an id. They now use
# get_current_user (required), so a request with no/invalid token must
# get a clean 401 before any DB query happens at all.
# ---------------------------------------------------------------------------

PRIVATE_ENDPOINTS = [
    ("GET", "/history"),
    ("GET", "/reviews/1"),
    ("DELETE", "/reviews/1"),
    ("GET", "/stats"),
    ("GET", "/stats/trend"),
    ("GET", "/stats/confidence-distribution"),
    ("GET", "/export/excel"),
    ("GET", "/export/pdf"),
]


@pytest.mark.parametrize("method,path", PRIVATE_ENDPOINTS)
def test_private_endpoint_without_token_returns_401(method, path):
    # No dependency overrides, no Authorization header at all — this is
    # the plain guest case that was previously the vulnerability.
    res = client.request(method, path)
    assert res.status_code == 401, f"{method} {path} should require auth but returned {res.status_code}"


@pytest.mark.parametrize("method,path", PRIVATE_ENDPOINTS)
def test_private_endpoint_with_garbage_token_returns_401(method, path):
    res = client.request(method, path, headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


def test_predict_still_works_without_a_token_guest_allowed():
    # /predict is the one endpoint guests ARE allowed to use.
    with patch("src.api.app.get_cached_result", return_value=None), \
         patch("src.api.app.save_cache_result", return_value=None), \
         patch("src.api.app.save_review", return_value=None), \
         patch("src.api.app.classify_review", return_value={
             "label": "Genuine", "confidence": 70, "confidence_level": "MEDIUM",
             "needs_human_review": False, "reasoning": "ok", "indicators": [],
         }):
        res = client.post("/predict", json={"review_text": "This is a fine review of reasonable length."})
    assert res.status_code == 200


@patch("src.api.app.get_review_by_id")
def test_get_review_not_found_when_authenticated(mock_get):
    from src.auth.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = _fake_current_user(1)
    try:
        mock_get.return_value = None
        res = client.get("/reviews/9999")
        assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()


@patch("src.api.app.delete_review")
def test_delete_review_not_found_when_authenticated(mock_delete):
    from src.auth.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = _fake_current_user(1)
    try:
        mock_delete.return_value = False
        res = client.delete("/reviews/9999")
        assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()


@patch("src.api.app.delete_review")
def test_delete_review_success_when_authenticated(mock_delete):
    from src.auth.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = _fake_current_user(1)
    try:
        mock_delete.return_value = True
        res = client.delete("/reviews/1")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
    finally:
        app.dependency_overrides.clear()


@patch("src.api.app.get_history")
def test_history_limit_validation_when_authenticated(mock_history):
    from src.auth.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = _fake_current_user(1)
    try:
        res = client.get("/history?limit=500")
        assert res.status_code == 400
    finally:
        app.dependency_overrides.clear()


@patch("src.api.app.get_stats")
def test_stats_endpoint_returns_real_shape_when_authenticated(mock_stats):
    from src.auth.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = _fake_current_user(1)
    try:
        mock_stats.return_value = {
            "total": 10, "fake_count": 4, "genuine_count": 6,
            "fake_percentage": 40.0, "genuine_percentage": 60.0,
            "avg_confidence": 77.5, "needs_human_review_count": 2,
            "cache_hits": 3, "llm_calls": 7,
        }
        res = client.get("/stats")
        assert res.status_code == 200
        body = res.json()
        assert body["fake_percentage"] == 40.0
        assert body["cache_hits"] + body["llm_calls"] == body["total"]
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Multi-user data isolation (User A must never see/modify User B's data)
# ---------------------------------------------------------------------------

def _fake_current_user(user_id):
    def _dep():
        return {"id": user_id, "username": f"user{user_id}"}
    return _dep


def test_history_is_scoped_to_the_authenticated_user():
    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = _fake_current_user(1)
    try:
        with patch("src.api.app.get_history") as mock_history:
            mock_history.return_value = []
            client.get("/history")
            # The user_id actually passed to the DB layer must match the
            # authenticated user — this is what prevents cross-user reads.
            _, kwargs = mock_history.call_args
            assert kwargs.get("user_id") == 1
    finally:
        app.dependency_overrides.clear()


def test_delete_review_is_scoped_to_the_authenticated_user():
    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = _fake_current_user(2)
    try:
        with patch("src.api.app.delete_review") as mock_delete:
            mock_delete.return_value = True
            client.delete("/reviews/42")
            args, kwargs = mock_delete.call_args
            # user_id must be passed through so the DB query can enforce
            # "only delete if this row belongs to user 2".
            assert kwargs.get("user_id") == 2 or (len(args) > 1 and args[1] == 2)
    finally:
        app.dependency_overrides.clear()


def test_get_single_review_is_scoped_to_the_authenticated_user():
    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = _fake_current_user(5)
    try:
        with patch("src.api.app.get_review_by_id") as mock_get:
            mock_get.return_value = {
                "id": 42, "user_id": 5, "review_text": "x" * 20, "rating": 4,
                "predicted_label": "Genuine", "confidence": 90, "created_at": "2026-01-01",
            }
            client.get("/reviews/42")
            args, kwargs = mock_get.call_args
            assert kwargs.get("user_id") == 5 or (len(args) > 1 and args[1] == 5)
    finally:
        app.dependency_overrides.clear()


def test_export_excel_is_scoped_to_the_authenticated_user():
    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = _fake_current_user(3)
    try:
        with patch("src.api.app.get_history") as mock_history:
            mock_history.return_value = [{
                "id": 1, "review_text": "x" * 20, "rating": 4, "predicted_label": "Genuine",
                "confidence": 90, "confidence_level": "HIGH", "needs_human_review": False,
                "reasoning": "ok", "created_at": "2026-01-01 00:00:00",
            }]
            client.get("/export/excel")
            _, kwargs = mock_history.call_args
            assert kwargs.get("user_id") == 3
    finally:
        app.dependency_overrides.clear()


def test_export_pdf_is_scoped_to_the_authenticated_user():
    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = _fake_current_user(3)
    try:
        with patch("src.api.app.get_history") as mock_history:
            mock_history.return_value = [{
                "id": 1, "review_text": "x" * 20, "rating": 4, "predicted_label": "Genuine",
                "confidence": 90, "confidence_level": "HIGH", "needs_human_review": False,
                "reasoning": "ok", "created_at": "2026-01-01 00:00:00",
            }]
            client.get("/export/pdf")
            _, kwargs = mock_history.call_args
            assert kwargs.get("user_id") == 3
    finally:
        app.dependency_overrides.clear()


def test_stats_trend_is_scoped_to_the_authenticated_user():
    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = _fake_current_user(7)
    try:
        with patch("src.api.app.get_trend") as mock_trend:
            mock_trend.return_value = []
            client.get("/stats/trend")
            _, kwargs = mock_trend.call_args
            assert kwargs.get("user_id") == 7
    finally:
        app.dependency_overrides.clear()


def test_confidence_distribution_is_scoped_to_the_authenticated_user():
    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = _fake_current_user(9)
    try:
        with patch("src.api.app.get_confidence_distribution") as mock_dist:
            mock_dist.return_value = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            client.get("/stats/confidence-distribution")
            _, kwargs = mock_dist.call_args
            assert kwargs.get("user_id") == 9
    finally:
        app.dependency_overrides.clear()


def test_predict_batch_rejects_exceeding_max_batch_rows():
    from src.api import app as app_module
    csv_content = "review_text,rating\n" + "\n".join([f"This is test review number {i}, it is great.,5" for i in range(10)])
    files = {"file": ("reviews.csv", csv_content, "text/csv")}
    with patch.object(app_module, "MAX_BATCH_ROWS", 5):
        res = client.post("/predict/batch", files=files)
        assert res.status_code == 400
        assert "Batch limited to 5 rows per upload." in res.json()["detail"]


@patch("src.api.app.save_cache_result")
@patch("src.api.app.get_cached_result")
@patch("src.api.app.classify_review")
def test_predict_batch_processes_within_limit(mock_classify, mock_get_cache, mock_save_cache):
    mock_classify.return_value = {
        "label": "Genuine", "confidence": 85, "confidence_level": "HIGH",
        "needs_human_review": False, "reasoning": "Looks authentic.", "indicators": ["specific detail"],
    }
    mock_get_cache.return_value = None
    mock_save_cache.return_value = None

    csv_content = "review_text,rating\nThis is a legitimate detailed review.,5\n"
    files = {"file": ("reviews.csv", csv_content, "text/csv")}
    res = client.post("/predict/batch", files=files)
    assert res.status_code == 200
    assert "predicted_label" in res.text
    assert "X-Batch-Summary" in res.headers

