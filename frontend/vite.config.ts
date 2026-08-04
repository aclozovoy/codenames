import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Proxy backend calls to the FastAPI server (default http://localhost:8000) so the
// browser talks to the same origin — no CORS, and WebSockets work transparently.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/health": "http://localhost:8000",
      "/models": "http://localhost:8000",
      "/games": {
        target: "http://localhost:8000",
        ws: true, // needed for the /games/{id}/ws WebSocket
      },
    },
  },
});
