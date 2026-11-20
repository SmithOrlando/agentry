import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

// In development the Vite server proxies API calls to Flask so the browser sees one
// origin (session cookie + CSRF work exactly as in production behind nginx).
// Port 5001, not Flask's default 5000: on macOS 12+ the AirPlay Receiver listens on 5000 and answers
// every request with 403 Forbidden, which looks exactly like a broken login.
const API = process.env.AGENTRY_API || "http://localhost:5001";

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API, changeOrigin: false },
      "/webhooks": { target: API, changeOrigin: false },
      "/healthz": { target: API, changeOrigin: false },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
