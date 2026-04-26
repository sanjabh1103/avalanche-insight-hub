import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";
import { VitePWA } from "vite-plugin-pwa";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
  },
  plugins: [
    react(),
    mode === "development" && componentTagger(),
    // Story 17: Offline-first PWA. Workbox BackgroundSync queues POSTs to
    // Supabase Edge Function `ingest-event` whenever the browser is offline;
    // the queue replays automatically on reconnect.
    VitePWA({
      registerType: "autoUpdate",
      strategies: "generateSW",
      includeAssets: ["favicon.ico", "robots.txt"],
      manifest: {
        name: "Avalanche Hub",
        short_name: "AvalancheHub",
        description: "AI-powered avalanche risk intelligence platform",
        start_url: "/",
        display: "standalone",
        background_color: "#0f1724",
        theme_color: "#0ea5e9",
        icons: [
          { src: "/favicon.ico", sizes: "64x64", type: "image/x-icon" },
        ],
      },
      workbox: {
        // Precache the built app shell.
        globPatterns: ["**/*.{js,css,html,ico,png,svg,webmanifest}"],
        // Avoid hitting Supabase URLs via the document caching plugin.
        navigateFallbackDenylist: [/^\/rest\//, /^\/functions\//, /^\/auth\//],
        // Allow the bundle to grow without blocking SW installation.
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        runtimeCaching: [
          {
            // Match browser-submitted field reports and direct ingest-event posts.
            urlPattern: ({ url, request }) =>
              request.method === "POST" && /\/functions\/v1\/(ingest-event|field-report-enrichment)\b/.test(url.pathname),
            handler: "NetworkOnly",
            method: "POST",
            options: {
              backgroundSync: {
                name: "field-report-queue",
                options: {
                  // Retain queued POSTs for up to 24h while offline.
                  maxRetentionTime: 24 * 60,
                },
              },
            },
          },
        ],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
  },
  build: {
    rollupOptions: {
      external: ['@turf/turf'],
    },
  },
}));
