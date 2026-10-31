const API_BASE = "";

const tabButtons = document.querySelectorAll(".tab-btn");
const loginForm = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");
const messageEl = document.getElementById("auth-message");
const statusEl = document.getElementById("auth-status");

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    loginForm.classList.toggle("hidden", tab !== "login");
    signupForm.classList.toggle("hidden", tab !== "signup");
    messageEl.classList.add("hidden");
  });
});

function showMessage(text) {
  messageEl.textContent = text;
  messageEl.classList.remove("hidden");
}

function saveSession(data) {
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("username", data.username);
}

async function handleAuthSubmit(url, body) {
  const res = await fetch(API_BASE + url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Something went wrong.");
  }
  return data;
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  messageEl.classList.add("hidden");
  try {
    const data = await handleAuthSubmit("/auth/login", {
      username: document.getElementById("login-username").value,
      password: document.getElementById("login-password").value,
    });
    saveSession(data);
    window.location.href = "/";
  } catch (err) {
    showMessage(err.message);
  }
});

signupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  messageEl.classList.add("hidden");
  try {
    const data = await handleAuthSubmit("/auth/signup", {
      username: document.getElementById("signup-username").value,
      password: document.getElementById("signup-password").value,
    });
    saveSession(data);
    window.location.href = "/";
  } catch (err) {
    showMessage(err.message);
  }
});

// Show current session state, if any
const existingUser = localStorage.getItem("username");
if (existingUser) {
  statusEl.textContent = `Currently logged in as ${existingUser}.`;
}
