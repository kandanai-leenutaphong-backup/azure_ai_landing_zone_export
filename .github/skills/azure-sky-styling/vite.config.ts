import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { rollupOptions: { input: { main: fileURLToPath(new URL("./index.html", import.meta.url)), plain: fileURLToPath(new URL("./plain.html", import.meta.url)), "security-review": fileURLToPath(new URL("./security-review.html", import.meta.url)) } } },
  server: { host: "127.0.0.1", port: 4317, strictPort: true },
  preview: { host: "127.0.0.1", port: 4318, strictPort: true },
});