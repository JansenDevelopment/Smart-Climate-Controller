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
  "old-backend-devices", "cv-paused-morning-short", "pause-open", "airco-external",
  "airco-unavailable", "all-unavailable", "entity-missing", "old-backend-pause",
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
    // Cooling block unfolded although cooling is not relevant (winter): forecast tiles + collapse control.
    shots.push({ card: "main", scenario: "winter-heat", theme, w, lang: "nl", coolOpen: true });
  }
}
for (const s of ["winter-heat", "summer-cool", "override-next", "leaving-soon", "all-manual", "airco-external",
  "airco-unavailable", "cv-paused-morning", "pause-open", "autumn-idle"]) {
  shots.push({ card: "main", scenario: s, theme: "light", w: 390, lang: "en" });
}
shots.push({ card: "main", scenario: "winter-heat", theme: "dark", w: 390, lang: "en", menu: "climate.cv", pick: "Don't use" });
shots.push({ card: "schedule", scenario: "winter-heat", theme: "dark", w: 700, lang: "en" });
shots.push({ card: "schedule", scenario: "old-backend", theme: "light", w: 390, lang: "en" });
shots.push({ card: "schedule", scenario: "schedule-52", theme: "light", w: 700, lang: "en" });
shots.push({ card: "schedule", scenario: "entity-missing", theme: "light", w: 390, lang: "nl" });

const errors = [];
const audits = []; // touch-target and contrast findings
const heights = []; // card heights, to keep an eye on the length
const browser = await chromium.launch();

// Runs inside the page: buttons smaller than 44 px (main card), and text below WCAG AA contrast.
function auditPage({ touch }) {
  const root = window.__card.shadowRoot;
  const parse = (c) => {
    // rgb(r, g, b[, a]) or, for color-mix() results, color(srgb r g b[ / a]) with 0..1 channels.
    const m = c.match(/[\d.]+(?:e-?\d+)?/g).map(Number);
    const k = c.startsWith("color(") ? 255 : 1;
    return { r: m[0] * k, g: m[1] * k, b: m[2] * k, a: m[3] ?? 1 };
  };
  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const lum = ({ r, g, b }) => {
    const f = (v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  const parentOf = (n) => n.parentElement || n.getRootNode().host || null;
  const bgOf = (el) => {
    const layers = [];
    for (let n = el; n; n = parentOf(n)) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c.a > 0) layers.push(c);
      if (c.a >= 1) break;
    }
    let base = parse(getComputedStyle(document.body).backgroundColor);
    if (base.a < 1) base = { r: 255, g: 255, b: 255, a: 1 };
    for (const l of layers.reverse()) base = over(l, base);
    return base;
  };
  const out = { small: [], contrast: [] };
  if (touch) {
    for (const el of root.querySelectorAll("button, [role=switch], input, select")) {
      const r = el.getBoundingClientRect();
      if (r.width < 43.5 || r.height < 43.5) {
        const label = (el.getAttribute("aria-label") || el.textContent).replace(/\s+/g, " ").trim().slice(0, 40);
        out.small.push(`${label} ${Math.round(r.width)}x${Math.round(r.height)}`);
      }
    }
  }
  for (const el of root.querySelectorAll("*")) {
    // Dimmed (coordinator off), disabled and the decorative glyph inside a node dot are not read as text.
    if (el.closest("[dimmed]") || el.disabled || el.closest("button:disabled") || el.classList.contains("next-badge")) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own.length) continue;
    const cs = getComputedStyle(el);
    const svgText = el instanceof SVGElement;
    const fg = parse(svgText ? cs.fill : cs.color);
    if (svgText && cs.fill === "none") continue;
    const bg = bgOf(svgText ? el.closest("svg") : el);
    const c = ratio(over(fg, bg), bg);
    const size = parseFloat(cs.fontSize);
    const bold = Number(cs.fontWeight) >= 700;
    const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
    if (c < need) out.contrast.push(`${own[0].textContent.trim().slice(0, 30)} (${size}px) ${c.toFixed(2)}:1 < ${need}`);
  }
  return out;
}

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
  const name = `${s.card}-${s.scenario}${s.menu ? "-menu" + (s.pick ? "-" + s.pick.toLowerCase().replace(/\W+/g, "") : "") : ""}${s.coolOpen ? "-cool" : ""}-${s.theme}-${s.w}${s.lang === "en" ? "-en" : ""}`;
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
  if (s.coolOpen) {
    await page.evaluate(() => window.__card.shadowRoot.querySelector(".fold")?.click());
    await page.waitForTimeout(150);
  }
  if (s.scenario !== "entity-missing") {
    const a = await page.evaluate(auditPage, { touch: s.card === "main" });
    for (const t of a.small) audits.push(`[touch ${name}] ${t}`);
    for (const t of a.contrast) audits.push(`[contrast ${name}] ${t}`);
  }
  if (s.card === "main" && s.theme === "light" && s.lang === "nl" && !s.menu && !s.coolOpen) {
    heights.push(`${s.scenario} @${s.w}: ${await page.evaluate(() => Math.round(window.__card.getBoundingClientRect().height))} px`);
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
    check("winter: cooling folded to one line", (await page.evaluate(() => window.__card.shadowRoot.querySelector(".fold")?.textContent.trim())) === "Koelen: Auto · nu niet nodig");
    check("winter: no forecast tiles while folded", await page.evaluate(() => !window.__card.shadowRoot.querySelector(".tiles")));
    await page.evaluate(() => window.__card.shadowRoot.querySelector(".fold").click());
    await page.waitForTimeout(100);
    check("tap unfolds cooling (aria-expanded, tiles, collapse control)", await page.evaluate(() => {
      const r = window.__card.shadowRoot;
      return !!r.querySelector(".tiles--in") && r.querySelector(".fold--close")?.getAttribute("aria-expanded") === "true";
    }));
    check("cooling 'Aan' button found", await click(page, "Aan"));
    check("set_cooling_mode on", (await calls(page)).some((c) => c.includes('smart_climate.set_cooling_mode') && c.includes('"mode":"on"')));
    check("override block comes first in the body", await page.evaluate(() => window.__card.shadowRoot.querySelector(".body > section")?.classList.contains("override")));
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
    check("old backend: no room-source line", await page.evaluate(() => !window.__card.shadowRoot.querySelector(".source")));
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
    check("no radiogroup/radio roles left (aria-pressed buttons instead)", await q(() => !window.__card.shadowRoot.querySelector('[role="radio"],[role="radiogroup"]')));
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
    await pickSeg("Niet gebruiken");
    await page.waitForTimeout(50);
    check("menu: picked mode is aria-pressed", await q(() => window.__card.shadowRoot.querySelector('.devmenu .segmented [aria-pressed="true"]')?.textContent.trim() === "Niet gebruiken"));
    check("Blijvend is the quiet (tertiary) option", await q(() => [...window.__card.shadowRoot.querySelectorAll(".devmenu .choice")].map((b) => b.classList.contains("choice--quiet")).join() === "false,false,false,true"));
    check("Niet gebruiken shows duration choices (30 min, 1 uur, Tot 10:00, Blijvend)", (await text(".devmenu .choices")) === "30 min 1 uur Tot 10:00 Blijvend", await text(".devmenu .choices"));
    check("pick does not call the service yet", !(await calls(page)).some((c) => c.includes("set_device_mode")));
    await choice("30 min", ".devmenu");
    check("Niet gebruiken 30 min -> set_device_mode off minutes 30", (await last()).includes('set_device_mode {"entity_id":"climate.smart_climate","device":"climate.airco","mode":"off","minutes":30}'), await last());
    await page.waitForTimeout(100);
    check("menu closed after pick", await q(() => !window.__card.shadowRoot.querySelector(".devmenu")));
    const chipText = await text(chip("climate.airco"));
    check("chip shows 'Airco · verwarmt' + 'Niet gebruiken · nog 30 min'", chipText?.includes("Airco · verwarmt") && chipText?.includes("Niet gebruiken · nog 30 min"), chipText);
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
    check("until_morning: toggle shows the real end 'Geen CV tot 10:00' and is pressed", (await text(".toggle-chip")) === "Geen CV tot 10:00" && (await q(() => window.__card.shadowRoot.querySelector(".toggle-chip").getAttribute("aria-pressed"))) === "true", await text(".toggle-chip"));
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
    const r = await page.evaluate(() => {
      const root = window.__card.shadowRoot;
      return {
        toggle: root.querySelector(".toggle-chip").textContent.trim(),
        pressed: root.querySelector(".toggle-chip").getAttribute("aria-pressed"),
        leaving: !!root.querySelector(".leaving-active"),
        dev: root.querySelector(".deviation")?.textContent.replace(/\s+/g, " ").trim(),
      };
    });
    check("user-set Niet gebruiken is not a pause (toggle off, no resume row)", r.toggle === "Geen CV tot morgenochtend" && r.pressed === "false" && !r.leaving, JSON.stringify(r));
    check("permanent deviation line under the headline", r.dev === "CV staat op Niet gebruiken — Weer automatisch", r.dev);
    await page.evaluate(() => window.__card.shadowRoot.querySelector(".deviation .link").click());
    check("'Weer automatisch' -> set_device_mode auto", (await calls(page)).at(-1)?.endsWith('"device":"climate.cv","mode":"auto"}'), (await calls(page)).at(-1));
    await page.waitForTimeout(100);
    check("deviation line gone after Weer automatisch", await page.evaluate(() => !window.__card.shadowRoot.querySelector(".deviation")));
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
  // ── pause kinds, external control, error states, room source ──
  const probe = async (scenario, lang, fn, arg) => {
    const { ctx, page } = await open({ card: "main", scenario, theme: "light", w: 390, lang });
    const r = await page.evaluate(fn, arg);
    await ctx.close();
    return r;
  };
  const txt = (sel) => (a) => window.__card.shadowRoot.querySelector(a)?.textContent.replace(/\s+/g, " ").trim() ?? null;
  {
    const r = await probe("cv-paused-morning-short", "nl", () => {
      const root = window.__card.shadowRoot;
      return { toggle: root.querySelector(".toggle-chip").textContent.trim(), pressed: root.querySelector(".toggle-chip").getAttribute("aria-pressed"), leaving: !!root.querySelector(".leaving-active") };
    });
    check("until_morning ending in 90 min (this morning): 'Geen CV tot 17:00', pressed, no 'ik ga zo weg'", r.toggle === "Geen CV tot 17:00" && r.pressed === "true" && !r.leaving, JSON.stringify(r));
  }
  {
    const r = await probe("pause-open", "nl", () => {
      const root = window.__card.shadowRoot;
      return { active: root.querySelector(".leaving-active")?.textContent.replace(/\s+/g, " ").trim(), pressed: root.querySelector(".toggle-chip").getAttribute("aria-pressed"), label: !!root.querySelector(".leaving-label") };
    });
    check("kind open: 'CV gepauzeerd (tot je hem hervat)' + Hervat", r.active === "CV gepauzeerd (tot je hem hervat) Hervat" && r.pressed === "false" && !r.label, JSON.stringify(r));
  }
  {
    const r = await probe("old-backend-pause", "nl", () => {
      const root = window.__card.shadowRoot;
      return { active: root.querySelector(".leaving-active")?.textContent.replace(/\s+/g, " ").trim(), chips: root.querySelectorAll("button.chip").length };
    });
    check("old backend (no support_pause_kind): duration heuristic still gives 'nog 40 min'", r.active?.startsWith("CV gepauzeerd, nog 40 min"), JSON.stringify(r));
  }
  {
    const { ctx, page } = await open({ card: "main", scenario: "airco-external", theme: "light", w: 390, lang: "nl" });
    const r = await page.evaluate(() => {
      const root = window.__card.shadowRoot;
      return {
        chip: root.querySelector('button.chip[data-device="climate.airco"]').textContent.replace(/\s+/g, " ").trim(),
        dev: root.querySelector(".deviation")?.textContent.replace(/\s+/g, " ").trim(),
      };
    });
    check("external control: chip says 'Handmatig (afstandsbediening)'", r.chip.includes("Airco · verwarmt") && r.chip.includes("Handmatig (afstandsbediening)"), r.chip);
    check("external control: deviation line", r.dev === "Airco staat op Handmatig (afstandsbediening) — Weer automatisch", r.dev);
    await ctx.close();
  }
  for (const [scenario, lang, expect] of [
    ["airco-unavailable", "nl", "Airco niet beschikbaar"],
    ["airco-unavailable", "en", "Airco not available"],
    ["all-unavailable", "nl", "Airco en CV niet beschikbaar"],
  ]) {
    const t = await probe(scenario, lang, txt(".sentence"), ".sentence");
    check(`unavailable sentence ${scenario}/${lang}`, t === expect, t);
  }
  {
    const t = await probe("airco-unavailable", "nl", () => window.__card.shadowRoot.querySelector('button.chip[data-device="climate.airco"]').textContent.replace(/\s+/g, " ").trim());
    check("unavailable chip says 'niet beschikbaar'", t.includes("Airco · niet beschikbaar"), t);
  }
  {
    const t = await probe("entity-missing", "nl", () => ({ title: window.__card.shadowRoot.querySelector(".error-title")?.textContent.trim(), icon: !!window.__card.shadowRoot.querySelector(".error ha-icon") }));
    check("missing entity: friendly error card with icon", t.title === "Entiteit niet gevonden" && t.icon, JSON.stringify(t));
  }
  for (const [scenario, expect] of [
    ["autumn-idle", "Kamer: Woonkamer sensor"],
    ["summer-cool", "Kamer: Airco"],
    ["winter-heat", "Kamer: gemiddelde van apparaten"],
  ]) {
    const t = await probe(scenario, "nl", txt(".source"), ".source");
    check(`room temperature source ${scenario}`, t === expect, t);
  }
  {
    const r = await probe("autumn-idle", "nl", () => {
      const root = window.__card.shadowRoot;
      return { fold: root.querySelector(".fold")?.textContent.trim(), tiles: !!root.querySelector(".tiles"), sentence: root.querySelector(".sentence").textContent.trim() };
    });
    check("autumn: cooling folded, tiles hidden", r.fold === "Koelen: Auto · nu niet nodig" && !r.tiles, JSON.stringify(r));
    check("idle sentence wording", r.sentence === "Niets actief: de kamer ligt boven het doel", r.sentence);
  }
  {
    const r = await probe("summer-cool", "nl", () => {
      const root = window.__card.shadowRoot;
      return { fold: !!root.querySelector(".fold"), tiles: !!root.querySelector(".tiles"), hint: root.querySelector(".hint")?.textContent.replace(/\s+/g, " ").trim() };
    });
    check("summer: cooling fully visible with tiles, no fold", !r.fold && r.tiles, JSON.stringify(r));
  }
  {
    const r = await probe("winter-heat", "en", () => {
      const root = window.__card.shadowRoot;
      return { toggle: root.querySelector(".toggle-chip").textContent.trim(), hint: root.querySelector(".pause .hint").textContent.trim() };
    });
    check("EN: 'No heating support until tomorrow morning'", r.toggle === "No heating support until tomorrow morning", r.toggle);
  }
  {
    // English texts use the support device's own name, "support heater" without one.
    const { ctx, page } = await open({ card: "main", scenario: "leaving-soon", theme: "light", w: 390, lang: "en" });
    const r = await page.evaluate(() => {
      window.__hass.states["climate.cv"].attributes.friendly_name = "Boiler";
      window.__card.hass = { ...window.__hass, states: { ...window.__hass.states } };
      return window.__card.updateComplete.then(() => {
        const root = window.__card.shadowRoot;
        const a = root.querySelector(".leaving-active").textContent.replace(/\s+/g, " ").trim();
        const h = root.querySelector(".pause .hint").textContent.trim();
        return { a, h, hasCV: /\bCV\b/.test(root.textContent) };
      });
    });
    check("EN: support name from friendly_name, no hardcoded CV", r.a.startsWith("Boiler paused, 40 min left") && r.h.includes("the Boiler") && !r.hasCV, JSON.stringify(r));
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "schedule", scenario: "winter-heat", theme: "light", w: 700, lang: "nl" });
    const r = await page.evaluate(() => {
      const root = window.__card.shadowRoot;
      const t = root.textContent.replace(/\s+/g, " ");
      const left = ["Schedule", "All Days", "Individual", " Save", "Weekday", "Temperature", "Time (24", "Double-click", "Heat to", "Cool above", "Idle band", "Leaving", "springt", "Unsaved", "Hard plafond"].filter((w) => t.includes(w));
      const band = [...root.querySelectorAll("svg.graph path")].find((p) => p.getAttribute("fill") === "#4aa8ff" && p.getAttribute("stroke") === "none")?.getAttribute("d") ?? "";
      const pts = band.replace(" Z", "").split(" L").map((q) => q.replace(/^M|^L/, "").split(",").map(Number));
      const last = pts.at(-1), prev = pts.at(-2);
      return { left, away: root.querySelector(".away-line")?.textContent.trim(), t, lastX: last?.[0], vertical: prev && last && prev[1] === last[1] };
    });
    check("schedule nl: no English leftovers", r.left.length === 0, JSON.stringify(r.left));
    check("schedule: away line", r.away === "Bij afwezigheid: 15° verwarmen / 28° koelen", r.away);
    check("schedule: idle band closes horizontally at x=0 (no diagonal)", r.lastX === 52 && r.vertical, JSON.stringify({ x: r.lastX, v: r.vertical }));
    check("schedule: 'CV mag bijspringen' + ceiling wording", (r.t.includes("CV mag bijspringen onder") || r.t.includes("CV onder ")) && r.t.includes("Koelen altijd toegestaan boven 26°") && r.t.includes("CV-drempel"), "");
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ card: "schedule", scenario: "winter-heat", theme: "light", w: 700, lang: "en" });
    const t = await page.evaluate(() => window.__card.shadowRoot.textContent.replace(/\s+/g, " "));
    check("schedule en: '{support} may join below' + away line", (t.includes("CV may join below") || t.includes("CV below ")) && t.includes("Cooling always allowed above 26°") && t.includes("When away: heat to 15° / cool to 28°"), "");
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
    await click(page, "Opslaan");
    await page.waitForTimeout(200);
    check("schedule: set_schedule called", (await calls(page)).some((x) => x.includes("smart_climate.set_schedule")));
    await ctx.close();
  }
  console.log("\n" + results.join("\n"));
}

console.log("\nCard heights (css px):\n" + heights.filter((h) => /@390/.test(h)).join("\n"));
if (audits.length) {
  const uniq = [...new Set(audits)];
  console.log(`\nAudit findings (${uniq.length}):\n` + uniq.join("\n"));
} else console.log("\nAudit: all touch targets >= 44 px and all text >= WCAG AA contrast.");
console.log(errors.length ? `\nConsole/page errors (${errors.length}):\n` + [...new Set(errors)].join("\n") : "\nNo console or page errors.");
await browser.close();
server?.close();
