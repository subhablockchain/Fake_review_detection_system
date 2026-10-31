const form = document.getElementById("review-form");
const submitBtn = document.getElementById("submit-btn");
const resultSection = document.getElementById("result");
const errorMessage = document.getElementById("error-message");
const authLink = document.getElementById("auth-link");
const humanReviewBanner = document.getElementById("human-review-banner");
const confidenceBadge = document.getElementById("confidence-level-badge");
const indicatorsWrap = document.getElementById("result-indicators-wrap");
const cachedNote = document.getElementById("result-cached-note");

// Reflect login state in the nav link
const username = localStorage.getItem("username");
if (authLink && username) {
  authLink.textContent = `Log Out (${username})`;
  authLink.href = "#";
  authLink.addEventListener("click", (e) => {
    e.preventDefault();
    localStorage.removeItem("access_token");
    localStorage.removeItem("username");
    window.location.reload();
  });
}

function confidenceBadgeClass(level) {
  if (level === "HIGH") return "badge-high";
  if (level === "MEDIUM") return "badge-medium";
  return "badge-low";
}

function confidenceBadgeIcon(level) {
  if (level === "HIGH") return "✓";
  if (level === "MEDIUM") return "◐";
  return "⚠️";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const reviewText = document.getElementById("review_text").value.trim();
  const ratingValue = document.getElementById("rating").value;

  resultSection.classList.add("hidden");
  errorMessage.classList.add("hidden");

  submitBtn.disabled = true;
  submitBtn.textContent = "Analyzing with AI...";

  const token = localStorage.getItem("access_token");
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  try {
    const response = await fetch("/predict", {
      method: "POST",
      headers,
      body: JSON.stringify({
        review_text: reviewText,
        rating: ratingValue ? parseInt(ratingValue, 10) : null,
      }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || "Something went wrong. Please try again.");
    }

    const data = await response.json();

    document.getElementById("result-label").textContent = data.label;
    document.getElementById("result-confidence").textContent = data.confidence;
    document.getElementById("result-reasoning").textContent = data.reasoning;

    confidenceBadge.textContent = `${confidenceBadgeIcon(data.confidence_level)} ${data.confidence_level} CONFIDENCE`;
    confidenceBadge.className = `confidence-badge ${confidenceBadgeClass(data.confidence_level)}`;

    humanReviewBanner.classList.toggle("hidden", !data.needs_human_review);

    if (data.indicators && data.indicators.length > 0) {
      document.getElementById("result-indicators").textContent = data.indicators.join(", ");
      indicatorsWrap.classList.remove("hidden");
    } else {
      indicatorsWrap.classList.add("hidden");
    }

    const isFake = data.label === "Fake";
    resultSection.className = `result ${isFake ? "result-fake result-false" : "result-genuine result-true"}`;
    const statusTag = document.getElementById("result-status-tag");
    if (statusTag) {
      statusTag.className = `result-status-tag ${isFake ? "tag-false" : "tag-true"}`;
      statusTag.textContent = isFake ? "🔴 False / Fake Review (Marked with Red Line)" : "🟢 True / Genuine Review (Marked with Green Line)";
    }

    cachedNote.classList.toggle("hidden", !data.cached);

    resultSection.classList.remove("hidden");
  } catch (err) {
    errorMessage.textContent = err.message;
    errorMessage.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Analyze Review";
  }
});
