# Stock App

A personal stock dashboard that displays real-time quotes and 30-day price charts for any stock symbol. Built following the article [Build & Publish Your First Stock App (for FREE!)](https://medium.com/@wl8380/build-publish-your-first-stock-app-for-free-df59820998aa) with a few modern tooling upgrades.

**Live demo:** https://oslinin.github.io/stock-app/

---

## Deviations from the article

The article uses `create-react-app` and `npm`. This repo uses:

- **Vite** instead of Create React App — faster dev server, faster builds, and CRA is no longer maintained.
- **pnpm** instead of npm — faster installs and smaller `node_modules`.
- **GitHub Actions** instead of the `gh-pages` CLI — fully automated, no manual deploy command needed.
- **Chart.js / react-chartjs-2** for the 30-day price chart (article's optional bonus step).

---

## Steps from the article

### Step 1 — Set up the React project

The article uses `create-react-app`. With Vite the equivalent is:

```bash
pnpm create vite stock-app --template react
cd stock-app
pnpm install
pnpm add axios
```

`axios` is used throughout the app to make HTTP requests to the Alpha Vantage API.

---

### Step 2 — Get a free stock data API key

Sign up at [alphavantage.co](https://www.alphavantage.co/support/#api-key) for a free API key. The free tier allows 25 requests per day.

Store the key in a `.env` file at the project root:

```
VITE_API_KEY=your_key_here
```

Vite exposes variables prefixed with `VITE_` to client code via `import.meta.env.VITE_API_KEY`. The `.env` file is listed in `.gitignore` so the key is never committed. For the deployed build the key is injected at build time via a GitHub Actions secret (see Step 5).

---

### Step 3 — Write the app code

Replace `src/App.jsx` with the stock lookup component. The component:

1. Keeps state for the search symbol, quote data, chart data, and any error message.
2. On search, fires two parallel API calls with `Promise.all`:
   - `GLOBAL_QUOTE` — current price, change, change percent, and volume.
   - `TIME_SERIES_DAILY` — daily closing prices for the chart.
3. Renders a stock card with the quote fields, or an error if the symbol is invalid or the API limit is reached.

The article's original `App.js` (class component / function component with a single quote call) is the starting point; the parallel chart call is added in Step 4.

Basic styling goes in `src/App.css`. The article provides a minimal stylesheet; `src/index.css` adds dark-mode support via `prefers-color-scheme`.

---

### Step 4 — Add a stock chart (optional but cool)

Install the charting libraries:

```bash
pnpm add react-chartjs-2 chart.js
```

In `App.jsx`, register the required Chart.js components and add a `<Line>` chart:

```jsx
import { Chart as ChartJS, CategoryScale, LinearScale,
         PointElement, LineElement, Title, Tooltip, Legend } from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, PointElement,
                 LineElement, Title, Tooltip, Legend);
```

The `TIME_SERIES_DAILY` response returns up to 100 days of data keyed by date. The app slices the 30 most recent dates, reverses them into chronological order, and maps them to closing prices for the chart dataset.

---

### Step 5 — Publish on GitHub Pages (for free)

#### 5a. Push the repo to GitHub

```bash
git remote add origin https://github.com/yourusername/stock-app.git
git branch -M main
git push -u origin main
```

#### 5b. Set the base path for GitHub Pages

Vite needs to know the sub-path under which the app will be served (`/stock-app/` in this case). `vite.config.js`:

```js
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/stock-app/' : '/',
}))
```

Using `command` keeps the dev server at `/` while the production build uses the correct sub-path.

#### 5c. Add the API key as a GitHub Actions secret

Go to **Settings → Secrets and variables → Actions → New repository secret** in your GitHub repo and add `VITE_API_KEY` with your Alpha Vantage key. The build workflow injects it at build time so it is never stored in the repo.

#### 5d. Create the GitHub Actions workflow

The article deploys with `gh-pages -d build` run manually. This repo automates that with `.github/workflows/deploy.yml`:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: latest

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - run: pnpm install

      - run: pnpm run build
        env:
          VITE_API_KEY: ${{ secrets.VITE_API_KEY }}

      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./dist
```

Every push to `main` triggers the workflow: it installs dependencies, builds the app (injecting the API key), and publishes the `dist/` folder to the `gh-pages` branch. GitHub Pages serves from that branch automatically.

#### 5e. Enable GitHub Pages

Go to **Settings → Pages** in your GitHub repo and set the source to the `gh-pages` branch, root folder. The app will be live at `https://yourusername.github.io/stock-app/`.

---

## Local development

```bash
# Install dependencies
pnpm install

# Create .env with your API key
echo "VITE_API_KEY=your_key_here" > .env

# Start the dev server
pnpm dev
```

---

## Tech stack

| Purpose | Library / Tool |
|---|---|
| UI framework | React 19 |
| Build tool | Vite 8 |
| HTTP client | Axios |
| Charting | Chart.js + react-chartjs-2 |
| Package manager | pnpm |
| Hosting | GitHub Pages |
| CI/CD | GitHub Actions |
| Stock data API | Alpha Vantage (free tier) |
