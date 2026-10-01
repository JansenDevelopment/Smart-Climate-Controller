// Renders screenshots of the cards in the mock harness and smoke-tests the
// interactions. Usage (from anywhere):
//
//   node tools/card-preview/shoot.mjs [filter]
//
// `filter` is an optional substring of the shot name (e.g. "winter").
// Needs Playwright (+ Chromium); point PLAYWRIGHT_PATH at its folder if it is not
// resolvable from here. It serves the repo root itself; set BASE_URL to use an
// already running `python -m http.server` instead.
import { createRequire } from "node:module";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const require = createRequire(import.meta.url);
const pwPath = process.env.PLAYWRIGHT_PATH ?? "D:/git/Martijn/HomeAssistant/tools/node_modules/playwright";
const { chromium } = require(pwPath);

const filter = process.argv[2] ?? "";
const shotsDir = path.join(here, "shots");
fs.mkdirSync(shotsDir, { recursive: true });

// ── static server ──────────────────────────────────────────────────────────
const types = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json" };
let base = process.env.BASE_URL;
let server;
if (!base) {
  server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split("?")[0]);
    const file = path.join(repoRoot, rel);
    if (!file.startsWith(repoRoot)) return res.writeHead(403).end();
    fs.readFile(file, (err, buf) => {
      if (err) return res.writeHead(404).end("not found");
      res.setHeader("content-type", types[path.extname(file)] ?? "application/octet-stream");
      res.end(buf);
    });
  });
  await new Promise((r) => server.listen(0, r));
  base = `http://localhost:${server.address().port}`;
}

// ── shot list ──────────────────────────────────────────────────────────────
const mainScenarios = [
  "autumn-idle", "winter-heat", "summer-cool", "off", "override-next", "old-backend",
  "override-timer", "ceiling-cool", "summer-on",
];
const scheduleScenarios = ["winter-heat", "summer-cool", "old-backend", "schedule-null", "schedule-52"];
const shots = [];
for (const theme of ["light", "dark"]) {
  for (const w of [700, 420]) {
    for (const s of mainScenarios) shots.push({ card: "main", scenario: s, theme, w, lang: "nl" });
    for (const s of scheduleScenarios) shots.push({ card: "schedule", scenario: s, theme, w, lang: "nl" });
  }
}
for (const s of ["winter-heat", "summer-cool", "override-next"]) {
  shots.push({ card: "main", scenario: s, theme: "light", w: 420, lang: "en" });
}
shots.push({ card: "schedule", scenario: "winter-heat", theme: "dark", w: 700, lang: "en" });
shots.push({ card: "schedule", scenario: "old-backend", theme: "light", w: 420, lang: "en" });

const errors = [];
const browser = await chromium.launch();

async function open(s, extra = {}) {
  const ctx = await browser.newContext({ viewport: { width: s.w + 32, height: 1200 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const tag = `${s.card}-${s.scenario}-${s.theme}-${s.w}-${s.lang}`;
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") errors.push(`[${tag}] console.${m.type()}: ${m.text().slice(0, 240)}`);
  });
  page.on("pageerror", (e) => errors.push(`[${tag}] PAGEERROR: ${String(e).slice(0, 300)}`));
  page.on("requestfailed", (r) => errors.push(`[${tag}] requestfailed: ${r.url().slice(0, 120)}`));
  // Fixed clock so the "now" marker and history are the same on every run.
  await page.clock.setFixedTime(new Date("2026-10-01T15:30:00"));
  const qs = new URLSearchParams({
    card: s.card, scenario: s.scenario, theme: s.theme, lang: s.lang, w: String(s.w), ...extra,
  });
  await page.goto(`${base}/tools/card-preview/index.html?${qs}`, { waitUntil: "load" });
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 20000 });
  await page.waitForTimeout(900);
  return { ctx, page, tag };
}

let n = 0;
for (const s of shots) {
  const name = `${s.card}-${s.scenario}-${s.theme}-${s.w}${s.lang === "en" ? "-en" : ""}`;
  if (filter && !name.includes(filter)) continue;
  const { ctx, page } = await open(s);
  await page.locator("#wrap").screenshot({ path: path.join(shotsDir, `${name}.png`) });
  await ctx.close();
  n++;
}
console.log(`${n} screenshots in ${shotsDir}`);

// ── interaction smoke tests (main card + schedule card) ─────────────────────
if (!filter) {
  const results = [];
  const check = (label, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${label}${ok ? "" : "  " + detail}`);
  const calls = (page) => page.evaluate(() => window.__hass.calls.map((c) => `${c.domain}.${c.service} ${JSON.stringify(c.data)}`));
  const click = (page, text, scope = "") =>
    page.evaluate(({ text, scope }) => {
      const root = window.__card.shadowRoot;
      const btn = [...root.querySelectorAll(`${scope} button`)].find((b) => b.textContent.trim() === text);
      if (!btn) return false;
      btn.click();
      return true;
    }, { text, scope });

  {
    const { ctx, page } = await open({ card: "main", scenario: "winter-heat", theme: "light", w: 420, lang: "nl" });
    check("cooling 'Aan' button found", await click(page, "Aan"));
    check("set_cooling_mode on", (await calls(page)).some((c) => c.includes('smart_climate.set_cooling_mode') && c.includes('"mode":"on"')));
    await click(page, "30 min");
    check("override timer 30 min with 20° start", (await calls(page)).some((c) => c.includes("set_override_timer") && c.includes('"minutes":30')), JSON.stringify(await calls(page)));
    await page.waitForTimeout(100);
    // Stepper: +0.5 twice from the backend's 21
    await page.evaluate(() => [...window.__card.shadowRoot.querySelectorAll(".stepper button")][1].click());
    await page.evaluate(() => [...window.__card.shadowRoot.querySelectorAll(".stepper button")][1].click());
    await page.waitForTimeout(800); // debounce re-applies the running timer with the new temperature
    const c = await calls(page);
    check("stepper re-applies running override with 22°", c.some((x) => x.includes("set_override_timer") && x.includes('"temperature":22')), JSON.stringify(c));
    check("'Terug naar schema' visible during override", await click(page, "Terug naar schema"));
    check("clear_override called", (await calls(page)).some((x) => x.includes("clear_override")));
    await page.evaluate(() => { window.__card.shadowRoot.querySelector(".switch").click(); });
    check("set_heat_support false", (await calls(page)).some((x) => x.includes("set_heat_support") && x.includes('"enabled":false')));
    await page.evaluate(() => { window.__card.shadowRoot.querySelector(".power").click(); });
    check("power off → climate.set_hvac_mode off", (await calls(page)).some((x) => x.includes("climate.set_hvac_mode") && x.includes('"off"')));
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "main", scenario: "override-next", theme: "light", w: 420, lang: "nl" });
    const status = await page.evaluate(() => window.__card.shadowRoot.querySelector(".status").textContent.trim());
    check("next_node status text", status === "Tot volgende schakeltijd", status);
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "main", scenario: "old-backend", theme: "light", w: 420, lang: "nl" });
    const txt = await page.evaluate(() => window.__card.shadowRoot.textContent);
    check("old backend: no cooling/support/tiles section", !txt.includes("Koelen") && !txt.includes("CV-ondersteuning") && !txt.includes("Verwacht max"));
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "schedule", scenario: "old-backend", theme: "light", w: 700, lang: "nl" });
    const r = await page.evaluate(() => {
      const root = window.__card.shadowRoot;
      return { warn: !!root.querySelector(".warning"), disabled: root.querySelector(".save-btn")?.disabled };
    });
    check("schedule: old backend shows warning + save disabled", r.warn && r.disabled === true, JSON.stringify(r));
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "schedule", scenario: "winter-heat", theme: "light", w: 700, lang: "nl" });
    // Add a node via double click on the graph, then save.
    const box = await page.evaluate(() => {
      const r = window.__card.shadowRoot.querySelector("svg.graph").getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    });
    await page.mouse.dblclick(box.x + box.w * 0.62, box.y + box.h * 0.4);
    await page.waitForTimeout(200);
    const saveEnabled = await page.evaluate(() => !window.__card.shadowRoot.querySelector(".save-btn").disabled);
    check("schedule: dblclick adds node → Save enabled", saveEnabled);
    await click(page, "Save");
    await page.waitForTimeout(200);
    check("schedule: set_schedule called", (await calls(page)).some((x) => x.includes("smart_climate.set_schedule")));
    await ctx.close();
  }
  console.log("\n" + results.join("\n"));
}

console.log(errors.length ? `\nConsole/page errors (${errors.length}):\n` + [...new Set(errors)].join("\n") : "\nNo console or page errors.");
await browser.close();
server?.close();
