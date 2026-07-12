import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const defaultAllowedHosts = [
  "story.soremekun.org",
  "144.126.234.61",
  "localhost",
  "127.0.0.1",
];

const extraAllowedHosts = (process.env.FRONTEND_ALLOWED_HOSTS ?? process.env.VITE_ALLOWED_HOSTS ?? "")
  .split(",")
  .map((host) => host.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: [...new Set([...defaultAllowedHosts, ...extraAllowedHosts])],
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    restoreMocks: true,
  },
});
