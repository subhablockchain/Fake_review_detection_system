/* =========================================================
   Fake Review Detection System - JavaScript Engine
   ========================================================= */

const SAMPLE_REVIEWS = {
  real: "I bought this laptop 3 months ago. The battery life is decent, around 7 hours under normal use. Build quality feels sturdy and typing on the keyboard is comfortable.",
  fake: "AMAZING PRODUCT BEST EVER BUY IT NOW!!!!!!! BEST QUALITY EVER CLICK HERE http://fake-deal.com TO GET 90% OFF BUY NOW WIN FREE GIFT SAVE90"
};

const FEATURE_WEIGHTS = {
  'click': -3.2, 'link': -2.8, 'http': -3.5, 'scam': -3.0, 'fake': -2.9, 'fraud': -3.1,
  'free': -2.5, 'gift': -2.2, 'save90': -3.4, 'buy': -1.2, '100%': -2.4, '1000%': -3.0,
  'miracle': -2.7, 'disaster': -2.6, 'reward': -2.5, 'claim': -2.4, 'win': -2.1,
  'battery': 2.8, 'laptop': 2.5, 'camera': 2.6, 'phone': 2.2, 'quality': 1.8,
  'shoe': 2.4, 'comfortable': 2.1, 'sound': 2.3, 'blender': 2.0, 'jacket': 2.2,
  'leather': 2.5, 'book': 2.1, 'coffee': 2.4, 'delivery': 1.9, 'size': 1.8
};

const STOP_WORDS = new Set([
  "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
  "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
  "can't", "cannot", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for",
  "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
  "his", "how", "i", "i'm", "if", "in", "into", "is", "it", "its", "me", "more", "most", "my",
  "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "our", "out", "over", "own",
  "same", "she", "should", "so", "some", "such", "than", "that", "the", "their", "them", "then",
  "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up", "very",
  "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why", "with", "you"
]);

let appState = { user: null, history: [] };

document.addEventListener('DOMContentLoaded', () => {
  initSession();
  renderHistory();
});

function initSession() {
  const savedUser = localStorage.getItem('fake_review_user');
  const savedHistory = localStorage.getItem('fake_review_history');
  if (savedHistory) { try { appState.history = JSON.parse(savedHistory); } catch (e) { appState.history = []; } }
  if (savedUser) { appState.user = JSON.parse(savedUser); showAppView(); } else { showLoginView(); }
}

function handleLogin(event) {
  event.preventDefault();
  const usernameInput = document.getElementById('username').value.trim();
  const passwordInput = document.getElementById('password').value.trim();
  if (!usernameInput || !passwordInput) return;
  
  appState.user = { username: usernameInput, displayName: usernameInput.charAt(0).toUpperCase() + usernameInput.slice(1) };
  localStorage.setItem('fake_review_user', JSON.stringify(appState.user));
  showAppView();
}

function fillDemo(user, pass) {
  document.getElementById('username').value = user;
  document.getElementById('password').value = pass;
  document.getElementById('login-form').dispatchEvent(new Event('submit'));
}

function handleLogout() {
  appState.user = null;
  localStorage.removeItem('fake_review_user');
  showLoginView();
}

function showLoginView() {
  document.getElementById('app-view').classList.remove('active');
  document.getElementById('app-view').classList.add('hidden');
  document.getElementById('login-view').classList.remove('hidden');
  document.getElementById('login-view').classList.add('active');
}

function showAppView() {
  document.getElementById('login-view').classList.remove('active');
  document.getElementById('login-view').classList.add('hidden');
  document.getElementById('app-view').classList.remove('hidden');
  document.getElementById('app-view').classList.add('active');

  if (appState.user) {
    document.getElementById('user-display-name').textContent = appState.user.displayName;
    document.getElementById('user-avatar-initial').textContent = appState.user.displayName.charAt(0).toUpperCase();
  }
}

function updateCharCount() {
  const text = document.getElementById('review-input').value;
  document.getElementById('char-count').textContent = `${text.length} characters`;
}

function clearInput() {
  document.getElementById('review-input').value = '';
  updateCharCount();
  document.getElementById('result-container').classList.add('hidden');
}

function loadSample(isReal) {
  const input = document.getElementById('review-input');
  input.value = isReal ? SAMPLE_REVIEWS.real : SAMPLE_REVIEWS.fake;
  updateCharCount();
}

function preprocessText(rawText) {
  let text = rawText.toLowerCase();
  text = text.replace(/<[^>]+>/g, ' ');
  const hasUrl = /http\S+|www\.\S+/.test(rawText);
  text = text.replace(/http\S+|www\.\S+/g, ' ');
  text = text.replace(/[^a-z\s]/g, ' ');

  const tokens = text.split(/\s+/).filter(t => t.length > 1 && !STOP_WORDS.has(t));
  return { tokens, hasUrl };
}

function analyzeReview() {
  const input = document.getElementById('review-input').value.trim();
  if (!input) { alert('Please enter or paste a review text first.'); return; }

  const btnText = document.getElementById('btn-text');
  const spinner = document.getElementById('btn-spinner');
  btnText.textContent = 'Analyzing...';
  spinner.classList.remove('hidden');

  setTimeout(() => {
    const { tokens, hasUrl } = preprocessText(input);
    const upperCount = (input.match(/[A-Z]/g) || []).length;
    const letterCount = (input.match(/[a-zA-Z]/g) || []).length;
    const capsRatio = letterCount > 0 ? (upperCount / letterCount) : 0;
    const exclCount = (input.match(/!/g) || []).length;

    let score = 0;
    let signals = [];

    tokens.forEach(token => { if (FEATURE_WEIGHTS[token] !== undefined) score += FEATURE_WEIGHTS[token]; });

    if (hasUrl) { score -= 4.0; signals.push('⚠️ Contains external promotional HTTP/URL links'); }
    if (capsRatio > 0.35) { score -= 3.5; signals.push('⚠️ Excessive ALL-CAPS text ratio detected'); }
    if (exclCount >= 3) { score -= 2.0; signals.push('⚠️ High frequency of exclamation marks (!)'); }

    const realTokensFound = tokens.filter(t => FEATURE_WEIGHTS[t] > 0);
    if (realTokensFound.length > 0) {
      signals.push(`✅ Genuine product attribute vocabulary matched (${realTokensFound.slice(0, 3).join(', ')})`);
    }

    const sigmoid = 1 / (1 + Math.exp(-score));
    const isReal = sigmoid >= 0.5;
    const confidence = isReal ? (sigmoid * 100) : ((1 - sigmoid) * 100);
    const finalConfidence = Math.min(99.5, Math.max(68.5, confidence));

    displayResults(isReal, finalConfidence, signals);
    saveToHistory(input, isReal ? 'REAL' : 'FAKE', finalConfidence);

    btnText.textContent = '🔍 Predict Review Authenticity';
    spinner.classList.add('hidden');
  }, 350);
}

function displayResults(isReal, confidence, signals) {
  const container = document.getElementById('result-container');
  const card = document.getElementById('result-card');
  const icon = document.getElementById('result-icon');
  const label = document.getElementById('result-label');
  const summary = document.getElementById('result-summary');
  const confVal = document.getElementById('confidence-score-val');
  const fill = document.getElementById('progress-fill');
  const signalsList = document.getElementById('signals-list');

  container.classList.remove('hidden');

  if (isReal) {
    card.className = 'result-card is-real';
    icon.textContent = '✅';
    label.textContent = 'REAL REVIEW';
    summary.textContent = 'Verified genuine customer feedback pattern.';
  } else {
    card.className = 'result-card is-fake';
    icon.textContent = '🚨';
    label.textContent = 'FAKE REVIEW DETECTED';
    summary.textContent = 'High probability of promotional spam or fake review pattern.';
  }

  confVal.textContent = `${confidence.toFixed(2)}%`;
  fill.style.width = `${confidence}%`;
  signalsList.innerHTML = signals.map(s => `<div class="signal-item">${s}</div>`).join('');
}

function saveToHistory(rawText, prediction, confidence) {
  let snippet = rawText.trim();
  if (snippet.length > 75) snippet = snippet.substring(0, 75) + '...';

  const historyItem = { id: Date.now(), text: snippet, fullText: rawText, prediction, confidence };
  appState.history.unshift(historyItem);
  appState.history = appState.history.slice(0, 5);

  localStorage.setItem('fake_review_history', JSON.stringify(appState.history));
  renderHistory();
}

function renderHistory() {
  const emptyView = document.getElementById('history-empty');
  const listView = document.getElementById('history-list');

  if (!appState.history || appState.history.length === 0) {
    emptyView.classList.remove('hidden');
    listView.innerHTML = '';
    return;
  }

  emptyView.classList.add('hidden');
  listView.innerHTML = appState.history.map((item, idx) => `
    <div class="history-card">
      <div class="history-left">
        <span class="history-index">${idx + 1}.</span>
        <span class="history-badge ${item.prediction === 'REAL' ? 'badge-real' : 'badge-fake'}">
          ${item.prediction === 'REAL' ? '🟢 REAL' : '🔴 FAKE'}
        </span>
        <span class="history-text" title="${escapeHtml(item.fullText)}">"${escapeHtml(item.text)}"</span>
      </div>
      <div class="history-right">
        <span class="history-conf">${item.confidence.toFixed(1)}%</span>
        <button type="button" class="btn-reuse" onclick="reuseHistoryItem(${item.id})">🔁 Re-test</button>
      </div>
    </div>
  `).join('');
}

function reuseHistoryItem(id) {
  const item = appState.history.find(h => h.id === id);
  if (item) {
    const input = document.getElementById('review-input');
    input.value = item.fullText;
    updateCharCount();
    window.scrollTo({ top: input.offsetTop - 100, behavior: 'smooth' });
  }
}

function clearHistory() {
  appState.history = [];
  localStorage.removeItem('fake_review_history');
  renderHistory();
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
