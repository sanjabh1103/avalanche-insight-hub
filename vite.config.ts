import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";
import { VitePWA } from "vite-plugin-pwa";
import { codeApiPlugin } from "./vite-plugin-code-api";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (
            id.includes("/react-dom/")
            || id.includes("/react/")
            || id.includes("/scheduler/")
            || id.includes("/react-is/")
            || id.includes("/use-sync-external-store/")
          ) {
            return "react-core";
          }
          if (
            id.includes("/react-router-dom/")
            || id.includes("/@tanstack/")
            || id.includes("/next-themes/")
            || id.includes("/sonner/")
          ) {
            return "router-query";
          }
          if (id.includes("/@supabase/")) {
            return "supabase-client";
          }
          if (
            id.includes("/react-leaflet/")
            || id.includes("/@react-leaflet/")
            || id.includes("/leaflet.heat/")
            || id.includes("/leaflet/")
          ) {
            return "leaflet-vendor";
          }
          if (id.includes("/@turf/") || id.includes("/d3-geo/")) {
            return "geo-vendor";
          }
          if (id.includes("/three/build/three.core.js")) {
            return "three-core";
          }
          if (id.includes("/three/build/three.module.js")) {
            return "three-module";
          }
          if (id.includes("/three/examples/jsm/")) {
            return "three-examples";
          }
          if (id.includes("/@react-three/fiber/")) {
            return "three-react";
          }
          if (id.includes("/@react-three/drei/")) {
            return "three-drei";
          }
          if (id.includes("/recharts/")) {
            return "chart-vendor";
          }
          if (id.includes("/@radix-ui/")) {
            return "radix-vendor";
          }
          if (id.includes("/framer-motion/")) {
            return "motion-vendor";
          }
          if (id.includes("/lucide-react/")) {
            return "icons-vendor";
          }
          if (
            id.includes("/react-hook-form/")
            || id.includes("/@hookform/")
            || id.includes("/react-day-picker/")
            || id.includes("/input-otp/")
            || id.includes("/zod/")
          ) {
            return "form-vendor";
          }
          if (
            id.includes("/cmdk/")
            || id.includes("/vaul/")
            || id.includes("/embla-carousel-react/")
            || id.includes("/react-resizable-panels/")
          ) {
            return "surface-vendor";
          }
          if (
            id.includes("/date-fns/")
            || id.includes("/clsx/")
            || id.includes("/class-variance-authority/")
            || id.includes("/tailwind-merge/")
          ) {
            return "utility-vendor";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    // CRITICAL: Default to loopback-only to prevent SSRF exposure of knowledge APIs.
    // Set VITE_ALLOW_LAN=true to explicitly bind to all interfaces for testing.
    host: process.env.VITE_ALLOW_LAN === "true" ? "::" : "localhost",
    port: 8080,
    hmr: {
      overlay: false,
    },
  },
  plugins: [
    react(),
    mode === "development" && codeApiPlugin(),
    mode === "development" && componentTagger(),
    // Story 17: Offline-first PWA. Workbox BackgroundSync queues POSTs to
    // Supabase Edge Function `ingest-event` whenever the browser is offline;
    // the queue replays automatically on reconnect.
    VitePWA({
      registerType: "autoUpdate",
      strategies: "generateSW",
      includeAssets: ["avalanche-favicon.svg", "avalanche-insight-hub-preview.png", "robots.txt"],
      manifest: {
        name: "Avalanche Hub",
        short_name: "AvalancheHub",
        description: "AI-powered avalanche risk intelligence platform",
        start_url: "/",
        display: "standalone",
        background_color: "#0f1724",
        theme_color: "#0ea5e9",
        icons: [
          { src: "/avalanche-favicon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" },
          { src: "/avalanche-insight-hub-preview.png", sizes: "1440x1000", type: "image/png" },
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
}));
