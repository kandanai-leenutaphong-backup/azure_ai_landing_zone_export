import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const encoded = await page.evaluate(() => {
    const size = 128;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");
    const image = context.createImageData(size, size);
    let seed = 0x415a5552;
    for (let offset = 0; offset < image.data.length; offset += 4) {
      seed ^= seed << 13;
      seed ^= seed >>> 17;
      seed ^= seed << 5;
      const shade = seed >>> 24;
      image.data.set([shade, shade, shade, 255], offset);
    }
    context.putImageData(image, 0, 0);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  const bytes = Buffer.from(encoded, "base64");
  assert.equal(bytes.readUInt32BE(16), 128);
  assert.equal(bytes.readUInt32BE(20), 128);
  const folder = new URL("../frontend/assets/", import.meta.url);
  await mkdir(folder, { recursive: true });
  await writeFile(new URL("surface-grain.png", folder), bytes);
  console.log(`PASS: generated deterministic 128x128 monochrome grain (${bytes.length} bytes); no runtime generator`);
} finally {
  await browser.close();
}