import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const metadata = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));
const dependencies = Object.keys({ ...metadata.dependencies, ...metadata.peerDependencies });

export default defineConfig({
  plugins: [react()],
  publicDir: false,
  base: "./",
  build: {
    outDir: "dist-library",
    assetsInlineLimit: 0,
    cssCodeSplit: false,
    rollupOptions: {
      input: fileURLToPath(new URL("./frontend/index.ts", import.meta.url)),
      preserveEntrySignatures: "strict",
      external: (identifier) => dependencies.some(name => identifier === name || identifier.startsWith(`${name}/`)),
      output: {
        format: "es",
        entryFileNames: "index.js",
        chunkFileNames: "[name]-[hash].js",
        assetFileNames: asset => asset.names.some(name => name.endsWith(".css"))
          ? "azure-sky.css" : "assets/[name]-[hash][extname]",
      },
    },
  },
});