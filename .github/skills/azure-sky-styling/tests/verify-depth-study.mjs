import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { preview } from "vite";
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const effects = [
  ["grain", "Static grain"], ["edge-light", "Edge light"], ["shadow", "Layered shadow"],
  ["blue-shading", "Blue shading"], ["sheen", "Broad sheen"], ["tonal-ground", "Tonal ground"],
];
const output = process.env.AZURE_SKY_DEPTH_ARTIFACT_DIR || "/tmp/azure-sky-depth-review";
await mkdir(output, { recursive: true });
const server = await preview({ preview: { host: "127.0.0.1", port: 0, strictPort: true }, logLevel: "error" });
const address = server.httpServer.address();
assert.ok(address && typeof address !== "string");
const browser = await chromium.launch({ headless: true });
const cases = [];
const measurements = [];
const errors = [];
async function check(name, run) {
  await run();
  cases.push({ name, status: "PASS" });
  console.log(`PASS: ${name}`);
}
async function comparePixels(page, original, modified) {
  return page.evaluate(async ({ original, modified }) => {
    async function decode(encoded) {
      const image = new Image();
      image.src = `data:image/png;base64,${encoded}`;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0);
      return context.getImageData(0, 0, canvas.width, canvas.height).data;
    }
    const left = await decode(original);
    const right = await decode(modified);
    if (left.length !== right.length) throw new Error("Pixel comparison dimensions changed");
    let changedPixels = 0;
    let totalDifference = 0;
    for (let offset = 0; offset < left.length; offset += 4) {
      const difference = Math.abs(left[offset] - right[offset]) + Math.abs(left[offset + 1] - right[offset + 1]) + Math.abs(left[offset + 2] - right[offset + 2]);
      if (difference > 0) changedPixels += 1;
      totalDifference += difference;
    }
    return { changedPixels, pixels: left.length / 4, meanChannelDifference: totalDifference / (left.length / 4 * 3) };
  }, { original: original.toString("base64"), modified: modified.toString("base64") });
}
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  page.on("response", response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
  page.on("worker", worker => errors.push(`Unexpected rendering worker: ${worker.url()}`));
  await page.goto(`http://127.0.0.1:${address.port}/`, { waitUntil: "domcontentloaded" });
  await page.getByRole("link", { name: "Surface depth", exact: true }).click();
  await page.evaluate(() => document.fonts.ready);
  const study = page.getByRole("region", { name: "Surface depth", exact: true });
  const combined = study.locator('[data-depth-sample="combined"]');
  const baseline = study.locator('[data-depth-sample="baseline"]');
  const plane = study.locator(".azs-depth-comparison figure").nth(1).locator(".azs-depth-plane");
  const checkbox = name => study.getByRole("checkbox", { name, exact: true });
  const reset = () => study.getByRole("button", { name: "Reset depth effects", exact: true }).click();
  async function clearEffects() { for (const [, label] of effects) await checkbox(label).uncheck(); }
  async function captureStudy(name) {
    const viewport = page.viewportSize();
    const dismiss = page.getByRole("button", { name: "Dismiss notification", exact: true });
    if (await dismiss.count()) await dismiss.click();
    await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
    const fullHeight = Math.ceil(await study.evaluate(element => element.getBoundingClientRect().height)) + 160;
    await page.setViewportSize({ width: viewport.width, height: Math.max(viewport.height, fullHeight) });
    await study.evaluate(element => element.scrollIntoView({ block: "start", behavior: "instant" }));
    await study.screenshot({ path: resolve(output, `${name}.png`) });
    await page.setViewportSize(viewport);
    await study.evaluate(element => element.scrollIntoView({ block: "start", behavior: "instant" }));
    const titleVisible = await study.locator("h3").evaluate(element => {
      const bounds = element.getBoundingClientRect();
      const visible = document.elementFromPoint(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
      return visible === element || element.contains(visible);
    });
    assert.ok(titleVisible, "Depth heading must not be covered by sticky navigation");
    await page.screenshot({ path: resolve(output, `${name}-viewport.png`) });
  }

  await check("six named isolated effects and four-effect default", async () => {
    assert.equal(await study.locator(".azs-depth-isolates article").count(), 6);
    assert.equal(await combined.getAttribute("data-effects"), "grain edge-light shadow blue-shading");
    assert.equal(await study.locator("#azs-depth-grain-opacity").inputValue(), "3");
    assert.equal(await combined.evaluate(element => getComputedStyle(element, "::before").opacity), "0.03");
    assert.equal(await baseline.getAttribute("data-effects"), "");
    for (const [id, label] of effects) {
      const tile = study.getByRole("article", { name: label, exact: true });
      assert.ok(await tile.isVisible());
      assert.equal(await tile.locator("[data-depth-sample]").getAttribute("data-effects"), id);
      assert.equal(await tile.locator(".azs-depth-class-name").innerText(), `.azs-depth-${id}`);
    }
    assert.equal(await page.locator("canvas").count(), 0);
  });

  await check("each toggle changes rendered pixels without changing sample dimensions", async () => {
    await clearEffects();
    const original = await plane.screenshot();
    const bounds = await combined.boundingBox();
    for (const [id, label] of effects) {
      await checkbox(label).check();
      const next = await combined.boundingBox();
      assert.equal(next.width, bounds.width);
      assert.equal(next.height, bounds.height);
      const pixels = await comparePixels(page, original, await plane.screenshot());
      assert.ok(pixels.changedPixels > 0, `${label} must visibly paint, not just add a class`);
      measurements.push({ effect: id, ...pixels });
      assert.equal(await combined.evaluate(element => getComputedStyle(element).opacity), "1");
      assert.equal(await page.locator(".azs-topbar").evaluate(element => getComputedStyle(element, "::before").opacity), "0.03", "Study toggles must not change the standard gallery material");
      await checkbox(label).uncheck();
    }
    assert.equal((await comparePixels(page, original, await plane.screenshot())).changedPixels, 0);
    assert.ok(await study.locator("#azs-depth-grain-opacity").isDisabled());
    await reset();
  });

  await check("isolated and combined copy recipes, grain range, and reset", async () => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    for (const [id, label] of effects) {
      await study.getByRole("button", { name: `Copy ${label.toLowerCase()} recipe`, exact: true }).click();
      const recipe = await page.evaluate(() => navigator.clipboard.readText());
      assert.ok(recipe.includes('href="./frontend/depth-effects.css"'));
      assert.ok(recipe.includes("azs-depth-surface"));
      assert.ok(recipe.includes(`azs-depth-${id}`));
      for (const [other] of effects.filter(([other]) => other !== id)) assert.ok(!recipe.includes(`azs-depth-${other} `) && !recipe.includes(`azs-depth-${other}"`));
      if (id === "tonal-ground") assert.ok(recipe.includes('<div class="azs-depth-tonal-ground" style="padding: 24px">'));
    }
    const range = study.locator("#azs-depth-grain-opacity");
    await range.focus();
    await page.keyboard.press("End");
    assert.equal(await range.inputValue(), "8");
    assert.equal(await combined.evaluate(element => getComputedStyle(element, "::before").opacity), "0.08");
    await study.getByRole("button", { name: "Copy combined depth recipe", exact: true }).click();
    assert.ok((await page.evaluate(() => navigator.clipboard.readText())).includes("--azs-depth-grain-opacity: 0.08"));
    assert.equal(await page.locator(".azs-topbar").evaluate(element => getComputedStyle(element, "::before").opacity), "0.03");
    await reset();
    assert.equal(await range.inputValue(), "3");
    assert.equal(await combined.getAttribute("data-effects"), "grain edge-light shadow blue-shading");
    await study.getByRole("button", { name: "Copy combined depth recipe", exact: true }).click();
    assert.ok((await page.evaluate(() => navigator.clipboard.readText())).includes("--azs-depth-grain-opacity: 0.03"));
  });

  await check("clipboard refusal exposes the exact isolated recipe", async () => {
    await page.evaluate(() => Object.defineProperty(navigator.clipboard, "writeText", { configurable: true, value: async () => { throw new Error("Clipboard refusal fixture"); } }));
    await study.getByRole("button", { name: "Copy broad sheen recipe", exact: true }).click();
    await study.locator(".azs-depth-recipe[open]").waitFor();
    assert.ok((await study.locator("pre code").innerText()).includes('class="azs-depth-surface azs-depth-sheen"'));
    assert.ok(await page.getByText("Clipboard unavailable. Recipe shown in the code panel.", { exact: true }).isVisible());
    await page.evaluate(() => { delete navigator.clipboard.writeText; });
    await reset();
    assert.equal(await study.locator(".azs-depth-recipe[open]").count(), 0);
  });

  await check("maximum grain plus all layers preserves normal-text contrast", async () => {
    for (const [, label] of effects) await checkbox(label).check();
    await study.locator("#azs-depth-grain-opacity").focus();
    await page.keyboard.press("End");
    await combined.evaluate(element => { for (const child of element.children) child.style.visibility = "hidden"; });
    const screenshot = await combined.screenshot();
    await combined.evaluate(element => { for (const child of element.children) child.style.visibility = ""; });
    const contrast = await page.evaluate(async encoded => {
      const image = new Image();
      image.src = `data:image/png;base64,${encoded}`;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let minimum = Infinity;
      for (let row = 8; row < canvas.height - 8; row += 1) {
        for (let column = 8; column < canvas.width - 8; column += 1) {
          const offset = (row * canvas.width + column) * 4;
          const linear = [...pixels.slice(offset, offset + 3)].map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
          const luminance = linear.reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
          minimum = Math.min(minimum, 1.05 / (luminance + .05));
        }
      }
      return minimum;
    }, screenshot.toString("base64"));
    assert.ok(contrast >= 4.5, `White on brightest rendered surface: ${contrast}`);
    measurements.push({ contrast: "white on all effects at 8% grain, rendered interior pixels", minimum: contrast });
    const audit = await new AxeBuilder({ page }).include("#depth").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    assert.deepEqual(audit.violations.map(issue => ({ id: issue.id, nodes: issue.nodes.map(node => node.target) })), []);
    await captureStudy("depth-all-effects-1440");
    await reset();
  });

  await check("keyboard checkbox operation, visible focus and recipe disclosure", async () => {
    const grain = checkbox("Static grain");
    await grain.focus();
    await page.keyboard.press("Space");
    assert.equal(await grain.isChecked(), false);
    assert.equal(await grain.evaluate(element => getComputedStyle(element).outlineStyle), "solid");
    await page.keyboard.press("Space");
    await study.locator("summary").focus();
    await page.keyboard.press("Enter");
    await study.locator(".azs-depth-recipe[open]").waitFor();
    assert.ok((await study.locator("pre code").innerText()).includes("azs-depth-grain"));
    await page.keyboard.press("Enter");
    await reset();
  });

  for (const [width, height] of [[360, 800], [768, 1024], [1440, 900], [1920, 1080]]) {
    await check(`responsive depth geometry and screenshot ${width}x${height}`, async () => {
      await page.setViewportSize({ width, height });
      const geometry = await study.evaluate(element => {
        const samples = [...element.querySelectorAll(".azs-depth-sample")];
        return {
          viewport: innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          contained: samples.every(sample => {
            const surface = sample.getBoundingClientRect();
            const plane = sample.parentElement.getBoundingClientRect();
            return surface.left >= plane.left && surface.right <= plane.right && surface.top >= plane.top && surface.bottom <= plane.bottom;
          }),
          clippedText: [...element.querySelectorAll("h3,h4,h5,button,output,summary,.azs-depth-class-name")].filter(item => item.clientWidth > 0 && item.scrollWidth > item.clientWidth + 1).map(item => item.textContent),
          overlaps: samples.flatMap(sample => {
            const title = sample.querySelector("h4").getBoundingClientRect();
            const eyebrow = sample.querySelector(".azs-eyebrow").getBoundingClientRect();
            const footer = sample.querySelector(".azs-depth-sample-footer").getBoundingClientRect();
            return title.top < eyebrow.bottom || title.bottom > footer.top ? [sample.dataset.depthSample] : [];
          }),
          shortTargets: [...element.querySelectorAll("button,.azs-depth-toggle,summary,input[type=range]")].filter(item => item.getBoundingClientRect().height < 43.9).map(item => item.getAttribute("aria-label") || item.textContent),
        };
      });
      assert.ok(geometry.scrollWidth <= width);
      assert.ok(geometry.contained);
      assert.deepEqual(geometry.clippedText, []);
      assert.deepEqual(geometry.overlaps, []);
      if (width === 360) assert.deepEqual(geometry.shortTargets, []);
      const original = await baseline.boundingBox();
      const modified = await combined.boundingBox();
      assert.equal(original.width, modified.width);
      assert.equal(original.height, modified.height);
      measurements.push({ viewport: `${width}x${height}`, ...geometry });
      if (width === 360 || width === 1440) {
        const audit = await new AxeBuilder({ page }).include("#depth").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(audit.violations.map(issue => ({ id: issue.id, nodes: issue.nodes.map(node => node.target) })), []);
      }
      await captureStudy(`depth-${width}`);
    });
  }
  await check("production reduced-transparency and forced-colors fallbacks", async () => {
    const session = await context.newCDPSession(page);
    await session.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] });
    assert.ok(await page.evaluate(() => matchMedia("(prefers-reduced-transparency: reduce)").matches));
    assert.equal(await combined.evaluate(element => getComputedStyle(element, "::before").display), "none");
    assert.equal(await page.locator(".azs-topbar").evaluate(element => getComputedStyle(element, "::before").display), "none");
    assert.ok(!(await combined.evaluate(element => getComputedStyle(element).backgroundImage)).includes("115deg"));
    await session.send("Emulation.setEmulatedMedia", { features: [] });
    await session.detach();
    await page.emulateMedia({ forcedColors: "active" });
    assert.equal(await combined.evaluate(element => getComputedStyle(element).backgroundImage), "none");
    assert.equal(await combined.evaluate(element => getComputedStyle(element).boxShadow), "none");
    assert.equal(await combined.evaluate(element => getComputedStyle(element, "::before").display), "none");
    assert.ok(!(await page.locator(".azs-topbar").evaluate(element => getComputedStyle(element).backgroundImage)).includes("gradient"));
    assert.equal(await page.locator(".azs-topbar").evaluate(element => getComputedStyle(element, "::before").display), "none");
    await captureStudy("depth-forced-colors");
    await page.emulateMedia({ forcedColors: "none" });
  });
  assert.deepEqual(errors, []);
  const artifact = createHash("sha256").update(await readFile(new URL("../dist/index.html", import.meta.url))).digest("hex");
  await writeFile(resolve(output, "report.json"), JSON.stringify({ status: "PASS", artifact, cases, measurements, errors }, null, 2) + "\n");
  console.log(`regression PASS: ${cases.length}/${cases.length} depth cases, 0 runtime errors; artifact ${artifact.slice(0, 12)}; evidence ${output}`);
} catch (error) {
  await writeFile(resolve(output, "failure.json"), JSON.stringify({ error: String(error), cases, measurements, errors }, null, 2) + "\n");
  throw error;
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.httpServer.close(error => error ? rejectClose(error) : resolveClose()));
}