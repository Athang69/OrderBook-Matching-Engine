import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the frontend runs on port 5173 and forwards API calls to the backend.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/v1": { target: "http://127.0.0.1:8000", ws: true },
    },
  },
});
