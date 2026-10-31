"""
AI Agent — Fake Review Classifier
----------------------------------
Supports:
- Claude API mode
- Free offline demo mode

Demo mode is used when DEMO_MODE=true.
"""

import os
import json
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (
    MODEL_VERSION,
    PROMPT_VERSION,
    get_confidence_level,
    needs_human_review,
)

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")

DEMO_MODE = os.getenv("DEMO_MODE", "true").strip().lower() == "true"

# Keep a default client so tests can still monkeypatch _client.
# Offline demo mode must work without an API key.
_client = anthropic.Anthropic(api_key=API_KEY) if API_KEY else None
_DEFAULT_CLIENT = _client

# Load system prompt
_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"

with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    PROMPT_TEMPLATE = f.read()

VALID_LABELS = {"Fake", "Genuine"}


class AgentResponseError(Exception):
    """Raised when the AI agent response is invalid."""
    pass


def build_prompt(review_text: str, rating: int | None = None) -> str:
    """Fill the system prompt template with review details."""
    return PROMPT_TEMPLATE.format(
        review_text=review_text.strip(),
        rating=rating if rating is not None else "Not provided",
    )


def validate_agent_output(raw: dict) -> dict:
    """
    Strictly validates the agent output.
    """

    if not isinstance(raw, dict):
        raise AgentResponseError(
            f"Agent response is not a JSON object: {raw!r}"
        )

    label = raw.get("label")

    if not isinstance(label, str) or label not in VALID_LABELS:
        raise AgentResponseError(
            f"Invalid or missing 'label': {label!r} "
            f"(must be Fake or Genuine)"
        )

    confidence = raw.get("confidence")

    if isinstance(confidence, bool) or not isinstance(
        confidence, (int, float)
    ):
        raise AgentResponseError(
            f"Invalid 'confidence': {confidence!r} "
            f"(must be numeric)"
        )

    if not (0 <= confidence <= 100):
        raise AgentResponseError(
            f"'confidence' out of range: {confidence!r} "
            f"(must be 0-100)"
        )

    confidence = int(round(confidence))

    reasoning = raw.get("reasoning")

    if not isinstance(reasoning, str) or not reasoning.strip():
        raise AgentResponseError(
            "Invalid or missing 'reasoning' "
            "(must be a non-empty string)"
        )

    indicators = raw.get("indicators", [])

    if indicators is None:
        indicators = []

    if not isinstance(indicators, list) or not all(
        isinstance(i, str) for i in indicators
    ):
        raise AgentResponseError(
            f"Invalid 'indicators': {indicators!r} "
            f"(must be a list of strings)"
        )

    return {
        "label": label,
        "confidence": confidence,
        "reasoning": reasoning.strip(),
        "indicators": indicators,
        "confidence_level": get_confidence_level(confidence),
        "needs_human_review": needs_human_review(confidence),
    }


def _demo_classify(
    review_text: str,
    rating: int | None = None,
) -> dict:
    """
    Robust offline demo classifier.
    Evaluates multi-dimensional linguistic signals:
    - Promotional and marketing hyperbole, repetitive phrasing, exclamation density
    - Authentic consumer signals: usage timeframes, concrete product attributes,
      measured tone, constructive caveats, and purchasing context
    Calculates dynamic confidence scores and human-readable reasoning based
    on observed evidence (never hardcoded to fixed values).
    """
    text = review_text.strip()
    lower = text.lower()
    words = re.findall(r"\b[a-z0-9_']+\b", lower)
    num_words = len(words)

    fake_signals = []
    genuine_signals = []

    fake_score = 0.0
    genuine_score = 0.0

    # 1. Hyperbolic promotional phrases
    promo_phrases = [
        ("changed my life", 35, "Life-altering claim ('changed my life')"),
        ("game changer", 28, "Promotional buzzword ('game changer')"),
        ("must buy", 30, "Urgent purchase directive ('must buy')"),
        ("buy now", 30, "Call-to-action directive ('buy now')"),
        ("order now", 30, "Call-to-action directive ('order now')"),
        ("run don't walk", 35, "Aggressive promotional hype"),
        ("100% recommend", 25, "Absolute recommendation ('100% recommend')"),
        ("10/10", 22, "Perfect score superlative ('10/10')"),
        ("best purchase ever", 30, "Extreme superlative purchase claim"),
        ("best product ever", 30, "Extreme superlative product claim"),
        ("best ever", 25, "Superlative phrase ('best ever')"),
        ("holy grail", 30, "Marketing hyperbole ('holy grail')"),
        ("miracle", 28, "Miraculous claim ('miracle')"),
        ("worth every penny", 20, "Generic hype ('worth every penny')"),
        ("don't hesitate", 25, "Urgency phrase ('don't hesitate')"),
        ("cheapest price", 28, "Commercial advertising phrase"),
        ("everyone must", 25, "Universal recommendation"),
        ("everyone should buy", 30, "Universal purchase directive"),
        ("thank me later", 25, "Influencer/marketing phrasing"),
        ("zero complaints", 22, "Unrealistic claim of zero flaws"),
        ("mind blowing", 28, "Hyperbolic praise ('mind blowing')"),
        ("unbelievable", 20, "Hyperbolic language ('unbelievable')"),
    ]
    for phrase, pts, desc in promo_phrases:
        if phrase in lower:
            fake_score += pts
            if desc not in fake_signals:
                fake_signals.append(desc)

    # 2. Strong promotional single words
    promo_words = {
        "miraculous": 20, "flawless": 18, "revolutionary": 22, "perfection": 18,
        "phenomenal": 18, "unrivaled": 20, "spectacular": 18, "superb": 14,
        "incredible": 14, "awesome": 10, "amazing": 10, "excellent": 8,
    }
    found_promo_words = [w for w in promo_words if f" {w} " in f" {lower} "]
    if len(found_promo_words) >= 3:
        fake_score += 25
        fake_signals.append(f"High density of promotional descriptors ({', '.join(found_promo_words[:3])})")
    elif len(found_promo_words) >= 2:
        fake_score += 15
        fake_signals.append(f"Multiple promotional descriptors ({', '.join(found_promo_words)})")

    # 3. Punctuation & Shouting
    excl_count = text.count("!")
    if excl_count >= 3:
        fake_score += min(32, excl_count * 8)
        fake_signals.append(f"Excessive exclamation points ({excl_count})")
    elif excl_count == 2:
        fake_score += 10
        fake_signals.append("Repeated exclamation points")

    caps_words = [w for w in text.split() if len(w) >= 4 and w.isupper() and w.isalpha()]
    if len(caps_words) >= 2:
        fake_score += 20
        fake_signals.append(f"Shouting in ALL CAPS ({', '.join(caps_words[:2])})")

    # Repetition
    for target in ["buy now", "best", "love", "amazing", "great"]:
        if lower.count(target) >= 2 and num_words < 30:
            fake_score += 20
            fake_signals.append(f"Repetitive usage of '{target}'")
            break

    words_set = set(words)

    # Concrete product attributes / nouns
    attributes = [
        "battery", "zipper", "cable", "screen", "material", "packaging", "delivery",
        "shipping", "fit", "size", "color", "sound", "volume", "buttons", "manual",
        "instructions", "assembly", "weight", "strap", "pocket", "seams", "stitching",
        "fabric", "plastic", "metal", "texture", "taste", "smell", "durability",
        "charger", "plug", "display", "case", "box", "inches", "cleaning", "handle",
        "lid", "remote", "setup", "noise", "wash", "port", "switch", "pillow", "fan",
        "bowl", "cup", "towels", "sheets", "blanket", "comforter", "knife", "pan",
        "product", "item", "unit", "device"
    ]
    found_attrs = [a for a in attributes if a in words_set or f"{a}s" in words_set]
    if len([a for a in found_attrs if a not in ("product", "item", "unit", "device")]) >= 2:
        genuine_score += 25
        genuine_signals.append(f"Concrete product features ({', '.join([a for a in found_attrs if a not in ('product', 'item', 'unit', 'device')][:3])})")
    elif len([a for a in found_attrs if a not in ("product", "item", "unit", "device")]) == 1:
        genuine_score += 18
        genuine_signals.append(f"Concrete product attribute ('{[a for a in found_attrs if a not in ('product', 'item', 'unit', 'device')][0]}')")

    # Empty short generic review without substance
    if num_words < 12 and any(w in lower for w in ["best ever", "greatest", "must buy", "10/10", "amazing", "perfect"]) and len(found_attrs) <= 1:
        if not any(sw in lower for sw in ["but", "though", "however", "because", "when", "after", "looking for", "needed", "intended"]):
            fake_score += 18
            fake_signals.append("Short generic praise without specific context")

    # High rating with purely generic promotional praise
    if rating == 5 and len(fake_signals) >= 1 and num_words < 20:
        fake_score += 14
        fake_signals.append("5-star rating with non-specific promotional praise")

    # 4. Genuine signals: Specific temporal / usage timeframe
    timeframe_patterns = [
        (r"\b(?:after|for|in)\s+(?:\d+|a couple of|several|a few|two|three|four|six)\s+(?:days|weeks|months|years|hours)\b", "Specific usage timeframe"),
        (r"\b(?:daily|every day|every week|months of use|daily use)\b", "Routine daily usage context"),
        (r"\b(?:since|arrived|delivered|received|ordered)\s+(?:on time|fast|broken|yesterday|last week|ago)\b", "Shipping or delivery context"),
        (r"\b(?:update|updated after)\b", "Long-term usage follow-up"),
    ]
    for pat, desc in timeframe_patterns:
        if re.search(pat, lower):
            genuine_score += 25
            if desc not in genuine_signals:
                genuine_signals.append(desc)

    # First-person purchase intent & context
    purchase_patterns = [
        (r"\b(?:bought|purchased)\s+(?:this|it|these)\s+for\b", "Specific purchase motivation/recipient"),
        (r"\b(?:bought to replace|needed something for|decided to try|was skeptical|was looking for|what i was looking for|what i needed)\b", "Personal purchasing context"),
        (r"\b(?:my son|my daughter|my wife|my husband|my dog|my cat|my kitchen|my desk|my bedroom)\b", "Personal relational context"),
    ]
    for pat, desc in purchase_patterns:
        if re.search(pat, lower):
            genuine_score += 25
            if desc not in genuine_signals:
                genuine_signals.append(desc)

    # Balanced / measured critique (strongest indicator of real human review)
    contrast_words = ["however", "although", "though", "downside", "drawback", "minor issue",
                      "only complaint", "only issue", "could be better", "wish it had",
                      "not perfect", "a bit", "a little", "pros and cons", "still usable"]
    found_contrasts = [c for c in contrast_words if c in lower]
    if " but " in lower:
        found_contrasts.append("but")
    if found_contrasts:
        genuine_score += 28
        genuine_signals.append(f"Balanced feedback with measured caveats ('{found_contrasts[0]}')")

    moderate_phrases = [
        "does the job", "as expected", "decent", "average", "works fine",
        "works well", "works as intended", "works as expected",
        "pretty good", "fairly good", "for the price", "not bad", "good quality"
    ]
    for phrase in moderate_phrases:
        if phrase in lower:
            genuine_score += 20
            genuine_signals.append(f"Measured sentiment ('{phrase}')")
            break

    # Constructive lower rating (1-4 stars with reasons)
    if rating in [2, 3, 4]:
        genuine_score += 15
        genuine_signals.append(f"Nuanced {rating}-star rating")
    elif rating == 1 and num_words > 10 and (genuine_signals or "not" in lower or "bad" in lower or "poor" in lower):
        genuine_score += 20
        genuine_signals.append("Critical authentic customer dissatisfaction")

    # Classification decision & dynamic confidence calculation
    net_score = fake_score - genuine_score

    if net_score >= 12:
        label = "Fake"
        base = 66 + min(29, int(abs(net_score) * 0.42) + len(fake_signals) * 3)
        confidence = min(98, max(60, base))
        sig_text = '; '.join(fake_signals[:3]) if fake_signals else 'promotional patterns'
        reasoning = (
            f"Review exhibits deceptive or promotional patterns: "
            f"{sig_text} without substantive context."
        )
        indicators = fake_signals
    elif net_score <= -8:
        label = "Genuine"
        base = 67 + min(29, int(abs(net_score) * 0.42) + len(genuine_signals) * 3)
        confidence = min(98, max(60, base))
        sig_text = '; '.join(genuine_signals[:3]) if genuine_signals else 'measured real-world experience'
        reasoning = (
            f"Review displays authentic customer characteristics: "
            f"{sig_text}."
        )
        indicators = genuine_signals
    else:
        # Borderline / Ambiguous review
        if fake_score > genuine_score:
            label = "Fake"
            confidence = min(59, max(50, 50 + int(fake_score - genuine_score)))
            reasoning = "Ambiguous review with slight promotional tendencies; warrants human verification."
            indicators = fake_signals or ["unclear signals"]
        else:
            label = "Genuine"
            diff = int(genuine_score - fake_score)
            confidence = min(82, max(56, 62 + diff * 2 + min(12, num_words // 5)))
            reasoning = "Authentic everyday customer review with natural phrasing and measured tone."
            indicators = genuine_signals or ["natural customer phrasing"]

    return validate_agent_output(
        {
            "label": label,
            "confidence": confidence,
            "reasoning": reasoning,
            "indicators": indicators,
        }
    )


def classify_review(
    review_text: str,
    rating: int | None = None,
) -> dict:
    """
    Classifies a review using either:

    1. Free offline demo mode
    2. Claude API mode
    """

    # FREE OFFLINE MODE
    #
    # The _client check keeps compatibility with tests that
    # monkeypatch the Anthropic client.
    if DEMO_MODE and _client is _DEFAULT_CLIENT:
        return _demo_classify(review_text, rating)

    # CLAUDE API MODE
    if _client is None:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing. Add it to .env, or set DEMO_MODE=true."
        )
    prompt = build_prompt(review_text, rating)

    response = _client.messages.create(
        model=MODEL_VERSION,
        max_tokens=350,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    raw_text = response.content[0].text.strip()

    # Defensive cleanup for markdown JSON fences
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AgentResponseError(
            f"Could not parse agent response as JSON: {raw_text}"
        ) from exc

    return validate_agent_output(parsed)


if __name__ == "__main__":

    sample_review = (
        "This product changed my life!!! "
        "Best purchase EVER, 10/10 would recommend "
        "to everyone!!!"
    )

    sample_rating = 5

    print("Testing review classifier...\n")

    try:
        output = classify_review(
            sample_review,
            sample_rating,
        )

        print(json.dumps(output, indent=2))

    except AgentResponseError as e:
        print(f"Agent error: {e}")