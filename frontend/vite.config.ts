import fs from 'node:fs'
import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const cacheRoot = path.resolve(process.cwd(), '.critiplan-cache')
const viteCacheDir = process.env.CRITIPLAN_VITE_CACHE_DIR
  ? path.resolve(process.env.CRITIPLAN_VITE_CACHE_DIR)
  : path.join(cacheRoot, 'vite')

fs.mkdirSync(viteCacheDir, { recursive: true })

// https://vite.dev/config/
export default defineConfig({
  cacheDir: viteCacheDir,
  plugins: [react(), tailwindcss()],
})
