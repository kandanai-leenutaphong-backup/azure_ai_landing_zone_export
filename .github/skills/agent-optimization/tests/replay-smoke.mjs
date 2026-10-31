import assert from "node:assert/strict";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const screenshots = await mkdtemp(join(tmpdir(), "agent-optimization-replay-"));
const server = await createServer({ root, configFile: false, esbuild: { jsx: "automatic" },
  optimizeDeps: { esbuildOptions: { jsx: "automatic" } },
  server: { host: "127.0.0.1", port: 0, strictPort: true } });
await server.listen();
const address = server.httpServer.address();
let browser;
try {
  browser = await chromium.launch({ headless: true });
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    page.setDefaultTimeout(5000);
    const errors = [];
    page.on("pageerror", error => { errors.push(error.message); console.error(error.message); });
    await page.route("**/*", route => new URL(route.request().url()).hostname === "127.0.0.1" ? route.continue() : route.abort());
    await page.goto(`http://127.0.0.1:${address.port}/examples/replay/`);
    await page.getByRole("button", { name: "Open recorded runs" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.locator('[aria-label="best training run"]').waitFor({ state: "visible" });
    await dialog.locator("details").first().locator("summary").click();
    await dialog.locator("pre").first().waitFor({ state: "visible" });
    assert.match(await dialog.locator("pre").first().innerText(), /Synthetic classification instructions/);
    await dialog.getByRole("tab", { name: "Evaluation", exact: true }).click();
    await dialog.locator('[aria-label="best evaluation run"]').waitFor({ state: "visible" });
    const geometry = await dialog.evaluate(element => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
        scrollWidth: element.scrollWidth, clientWidth: element.clientWidth };
    });
    assert.ok(geometry.left >= 0 && geometry.right <= viewport.width && geometry.top >= 0 && geometry.bottom <= viewport.height);
    assert.ok(geometry.scrollWidth <= geometry.clientWidth + 1, JSON.stringify(geometry));
    assert.ok((await page.evaluate(() => window.replayReads)).some(path => path.includes("/training/")));
    assert.ok((await page.evaluate(() => window.replayReads)).some(path => path.includes("/evaluation/")));
    await page.screenshot({ path: join(screenshots, `replay-${viewport.width}.png`), fullPage: true });
    await dialog.getByRole("button", { name: "Close run replay" }).click();
    await dialog.waitFor({ state: "detached" });
    assert.deepEqual(errors, []);
    await page.close();
    console.log(`PASS replay ${viewport.width}x${viewport.height}: public exports, stage reads, source viewer, close, geometry`);
  }
  console.log(`REPLAY_SCREENSHOTS=${screenshots}`);
} finally {
  await browser?.close();
  await server.close();
}