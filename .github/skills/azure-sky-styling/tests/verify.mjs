import assert from "node:assert/strict";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { preview } from "vite";
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const { values } = parseArgs({ options: { slice: { type: "string", default: "all" } } });
const output = process.env.AZURE_SKY_ARTIFACT_DIR || "/tmp/azure-sky-review";
await mkdir(output, { recursive: true });
const server = await preview({ preview: { host: "127.0.0.1", port: 0, strictPort: true }, logLevel: "error" });
const address = server.httpServer.address();
assert.ok(address && typeof address !== "string");
const baseUrl = `http://127.0.0.1:${address.port}`;
const browser = await chromium.launch({ headless: true });
const cases = [];
const measurements = [];
const errors = [];
const workers = [];
const accessibility = [];
async function check(name, run) {
  await run();
  cases.push({ name, status: "PASS" });
  console.log(`PASS ${name}`);
}
async function setMaterialRange(page, id, value) {
  await page.locator(`#${id}`).evaluate((element, next) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, String(next));
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}
async function materialExtreme(page) {
  await page.getByRole("group", { name: "Material ground", exact: true }).getByRole("button", { name: "Cobalt", exact: true }).click();
  await page.locator("#materials").getByRole("button", { name: /^Mist / }).click();
  await setMaterialRange(page, "azs-gradation", 100);
  await setMaterialRange(page, "azs-material-opacity", 65);
  await setMaterialRange(page, "azs-layer-gap", 24);
  await page.getByRole("switch", { name: "Frosted surface", exact: true }).uncheck();
}
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on("worker", worker => workers.push(worker.url()));
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  page.on("response", response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);

  await check("production gallery and fonts; no cloud runtime", async () => {
    assert.equal(await page.title(), "Azure Sky / Visual Study");
    assert.ok(await page.getByRole("heading", { name: "Azure Sky", exact: true }).isVisible());
    assert.equal(await page.locator("canvas, .azs-procedural-sky, #artwork").count(), 0);
    assert.equal(await page.getByRole("link", { name: "Sky laboratory", exact: true }).count(), 0);
    assert.deepEqual(workers, []);
    const assets = await readdir(new URL("../dist/assets/", import.meta.url));
    assert.deepEqual(assets.filter(file => /sky\.worker|cloudscape|cloud-detail|azure-study|fleet/.test(file)), []);
    assert.ok(await page.evaluate(() => document.fonts.check('600 16px "Barlow Condensed"') && document.fonts.check('400 14px "IBM Plex Sans"')));
  });
  await check("density persists and remaining navigation resolves", async () => {
    await page.getByRole("button", { name: "Compact", exact: true }).click();
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.locator("[data-density]").getAttribute("data-density"), "Compact");
    assert.equal(await page.getByRole("group", { name: "Atmosphere", exact: true }).count(), 0);
    assert.equal(await page.locator(".azs-section-nav a").count(), 7);
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('a[href^="#"]')].map(element => element.getAttribute("href")).filter(href => href.length > 1 && !document.getElementById(href.slice(1)))), []);
    await page.getByRole("button", { name: "View archive", exact: true }).click();
    assert.ok(await page.getByRole("tab", { name: "Report", exact: true }).isVisible());
    await page.getByRole("button", { name: "Comfortable", exact: true }).click();
  });
  await check("material gradation, opacity, layers, highlights and reset", async () => {
    await page.getByRole("link", { name: "Material study", exact: true }).click();
    const material = page.locator("#materials");
    await materialExtreme(page);
    assert.equal(await material.getAttribute("data-highlight"), "Mist");
    assert.equal(await material.getAttribute("data-ground"), "Cobalt");
    const styles = await material.evaluate(element => {
      const root = getComputedStyle(element);
      const front = getComputedStyle(element.querySelector(".azs-material-window"));
      const far = getComputedStyle(element.querySelector(".azs-material-sheet-far"));
      return { strength: root.getPropertyValue("--azs-material-strength"), alpha: root.getPropertyValue("--azs-material-alpha"), gap: root.getPropertyValue("--azs-material-gap"), background: front.backgroundColor, opacity: front.opacity, transform: far.transform, blur: front.backdropFilter };
    });
    assert.equal(styles.strength, "1");
    assert.equal(styles.alpha, "0.65");
    assert.equal(styles.gap, "24px");
    assert.equal(styles.opacity, "1", "Text must not inherit reduced opacity");
    assert.ok(styles.background.endsWith("0.65)"));
    assert.equal(styles.transform, "matrix(1, 0, 0, 1, 48, -48)");
    assert.ok(styles.blur === "blur(0px)" || styles.blur === "none");
    await material.getByRole("button", { name: "Unpin material reference", exact: true }).click();
    assert.equal(await material.locator(".azs-material-label").innerText(), "Reference");
    await material.getByRole("button", { name: "Pin material reference", exact: true }).click();
    assert.equal(await material.locator(".azs-material-label").innerText(), "Pinned");
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await material.getByRole("button", { name: "Copy material recipe", exact: true }).click();
    const recipe = await page.evaluate(() => navigator.clipboard.readText());
    assert.ok(recipe.includes("--azs-material-alpha: 0.65") && recipe.includes('data-highlight="Mist"') && recipe.includes("--azs-material-gap: 24px"));
    await material.getByRole("button", { name: "Add to review", exact: true }).click();
    await page.getByText("Collection added to the review preview", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Dismiss notification", exact: true }).click();
    await material.getByRole("button", { name: "Reset materials", exact: true }).click();
    assert.equal(await page.locator("#azs-gradation").inputValue(), "60");
    assert.equal(await page.locator("#azs-material-opacity").inputValue(), "82");
    assert.equal(await page.locator("#azs-layer-gap").inputValue(), "16");
    assert.equal(await material.getAttribute("data-highlight"), "Mint");
    assert.equal(await material.getAttribute("data-ground"), "Porcelain");
    assert.ok(await page.getByRole("switch", { name: "Frosted surface", exact: true }).isChecked());
    await setMaterialRange(page, "azs-gradation", 0);
    await setMaterialRange(page, "azs-material-opacity", 100);
    await setMaterialRange(page, "azs-layer-gap", 0);
    assert.equal(await material.locator(".azs-material-window").evaluate(element => getComputedStyle(element).backgroundColor), "rgb(247, 251, 255)");
    assert.equal(await material.locator(".azs-material-sheet-far").evaluate(element => getComputedStyle(element).transform), "matrix(1, 0, 0, 1, 0, 0)");
    await material.getByRole("button", { name: "Reset materials", exact: true }).click();
  });
  await check("subtle mint, gradient stops and minimum translucent-surface contrast", async () => {
    const contrasts = await page.locator(".azure-sky[data-density]").evaluate(element => {
      const style = getComputedStyle(element);
      const color = token => style.getPropertyValue(token).trim().slice(1).match(/../g).map(part => parseInt(part, 16));
      const luminance = channels => channels.map(channel => channel / 255).map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
      const ratio = (foreground, background) => { const values = [luminance(foreground), luminance(background)].sort((left, right) => left - right); return (values[1] + 0.05) / (values[0] + 0.05); };
      const surface = color("--azs-porcelain");
      const darkest = color("--azs-cobalt");
      const minimumSurface = surface.map((channel, index) => channel * .65 + darkest[index] * .35);
      const glassLightest = color("--azs-action").map(channel => 255 * .10 + channel * .90);
      return {
        mint: ratio(color("--azs-mint-ink"), color("--azs-mint")),
        mistHighlight: ratio(color("--azs-steel"), color("--azs-mist")),
        translucentMinimum: ratio(color("--azs-ink"), minimumSurface),
        headerLightest: ratio(color("--azs-white"), color("--azs-action")),
        headerGlassLightest: ratio(color("--azs-white"), glassLightest),
        inverseSecondaryLightest: ratio(color("--azs-mist"), color("--azs-action")),
        surfaceSecondaryDarkest: ratio(color("--azs-steel"), color("--azs-mist")),
        mistSecondaryDarkest: ratio(color("--azs-steel"), [220, 236, 255]),
      };
    });
    for (const [name, ratio] of Object.entries(contrasts)) assert.ok(ratio >= 4.5, `${name} text contrast must meet normal-text AA: ${ratio}`);
    measurements.push({ kind: "calculated-material-contrast", ...contrasts });
  });
  await check("orange removed and cool surface gradients extend beyond the study", async () => {
    const stylesheet = await readFile(new URL("../frontend/azure-sky.css", import.meta.url), "utf8");
    assert.ok(!/tangerine|apricot|button-fruit|#ffb176|#ffa35d|#ffe4cf|255 228 207/i.test(stylesheet));
    assert.equal(await page.getByRole("button", { name: /Tangerine/ }).count(), 0);
    assert.equal(await page.locator(".azs-button-fruit").count(), 0);
    assert.equal(await page.locator(".azure-sky[data-density]").evaluate(element => getComputedStyle(element).getPropertyValue("--azs-mint").trim()), "#e5f1ec");
    const surfaces = [".azs-topbar", ".azs-intro", ".azs-section-nav", ".azs-state-strip", ".azs-records", ".azs-table-toolbar", ".azs-inspector", ".azs-chart-main", ".azs-feedback-sample", ".azs-composition-shell", ".azs-composition-nav"];
    for (const selector of surfaces) {
      const paint = await page.locator(selector).first().evaluate(element => ({ image: getComputedStyle(element).backgroundImage, opacity: getComputedStyle(element).opacity }));
      assert.ok(paint.image.includes("linear-gradient"), `${selector} should carry the shared gradation`);
      assert.equal(paint.opacity, "1", `${selector} must not fade its text`);
    }
    const input = await page.getByLabel("Contact email", { exact: true }).evaluate(element => ({ background: getComputedStyle(element).backgroundColor, opacity: getComputedStyle(element).opacity }));
    assert.equal(input.background, "rgb(247, 251, 255)");
    assert.equal(input.opacity, "1");
    const materialPaint = element => ({ background: getComputedStyle(element).backgroundImage, shadow: getComputedStyle(element).boxShadow, grain: getComputedStyle(element, "::before").backgroundImage, grainOpacity: getComputedStyle(element, "::before").opacity, opacity: getComputedStyle(element).opacity });
    const standard = await page.locator('[data-depth-sample="combined"]').evaluate(materialPaint);
    assert.equal(standard.grainOpacity, "0.03");
    for (const selector of [".azs-topbar", ".azs-intro", ".azs-sample-cobalt", ".azs-inspector", ".azs-footer"]) assert.deepEqual(await page.locator(selector).first().evaluate(materialPaint), standard, `${selector} must use the standard four-effect paint`);
    assert.deepEqual(await page.getByRole("button", { name: "Save workspace", exact: true }).evaluate(materialPaint), standard);
    for (const selector of [".azs-button-danger", ".azs-button:disabled", ".azs-swatch-color", '[data-depth-sample="baseline"]']) assert.equal(await page.locator(selector).first().evaluate(element => getComputedStyle(element, "::before").content), "none", `${selector} must not receive the material grain`);
    measurements.push({ kind: "standard-material", ...standard, effects: ["grain", "edge-light", "shadow", "blue-shading"] });
  });
  await check("shaded Cloud and restrained light stain with separate white text", async () => {
    const cloud = page.getByRole("button", { name: "Copy Cloud #EFF3F8", exact: true });
    assert.equal(await cloud.locator(".azs-swatch-color").evaluate(element => getComputedStyle(element).backgroundColor), "rgb(239, 243, 248)");
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await cloud.click();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), "#EFF3F8");
    assert.equal(await page.locator(".azs-intro").evaluate(element => getComputedStyle(element).color), "rgb(255, 255, 255)");
    const surfaces = [".azs-sample-porcelain", ".azs-sample-mist", ".azs-button-cloud", ".azs-button-secondary", ".azs-records", ".azs-chart-main", ".azs-feedback-sample", ".azs-composition-nav"];
    for (const selector of surfaces) {
      const paint = await page.locator(selector).first().evaluate(element => ({ background: getComputedStyle(element).backgroundImage, opacity: getComputedStyle(element).opacity, grain: getComputedStyle(element, "::before").opacity, blend: getComputedStyle(element, "::before").mixBlendMode, events: getComputedStyle(element, "::before").pointerEvents }));
      assert.ok(paint.background.includes("112deg") && paint.background.includes("22deg"), `${selector}: faint stain layers`);
      assert.equal(paint.opacity, "1");
      assert.equal(paint.grain, "0.02");
      assert.equal(paint.blend, "multiply");
      assert.equal(paint.events, "none");
    }
    measurements.push({ kind: "light-material", cloud: "#EFF3F8", white: "#FFFFFF", grainOpacity: .02, surfaces });
  });
  await check("form negative path and persisted read-back", async () => {
    await page.getByLabel("Workspace name", { exact: false }).fill("");
    await page.getByRole("button", { name: "Save workspace", exact: true }).click();
    assert.ok(await page.getByText("A workspace name is required.", { exact: true }).isVisible());
    await page.getByLabel("Workspace name", { exact: false }).fill("Azure review fixture");
    await page.getByLabel("Contact email", { exact: true }).fill("invalid");
    await page.getByRole("button", { name: "Save workspace", exact: true }).click();
    assert.ok(await page.getByText("Enter a valid email address.", { exact: true }).isVisible());
    await page.getByLabel("Contact email", { exact: true }).fill("review@example.com");
    await page.getByRole("button", { name: "Save workspace", exact: true }).click();
    assert.equal(await page.evaluate(() => localStorage.getItem("azure-sky:workspace")), "Azure review fixture");
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.getByLabel("Workspace name", { exact: false }).inputValue(), "Azure review fixture");
    await page.getByLabel("Workspace name", { exact: false }).fill("North observatory");
  });
  await check("file selection, formatting, stepper, selection preview", async () => {
    await page.getByLabel("Choose a fixture file").setInputFiles({ name: "sample.csv", mimeType: "text/csv", buffer: Buffer.from("name,value\nCirrus,12\n") });
    assert.ok(await page.getByText("Selected locally", { exact: true }).isVisible());
    await page.getByRole("button", { name: "Remove file", exact: true }).click();
    await page.getByRole("button", { name: "bold", exact: true }).click();
    assert.equal(await page.locator(".azs-format-bar p").evaluate(element => getComputedStyle(element).fontWeight), "600");
    await page.getByRole("button", { name: "Increase samples" }).click();
    assert.equal(await page.getByRole("spinbutton", { name: "Samples", exact: true }).inputValue(), "5");
    await page.getByRole("group", { name: "Collection view", exact: true }).getByRole("button", { name: "List", exact: true }).click();
    assert.equal(await page.locator(".azs-view-preview").getAttribute("data-view"), "List");
    await page.getByRole("button", { name: "Show private note" }).click();
    assert.equal(await page.getByLabel("Private note", { exact: true }).getAttribute("type"), "text");
  });
  await check("table filter, empty recovery, sorting, selection, export and inspection", async () => {
    await page.getByRole("searchbox", { name: "Search references", exact: true }).fill("no-such-reference");
    await page.getByRole("heading", { name: "No matching references" }).waitFor({ state: "visible" });
    assert.ok(await page.getByRole("heading", { name: "No matching references" }).isVisible());
    await page.getByRole("button", { name: "Reset filters", exact: true }).click();
    await page.getByLabel("Filter status", { exact: true }).selectOption("Reviewed");
    assert.equal(await page.locator(".azs-table tbody tr").count(), 5);
    await page.getByRole("button", { name: "Records", exact: true }).click();
    assert.equal(await page.locator("th[aria-sort=ascending]").innerText(), "Records");
    await page.getByLabel("Select this page", { exact: true }).check();
    assert.ok(await page.getByText("5 selected", { exact: true }).isVisible());
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export (5)", exact: true }).click();
    const download = await downloadPromise;
    const csv = await readFile(await download.path(), "utf8");
    assert.equal(csv.split("\n").length, 6);
    assert.ok(csv.includes("AS-0001"));
    await page.getByRole("button", { name: "Inspect Cirrus array", exact: true }).click();
    assert.ok((await page.getByRole("complementary", { name: "Reference inspector" }).innerText()).includes("12,408"));
    await page.getByRole("button", { name: "Clear selection", exact: true }).click();
    await page.getByLabel("Filter status", { exact: true }).selectOption("All statuses");
  });
  await check("chart variants, graph selection and heatmap read-back", async () => {
    await page.getByRole("group", { name: "Chart type", exact: true }).getByRole("button", { name: "Line", exact: true }).click();
    assert.ok(await page.getByLabel("Line chart of synthetic observation volume").isVisible());
    await page.getByRole("group", { name: "Chart type", exact: true }).getByRole("button", { name: "Bars", exact: true }).click();
    assert.ok(await page.getByLabel("Bars chart of synthetic observation volume").isVisible());
    await page.getByRole("group", { name: "Chart type", exact: true }).getByRole("button", { name: "Area", exact: true }).click();
    await page.getByRole("button", { name: "Cirrus", exact: true }).click();
    assert.ok((await page.locator(".azs-network-detail").innerText()).includes("Cirrus / 3 connections"));
    await page.getByRole("button", { name: "Mon 00:00 7 samples", exact: true }).click();
    assert.ok(await page.getByText("Mon / 00:00 / 7 samples", { exact: true }).isVisible());
  });

  await check("dialog focus, invalid/duplicate names and collection read-back", async () => {
    const trigger = page.getByRole("button", { name: "Create collection", exact: true });
    await trigger.click();
    let dialog = page.getByRole("dialog", { name: "Create a collection", exact: true });
    await dialog.getByRole("button", { name: "Create", exact: true }).click();
    assert.ok(await dialog.getByText("A collection name is required.", { exact: true }).isVisible());
    await dialog.getByLabel("Collection name", { exact: true }).fill("Browser review collection");
    await page.screenshot({ path: resolve(output, "azure-sky-dialog-desktop.png") });
    await dialog.getByRole("button", { name: "Create", exact: true }).click();
    assert.deepEqual(await page.evaluate(() => JSON.parse(localStorage.getItem("azure-sky:collections"))), ["Northbound study", "Browser review collection"]);
    assert.ok(await page.getByText("Browser review collection", { exact: true }).isVisible());
    await trigger.click();
    dialog = page.getByRole("dialog", { name: "Create a collection", exact: true });
    await dialog.getByLabel("Collection name", { exact: true }).fill("Browser review collection");
    await dialog.getByRole("button", { name: "Create", exact: true }).click();
    assert.ok(await dialog.getByText("A collection with this name already exists.", { exact: true }).isVisible());
    await page.keyboard.press("Escape");
    await page.waitForFunction(element => document.activeElement === element, await trigger.elementHandle(), { timeout: 1000 });
    assert.ok(await trigger.evaluate(element => document.activeElement === element));
    await page.getByRole("button", { name: "Remove collection", exact: true }).click();
    await page.getByRole("button", { name: "Keep collection", exact: true }).click();
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("azure-sky:collections")).length), 2);
    await page.getByRole("button", { name: "Remove collection", exact: true }).click();
    await page.getByRole("button", { name: "Remove", exact: true }).click();
    assert.deepEqual(await page.evaluate(() => JSON.parse(localStorage.getItem("azure-sky:collections"))), ["Northbound study"]);
  });
  await check("drawer, popover and keyboard command navigation", async () => {
    await page.getByRole("button", { name: "Open inspector", exact: true }).click();
    assert.ok(await page.getByRole("dialog", { name: "Reference details", exact: true }).isVisible());
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Observation date", exact: true }).click();
    await page.locator(".azs-popover").getByLabel("Date", { exact: true }).fill("2026-09-08");
    await page.getByRole("button", { name: "Done", exact: true }).click();
    assert.ok(await page.getByText("OBSERVATION / 2026-09-08", { exact: true }).isVisible());
    await page.keyboard.press("Control+k");
    await page.getByRole("combobox", { name: "Find a section", exact: true }).fill("visual");
    await page.keyboard.press("Enter");
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    assert.ok(await page.locator("#charts-title").isVisible());
  });
  await check("empty-state action, retry recovery and progress completion", async () => {
    await page.getByRole("button", { name: "Create view", exact: true }).click();
    assert.ok(await page.getByRole("heading", { name: "North sector review", exact: true }).isVisible());
    await page.getByRole("button", { name: "Retry sample", exact: true }).click();
    await page.getByRole("heading", { name: "Fixture loaded", exact: true }).waitFor();
    assert.ok(await page.getByText("3 of 3 sample sources available.", { exact: true }).isVisible());
    await page.getByRole("button", { name: "Run sample", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("progress").value === 100);
    assert.ok(await page.locator(".azs-progress-line").getByText("Archive prepared", { exact: true }).isVisible());
    await page.getByRole("button", { name: "Error notification", exact: true }).click();
    assert.ok(await page.locator(".azs-toast-error").isVisible());
    await page.getByRole("button", { name: "Dismiss notification", exact: true }).click();
  });

  await check("workspace cards, filtering, profile read-back and inverse surfaces", async () => {
    await page.getByRole("tab", { name: "Workspace", exact: true }).click();
    await page.getByRole("searchbox", { name: "Search collections", exact: true }).fill("no-such-collection");
    await page.getByRole("heading", { name: "No collections found", exact: true }).waitFor();
    await page.getByRole("button", { name: "Clear collection search", exact: true }).click();
    await page.getByRole("button", { name: "Bookmark Reference atlas", exact: true }).click();
    assert.equal(await page.getByRole("button", { name: "Bookmark Reference atlas", exact: true }).getAttribute("aria-pressed"), "true");
    await page.locator(".azs-collection-card").filter({ has: page.getByRole("heading", { name: "Reference atlas", exact: true }) }).getByRole("button", { name: "Open", exact: true }).click();
    assert.ok((await page.getByRole("navigation", { name: "Workspace breadcrumb", exact: true }).innerText()).includes("Reference atlas"));
    await page.getByRole("tab", { name: "Settings", exact: true }).click();
    await page.getByLabel("Display name", { exact: true }).fill("Review observer");
    await page.getByRole("button", { name: "Update profile", exact: true }).click();
    await page.getByText("Profile preview: Review observer", { exact: true }).waitFor();
    for (const surface of ["Porcelain", "Mist", "Cobalt"]) {
      await page.getByRole("group", { name: "Reference surface", exact: true }).getByRole("button", { name: surface, exact: true }).click();
      assert.ok(await page.locator(`.azs-material-${surface.toLowerCase()}`).isVisible());
    }
    await page.getByLabel("Display name", { exact: true }).fill("Mira Chen");
    await page.getByRole("tab", { name: "Report", exact: true }).click();
    await page.getByRole("button", { name: "North observatory", exact: true }).click();
  });
  await check("palette clipboard, stylesheet download and font notices", async () => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "Copy Cobalt #123F91", exact: true }).click();
    await page.waitForFunction(() => navigator.clipboard.readText().then(value => value === "#123F91"));
    const styleDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download Azure Sky stylesheet", exact: true }).click();
    const styleFile = await styleDownload;
    const style = await readFile(await styleFile.path(), "utf8");
    assert.ok(style.includes("--azs-cobalt: #123f91"));
    assert.ok(style.includes("prefers-reduced-motion"));
    assert.ok(!style.includes("azs-procedural-sky") && !style.includes("azs-studio-scene"));
    assert.ok(!style.includes('@import "./depth-effects.css";'), "Downloaded CSS must include its depth dependency");
    const embeddedGrain = style.match(/url\("data:image\/png;base64,([^\"]+)"\)/)?.[1];
    assert.ok(embeddedGrain, "Downloaded CSS must include the grain image");
    assert.deepEqual(Buffer.from(embeddedGrain, "base64"), await readFile(new URL("../frontend/assets/surface-grain.png", import.meta.url)));
    const notices = await page.request.get(`${baseUrl}/THIRD_PARTY_NOTICES.txt`);
    assert.equal(notices.status(), 200);
    assert.ok((await notices.text()).includes("SIL OPEN FONT LICENSE"));
  });
  await check("keyboard focus and dialog containment", async () => {
    await page.reload({ waitUntil: "networkidle" });
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.textContent), "Skip to specimens");
    const focus = await page.getByRole("link", { name: "Skip to specimens", exact: true }).evaluate(element => ({ outline: getComputedStyle(element).outlineStyle, top: element.getBoundingClientRect().top }));
    assert.equal(focus.outline, "solid");
    assert.ok(focus.top >= 0);
    await page.keyboard.press("Enter");
    assert.equal(await page.evaluate(() => document.activeElement.id), "specimens");
    const trigger = page.getByRole("button", { name: "Create collection", exact: true });
    await trigger.click();
    for (let tab = 0; tab < 9; tab += 1) {
      await page.keyboard.press("Tab");
      assert.ok(await page.evaluate(() => !!document.activeElement.closest('[role="dialog"]')));
    }
    await page.keyboard.press("Escape");
    await page.waitForFunction(element => document.activeElement === element, await trigger.elementHandle(), { timeout: 1000 });
    assert.ok(await trigger.evaluate(element => element === document.activeElement));
  });

  if (values.slice === "all") {
    for (const width of [1440, 360]) {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : 800 });
      for (const tab of ["Report", "Workspace", "Settings"]) {
        await check(`automated WCAG A/AA ${tab} at ${width}px`, async () => {
          await page.getByRole("tab", { name: tab, exact: true }).click();
          const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
          const violations = result.violations.map(issue => ({ id: issue.id, nodes: issue.nodes.map(node => ({ target: node.target, detail: node.failureSummary })) }));
          accessibility.push({ tab, width, violations, incomplete: result.incomplete.map(issue => issue.id) });
          assert.deepEqual(violations, []);
          await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
          await page.locator("#compositions").screenshot({ path: resolve(output, `composition-${tab.toLowerCase()}-${width}.png`) });
        });
      }
    }
    await page.getByRole("tab", { name: "Report", exact: true }).click();
  }

  for (const [width, height] of values.slice === "all" ? [[360, 800], [768, 1024], [1440, 900], [1920, 1080]] : [[360, 800], [1440, 900]]) {
    await check(`responsive geometry ${width}x${height}`, async () => {
      await page.setViewportSize({ width, height });
      await page.evaluate(() => window.scrollTo(0, 0));
      const geometry = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, chartWidth: document.querySelector(".azs-chart-canvas").getBoundingClientRect().width, titleWidth: document.querySelector("h1").getBoundingClientRect().width, clippedText: [...document.querySelectorAll("h1,h2,h3,.azs-button,.azs-segmented button,.azs-tabs button")].filter(element => element.getBoundingClientRect().width > 0 && element.clientWidth > 0 && element.scrollWidth > element.clientWidth + 1).map(element => element.textContent) }));
      assert.ok(geometry.scrollWidth <= geometry.width, JSON.stringify(geometry));
      assert.ok(geometry.chartWidth > 200);
      assert.deepEqual(geometry.clippedText, []);
      if (width === 360) {
        const targets = await page.evaluate(() => [...document.querySelectorAll(".azs-button,.azs-icon-button,.azs-segmented button,.azs-heatmap button,.azs-tag button,.azs-tabs button")].filter(element => element.getBoundingClientRect().width > 0).map(element => ({ name: element.getAttribute("aria-label") || element.textContent, width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height })).filter(target => target.width < 43.9 || target.height < 43.9));
        assert.deepEqual(targets, [], "Mobile primary controls must have 44px targets");
        await page.getByRole("button", { name: "Create collection", exact: true }).click();
        await page.screenshot({ path: resolve(output, "azure-sky-dialog-mobile.png") });
        const dialog = await page.getByRole("dialog", { name: "Create a collection", exact: true }).boundingBox();
        assert.ok(dialog && dialog.x >= 0 && dialog.x + dialog.width <= width);
        await page.keyboard.press("Escape");
        await page.evaluate(() => window.scrollTo(0, 0));
      }
      measurements.push({ viewport: `${width}x${height}`, ...geometry });
      await page.screenshot({ path: resolve(output, `azure-sky-${width}.png`), fullPage: true });
      await page.screenshot({ path: resolve(output, `azure-sky-first-view-${width}.png`) });
      await materialExtreme(page);
      const materials = page.locator("#materials");
      const materialBounds = await materials.evaluate(element => {
        const plane = element.querySelector(".azs-material-plane").getBoundingClientRect();
        const layers = [...element.querySelectorAll(".azs-material-sheet, .azs-material-window")].map(sheet => sheet.getBoundingClientRect());
        const window = element.querySelector(".azs-material-window").getBoundingClientRect();
        const controls = element.querySelector(".azs-material-controls").getBoundingClientRect();
        const labels = [...element.querySelectorAll("h3,h4,button,output")].filter(item => item.clientWidth > 0 && item.scrollWidth > item.clientWidth + 1).map(item => item.textContent);
        return { contained: layers.every(rect => rect.left >= plane.left - 1 && rect.right <= plane.right + 1 && rect.top >= plane.top - 1 && rect.bottom <= plane.bottom + 1), controlsSeparate: controls.left >= plane.right || controls.top >= plane.bottom, foregroundOpaque: getComputedStyle(element.querySelector(".azs-material-window")).opacity === "1", width: window.width, labels };
      });
      assert.ok(materialBounds.contained, "Layer edges must fit the reserved preview area");
      assert.ok(materialBounds.controlsSeparate, "Controls must not overlap the layer preview");
      assert.ok(materialBounds.foregroundOpaque);
      assert.deepEqual(materialBounds.labels, []);
      await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
      await materials.screenshot({ path: resolve(output, `materials-extreme-${width}.png`) });
      if (width === 360 || width === 1440) {
        const audit = await new AxeBuilder({ page }).include("#materials").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(audit.violations.map(issue => ({ id: issue.id, nodes: issue.nodes.map(node => node.target) })), []);
        accessibility.push({ view: "materials-minimum-opacity", width, violations: [], incomplete: audit.incomplete.map(issue => issue.id) });
      }
      measurements.push({ viewport: `${width}x${height}`, materialBounds });
      await materials.getByRole("button", { name: "Reset materials", exact: true }).click();
      await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
      await materials.screenshot({ path: resolve(output, `materials-default-${width}.png`) });
    });
  }
  if (values.slice === "all") {
    await check("200% layout-zoom equivalent and remaining controls", async () => {
      const zoomContext = await browser.newContext({ viewport: { width: 720, height: 450 }, deviceScaleFactor: 2, reducedMotion: "reduce" });
      const zoomPage = await zoomContext.newPage();
      await zoomPage.goto(baseUrl, { waitUntil: "networkidle" });
      await zoomPage.evaluate(() => document.fonts.ready);
      const geometry = await zoomPage.evaluate(() => ({ cssWidth: innerWidth, dpr: devicePixelRatio, scrollWidth: document.documentElement.scrollWidth }));
      assert.equal(geometry.cssWidth, 720);
      assert.equal(geometry.dpr, 2);
      assert.ok(geometry.scrollWidth <= 720);
      await zoomPage.getByRole("tab", { name: "Settings", exact: true }).click();
      await zoomPage.getByLabel("Display name", { exact: true }).fill("Zoom review");
      await zoomPage.getByRole("button", { name: "Update profile", exact: true }).click();
      await zoomPage.getByText("Profile preview: Zoom review", { exact: true }).waitFor();
      await zoomPage.locator("#compositions").screenshot({ path: resolve(output, "azure-sky-layout-zoom-200.png") });
      await materialExtreme(zoomPage);
      assert.ok(await zoomPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await zoomPage.locator("#materials").screenshot({ path: resolve(output, "materials-layout-zoom-200.png") });
      assert.equal(await zoomPage.locator("canvas, #artwork").count(), 0);
      measurements.push({ zoom: "200% layout equivalent: 720x450 CSS pixels at 2x DPR, 1440x900 physical", ...geometry });
      await zoomContext.close();
    });
    await check("plain HTML works with JavaScript disabled", async () => {
      const plainContext = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 360, height: 800 } });
      const plainPage = await plainContext.newPage();
      const scripts = [];
      plainPage.on("request", request => { if (request.resourceType() === "script") scripts.push(request.url()); });
      await plainPage.goto(`${baseUrl}/plain.html`, { waitUntil: "networkidle" });
      assert.equal(await plainPage.title(), "Azure Sky / HTML Specimen");
      await plainPage.getByLabel("Collection name", { exact: true }).fill("HTML review");
      assert.equal(await plainPage.getByLabel("Collection name", { exact: true }).inputValue(), "HTML review");
      await plainPage.getByLabel("Include provenance", { exact: true }).uncheck();
      assert.equal(await plainPage.getByLabel("Include provenance", { exact: true }).isChecked(), false);
      await plainPage.getByText("Source provenance", { exact: true }).click();
      assert.ok(await plainPage.getByText("Local synthetic fixture. No external connection.", { exact: true }).isVisible());
      assert.deepEqual(scripts, []);
      assert.ok(await plainPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await plainPage.screenshot({ path: resolve(output, "azure-sky-plain-html-mobile.png"), fullPage: true });
      await plainContext.close();
    });
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(workers, []);
  const artifact = createHash("sha256").update(await readFile(new URL("../dist/index.html", import.meta.url))).digest("hex");
  await writeFile(resolve(output, "report.json"), JSON.stringify({ status: "PASS", artifact, cases, measurements, accessibility, errors }, null, 2) + "\n");
  console.log(`regression PASS: ${cases.length}/${cases.length} cases, 0 runtime errors; artifact ${artifact.slice(0, 12)}; evidence ${output}`);
} catch (error) {
  await writeFile(resolve(output, "failure.json"), JSON.stringify({ error: String(error), cases, measurements, accessibility, errors }, null, 2) + "\n");
  throw error;
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.httpServer.close(error => error ? rejectClose(error) : resolveClose()));
}