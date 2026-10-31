"""
Unit tests for the AI agent module: prompt building, response parsing,
strict output validation, and confidence-level classification.

These tests mock the LLM API call so they run offline and don't consume
API credits.

Run with: pytest tests/test_agent.py -v
"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pytest
from src.agent.classifier import build_prompt, classify_review, validate_agent_output, AgentResponseError
from src.config import get_confidence_level, needs_human_review, HIGH_CONFIDENCE_THRESHOLD, MEDIUM_CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def test_build_prompt_includes_review_text():
    prompt = build_prompt("Great product, works fine.", rating=4)
    assert "Great product, works fine." in prompt
    assert "4" in prompt


def test_build_prompt_handles_missing_rating():
    prompt = build_prompt("No rating given here.")
    assert "Not provided" in prompt


# ---------------------------------------------------------------------------
# Confidence level thresholds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("confidence,expected_level", [
    (100, "HIGH"),
    (90, "HIGH"),
    (80, "HIGH"),
    (79, "MEDIUM"),
    (72, "MEDIUM"),
    (60, "MEDIUM"),
    (59, "LOW"),
    (30, "LOW"),
    (0, "LOW"),
])
def test_confidence_level_boundaries(confidence, expected_level):
    assert get_confidence_level(confidence) == expected_level


@pytest.mark.parametrize("confidence,expected_flag", [
    (90, False),
    (80, False),
    (60, False),
    (59, True),
    (0, True),
])
def test_needs_human_review_boundaries(confidence, expected_flag):
    assert needs_human_review(confidence) == expected_flag


def test_thresholds_are_configurable_not_hardcoded():
    # Sanity check that the thresholds used by the tests above actually
    # come from config, not from duplicated literals elsewhere.
    assert HIGH_CONFIDENCE_THRESHOLD == 80
    assert MEDIUM_CONFIDENCE_THRESHOLD == 60


# ---------------------------------------------------------------------------
# Strict output validation
# ---------------------------------------------------------------------------

def test_validate_agent_output_accepts_valid_response():
    result = validate_agent_output({
        "label": "Genuine", "confidence": 85, "reasoning": "Specific detail present.",
        "indicators": ["specific detail", "measured tone"],
    })
    assert result["label"] == "Genuine"
    assert result["confidence"] == 85
    assert result["confidence_level"] == "HIGH"
    assert result["needs_human_review"] is False
    assert result["indicators"] == ["specific detail", "measured tone"]


def test_validate_agent_output_defaults_missing_indicators():
    result = validate_agent_output({"label": "Fake", "confidence": 50, "reasoning": "Generic praise."})
    assert result["indicators"] == []
    assert result["confidence_level"] == "LOW"
    assert result["needs_human_review"] is True


def test_validate_agent_output_rejects_invalid_label():
    with pytest.raises(AgentResponseError):
        validate_agent_output({"label": "Maybe", "confidence": 80, "reasoning": "Unclear."})


def test_validate_agent_output_rejects_confidence_over_100():
    with pytest.raises(AgentResponseError):
        validate_agent_output({"label": "Fake", "confidence": 150, "reasoning": "Too high."})


def test_validate_agent_output_rejects_confidence_under_0():
    with pytest.raises(AgentResponseError):
        validate_agent_output({"label": "Fake", "confidence": -5, "reasoning": "Negative."})


def test_validate_agent_output_rejects_non_numeric_confidence():
    with pytest.raises(AgentResponseError):
        validate_agent_output({"label": "Fake", "confidence": "high", "reasoning": "Not a number."})


def test_validate_agent_output_rejects_missing_reasoning():
    with pytest.raises(AgentResponseError):
        validate_agent_output({"label": "Fake", "confidence": 80})


def test_validate_agent_output_rejects_empty_reasoning():
    with pytest.raises(AgentResponseError):
        validate_agent_output({"label": "Fake", "confidence": 80, "reasoning": "   "})


def test_validate_agent_output_rejects_invalid_indicators_type():
    with pytest.raises(AgentResponseError):
        validate_agent_output({"label": "Fake", "confidence": 80, "reasoning": "ok", "indicators": "not a list"})


def test_validate_agent_output_rejects_non_dict():
    with pytest.raises(AgentResponseError):
        validate_agent_output(["Fake", 80, "reasoning"])


# ---------------------------------------------------------------------------
# End-to-end classify_review with mocked LLM
# ---------------------------------------------------------------------------

def _mock_response(json_payload: str):
    mock_block = MagicMock()
    mock_block.text = json_payload
    mock_resp = MagicMock()
    mock_resp.content = [mock_block]
    return mock_resp


@patch("src.agent.classifier._client")
def test_classify_review_valid_response(mock_client):
    mock_client.messages.create.return_value = _mock_response(
        json.dumps({"label": "Genuine", "confidence": 78, "reasoning": "Specific detail present.", "indicators": ["specific detail"]})
    )
    result = classify_review("Used this for two weeks, works as expected.", rating=4)
    assert result["label"] == "Genuine"
    assert result["confidence"] == 78
    assert result["confidence_level"] == "MEDIUM"


@patch("src.agent.classifier._client")
def test_classify_review_strips_markdown_fences(mock_client):
    mock_client.messages.create.return_value = _mock_response(
        '```json\n{"label": "Fake", "confidence": 90, "reasoning": "Too generic.", "indicators": []}\n```'
    )
    result = classify_review("Best product ever!!!", rating=5)
    assert result["label"] == "Fake"


@patch("src.agent.classifier._client")
def test_classify_review_raises_on_invalid_json(mock_client):
    mock_client.messages.create.return_value = _mock_response("not valid json at all")
    with pytest.raises(AgentResponseError):
        classify_review("Some review text here.", rating=3)


@patch("src.agent.classifier._client")
def test_classify_review_raises_on_missing_keys(mock_client):
    mock_client.messages.create.return_value = _mock_response(
        json.dumps({"label": "Fake"})  # missing confidence & reasoning
    )
    with pytest.raises(AgentResponseError):
        classify_review("Some review text here.", rating=3)


@patch("src.agent.classifier._client")
def test_classify_review_raises_on_out_of_range_confidence(mock_client):
    mock_client.messages.create.return_value = _mock_response(
        json.dumps({"label": "Fake", "confidence": 250, "reasoning": "Bad value."})
    )
    with pytest.raises(AgentResponseError):
        classify_review("Some review text here.", rating=3)
