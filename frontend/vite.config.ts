import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the React app runs on :5173 and forwards /api to Django,
// so cookies (session + CSRF) stay same-origin — the same as production behind Caddy.
const target = process.env.API_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target, changeOrigin: false } } },
});
