import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'stock-app — trading platform',
        short_name: 'stock-app',
        description: 'Strategy DB, market data, watchlist/screeners, portfolio, and paper bots.',
        theme_color: '#aa3bff',
        background_color: '#ffffff',
        display: 'standalone',
        icons: [
          { src: 'favicon.svg', sizes: '192x192', type: 'image/svg+xml', purpose: 'any' },
          { src: 'favicon.svg', sizes: '512x512', type: 'image/svg+xml', purpose: 'any' },
        ],
      },
      // /api is same-origin only in local dev; the deployed frontend always
      // calls a separately-hosted backend (cross-origin), which the SW never
      // intercepts by default — no runtime caching needed for API calls.
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg}'],
      },
    }),
  ],
  // DEPLOY_BASE_PATH lets PR-preview builds serve from a subpath
  // (preview/<branch>/) without touching the production build, which
  // always falls back to the normal /stock-app/ root.
  base: command === 'build' ? process.env.DEPLOY_BASE_PATH || '/stock-app/' : '/',
}))
