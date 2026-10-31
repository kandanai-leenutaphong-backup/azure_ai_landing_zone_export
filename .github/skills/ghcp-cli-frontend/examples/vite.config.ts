import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

const root = fileURLToPath(new URL('.', import.meta.url))
const library = resolve(root, '..')
const output = process.env.GHCP_FRONTEND_BUILD_DIR
if (!output || !isAbsolute(output) || !relative(library, output).startsWith('..')) {
  throw new Error('GHCP_FRONTEND_BUILD_DIR must be an absolute output directory outside the library')
}

export default defineConfig({ root, build: { outDir: output, emptyOutDir: false } })