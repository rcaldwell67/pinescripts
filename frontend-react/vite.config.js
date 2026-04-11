import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";


// Set base path for GitHub Pages deployment
const base = "/pinescripts/";

export default defineConfig({
  plugins: [react()],
  base,
  server: {
    middlewareMode: false,
    configureServer: (server) => {
      server.middlewares.use((req, res, next) => {
        if (req.url && req.url.endsWith('.wasm')) {
          res.setHeader('Content-Type', 'application/wasm');
        }
        next();
      });
    },
  },
  build: {
    outDir: '../docs', // Output to top-level docs/ for GitHub Pages
    emptyOutDir: true,
  },
});
