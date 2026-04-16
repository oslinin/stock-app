I am following https://medium.com/@wl8380/build-publish-your-first-stock-app-for-free-df59820998aa
but using vite since create-react-app is a bit outdated and slow. 
- Also using pnpm instead of npm for faster installs.  
- my github is https://github.com/oslinin/stock-app, and 
- the live app is https://oslinin.github.io/stock-app/ using github pages.
- I am using gemini CLI: gemini --yolo, or claude --dangerously-skip-permissions

# Step 1 — Setting Up Your React Project

(npx create-react-app stock-app)  
(pnpm dlx create-react-app stock-app )
pnpm create vite stock-app --template react  
cd stock-app  
pnpm install
pnpm add axios

# 📡 Step 2 — Get a Free Stock Data API

# 🎨 Step 3 — Write the App Code

Replace src/App.js  
Add some basic styling in src/App.css:

# Step 4 — Add a Stock Chart (Optional but Cool 😎)

pnpm install react-chartjs-2 chart.js

# 🌍 Step 5 — Publish on GitHub Pages (for FREE)

git remote remove origin
git remote add origin https://github.com/oslinin/stock-app.git
git config --global credential.helper store
git init main
git add .
git commit -m "First stock app"
git branch -M main
git push -u origin main --force

## 2. Install GitHub Pages:

pnpm install gh-pages --save-dev

## 3. Edit package.json:

```json
"homepage": "https://yourusername.github.io/stock-app",
"scripts": {
  "start": "react-scripts start",
  "build": "react-scripts build",
  "predeploy": "npm run build",
  "deploy": "gh-pages -d build"
}
```

# 4. Deploy!

pnpm run deploy
Pipeline fixed!
