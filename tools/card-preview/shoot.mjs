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
  "cv-paused-morning", "leaving-soon", "airco-manual", "all-manual", "cv-off-forever",
  "old-backend-devices",
];
const scheduleScenarios = ["winter-heat", "summer-cool", "old-backend", "schedule-null", "schedule-52"];
const shots = [];
for (const theme of ["light", "dark"]) {
  for (const w of [700, 390]) {
    for (const s of mainScenarios) shots.push({ card: "main", scenario: s, theme, w, lang: "nl" });
    for (const s of scheduleScenarios) shots.push({ card: "schedule", scenario: s, theme, w, lang: "nl" });
    // Device control menu open on the airco chip (Auto, and Off with the duration choices).
    shots.push({ card: "main", scenario: "winter-heat", theme, w, lang: "nl", menu: "climate.airco" });
    shots.push({ card: "main", scenario: "airco-manual", theme, w, lang: "nl", menu: "climate.airco", pick: "Handmatig" });
  }
}
for (const s of ["winter-heat", "summer-cool", "override-next", "leaving-soon", "all-manual"]) {
  shots.push({ card: "main", scenario: s, theme: "light", w: 390, lang: "en" });
}
shots.push({ card: "main", scenario: "winter-heat", theme: "dark", w: 390, lang: "en", menu: "climate.cv", pick: "Off" });
shots.push({ card: "schedule", scenario: "winter-heat", theme: "dark", w: 700, lang: "en" });
shots.push({ card: "schedule", scenario: "old-backend", theme: "light", w: 390, lang: "en" });

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
  const name = `${s.card}-${s.scenario}${s.menu ? "-menu" + (s.pick ? "-" + s.pick.toLowerCase() : "") : ""}-${s.theme}-${s.w}${s.lang === "en" ? "-en" : ""}`;
  if (filter && !name.includes(filter)) continue;
  const { ctx, page } = await open(s);
  if (s.menu) {
    await page.evaluate((id) => window.__card.shadowRoot.querySelector(`button.chip[data-device="${id}"]`).click(), s.menu);
    if (s.pick) {
      await page.evaluate((t) => {
        [...window.__card.shadowRoot.querySelectorAll(".devmenu .segmented button")].find((b) => b.textContent.trim() === t).click();
      }, s.pick);
    }
    await page.waitForTimeout(150);
  }
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
    const { ctx, page } = await open({ card: "main", scenario: "winter-heat", theme: "light", w: 390, lang: "nl" });
    check("cooling 'Aan' button found", await click(page, "Aan"));
    check("set_cooling_mode on", (await calls(page)).some((c) => c.includes('smart_climate.set_cooling_mode') && c.includes('"mode":"on"')));
    await click(page, "30 min", ".override");
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
    const { ctx, page } = await open({ card: "main", scenario: "override-next", theme: "light", w: 390, lang: "nl" });
    const status = await page.evaluate(() => window.__card.shadowRoot.querySelector(".status").textContent.trim());
    check("next_node status text", status === "Tot volgende schakeltijd", status);
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "main", scenario: "old-backend", theme: "light", w: 390, lang: "nl" });
    const txt = await page.evaluate(() => window.__card.shadowRoot.textContent);
    check("old backend: no cooling/support/tiles section", !txt.includes("Koelen") && !txt.includes("CV-ondersteuning") && !txt.includes("Verwacht max"));
    await ctx.close();
  }
  // ── device chips, control menu and support pause ──
  {
    const { ctx, page } = await open({ card: "main", scenario: "winter-heat", theme: "light", w: 390, lang: "nl" });
    const q = (fn, ...a) => page.evaluate(fn, ...a);
    const chip = (id) => `button.chip[data-device="${id}"]`;
    const clickSel = (sel) => q((s) => { const el = window.__card.shadowRoot.querySelector(s); el?.click(); return !!el; }, sel);
    const text = (sel) => q((s) => window.__card.shadowRoot.querySelector(s)?.textContent.replace(/\s+/g, " ").trim() ?? null, sel);
    const pickSeg = (t) => q((t) => { const b = [...window.__card.shadowRoot.querySelectorAll(".devmenu .segmented button")].find((x) => x.textContent.trim() === t); b?.click(); return !!b; }, t);
    const choice = (t, scope) => q(({ t, scope }) => { const b = [...window.__card.shadowRoot.querySelectorAll(`${scope} .choice`)].find((x) => x.textContent.trim() === t); b?.click(); return !!b; }, { t, scope });
    const last = async () => (await calls(page)).at(-1) ?? "";

    check("device chips are buttons", await q(() => [...window.__card.shadowRoot.querySelectorAll("button.chip[data-device]")].length === 2));
    check("menu closed initially", (await q(() => !window.__card.shadowRoot.querySelector(".devmenu"))));
    await clickSel(chip("climate.airco"));
    await page.waitForTimeout(50);
    check("chip tap opens menu, aria-expanded", await q(() => !!window.__card.shadowRoot.querySelector(".devmenu") && window.__card.shadowRoot.querySelector('button.chip[data-device="climate.airco"]').getAttribute("aria-expanded") === "true"));
    check("focus moved into menu", await q(() => window.__card.shadowRoot.activeElement?.closest?.(".devmenu") != null));
    await page.keyboard.press("Escape");
    await page.waitForTimeout(50);
    check("Escape closes menu and refocuses chip", await q(() => !window.__card.shadowRoot.querySelector(".devmenu") && window.__card.shadowRoot.activeElement?.dataset?.device === "climate.airco"));
    await clickSel(chip("climate.airco"));
    await page.waitForTimeout(50);
    await page.mouse.click(5, 5); // outside the card
    await page.waitForTimeout(50);
    check("click outside closes menu", await q(() => !window.__card.shadowRoot.querySelector(".devmenu")));

    await clickSel(chip("climate.airco"));
    await pickSeg("Uit");
    await page.waitForTimeout(50);
    check("Uit shows duration choices (30 min, 1 uur, Tot 10:00, Blijvend)", (await text(".devmenu .choices")) === "30 min 1 uur Tot 10:00 Blijvend", await text(".devmenu .choices"));
    check("Uit does not call the service yet", !(await calls(page)).some((c) => c.includes("set_device_mode")));
    await choice("30 min", ".devmenu");
    check("Uit 30 min -> set_device_mode off minutes 30", (await last()).includes('set_device_mode {"entity_id":"climate.smart_climate","device":"climate.airco","mode":"off","minutes":30}'), await last());
    await page.waitForTimeout(100);
    check("menu closed after pick", await q(() => !window.__card.shadowRoot.querySelector(".devmenu")));
    const chipText = await text(chip("climate.airco"));
    check("chip shows 'Uit · nog 30 min'", chipText?.includes("Uit · nog 30 min"), chipText);
    check("chip marked data-mode=off", await q(() => window.__card.shadowRoot.querySelector('button.chip[data-device="climate.airco"]').dataset.mode === "off"));
    check("sentence no longer names the airco as active", !(await text(".sentence")).includes("Airco"), await text(".sentence"));

    await clickSel(chip("climate.airco"));
    await pickSeg("Handmatig");
    await choice("Blijvend", ".devmenu");
    check("Handmatig Blijvend -> no minutes/until", (await last()).endsWith('"mode":"manual"}'), await last());
    await page.waitForTimeout(100);
    check("chip shows 'Handmatig' without time", (await text(chip("climate.airco"))).endsWith("Handmatig"), await text(chip("climate.airco")));

    await clickSel(chip("climate.airco"));
    await pickSeg("Handmatig");
    await choice("Tot 10:00", ".devmenu");
    const m = /"minutes":(\d+)/.exec(await last());
    check("Tot 10:00 -> minutes until next 10:00 (fixed clock 15:30 => 1110)", m && Number(m[1]) === 1110, await last());
    await page.waitForTimeout(100);
    check("chip shows 'tot 10:00'", (await text(chip("climate.airco"))).includes("tot 10:00"), await text(chip("climate.airco")));

    await clickSel(chip("climate.airco"));
    await pickSeg("Auto");
    check("Auto -> set_device_mode auto without minutes", (await last()).endsWith('"device":"climate.airco","mode":"auto"}'), await last());
    await page.waitForTimeout(100);
    check("chip back to normal after Auto", await q(() => window.__card.shadowRoot.querySelector('button.chip[data-device="climate.airco"]').dataset.mode === "auto"));

    // Support pause
    check("support pause block present", (await text(".pause")) !== null);
    await clickSel(".toggle-chip");
    check("'Geen CV tot morgenochtend' -> until_morning", (await last()).includes('set_support_pause {"entity_id":"climate.smart_climate","enabled":true,"until_morning":true}'), await last());
    await page.waitForTimeout(100);
    check("toggle shows 'Geen CV tot 10:00' and is pressed", (await text(".toggle-chip")) === "Geen CV tot 10:00" && (await q(() => window.__card.shadowRoot.querySelector(".toggle-chip").getAttribute("aria-pressed"))) === "true", await text(".toggle-chip"));
    check("sentence says (CV gepauzeerd)", (await text(".sentence")).includes("(CV gepauzeerd)"), await text(".sentence"));
    await clickSel(".toggle-chip");
    check("toggle off -> enabled false", (await last()).endsWith('"enabled":false}'), await last());
    await page.waitForTimeout(100);
    check("toggle back to 'Geen CV tot morgenochtend'", (await text(".toggle-chip")) === "Geen CV tot morgenochtend", await text(".toggle-chip"));
    await choice("1 uur", ".leaving");
    check("'Ik ga zo weg' 1 uur -> minutes 60", (await last()).includes('"enabled":true,"minutes":60'), await last());
    await page.waitForTimeout(100);
    check("shows 'CV gepauzeerd, nog 1 u' + Hervat", (await text(".leaving-active")).startsWith("CV gepauzeerd, nog 1 u"), await text(".leaving-active"));
    check("short pause: morning toggle stays off", (await text(".toggle-chip")) === "Geen CV tot morgenochtend");
    await choice("Hervat", ".leaving");
    check("Hervat -> enabled false", (await last()).endsWith('"enabled":false}'), await last());
    await ctx.close();
  }
  for (const [scenario, lang, expect] of [
    ["cv-paused-morning", "nl", "Airco verwarmt naar 20° (CV gepauzeerd)"],
    ["airco-manual", "nl", "CV verwarmt naar 20°"],
    ["all-manual", "nl", "Alles handmatig: de coördinator stuurt niets aan"],
    ["all-manual", "en", "Everything manual: the coordinator drives nothing"],
  ]) {
    const { ctx, page } = await open({ card: "main", scenario, theme: "light", w: 390, lang });
    const t = await page.evaluate(() => window.__card.shadowRoot.querySelector(".sentence").textContent.trim());
    check(`sentence ${scenario}/${lang}`, t === expect, t);
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "main", scenario: "leaving-soon", theme: "light", w: 390, lang: "nl" });
    const r = await page.evaluate(() => {
      const root = window.__card.shadowRoot;
      return { active: root.querySelector(".leaving-active")?.textContent.replace(/\s+/g, " ").trim(), morning: root.querySelector(".toggle-chip").textContent.trim() };
    });
    check("leaving-soon: 'CV gepauzeerd, nog 40 min'", r.active?.startsWith("CV gepauzeerd, nog 40 min"), JSON.stringify(r));
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "main", scenario: "cv-off-forever", theme: "light", w: 390, lang: "nl" });
    const t = await page.evaluate(() => window.__card.shadowRoot.querySelector(".toggle-chip").textContent.trim());
    check("open-ended pause label", t === "Geen CV (tot je hem weer aanzet)", t);
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "main", scenario: "old-backend-devices", theme: "light", w: 390, lang: "nl" });
    const r = await page.evaluate(() => {
      const root = window.__card.shadowRoot;
      return { support: !!root.textContent.includes("CV-ondersteuning"), pause: !!root.querySelector(".pause"), chips: root.querySelectorAll("button.chip[data-device]").length };
    });
    check("backend without new attributes: support block stays, no pause shortcuts, chips still work", r.support && !r.pause && r.chips === 2, JSON.stringify(r));
    await ctx.close();
  }
  {
    // Time helpers, independent of the browser's own time zone.
    const { ctx, page } = await open({ card: "main", scenario: "winter-heat", theme: "light", w: 390, lang: "nl" });
    const r = await page.evaluate(async () => {
      const m = await import("/custom_components/smart_climate/smart-climate-shared.js");
      const now = new Date("2026-10-01T12:00:00Z"); // 14:00 in Amsterdam, 08:00 in New York
      return {
        ams: m.minutesUntilClock({ config: { time_zone: "Europe/Amsterdam" } }, 10, 0, now),
        ny: m.minutesUntilClock({ config: { time_zone: "America/New_York" } }, 10, 0, now),
        bad: Number.isInteger(m.minutesUntilClock({ config: { time_zone: "Nope/Zone" } }, 10, 0, now)),
        clock: m.fmtClock("2026-10-02T08:00:00Z", { config: { time_zone: "Europe/Amsterdam" } }),
        empty: m.fmtClock("", {}),
      };
    });
    check("minutesUntilClock follows the HA time zone", r.ams === 20 * 60 && r.ny === 2 * 60 && r.bad, JSON.stringify(r));
    check("fmtClock in HA time zone", r.clock === "10:00" && r.empty === "", JSON.stringify(r));
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
