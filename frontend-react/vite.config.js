import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";


// Set base path for GitHub Pages deployment
const base = "/pinescripts/";

export default defineConfig({
  plugins: [react()],
  base,
});
