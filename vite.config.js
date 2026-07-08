import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  // DEPLOY_BASE_PATH lets PR-preview builds serve from a subpath
  // (preview/<branch>/) without touching the production build, which
  // always falls back to the normal /stock-app/ root.
  base: command === 'build' ? process.env.DEPLOY_BASE_PATH || '/stock-app/' : '/',
}))
