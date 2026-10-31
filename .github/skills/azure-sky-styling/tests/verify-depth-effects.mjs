import assert from "node:assert/strict";
import { createServer as createHttpServer } from "node:http";
import { createServer } from "vite";
import { chromium } from "playwright";

const server = await createServer({ server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const httpServer = createHttpServer(server.middlewares);
await new Promise(resolve => httpServer.listen(0, "127.0.0.1", resolve));
const address = httpServer.address();
assert.ok(address && typeof address !== "string");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
  page.setDefaultTimeout(10000);
  await page.goto(`http://127.0.0.1:${address.port}/plain.html`, { waitUntil: "domcontentloaded" });
  await page.setContent(`<link rel="stylesheet" href="/frontend/depth-effects.css">
    <div id="ground" style="padding:32px"><div id="sample" class="azs-depth-surface" style="width:320px;height:160px;padding:24px;box-sizing:border-box">Azure Sky</div></div>`);
  await page.waitForFunction(() => getComputedStyle(document.querySelector("#sample")).backgroundColor === "rgb(18, 63, 145)");
  const sample = page.locator("#sample");
  const bounds = await sample.boundingBox();
  const effects = ["grain", "edge-light", "shadow", "blue-shading", "sheen"];
  for (const effect of effects) {
    await sample.evaluate((element, name) => { element.className = `azs-depth-surface azs-depth-${name}`; }, effect);
    assert.deepEqual(await sample.boundingBox(), bounds, `${effect}: geometry must stay fixed`);
    const style = await sample.evaluate(element => {
      const paint = getComputedStyle(element);
      const grain = getComputedStyle(element, "::before");
      return { image: paint.backgroundImage, shadow: paint.boxShadow, opacity: paint.opacity, color: paint.color, grain: grain.backgroundImage, grainOpacity: grain.opacity };
    });
    assert.equal(style.opacity, "1");
    assert.equal(style.color, "rgb(255, 255, 255)");
    if (effect === "grain") {
      assert.ok(style.grain.includes("surface-grain.png"));
      assert.equal(style.grainOpacity, "0.03");
      await page.evaluate(async () => {
        const image = new Image();
        image.src = "/frontend/assets/surface-grain.png";
        await image.decode();
        if (image.naturalWidth !== 128 || image.naturalHeight !== 128) throw new Error("Invalid grain dimensions");
      });
    }
    if (effect === "edge-light") assert.ok(style.shadow.includes("inset"));
    if (effect === "shadow") assert.ok(style.shadow.includes("16px"));
    if (["blue-shading", "sheen"].includes(effect)) assert.ok(style.image.includes("linear-gradient"));
    console.log(`PASS: isolated ${effect}; fixed bounds and opaque text`);
  }
  await page.locator("#ground").evaluate(element => element.classList.add("azs-depth-tonal-ground"));
  assert.equal(await page.locator("#ground").evaluate(element => getComputedStyle(element).backgroundColor), "rgb(220, 232, 245)");
  assert.deepEqual(await sample.boundingBox(), bounds);
  console.log("PASS: isolated tonal ground; surface geometry unchanged");
  await sample.evaluate((element, names) => { element.className = `azs-depth-surface ${names.map(name => `azs-depth-${name}`).join(" ")}`; }, effects);
  const combined = await sample.evaluate(element => ({ image: getComputedStyle(element).backgroundImage, shadow: getComputedStyle(element).boxShadow, grain: getComputedStyle(element, "::before").backgroundImage }));
  assert.ok(combined.image.includes("115deg") && combined.image.includes("155deg"));
  assert.ok(combined.shadow.includes("inset") && combined.shadow.includes("16px"));
  assert.ok(combined.grain.includes("surface-grain.png"));
  assert.deepEqual(await sample.boundingBox(), bounds);
  console.log("PASS: combined effects preserve every independent paint layer");
  await sample.evaluate(element => { element.className = "azs-depth-surface azs-depth-grain azs-depth-edge-light azs-depth-shadow azs-depth-blue-shading"; });
  const selectedPaint = await sample.evaluate(element => ({ background: getComputedStyle(element).backgroundImage, shadow: getComputedStyle(element).boxShadow, grain: getComputedStyle(element, "::before").backgroundImage, opacity: getComputedStyle(element, "::before").opacity }));
  await sample.evaluate(element => { element.className = "azs-depth-surface azs-depth-standard"; });
  const standardPaint = await sample.evaluate(element => ({ background: getComputedStyle(element).backgroundImage, shadow: getComputedStyle(element).boxShadow, grain: getComputedStyle(element, "::before").backgroundImage, opacity: getComputedStyle(element, "::before").opacity }));
  assert.deepEqual(standardPaint, selectedPaint);
  assert.equal(standardPaint.opacity, "0.03");
  assert.deepEqual(await sample.boundingBox(), bounds);
  console.log("PASS: standard preset exactly matches the four effects at 3% grain");
  await page.emulateMedia({ forcedColors: "active" });
  assert.equal(await sample.evaluate(element => getComputedStyle(element).backgroundImage), "none");
  assert.equal(await sample.evaluate(element => getComputedStyle(element, "::before").display), "none");
  console.log("PASS: forced-colors fallback removes decorative paint");
  await page.emulateMedia({ forcedColors: "none" });
  await page.setContent(`<link rel="stylesheet" href="/frontend/azure-sky.css">
    <div class="azure-sky"><header class="azs-topbar">Azure Sky</header>
      <button class="azs-button" id="primary">Primary</button>
      <button class="azs-button azs-button-danger" id="danger">Remove</button>
      <button class="azs-button azs-button-secondary" id="secondary">Secondary</button>
      <button class="azs-button" id="disabled" disabled>Disabled</button>
      <div class="azs-depth-surface" id="baseline">Baseline</div>
    </div>`);
  await page.waitForFunction(() => getComputedStyle(document.querySelector(".azs-topbar"), "::before").opacity === "0.03");
  for (const selector of [".azs-topbar", "#primary"]) {
    const paint = await page.locator(selector).evaluate(element => ({ background: getComputedStyle(element).backgroundImage, shadow: getComputedStyle(element).boxShadow, grain: getComputedStyle(element, "::before").backgroundImage, opacity: getComputedStyle(element, "::before").opacity }));
    assert.deepEqual(paint, standardPaint);
  }
  for (const selector of ["#danger", "#disabled", "#baseline"]) assert.equal(await page.locator(selector).evaluate(element => getComputedStyle(element, "::before").content), "none");
  assert.equal(await page.locator("#secondary").evaluate(element => getComputedStyle(element, "::before").opacity), "0.02");
  assert.equal(await page.locator("#baseline").evaluate(element => getComputedStyle(element).backgroundImage), "none, none");
  assert.equal(await page.locator("#danger").evaluate(element => getComputedStyle(element).backgroundColor), "rgb(181, 54, 74)");
  console.log("PASS: theme blue roles reuse the preset; semantic buttons and baseline stay unchanged");
  await page.setContent(`<link rel="stylesheet" href="/frontend/depth-effects.css">
    <div id="light" style="width:320px;height:160px;padding:24px;box-sizing:border-box;background-color:#eff3f8">Cloud</div>`);
  const light = page.locator("#light");
  const lightBounds = await light.boundingBox();
  await light.evaluate(element => element.classList.add("azs-depth-stain"));
  await page.waitForFunction(() => getComputedStyle(document.querySelector("#light")).backgroundImage.includes("112deg"));
  assert.equal(await light.evaluate(element => getComputedStyle(element, "::before").content), "none");
  assert.deepEqual(await light.boundingBox(), lightBounds);
  console.log("PASS: isolated light stain paints without grain or geometry changes");
  await light.evaluate(element => { element.className = "azs-depth-light"; element.style.backgroundColor = ""; });
  const lightPaint = await light.evaluate(element => ({ background: getComputedStyle(element).backgroundColor, image: getComputedStyle(element).backgroundImage, color: getComputedStyle(element).color, opacity: getComputedStyle(element).opacity, grain: getComputedStyle(element, "::before").opacity, blend: getComputedStyle(element, "::before").mixBlendMode }));
  assert.equal(lightPaint.background, "rgb(239, 243, 248)");
  assert.equal(lightPaint.color, "rgb(16, 45, 80)");
  assert.ok(lightPaint.image.includes("112deg") && lightPaint.image.includes("22deg"));
  assert.equal(lightPaint.opacity, "1");
  assert.equal(lightPaint.grain, "0.02");
  assert.equal(lightPaint.blend, "multiply");
  assert.deepEqual(await light.boundingBox(), lightBounds);
  console.log("PASS: Cloud light preset combines stain and 2% grain with opaque text");
  await page.emulateMedia({ forcedColors: "active" });
  assert.equal(await light.evaluate(element => getComputedStyle(element).backgroundImage), "none");
  assert.equal(await light.evaluate(element => getComputedStyle(element, "::before").display), "none");
  console.log("PASS: light material respects forced-color fallback");
} finally {
  await browser.close();
  await new Promise(resolve => httpServer.close(resolve));
  await server.close();
}