import assert from "node:assert/strict";
import { createServer as createHttpServer } from "node:http";
import { mkdir, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { createServer } from "vite";
import { chromium } from "playwright";

const server = await createServer({ server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const httpServer = createHttpServer(server.middlewares);
await new Promise(resolve => httpServer.listen(0, "127.0.0.1", resolve));
const address = httpServer.address();
assert.ok(address && typeof address !== "string");
const browser = await chromium.launch();
try {
  const manifest = JSON.parse(await readFile(new URL("../frontend/assets/painterly/manifest.json", import.meta.url), "utf8"));
  assert.equal(manifest.masks.length, 3);
  for (const [filename, expected] of [["painterly-mask-recipes.json", manifest.recipe_sha256], ["generate-painterly-masks.mjs", manifest.generator_sha256]]) {
    assert.equal(createHash("sha256").update(await readFile(new URL(`../scripts/${filename}`, import.meta.url))).digest("hex"), expected);
  }
  for (const mask of manifest.masks) {
    const bytes = await readFile(new URL(`../frontend/assets/painterly/${mask.filename}`, import.meta.url));
    assert.equal(createHash("sha256").update(bytes).digest("hex"), mask.sha256);
    const source = await readFile(new URL(`../research/painterly/holdings/originals/met-${mask.object_id}-original.jpg`, import.meta.url));
    assert.equal(createHash("sha256").update(source).digest("hex"), mask.source_sha256);
  }
  console.log("PASS: three derived masks match their manifest and original-source hashes");
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`http://127.0.0.1:${address.port}/plain.html`, { waitUntil: "domcontentloaded" });
  const result = await page.evaluate(async () => {
    const { generateDistantArchitecture, paintDistantArchitecture } = await import("/frontend/distantArchitecture.ts");
    const scene = generateDistantArchitecture(20260910);
    const second = generateDistantArchitecture(20260911);
    const canvas = document.createElement("canvas");
    const started = performance.now();
    const first = paintDistantArchitecture(canvas, scene, 1440, 900);
    const milliseconds = performance.now() - started;
    const repeat = paintDistantArchitecture(canvas, scene, 1440, 900);
    const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let visiblePixels = 0;
    let maximumAlpha = 0;
    for (let offset = 3; offset < pixels.length; offset += 4) {
      if (pixels[offset] > 0) visiblePixels += 1;
      maximumAlpha = Math.max(maximumAlpha, pixels[offset]);
    }
    const different = paintDistantArchitecture(canvas, second, 1440, 900);
    const image = new Image();
    image.src = first;
    await image.decode();
    document.body.replaceChildren(image);
    Object.assign(document.body.style, { margin: "0", background: "#eff3f8" });
    Object.assign(image.style, { display: "block", width: "100vw", height: "100vh" });
    return { scene, repeatScene: generateDistantArchitecture(20260910), second, deterministicPixels: first === repeat, differentPixels: first !== different, visiblePixels, maximumAlpha, milliseconds };
  });
  assert.deepEqual(result.scene, result.repeatScene);
  assert.notDeepEqual(result.scene, result.second);
  assert.equal(result.scene.edifices.length, 5);
  assert.ok(result.deterministicPixels && result.differentPixels);
  assert.ok(result.visiblePixels > 10000);
  assert.ok(result.maximumAlpha > 0 && result.maximumAlpha <= 32, "Distance layers must remain faint");
  await mkdir("/tmp/azure-sky-architecture-review", { recursive: true });
  await page.screenshot({ path: "/tmp/azure-sky-architecture-review/generator-1440.png" });
  console.log(`PASS: seed reproduces geometry and pixels; alternate seed changes both; five bounded edifices; ${result.visiblePixels} nontransparent pixels; max alpha ${result.maximumAlpha}/255; one render ${result.milliseconds.toFixed(2)}ms`);
  const painterly = await page.evaluate(async () => {
    const { generateDistantArchitecture, paintDistantArchitecture } = await import("/frontend/distantArchitecture.ts");
    const { loadPainterlyArchitectureMasks } = await import("/frontend/painterlyArchitecture.ts");
    const firstLoad = loadPainterlyArchitectureMasks();
    const sameLoad = loadPainterlyArchitectureMasks();
    const masks = await firstLoad;
    const canvas = document.createElement("canvas");
    const scene = generateDistantArchitecture(20260910);
    const first = paintDistantArchitecture(canvas, scene, 1440, 900, "#345a80", masks);
    const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let visiblePixels = 0;
    let maximumAlpha = 0;
    for (let offset = 3; offset < pixels.length; offset += 4) {
      if (pixels[offset] > 0) visiblePixels += 1;
      maximumAlpha = Math.max(maximumAlpha, pixels[offset]);
    }
    const repeat = paintDistantArchitecture(canvas, scene, 1440, 900, "#345a80", masks);
    const alternate = paintDistantArchitecture(canvas, generateDistantArchitecture(20260911), 1440, 900, "#345a80", masks);
    const geometric = paintDistantArchitecture(canvas, scene, 1440, 900);
    paintDistantArchitecture(canvas, scene, 360, 800, "#345a80", masks);
    const mobilePixels = canvas.getContext("2d").getImageData(0, 420, canvas.width, canvas.height - 420).data;
    let mobileVisiblePixels = 0;
    for (let offset = 3; offset < mobilePixels.length; offset += 4) if (mobilePixels[offset] > 0) mobileVisiblePixels += 1;
    const image = new Image();
    image.src = first;
    await image.decode();
    Object.assign(image.style, { display: "block", width: "100vw", height: "100vh" });
    document.body.replaceChildren(image);
    return { cached: firstLoad === sameLoad, masks: masks.map(mask => ({ id: mask.id, width: mask.image.naturalWidth, height: mask.image.naturalHeight })), deterministic: first === repeat, differentSeed: first !== alternate, differentStyle: first !== geometric, visiblePixels, maximumAlpha, mobileVisiblePixels };
  });
  assert.ok(painterly.cached && painterly.deterministic && painterly.differentSeed && painterly.differentStyle);
  assert.equal(painterly.masks.length, 3);
  assert.ok(painterly.visiblePixels > 10000);
  assert.ok(painterly.maximumAlpha > 0 && painterly.maximumAlpha <= 32);
  assert.ok(painterly.mobileVisiblePixels > 1000, "Colossal foreground architecture must remain visible below the mobile header");
  await page.screenshot({ path: "/tmp/azure-sky-architecture-review/painterly-generator-1440.png" });
  console.log(`PASS: cached painterly masks reproduce the seed, differ from geometric shapes, and paint ${painterly.visiblePixels} pixels at max alpha ${painterly.maximumAlpha}/255`);
} finally {
  await browser.close();
  await server.close();
  await new Promise(resolve => httpServer.close(resolve));
}