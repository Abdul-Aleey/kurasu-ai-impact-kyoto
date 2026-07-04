import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Kurasu AI',
        short_name: 'Kurasu AI',
        description: 'Your assistant for living in Japan',
        theme_color: '#160e28',
        background_color: '#160e28',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        // Static by necessity (the manifest is generated at frontend build
        // time, before the backend/agent registry exists). The panel list
        // itself stays fully dynamic via /api/agents -- only these optional
        // home-screen shortcuts need a manual entry when adding an agent.
        shortcuts: [
          { name: 'Clinic Finder', url: '/chat/clinic_finder' },
          { name: 'Delivery Scheduler', url: '/chat/delivery_scheduler' },
          { name: 'Restaurant Guide', url: '/chat/restaurant_guide' },
        ],
      },
      workbox: {
        // Live AI app, not offline-first -- never let the service worker
        // cache API responses, only precache the static build assets.
        navigateFallbackDenylist: [/^\/api\//, /^\/config$/],
        runtimeCaching: [
          {
            urlPattern: /^\/(api|config)/,
            handler: 'NetworkOnly',
          },
        ],
      },
    }),
  ],
})
