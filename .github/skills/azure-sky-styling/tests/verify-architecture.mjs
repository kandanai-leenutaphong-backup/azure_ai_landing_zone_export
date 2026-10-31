import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { preview } from "vite";
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const output = process.env.AZURE_SKY_ARCHITECTURE_ARTIFACT_DIR || "/tmp/azure-sky-architecture-review";
await mkdir(output, { recursive: true });
const server = await preview({ preview: { host: "127.0.0.1", port: 0, strictPort: true }, logLevel: "error" });
const address = server.httpServer.address();
assert.ok(address && typeof address !== "string");
const browser = await chromium.launch();
const cases = [];
const measurements = [];
const errors = [];
async function check(name, run) {
  await run();
  cases.push({ name, status: "PASS" });
  console.log(`PASS: ${name}`);
}
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const maskRequests = [];
  const maskPattern = /\/(?:legeay-temple|challe-crowned-hall|challe-arcade)-[^/]+\.webp$/;
  page.on("request", request => { if (maskPattern.test(request.url())) maskRequests.push(request.url()); });
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  page.on("response", response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
  page.on("worker", worker => errors.push(`Unexpected worker: ${worker.url()}`));
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const backdrop = page.locator(".azs-distant-architecture");
  const image = backdrop.locator("img");
  const toggle = page.getByRole("button", { name: "Distant architecture", exact: true });
  const shuffle = page.getByRole("button", { name: "Generate new distant architecture", exact: true });
  async function loaded() {
    await image.waitFor();
    await image.evaluate(element => element.decode());
    await page.evaluate(() => document.fonts.ready);
  }
  await page.goto(`${baseUrl}/?architecture=20260910`, { waitUntil: "domcontentloaded" });
  await loaded();
  await check("seeded background is decorative, decoded and bounded", async () => {
    assert.equal(await backdrop.getAttribute("data-architecture-seed"), "20260910");
    assert.equal(await backdrop.getAttribute("data-architecture-style"), "Painterly");
    assert.equal(await backdrop.getAttribute("data-mask-count"), "3");
    assert.equal(await backdrop.getAttribute("aria-hidden"), "true");
    assert.equal(await image.getAttribute("alt"), "");
    const paint = await backdrop.evaluate(element => ({ pointerEvents: getComputedStyle(element).pointerEvents, position: getComputedStyle(element).position, opacity: getComputedStyle(element).opacity, animation: getComputedStyle(element).animationName }));
    assert.equal(paint.pointerEvents, "none");
    assert.equal(paint.position, "fixed");
    assert.equal(paint.animation, "none");
    assert.equal(await page.locator("canvas").count(), 0);
    assert.equal(maskRequests.length, 3);
    assert.equal(new Set(maskRequests).size, 3);
    assert.ok(maskRequests.every(url => new URL(url).origin === baseUrl));
    const assets = await readdir(new URL("../dist/assets/", import.meta.url));
    assert.equal(assets.filter(filename => /^(legeay-temple|challe-crowned-hall|challe-arcade)-.*\.webp$/.test(filename)).length, 3);
    assert.deepEqual(assets.filter(filename => /original|\.jpe?g$/i.test(filename)), []);
    const credits = await page.request.get(`${baseUrl}/THIRD_PARTY_NOTICES.txt`);
    assert.equal(credits.status(), 200);
    const text = await credits.text();
    assert.ok(text.includes("Jean Laurent Legeay") && text.includes("Charles Michel Ange Challe") && text.includes("public-domain"));
    measurements.push({ kind: "backdrop", seed: 20260910, ...paint, renderMilliseconds: Number(await backdrop.getAttribute("data-render-ms")) });
  });

  await check("Painterly and Geometric compare at the same seed without reloading masks", async () => {
    const painterly = await image.getAttribute("src");
    const panel = await page.locator(".azs-three-surfaces").boundingBox();
    const style = page.getByRole("group", { name: "Architecture style", exact: true });
    assert.equal(await style.getByRole("button", { name: "Painterly", exact: true }).getAttribute("aria-pressed"), "true");
    await style.getByRole("button", { name: "Geometric", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".azs-distant-architecture").dataset.architectureStyle === "Geometric");
    await loaded();
    assert.equal(await backdrop.getAttribute("data-architecture-seed"), "20260910");
    assert.equal(await backdrop.getAttribute("data-mask-count"), "0");
    assert.notEqual(await image.getAttribute("src"), painterly);
    assert.deepEqual(await page.locator(".azs-three-surfaces").boundingBox(), panel);
    await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
    await page.screenshot({ path: resolve(output, "geometric-comparison-1440.png") });
    await style.getByRole("button", { name: "Painterly", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".azs-distant-architecture").dataset.architectureStyle === "Painterly");
    await loaded();
    assert.equal(await image.getAttribute("src"), painterly);
    assert.equal(maskRequests.length, 3);
    await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
    await page.screenshot({ path: resolve(output, "painterly-comparison-1440.png") });
  });

  await check("hide/show changes exposed background pixels without changing panel geometry", async () => {
    const source = await image.getAttribute("src");
    const before = await page.locator(".azs-three-surfaces").boundingBox();
    const heading = await page.locator("#foundations-title").boundingBox();
    const clip = { x: 0, y: Math.floor(heading.y), width: 1440, height: Math.ceil(heading.height) };
    await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
    const shown = await page.screenshot({ clip });
    await toggle.click();
    assert.equal(await toggle.getAttribute("aria-pressed"), "false");
    assert.equal(await backdrop.isVisible(), false);
    assert.equal(await shuffle.isDisabled(), true);
    const hidden = await page.screenshot({ clip });
    assert.notDeepEqual(shown, hidden, "Silhouettes must affect actual visible page pixels");
    assert.deepEqual(await page.locator(".azs-three-surfaces").boundingBox(), before);
    await toggle.click();
    await loaded();
    assert.equal(await toggle.getAttribute("aria-pressed"), "true");
    assert.equal(await image.getAttribute("src"), source);
    assert.equal(await shuffle.isDisabled(), false);
  });

  await check("regenerated architecture replays exactly from its seed URL", async () => {
    const initial = await image.getAttribute("src");
    await shuffle.click();
    await page.waitForFunction(() => document.querySelector(".azs-distant-architecture").dataset.architectureSeed !== "20260910");
    await loaded();
    const nextSeed = await backdrop.getAttribute("data-architecture-seed");
    const nextImage = await image.getAttribute("src");
    assert.notEqual(nextImage, initial);
    await page.goto(`${baseUrl}/?architecture=${nextSeed}`, { waitUntil: "domcontentloaded" });
    await loaded();
    assert.equal(await backdrop.getAttribute("data-architecture-seed"), nextSeed);
    assert.equal(await image.getAttribute("src"), nextImage);
    await page.goto(`${baseUrl}/?architecture=20260910`, { waitUntil: "domcontentloaded" });
    await loaded();
    assert.equal(await image.getAttribute("src"), initial);
  });

  await check("material controls and scrolling do not redraw the bitmap", async () => {
    await page.evaluate(() => {
      window.architectureWrites = 0;
      window.architectureObserver = new MutationObserver(mutations => { window.architectureWrites += mutations.length; });
      window.architectureObserver.observe(document.querySelector(".azs-distant-architecture img"), { attributes: true, attributeFilter: ["src"] });
    });
    const source = await image.getAttribute("src");
    await page.getByRole("button", { name: "Pin Porcelain", exact: true }).click();
    await page.getByRole("button", { name: "Unpin Porcelain", exact: true }).click();
    await page.getByRole("button", { name: "Compact", exact: true }).click();
    await page.getByRole("button", { name: "Comfortable", exact: true }).click();
    await page.getByRole("link", { name: "Surface depth", exact: true }).click();
    await page.getByRole("checkbox", { name: "Broad sheen", exact: true }).check();
    await page.getByRole("button", { name: "Reset depth effects", exact: true }).click();
    assert.equal(await image.getAttribute("src"), source);
    assert.equal(await page.evaluate(() => window.architectureWrites), 0);
    await page.evaluate(() => { window.architectureObserver.disconnect(); window.scrollTo(0, 0); });
  });

  await check("exposed secondary labels remain readable over the distant silhouettes", async () => {
    const targets = [".azs-workbench-heading > .azs-eyebrow", ".azs-swatch .azs-muted", "#foundations .azs-section-tag"];
    for (const selector of targets) {
      const labels = page.locator(selector);
      for (let index = 0; index < await labels.count(); index += 1) {
        const label = labels.nth(index);
        const foreground = await label.evaluate(element => getComputedStyle(element).color.match(/[\d.]+/g).slice(0, 3).map(Number));
        await label.evaluate(element => { element.style.visibility = "hidden"; });
        const bounds = await label.boundingBox();
        const background = await page.screenshot({ clip: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height } });
        await label.evaluate(element => { element.style.visibility = ""; });
        const contrast = await page.evaluate(async ({ encoded, foreground }) => {
          const image = new Image();
          image.src = `data:image/png;base64,${encoded}`;
          await image.decode();
          const canvas = document.createElement("canvas");
          canvas.width = image.naturalWidth;
          canvas.height = image.naturalHeight;
          const context = canvas.getContext("2d");
          context.drawImage(image, 0, 0);
          const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          const luminance = channels => channels.map(channel => channel / 255).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4).reduce((sum, channel, position) => sum + channel * [.2126, .7152, .0722][position], 0);
          const text = luminance(foreground);
          let minimum = Infinity;
          for (let offset = 0; offset < pixels.length; offset += 4) minimum = Math.min(minimum, (luminance([...pixels.slice(offset, offset + 3)]) + .05) / (text + .05));
          return minimum;
        }, { encoded: background.toString("base64"), foreground });
        assert.ok(contrast >= 4.5, `${selector} ${index}: ${contrast}`);
        measurements.push({ selector, index, minimumTextContrast: contrast });
      }
    }
  });

  for (const [width, height] of [[360, 800], [768, 1024], [1440, 900], [1920, 1080]]) {
    await check(`responsive framing and controls ${width}x${height}`, async () => {
      await page.setViewportSize({ width, height });
      await page.waitForFunction(({ width, height }) => {
        const image = document.querySelector(".azs-distant-architecture img");
        const scale = Math.min(1, 1600 / width, 1100 / height);
        return image.naturalWidth === Math.round(width * scale) && image.naturalHeight === Math.round(height * scale);
      }, { width, height });
      await loaded();
      const bounds = await backdrop.boundingBox();
      assert.equal(bounds.width, width);
      assert.equal(bounds.height, height);
      assert.equal(bounds.x, 0);
      assert.equal(bounds.y, 0);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if (width === 360) {
        for (const control of [toggle, shuffle]) {
          const target = await control.boundingBox();
          assert.ok(target.width >= 44 && target.height >= 44);
        }
      }
      await page.evaluate(() => { document.activeElement instanceof HTMLElement && document.activeElement.blur(); window.scrollTo(0, 0); });
      await page.screenshot({ path: resolve(output, `architecture-${width}.png`) });
      if (width === 360 || width === 1440) {
        const audit = await new AxeBuilder({ page }).include(".azs-workbench-heading").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(audit.violations.map(issue => ({ id: issue.id, nodes: issue.nodes.map(node => node.target) })), []);
      }
      measurements.push({ viewport: `${width}x${height}`, renderMilliseconds: Number(await backdrop.getAttribute("data-render-ms")), bitmap: await image.evaluate(element => [element.naturalWidth, element.naturalHeight]) });
    });
  }
  await check("keyboard access and transparency/forced-color fallbacks", async () => {
    await toggle.focus();
    await page.keyboard.press("Space");
    assert.equal(await toggle.getAttribute("aria-pressed"), "false");
    assert.equal(await toggle.evaluate(element => getComputedStyle(element).outlineStyle), "solid");
    await page.keyboard.press("Space");
    const session = await context.newCDPSession(page);
    await session.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] });
    assert.equal(await backdrop.isVisible(), false);
    await session.send("Emulation.setEmulatedMedia", { features: [] });
    await session.detach();
    assert.equal(await backdrop.isVisible(), true);
    await page.emulateMedia({ forcedColors: "active" });
    assert.equal(await backdrop.isVisible(), false);
    await page.emulateMedia({ forcedColors: "none" });
    assert.equal(await backdrop.isVisible(), true);
  });
  await check("failed painterly assets use an explicit geometric fallback and regenerate retries", async () => {
    const failureContext = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
    try {
      const failedPage = await failureContext.newPage();
      failedPage.setDefaultTimeout(10000);
      await failedPage.route(maskPattern, route => route.abort("failed"));
      await failedPage.goto(`${baseUrl}/?architecture=20260910`, { waitUntil: "domcontentloaded" });
      await failedPage.waitForFunction(() => document.querySelector(".azs-distant-architecture")?.dataset.architectureStyle === "Geometric");
      await failedPage.getByText("Painterly masks unavailable. Showing geometric architecture.", { exact: true }).waitFor();
      assert.equal(await failedPage.locator(".azs-distant-architecture").getAttribute("data-mask-count"), "0");
      await failedPage.locator(".azs-distant-architecture img").evaluate(element => element.decode());
      await failedPage.unroute(maskPattern);
      await failedPage.getByRole("button", { name: "Generate new distant architecture", exact: true }).click();
      await failedPage.waitForFunction(() => document.querySelector(".azs-distant-architecture").dataset.architectureStyle === "Painterly");
      assert.equal(await failedPage.locator(".azs-distant-architecture").getAttribute("data-mask-count"), "3");
    } finally { await failureContext.close(); }
  });
  await check("late mask decoding cannot overwrite a newer geometric selection", async () => {
    const delayedContext = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
    let release;
    const gate = new Promise(resolveGate => { release = resolveGate; });
    let requested;
    const requestSeen = new Promise(resolveSeen => { requested = resolveSeen; });
    try {
      const delayedPage = await delayedContext.newPage();
      delayedPage.setDefaultTimeout(10000);
      const heldMask = /\/legeay-temple-[^/]+\.webp$/;
      await delayedPage.route(heldMask, async route => { requested(); await gate; await route.continue(); });
      await delayedPage.goto(`${baseUrl}/?architecture=20260910`, { waitUntil: "domcontentloaded" });
      await requestSeen;
      const styles = delayedPage.getByRole("group", { name: "Architecture style", exact: true });
      await styles.getByRole("button", { name: "Geometric", exact: true }).click();
      await delayedPage.waitForFunction(() => document.querySelector(".azs-distant-architecture").dataset.architectureStyle === "Geometric");
      const geometric = await delayedPage.locator(".azs-distant-architecture img").getAttribute("src");
      const completion = delayedPage.waitForResponse(response => heldMask.test(response.url()));
      release();
      await (await completion).finished();
      await delayedPage.evaluate(() => new Promise(requestAnimationFrame));
      assert.equal(await delayedPage.locator(".azs-distant-architecture").getAttribute("data-architecture-style"), "Geometric");
      assert.equal(await delayedPage.locator(".azs-distant-architecture img").getAttribute("src"), geometric);
      await styles.getByRole("button", { name: "Painterly", exact: true }).click();
      await delayedPage.waitForFunction(() => document.querySelector(".azs-distant-architecture").dataset.architectureStyle === "Painterly");
      assert.equal(await delayedPage.locator(".azs-distant-architecture").getAttribute("data-mask-count"), "3");
    } finally { release(); await delayedContext.close(); }
  });
  assert.deepEqual(errors, []);
  const artifact = createHash("sha256").update(await readFile(new URL("../dist/index.html", import.meta.url))).digest("hex");
  await writeFile(resolve(output, "report.json"), JSON.stringify({ status: "PASS", artifact, cases, measurements, errors }, null, 2) + "\n");
  console.log(`regression PASS: ${cases.length}/${cases.length} architecture cases, 0 runtime errors; artifact ${artifact.slice(0, 12)}; evidence ${output}`);
} catch (error) {
  await writeFile(resolve(output, "failure.json"), JSON.stringify({ error: String(error), cases, measurements, errors }, null, 2) + "\n");
  throw error;
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.httpServer.close(error => error ? rejectClose(error) : resolveClose()));
}