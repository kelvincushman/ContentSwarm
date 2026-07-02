import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base './' so built assets load correctly when served from the FastAPI mount.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
  server: { proxy: { "/devices": "http://localhost:8770", "/apps": "http://localhost:8770", "/onboard": "http://localhost:8770", "/registry": "http://localhost:8770", "/config": "http://localhost:8770", "/integration": "http://localhost:8770", "/health": "http://localhost:8770" } },
});
