# React + Tailwind Frontend (Alternative UI)

A polished, single-page alternative to the plain HTML/CSS/JS frontend in
`/templates` and `/static`. No build step required — React, ReactDOM, and
Babel are loaded from CDN, and Tailwind is loaded via the Tailwind CDN
script, so this file can be opened directly or served by any static file
server.

## Run it

1. Make sure the backend is running (see the root `README.md`):
   ```bash
   uvicorn src.api.app:app --reload
   ```

2. Open `index.html` directly in a browser, or serve it:
   ```bash
   cd frontend-react
   python -m http.server 5500
   ```
   Then visit `http://127.0.0.1:5500`.

3. If the backend isn't running on `http://127.0.0.1:8000`, update the
   `API_BASE` constant near the top of the `<script type="text/babel">`
   block in `index.html`.

## What it includes

- **Check** — single review analysis with live result card
- **Dashboard** — stats cards + history table with delete
- **Batch** — CSV upload, downloads a results CSV
- **Login / Sign Up** — JWT auth, token stored in `localStorage`,
  automatically attached to API calls when present

## Note on the CDN/Babel approach

This setup is meant for fast iteration and coursework — it compiles JSX
in the browser on every page load, which is fine for a project of this
size but not recommended for production. For production, scaffold a
proper Vite/CRA build (`npm create vite@latest`) and port these
components into `.jsx` files with a real build pipeline.
