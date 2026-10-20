import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.VITE_BACKEND_URL || "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      port: 3000,
      host: "0.0.0.0",
      // Same-origin API calls in development; SSE streaming passes straight through.
      proxy: { "/api": { target: backend, changeOrigin: true } },
    },
    preview: { port: 3000 },
  };
});
