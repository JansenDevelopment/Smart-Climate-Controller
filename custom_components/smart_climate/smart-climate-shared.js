// Small helpers shared by the Smart Climate cards (language, number formatting,
// and the auto-cooling explanation). Imported as an ES module by the cards;
// frontend.py copies it next to them and cache-busts the import.

/** "nl" when Home Assistant runs in Dutch, otherwise "en". */
export function langOf(hass) {
  const l = hass?.language || hass?.locale?.language || "en";
  return String(l).toLowerCase().startsWith("nl") ? "nl" : "en";
}

/**
 * Look up `key` in a `{ nl: {...}, en: {...} }` dictionary and fill `{name}`
 * placeholders from `vars`. Falls back to English, then to the key itself.
 */
export function translate(dict, hass, key, vars = {}) {
  const text = dict[langOf(hass)]?.[key] ?? dict.en?.[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ""));
}

/** Round to one decimal and use the decimal comma in Dutch. Null/NaN → "—". */
export function fmtNum(value, hass) {
  const n = Number(value);
  if (value === null || value === undefined || value === "" || Number.isNaN(n)) return "—";
  const s = String(Math.round(n * 10) / 10);
  return langOf(hass) === "nl" ? s.replace(".", ",") : s;
}

/** Temperature with degree sign, e.g. "19,5°". */
export function fmtTemp(value, hass) {
  const s = fmtNum(value, hass);
  return s === "—" ? s : `${s}°`;
}

/** Friendly name of an entity, falling back to the entity id. */
export function entityName(hass, entityId) {
  return hass?.states?.[entityId]?.attributes?.friendly_name ?? entityId;
}

/** Devices of a coordinator that act as support heater (e.g. the CV). */
export function supportDevices(attrs) {
  return (Array.isArray(attrs?.devices) ? attrs.devices : []).filter((d) => d.tier === "support");
}

/**
 * Control mode of one actuator: "auto" (the coordinator drives it), "off" (kept
 * off, never used) or "manual" (hands off). Backends without `device_modes`
 * know only "auto". Returns `{ mode, until }` (`until` is an ISO string or null).
 */
export function deviceMode(attrs, entityId) {
  const m = attrs?.device_modes?.[entityId];
  const mode = m?.mode === "off" || m?.mode === "manual" ? m.mode : "auto";
  return { mode, until: mode === "auto" ? null : m?.until || null };
}

/** Wall-clock parts of `date` in `timeZone` (the browser zone if it is missing/unknown). */
function zonedParts(date, timeZone) {
  const opts = {
    hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  };
  let fmt;
  try {
    fmt = new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: timeZone || undefined });
  } catch (_) {
    fmt = new Intl.DateTimeFormat("en-GB", opts);
  }
  const p = {};
  for (const part of fmt.formatToParts(date)) p[part.type] = Number(part.value);
  return p;
}

/** "10:00" for an ISO timestamp, in the Home Assistant time zone. Invalid input → "". */
export function fmtClock(iso, hass) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return "";
  const p = zonedParts(d, hass?.config?.time_zone);
  return `${String(p.hour).padStart(2, "0")}:${String(p.minute).padStart(2, "0")}`;
}

/**
 * Whole minutes (rounded up) from `now` until the next `hh:mm` wall-clock time in
 * the Home Assistant time zone. Sent as `minutes` so the browser's own time zone
 * never decides when "until 10:00" is.
 */
export function minutesUntilClock(hass, hh, mm, now = new Date()) {
  const p = zonedParts(now, hass?.config?.time_zone);
  let diff = hh * 60 + mm - (p.hour * 60 + p.minute + p.second / 60);
  if (diff <= 0) diff += 1440;
  return Math.ceil(diff);
}

/** Mode labels for the cooling policy. */
const COOLING_LABELS = {
  nl: { off: "Uit", auto: "Auto", on: "Aan" },
  en: { off: "Off", auto: "Auto", on: "On" },
};

/** Translated name of a cooling mode (off / auto / on). */
export function coolingLabel(hass, mode) {
  return COOLING_LABELS[langOf(hass)][mode] ?? mode;
}

const COOLING_TEXT = {
  nl: {
    ceiling: "kamer boven hard plafond",
    ceilingFacts: "{room} bij plafond {ceiling}",
    warm: "warme periode",
    forecast: "verwachte max {t}",
    measured: "max {t} gemeten",
    threshold: "drempel {t}",
    noData: "geen buitentemperatuur bekend, alleen boven {ceiling}",
  },
  en: {
    ceiling: "room above hard ceiling",
    ceilingFacts: "{room} at ceiling {ceiling}",
    warm: "warm period",
    forecast: "forecast high {t}",
    measured: "{t} max measured",
    threshold: "threshold {t}",
    noData: "no outdoor temperature known, only above {ceiling}",
  },
};

/**
 * Explain the auto-cooling policy from the coordinator's attributes.
 *
 * Returns null when the backend does not publish `cooling_mode` (older
 * versions), otherwise `{ mode, label, allowed, why, facts }`:
 *  - `mode` off | auto | on, `label` its translated name,
 *  - `allowed` whether auto-cooling may run now (null when unknown),
 *  - `why` short reason when allowed (e.g. "warme periode"), else null,
 *  - `facts` the numbers behind the decision, e.g. "verwachte max 19°, drempel 22°".
 */
export function coolingInfo(attrs, hass) {
  const mode = attrs?.cooling_mode;
  if (!mode) return null;
  const lang = langOf(hass);
  const T = COOLING_TEXT[lang];
  const label = coolingLabel(hass, mode);
  const allowed = typeof attrs.cooling_allowed === "boolean" ? attrs.cooling_allowed : null;
  const info = { mode, label, allowed, why: null, facts: null };
  if (mode !== "auto") return info;

  const fill = (s, v) => s.replace(/\{(\w+)\}/g, (_, k) => v[k]);
  const threshold = attrs.warm_threshold;
  const ceiling = attrs.hard_ceiling;
  const room = attrs.current_temperature;

  // Known outdoor highs, with where they come from.
  const highs = [
    { v: attrs.forecast_high_today, text: T.forecast },
    { v: attrs.forecast_high_tomorrow, text: T.forecast },
    { v: attrs.outdoor_max_24h, text: T.measured },
  ].filter((h) => typeof h.v === "number");
  const best = highs.reduce((a, b) => (a && a.v >= b.v ? a : b), null);

  const roomAboveCeiling =
    typeof room === "number" && typeof ceiling === "number" && room >= ceiling;

  if (allowed === true) {
    if (roomAboveCeiling && !(best && typeof threshold === "number" && best.v >= threshold)) {
      info.why = T.ceiling;
      info.facts = fill(T.ceilingFacts, { room: fmtTemp(room, hass), ceiling: fmtTemp(ceiling, hass) });
    } else if (best) {
      info.why = T.warm;
      info.facts = fill(best.text, { t: fmtTemp(best.v, hass) });
    }
  } else if (allowed === false) {
    if (best) {
      info.facts = fill(best.text, { t: fmtTemp(best.v, hass) });
      if (typeof threshold === "number") {
        info.facts += ", " + fill(T.threshold, { t: fmtTemp(threshold, hass) });
      }
    } else {
      info.facts = fill(T.noData, { ceiling: fmtTemp(ceiling, hass) });
    }
  }
  return info;
}
