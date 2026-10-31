import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { preview } from "vite";
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

const output = process.env.AZURE_SKY_PREVIEW_ARTIFACT_DIR || "/tmp/azure-sky-security-review";
await mkdir(output, { recursive: true });
const server = await preview({ preview: { port: 0, host: "127.0.0.1", strictPort: true }, logLevel: "error" });
const address = server.httpServer.address();
assert.ok(address && typeof address !== "string");
const origin = `http://127.0.0.1:${address.port}`;
const browser = await chromium.launch();
const cases = [];
const measurements = [];
const errors = [];
const prohibitedRequests = [];
async function check(name, run) { await run(); cases.push({ name, status: "PASS" }); console.log(`PASS ${name}`); }
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || /^\/(api|auth)(\/|$)/.test(url.pathname)) { prohibitedRequests.push(url.href); return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  page.on("response", response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
  await check("atlas links to the isolated application preview", async () => {
    await page.goto(origin, { waitUntil: "networkidle" });
    await page.getByRole("link", { name: "Security review preview", exact: true }).click();
    await page.waitForURL("**/security-review.html");
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.title(), "Security Review / Azure Sky Preview");
    assert.ok((await page.locator(".rv-preview-strip").innerText()).includes("Synthetic fixtures / no live connections"));
    assert.equal(await page.locator("canvas, .azs-button-fruit").count(), 0);
    assert.equal(await page.locator(".rv-situation").count(), 2);
    assert.ok(!(await page.locator(".rv-rules").getAttribute("open")));
  });
  const board = page.getByRole("region", { name: "Central tool board", exact: true });
  const chat = page.getByRole("region", { name: "Review agent chat", exact: true });
  await check("situation selection updates board and chat without mixing evidence", async () => {
    await page.getByRole("button", { name: "Select situation dns-review-02", exact: true }).click();
    assert.equal(await board.locator(".rv-host-button").innerText(), "dns-review-02");
    assert.ok((await chat.locator(".rv-agent-context").innerText()).includes("dns-review-02"));
    assert.equal(await board.locator(".rv-sequence li").count(), 3);
    await page.getByRole("tab", { name: "Situation Summary", exact: true }).click();
    assert.ok((await chat.innerText()).includes("Repeated queries for one example domain"));
    await page.getByRole("tab", { name: "Explorer", exact: true }).click();
    await page.getByRole("tab", { name: "Investigation", exact: true }).click();
    assert.equal(await board.locator(".rv-host-button").innerText(), "dns-review-02");
    assert.equal(await page.getByRole("tab", { name: "Situation Summary", exact: true }).getAttribute("aria-selected"), "true");
  });
  await check("sequence opens its evidence, filtering recovers and export matches rows", async () => {
    await board.locator(".rv-sequence li").first().locator("summary").click();
    await board.getByRole("button", { name: "fixture:evt-007", exact: true }).click();
    assert.equal(await board.getByRole("tab", { name: "evidence", exact: true }).getAttribute("aria-selected"), "true");
    assert.equal(await board.locator("tbody tr").count(), 3);
    await board.getByRole("searchbox", { name: "Search cited evidence", exact: true }).fill("no matching fixture");
    await board.getByText("No matching records", { exact: true }).waitFor();
    await board.getByRole("button", { name: "Clear record search", exact: true }).click();
    await board.getByRole("button", { name: "DNS lookup", exact: true }).first().click();
    assert.ok((await board.locator(".rv-evidence-inspect").innerText()).includes("Reserved example domain"));
    const downloading = page.waitForEvent("download");
    await board.getByRole("button", { name: "Download cited evidence", exact: true }).click();
    const records = JSON.parse(await readFile(await (await downloading).path(), "utf8"));
    assert.deepEqual(records.map(row => row.id), ["fixture:evt-007", "fixture:evt-008", "fixture:evt-009"]);
  });
  await check("tool outputs, entity selection and graph controls respond", async () => {
    await board.getByRole("tab", { name: "tools", exact: true }).click();
    await board.getByRole("button", { name: "Product composition Open sample result", exact: true }).click();
    assert.ok((await board.locator(".rv-tool-result").innerText()).includes("DNS"));
    await board.getByRole("button", { name: "Firewall baseline Open sample result", exact: true }).click();
    assert.ok(await board.getByRole("heading", { name: "No firewall fixture", exact: true }).isVisible());
    await board.getByRole("tab", { name: "situation", exact: true }).click();
    await board.getByRole("button", { name: "dns-review-02", exact: true }).click();
    await board.getByRole("button", { name: "Visualize", exact: true }).click();
    assert.equal(await board.getByRole("tab", { name: "graph", exact: true }).getAttribute("aria-selected"), "true");
    await board.locator(".rv-entity-node").filter({ hasText: "Service account" }).click();
    assert.ok((await board.locator(".rv-graph-detail").innerText()).includes("Service account"));
    await board.getByRole("button", { name: "Zoom in graph", exact: true }).click();
    assert.ok((await board.locator(".rv-graph-toolbar").innerText()).includes("110%"));
  });
  await check("column resize, expand and restore preserve the workspace", async () => {
    const before = await board.boundingBox();
    const separator = page.getByRole("separator", { name: "Resize scanner and tool board", exact: true });
    await separator.focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await separator.getAttribute("aria-valuenow"), "27");
    assert.ok((await board.boundingBox()).width < before.width);
    const grip = await separator.boundingBox();
    await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2);
    await page.mouse.down();
    await page.mouse.move(grip.x + grip.width / 2 + 40, grip.y + grip.height / 2, { steps: 5 });
    await page.mouse.up();
    assert.ok(Number(await separator.getAttribute("aria-valuenow")) > 27);
    await page.getByRole("button", { name: "Reset column widths", exact: true }).click();
    assert.equal(await separator.getAttribute("aria-valuenow"), "25");
    await board.getByRole("button", { name: "Expand tool board", exact: true }).click();
    assert.ok((await board.boundingBox()).width > 1300);
    await page.keyboard.press("Escape");
    assert.equal(await page.locator(".rv-investigation").getAttribute("data-expanded"), "none");
  });
  await check("invalid windows reject and quiet, error, idle and replay states work", async () => {
    await page.getByLabel("Scan end UTC", { exact: true }).fill("2026-08-13T01:00");
    await page.getByRole("button", { name: "Scan ADX window", exact: true }).click();
    assert.ok(await page.getByText("Window end must be after window start.", { exact: true }).isVisible());
    await page.getByLabel("Test Scenarios", { exact: true }).selectOption("quiet");
    await page.getByRole("button", { name: "Scan ADX window", exact: true }).click();
    await page.getByRole("heading", { name: "No qualifying situations", exact: true }).waitFor();
    assert.equal(await page.locator(".rv-situation").count(), 0);
    await page.getByLabel("Preview state", { exact: true }).selectOption("idle");
    assert.ok(await page.getByRole("heading", { name: "Scanner idle", exact: true }).isVisible());
    await page.getByLabel("Test Scenarios", { exact: true }).selectOption("credentials");
    await page.getByLabel("Preview state", { exact: true }).selectOption("error");
    await page.getByRole("button", { name: "Retry fixture", exact: true }).click();
    await page.getByRole("button", { name: "Select situation ws-alpha-01", exact: true }).waitFor();
    assert.equal(await board.locator(".rv-host-button").innerText(), "ws-alpha-01");
  });
  await check("chat prefill, fixture response, cancellation and tab retention", async () => {
    await board.getByRole("button", { name: "Take it further in chat", exact: true }).click();
    assert.ok((await page.getByRole("textbox", { name: "Message Review agent", exact: true }).inputValue()).includes("ws-alpha-01"));
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await page.locator(".rv-message-agent").getByText(/Fixed fixture response/).waitFor();
    assert.ok((await chat.getByRole("tabpanel", { name: "Review agent", exact: true }).locator(".rv-message-agent").innerText()).includes("fixture:evt-001"));
    await page.getByRole("tab", { name: "Explorer", exact: true }).click();
    await page.getByRole("tab", { name: "Investigation", exact: true }).click();
    assert.equal(await chat.locator(".rv-message-user").count(), 1);
    await page.getByRole("textbox", { name: "Message Review agent", exact: true }).fill("Stop this sample");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await page.getByRole("button", { name: "Stop fixture response", exact: true }).click();
    assert.ok(await page.getByText("Fixture response stopped.", { exact: true }).isVisible());
    assert.equal(await chat.getByRole("tabpanel", { name: "Review agent", exact: true }).locator(".rv-message-agent").count(), 1);
  });
  await check("Explorer source/schema/preview and exact datasource highlighting", async () => {
    await page.getByRole("tab", { name: "Explorer", exact: true }).click();
    const viewer = page.getByRole("region", { name: "Selected item viewer", exact: true });
    await page.getByRole("button", { name: "EventsUnified", exact: true }).click();
    await viewer.getByRole("tab", { name: "schema", exact: true }).click();
    assert.equal(await viewer.locator("tbody tr").count(), 6);
    await viewer.getByRole("tab", { name: "preview", exact: true }).click();
    assert.equal(await viewer.locator("tbody tr").count(), 9);
    await page.getByRole("button", { name: "EndpointEvents", exact: true }).click();
    assert.equal(await viewer.locator("tbody tr").count(), 3);
    await page.getByRole("complementary", { name: "Loaded agents", exact: true }).getByRole("button", { name: "Situation evidence", exact: true }).click();
    assert.equal(await page.locator(".rv-source-match").count(), 2);
    assert.ok((await viewer.getByRole("region", { name: "Tool datasources", exact: true }).innerText()).includes("Endpoint telemetry replay"));
    await page.getByRole("button", { name: "MITRE ATT&CK references", exact: true }).click();
    assert.equal(await page.locator(".rv-source-match").count(), 1);
    assert.ok((await page.locator(".rv-source-match").innerText()).includes("Open-source technique references"));
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "Copy source specimen", exact: true }).click();
    assert.ok((await page.evaluate(() => navigator.clipboard.readText())).includes("synthetic-preview"));
    await page.getByRole("searchbox", { name: "Search data sources", exact: true }).fill("no such source");
    await page.getByText("No matching sources", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Clear source search", exact: true }).click();
    await page.getByRole("button", { name: "Refresh fixture sources", exact: true }).click();
    assert.ok(await page.getByText("Refreshed", { exact: true }).isVisible());
  });
  await check("Configuration is explicit about disconnected services and returns focus", async () => {
    await page.getByRole("button", { name: "Configuration", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Configuration", exact: true });
    assert.equal(await dialog.getByText("Not connected", { exact: true }).count(), 2);
    await page.screenshot({ path: resolve(output, "configuration-desktop.png") });
    await page.keyboard.press("Tab");
    assert.ok(await page.evaluate(() => !!document.activeElement.closest('[role="dialog"]')));
    await page.keyboard.press("Escape");
    assert.ok(await page.getByRole("button", { name: "Configuration", exact: true }).evaluate(element => element === document.activeElement));
  });

  for (const [width, height] of [[1440, 900], [1920, 1080], [768, 1024], [360, 800]]) {
    await check(`workspace and responsive geometry ${width}x${height}`, async () => {
      await page.setViewportSize({ width, height });
      await page.getByRole("tab", { name: "Investigation", exact: true }).click();
      if (width < 768) await page.getByRole("group", { name: "Investigation panels", exact: true }).getByRole("button", { name: "Tool board", exact: true }).click();
      await board.getByRole("tab", { name: "situation", exact: true }).click();
      await board.getByRole("tabpanel", { name: "situation", exact: true }).evaluate(element => element.scrollTop = 0);
      await page.locator(".rv-scanner").evaluate(element => element.scrollTop = 0);
      const geometry = await page.evaluate(() => {
        const visible = [...document.querySelectorAll(".rv-column")].filter(element => element.getBoundingClientRect().width > 0).map(element => ({ class: element.className, box: element.getBoundingClientRect().toJSON() }));
        const clipped = [...document.querySelectorAll("h1,h2,h3,.rv-severity,.rv-workspace-tabs button,.rv-board-tabs button,.azs-button")].filter(element => element.clientWidth > 0 && element.scrollWidth > element.clientWidth + 1).map(element => element.textContent);
        return { width: innerWidth, scrollWidth: document.documentElement.scrollWidth, visible, clipped };
      });
      assert.ok(geometry.scrollWidth <= width, JSON.stringify(geometry));
      assert.deepEqual(geometry.clipped, []);
      if (width >= 1101) { assert.equal(geometry.visible.length, 3); assert.ok(geometry.visible[0].box.right <= geometry.visible[1].box.x); assert.ok(geometry.visible[1].box.right <= geometry.visible[2].box.x); }
      if (width < 768) assert.equal(geometry.visible.length, 1);
      measurements.push({ viewport: `${width}x${height}`, ...geometry });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: resolve(output, `investigation-${width}.png`), fullPage: width < 1101 });
      if (width === 360) {
        await page.getByRole("group", { name: "Investigation panels", exact: true }).getByRole("button", { name: "Scanner", exact: true }).click();
        assert.ok(await page.getByRole("button", { name: "Scan ADX window", exact: true }).isVisible());
        await page.screenshot({ path: resolve(output, "scanner-mobile.png"), fullPage: true });
        await page.getByRole("group", { name: "Investigation panels", exact: true }).getByRole("button", { name: "Chat", exact: true }).click();
        assert.ok(await page.getByRole("textbox", { name: "Message Review agent", exact: true }).isVisible());
        await page.screenshot({ path: resolve(output, "chat-mobile.png"), fullPage: true });
      }
      await page.getByRole("tab", { name: "Explorer", exact: true }).click();
      await page.getByRole("button", { name: "EventsUnified", exact: true }).click();
      await page.getByRole("tab", { name: "metadata", exact: true }).click();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: resolve(output, `explorer-${width}.png`), fullPage: width < 1101 });
      if (width === 360) {
        await page.getByRole("button", { name: "Configuration", exact: true }).click();
        const bounds = await page.getByRole("dialog", { name: "Configuration", exact: true }).boundingBox();
        assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width);
        await page.keyboard.press("Escape");
      }
    });
  }
  for (const width of [1440, 360]) {
    await page.setViewportSize({ width, height: 900 });
    for (const workspace of ["Investigation", "Explorer"]) {
      await check(`automated accessibility ${workspace} at ${width}px`, async () => {
        await page.getByRole("tab", { name: workspace, exact: true }).click();
        const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
        assert.deepEqual(result.violations.map(issue => ({ id: issue.id, nodes: issue.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) })), []);
      });
    }
  }
  await check("200% equivalent reflow and keyboard workspace switch", async () => {
    await page.setViewportSize({ width: 720, height: 450 });
    await page.getByRole("tab", { name: "Investigation", exact: true }).focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.getByRole("tab", { name: "Explorer", exact: true }).getAttribute("aria-selected"), "true");
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: resolve(output, "explorer-zoom-reflow.png"), fullPage: true });
  });
  assert.deepEqual(prohibitedRequests, []);
  assert.deepEqual(errors, []);
  const artifact = createHash("sha256").update(await readFile(new URL("../dist/security-review.html", import.meta.url))).digest("hex");
  await writeFile(resolve(output, "report.json"), JSON.stringify({ status: "PASS", cases, measurements, errors, prohibitedRequests, artifact }, null, 2) + "\n");
  console.log(`Security review preview PASS: ${cases.length}/${cases.length}, no API/external requests or runtime errors; ${output}`);
} catch (error) {
  await writeFile(resolve(output, "failure.json"), JSON.stringify({ error: String(error), cases, errors, prohibitedRequests, measurements }, null, 2) + "\n");
  throw error;
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.httpServer.close(error => error ? rejectClose(error) : resolveClose()));
}