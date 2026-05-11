import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['logo.svg'],
        manifest: {
          name: 'AI Skills Gap Analyzer',
          short_name: 'SkillsGap',
          description: 'Analyze your skills and market demand using AI',
          theme_color: '#050505',
          background_color: '#050505',
          display: 'standalone',
          icons: [
            {
              src: 'logo.svg',
              sizes: '192x192 512x512',
              type: 'image/svg+xml',
              purpose: 'any maskable'
            }
          ]
        }
      })
    ],
    // Vercel hosts at the root (/) by default. If VERCEL is present, override the VITE_BASE_PATH
    base: env.VERCEL === '1' ? '/' : (env.VITE_BASE_PATH || '/'),
    build: {
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom', 'react-router-dom'],
            ui: ['lucide-react', 'motion'],
            pdf: ['jspdf', 'html-to-image'],
            charts: ['recharts']
          }
        }
      }
    }
  }
})
