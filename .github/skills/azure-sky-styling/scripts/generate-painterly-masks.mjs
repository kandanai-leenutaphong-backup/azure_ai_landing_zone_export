import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

const recipesUrl = new URL("./painterly-mask-recipes.json", import.meta.url);
const recipeBytes = await readFile(recipesUrl);
const recipes = JSON.parse(recipeBytes);
const originals = new URL("../research/painterly/holdings/originals/", import.meta.url);
const acquisitions = JSON.parse(await readFile(new URL("../catalogue.json", originals), "utf8"));
const destination = new URL("../frontend/assets/painterly/", import.meta.url);
const evidence = process.env.AZURE_SKY_MASK_ARTIFACT_DIR || "/tmp/azure-sky-painterly-mask-review";
await mkdir(destination, { recursive: true });
await mkdir(evidence, { recursive: true });
const browser = await chromium.launch({ headless: true });
const manifest = { version: recipes.version, recipe_sha256: createHash("sha256").update(recipeBytes).digest("hex"), generator_sha256: createHash("sha256").update(await readFile(new URL(import.meta.url))).digest("hex"), masks: [] };
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 1100 } });
  for (const recipe of recipes.masks) {
    const sourceBytes = await readFile(new URL(recipe.source, originals));
    const acquisition = acquisitions.entries.find(entry => entry.artefact === `originals/${recipe.source}`);
    assert.ok(acquisition, `${recipe.id}: original acquisition record required`);
    assert.equal(createHash("sha256").update(sourceBytes).digest("hex"), acquisition.sha256);
    const record = JSON.parse(await readFile(new URL(`../records/met-${recipe.object_id}.json`, originals), "utf8"));
    assert.equal(record.isPublicDomain, true);
    assert.equal(record.primaryImage, recipe.source_url);
    const result = await page.evaluate(async ({ encoded, recipe }) => {
      const original = new Image();
      original.src = `data:image/jpeg;base64,${encoded}`;
      await original.decode();
      const points = recipe.polygon.map(([horizontal, vertical]) => [horizontal * original.naturalWidth, vertical * original.naturalHeight]);
      const left = Math.min(...points.map(point => point[0]));
      const top = Math.min(...points.map(point => point[1]));
      const sourceWidth = Math.max(...points.map(point => point[0])) - left;
      const sourceHeight = Math.max(...points.map(point => point[1])) - top;
      const scale = Math.min(1, 744 / sourceWidth, 936 / sourceHeight);
      const margin = 12;
      const width = Math.ceil(sourceWidth * scale) + margin * 2;
      const height = Math.ceil(sourceHeight * scale) + margin * 2;
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      context.drawImage(original, left, top, sourceWidth, sourceHeight, margin, margin, sourceWidth * scale, sourceHeight * scale);
      const crop = canvas.toDataURL("image/png");
      const pixels = context.getImageData(0, 0, width, height);
      const selection = document.createElement("canvas");
      selection.width = width;
      selection.height = height;
      const selector = selection.getContext("2d");
      selector.beginPath();
      points.forEach(([horizontal, vertical], index) => {
        const position = [(horizontal - left) * scale + margin, (vertical - top) * scale + margin];
        if (index === 0) selector.moveTo(...position);
        else selector.lineTo(...position);
      });
      selector.closePath();
      selector.fillStyle = "white";
      selector.fill();
      const selected = selector.getImageData(0, 0, width, height).data;
      const tones = [];
      const luminosity = offset => .2126 * pixels.data[offset] + .7152 * pixels.data[offset + 1] + .0722 * pixels.data[offset + 2];
      for (let offset = 0; offset < pixels.data.length; offset += 4) if (selected[offset + 3] > 250) tones.push(luminosity(offset));
      tones.sort((first, second) => first - second);
      const paper = tones[Math.floor((tones.length - 1) * recipe.paper_quantile)];
      const ink = tones[Math.floor((tones.length - 1) * recipe.ink_quantile)];
      const feathered = document.createElement("canvas");
      feathered.width = width;
      feathered.height = height;
      const feather = feathered.getContext("2d");
      feather.filter = "blur(1.6px)";
      feather.drawImage(selection, 0, 0);
      const featherPixels = feather.getImageData(0, 0, width, height).data;
      const alphaLevels = new Set();
      let visiblePixels = 0;
      let borderPixels = 0;
      for (let offset = 0; offset < pixels.data.length; offset += 4) {
        const horizontal = (offset / 4) % width;
        const vertical = Math.floor(offset / 4 / width);
        const density = Math.max(0, Math.min(1, ((paper - luminosity(offset)) / Math.max(1, paper - ink) - recipe.paper_cutoff) / (1 - recipe.paper_cutoff)));
        const baseFade = Math.min(1, Math.max(0, (height - margin - vertical) / ((height - margin * 2) * recipe.bottom_fade)));
        const alpha = Math.round(255 * Math.pow(density, recipe.gamma) * recipe.maximum_alpha * (featherPixels[offset + 3] / 255) * baseFade);
        pixels.data.set([255, 255, 255, alpha], offset);
        alphaLevels.add(alpha);
        if (alpha > 0) {
          visiblePixels += 1;
          if (horizontal < 4 || vertical < 4 || horizontal >= width - 4 || vertical >= height - 4) borderPixels += 1;
        }
      }
      context.putImageData(pixels, 0, 0);
      const encodedMask = canvas.toDataURL("image/webp", .9);
      const decoded = new Image();
      decoded.src = encodedMask;
      await decoded.decode();
      context.clearRect(0, 0, width, height);
      context.drawImage(decoded, 0, 0);
      const readBack = context.getImageData(0, 0, width, height).data;
      let alphaDifferences = 0;
      for (let offset = 3; offset < readBack.length; offset += 4) if (readBack[offset] !== pixels.data[offset]) alphaDifferences += 1;
      return { encodedMask, crop, width, height, sourceDimensions: [original.naturalWidth, original.naturalHeight], paper, ink, alphaLevels: alphaLevels.size, visiblePixels, borderPixels, alphaDifferences };
    }, { encoded: sourceBytes.toString("base64"), recipe });
    assert.ok(result.width <= 768 && result.height <= 960);
    assert.ok(result.visiblePixels > 1000, `${recipe.id}: empty mask`);
    assert.ok(result.alphaLevels > 100, `${recipe.id}: painterly tones must not become a binary silhouette`);
    assert.equal(result.borderPixels, 0, `${recipe.id}: no rectangular crop boundary`);
    assert.equal(result.alphaDifferences, 0, `${recipe.id}: WebP must preserve every alpha sample`);
    assert.ok(result.encodedMask.startsWith("data:image/webp;base64,"));
    const bytes = Buffer.from(result.encodedMask.split(",")[1], "base64");
    await writeFile(new URL(`${recipe.id}.webp`, destination), bytes);
    await unlink(new URL(`${recipe.id}.png`, destination)).catch(error => { if (error.code !== "ENOENT") throw error; });
    manifest.masks.push({ id: recipe.id, filename: `${recipe.id}.webp`, object_id: recipe.object_id, artist: recipe.artist, title: recipe.title, source_url: recipe.source_url, source_sha256: createHash("sha256").update(sourceBytes).digest("hex"), source_dimensions: result.sourceDimensions, width: result.width, height: result.height, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex"), alpha_levels: result.alphaLevels, visible_pixels: result.visiblePixels, paper: result.paper, ink: result.ink, rights: "Derivative of a public-domain Met image; cropped, desaturated to alpha, feathered; source artist credited, no endorsement" });
    await page.evaluate(({ id, encodedMask, crop }) => {
      if (!document.querySelector("main")) document.body.innerHTML = '<main style="display:grid;gap:20px;padding:20px;font:16px sans-serif;background:#eff3f8"></main>';
      const row = document.createElement("section");
      const label = document.createElement("h2");
      label.textContent = id;
      label.style.cssText = "margin:0 0 12px;font-size:18px";
      const images = document.createElement("div");
      images.style.cssText = "display:flex;gap:20px;align-items:start;height:340px";
      const source = new Image();
      source.src = crop;
      source.style.cssText = "height:100%;width:48%;object-fit:contain";
      const mask = document.createElement("div");
      mask.style.cssText = `height:100%;width:48%;background:#345a80;mask:url(${encodedMask}) center / contain no-repeat`;
      images.append(source, mask);
      row.append(label, images);
      document.querySelector("main").append(row);
    }, { id: recipe.id, encodedMask: result.encodedMask, crop: result.crop });
    console.log(`PASS: ${recipe.id}, ${result.width}x${result.height}, ${result.alphaLevels} alpha levels preserved exactly, ${bytes.length} bytes, transparent edges`);
  }
  await writeFile(new URL("manifest.json", destination), JSON.stringify(manifest, null, 2) + "\n");
  await page.screenshot({ path: `${evidence}/mask-contact-sheet.png`, fullPage: true });
} finally {
  await browser.close();
}