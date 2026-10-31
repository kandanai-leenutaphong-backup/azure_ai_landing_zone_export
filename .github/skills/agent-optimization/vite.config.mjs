import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const frontendPackage = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));
const externalPackages = ["react-dom", ...Object.keys(frontendPackage.peerDependencies)];

export default {
  build: {
    outDir: "dist",
    emptyOutDir: true,
    lib: {
      entry: fileURLToPath(new URL("./frontend/index.ts", import.meta.url)),
      formats: ["es"],
      fileName: "agent-optimization",
      cssFileName: "optimization",
    },
    rollupOptions: {
      external: (specifier) => externalPackages.some(name => specifier === name || specifier.startsWith(`${name}/`)),
    },
  },
};