// Mock Home Assistant frontend for previewing the Smart Climate cards without HA.
// Used by index.html; scenarios are picked with ?scenario=<name>.

export const ENTITY = "climate.smart_climate";

const SCHEDULE = {
  mode: "daily",
  daily: [
    { time: "06:30", temp: 20, cool_temp: 24 },
    { time: "09:00", temp: 18, cool_temp: 25 },
    { time: "17:00", temp: 21, cool_temp: 25 },
    { time: "22:30", temp: 17, cool_temp: 26 },
  ],
};

const DEVICES = [
  { entity_id: "climate.airco", role: "both", tier: "primary", park: "fan_only" },
  { entity_id: "climate.cv", role: "heat", tier: "support", park: "off" },
];

const AIRCO = "climate.airco";
const CV = "climate.cv";

/** ISO time `n` minutes from now (the harness clock is fixed by shoot.mjs, so this is stable). */
const inMin = (n) => new Date(Date.now() + n * 60000).toISOString();

/** ISO time of the next 10:00 (local), like the backend's "until morning". */
function nextMorning() {
  const d = new Date();
  d.setHours(10, 0, 0, 0);
  if (d <= new Date()) d.setDate(d.getDate() + 1);
  return d.toISOString();
}

/** `device_modes` attribute: everything auto unless overridden, e.g. { [CV]: { mode: "off", until } }. */
function modes(over = {}) {
  const out = {};
  for (const d of DEVICES) out[d.entity_id] = { mode: "auto", until: null };
  return { ...out, ...over };
}

/** `support_paused_until` as the backend derives it from the support devices' modes. */
function pausedUntil(deviceModes) {
  const ends = DEVICES.filter((d) => d.tier === "support")
    .map((d) => deviceModes[d.entity_id])
    .filter((m) => m && m.mode === "off")
    .map((m) => m.until ?? "");
  if (!ends.length) return null;
  const timed = ends.filter(Boolean);
  return timed.length === ends.length ? timed.sort()[0] : "";
}

/** Attributes of a modern backend; scenarios override parts of it. */
function base(over = {}) {
  return {
    friendly_name: "Woonkamer",
    hvac_modes: ["off", "heat", "cool", "auto"],
    hvac_action: "idle",
    current_temperature: 21.2,
    temperature: 20,
    mode: "auto",
    presence: "home",
    remaining_minutes: 0,
    interruptible: true,
    override_temperature: 21,
    away_delay_seconds_remaining: 0,
    wrapped_climate: "climate.airco",
    auto_temperature: 20,
    away_temperature: 15,
    away_delay_minutes: 5,
    default_override_mode: "timer",
    default_override_duration: 30,
    heat_target: 20,
    cool_limit: 25,
    intent: "idle",
    devices: DEVICES,
    schedule: SCHEDULE,
    cooling_mode: "auto",
    cooling_allowed: false,
    support_enabled: true,
    support_active: false,
    support_delta: 1.5,
    device_modes: modes(),
    support_paused_until: null,
    warm_threshold: 22,
    hard_ceiling: 26,
    forecast_high_today: 19,
    forecast_high_tomorrow: 17,
    outdoor_max_24h: 16.5,
    weather_entity: "weather.home",
    outdoor_sensor: null,
    ...over,
  };
}

const SCENARIOS = {
  // Autumn afternoon: warm room after the sun, nothing runs, cooling not allowed.
  "autumn-idle": { state: "auto", attrs: base(), airco: "off", cv: "off" },
  // Cold winter evening: airco and CV both heating, someone is about to leave.
  "winter-heat": {
    state: "auto",
    airco: "heat",
    cv: "heat",
    attrs: base({
      current_temperature: 17.8,
      temperature: 20,
      hvac_action: "heating",
      intent: "heat",
      support_active: true,
      forecast_high_today: 3,
      forecast_high_tomorrow: 5.5,
      outdoor_max_24h: 4.2,
      away_delay_seconds_remaining: 252,
    }),
  },
  // Hot summer day: cooling allowed because of the warm period.
  "summer-cool": {
    state: "auto",
    airco: "cool",
    cv: "off",
    attrs: base({
      current_temperature: 25.3,
      temperature: 25,
      hvac_action: "cooling",
      intent: "cool",
      cooling_allowed: true,
      forecast_high_today: 29,
      forecast_high_tomorrow: 31,
      outdoor_max_24h: 27.4,
    }),
  },
  // Summer, cooling forced on by the user.
  "summer-on": {
    state: "auto",
    airco: "cool",
    cv: "off",
    attrs: base({
      current_temperature: 24.8,
      temperature: 25,
      hvac_action: "cooling",
      intent: "cool",
      cooling_mode: "on",
      cooling_allowed: true,
      forecast_high_today: 28,
      forecast_high_tomorrow: null,
      outdoor_max_24h: null,
    }),
  },
  // Room above the hard ceiling in a cold period.
  "ceiling-cool": {
    state: "auto",
    airco: "cool",
    cv: "off",
    attrs: base({
      current_temperature: 26.4,
      temperature: 25,
      hvac_action: "cooling",
      intent: "cool",
      cooling_allowed: true,
      forecast_high_today: 18,
      forecast_high_tomorrow: 16,
      outdoor_max_24h: 15,
    }),
  },
  // Coordinator switched off.
  off: {
    state: "off",
    airco: "off",
    cv: "off",
    attrs: base({ hvac_action: "off", intent: "off", cooling_allowed: false }),
  },
  // Override until the next schedule time.
  "override-next": {
    state: "auto",
    airco: "heat",
    cv: "off",
    attrs: base({
      current_temperature: 19.6,
      temperature: 22.5,
      hvac_action: "heating",
      intent: "heat",
      mode: "override_next_node",
      override_temperature: 22.5,
    }),
  },
  "override-timer": {
    state: "auto",
    airco: "heat",
    cv: "off",
    attrs: base({
      current_temperature: 20.1,
      temperature: 22,
      hvac_action: "heating",
      intent: "heat",
      mode: "override_timer",
      override_temperature: 22,
      remaining_minutes: 84,
    }),
  },
  "override-infinity": {
    state: "auto",
    airco: "heat",
    cv: "off",
    attrs: base({
      temperature: 23,
      hvac_action: "heating",
      intent: "heat",
      mode: "override_infinity",
      override_temperature: 23,
    }),
  },
  // Winter evening, CV switched off until tomorrow 10:00 ("Geen CV tot morgenochtend").
  "cv-paused-morning": (() => {
    const dm = modes({ [CV]: { mode: "off", until: nextMorning() } });
    return {
      state: "auto",
      airco: "heat",
      cv: "off",
      attrs: base({
        current_temperature: 18.4,
        hvac_action: "heating",
        intent: "heat",
        device_modes: dm,
        support_paused_until: pausedUntil(dm),
        forecast_high_today: 4,
        forecast_high_tomorrow: 6,
        outdoor_max_24h: 5,
      }),
    };
  })(),
  // "Ik ga zo weg": CV paused for another 40 minutes.
  "leaving-soon": (() => {
    const dm = modes({ [CV]: { mode: "off", until: inMin(40) } });
    return {
      state: "auto",
      airco: "heat",
      cv: "off",
      attrs: base({
        current_temperature: 18.9,
        hvac_action: "heating",
        intent: "heat",
        device_modes: dm,
        support_paused_until: pausedUntil(dm),
        forecast_high_today: 4,
        forecast_high_tomorrow: 6,
        outdoor_max_24h: 5,
      }),
    };
  })(),
  // The airco is operated by hand for 25 more minutes; the CV carries the heating.
  "airco-manual": (() => {
    const dm = modes({ [AIRCO]: { mode: "manual", until: inMin(25) } });
    return {
      state: "auto",
      airco: "heat",
      cv: "heat",
      attrs: base({
        current_temperature: 18.1,
        hvac_action: "heating",
        intent: "heat",
        support_active: true,
        device_modes: dm,
        support_paused_until: pausedUntil(dm),
        forecast_high_today: 4,
        forecast_high_tomorrow: 6,
        outdoor_max_24h: 5,
      }),
    };
  })(),
  // Both actuators on hand-operation, permanently / until 10:00.
  "all-manual": (() => {
    const dm = modes({
      [AIRCO]: { mode: "manual", until: null },
      [CV]: { mode: "manual", until: nextMorning() },
    });
    return {
      state: "auto",
      airco: "heat",
      cv: "off",
      attrs: base({
        current_temperature: 18.1,
        hvac_action: "heating",
        intent: "heat",
        device_modes: dm,
        support_paused_until: pausedUntil(dm),
      }),
    };
  })(),
  // The CV is off with no end: the pause has no time ("tot je hem weer aanzet").
  "cv-off-forever": (() => {
    const dm = modes({ [CV]: { mode: "off", until: null } });
    return {
      state: "auto",
      airco: "off",
      cv: "off",
      attrs: base({ device_modes: dm, support_paused_until: pausedUntil(dm) }),
    };
  })(),
  // Backend with `devices` but from before the per-device modes: attributes missing.
  "old-backend-devices": {
    state: "auto",
    airco: "heat",
    cv: "heat",
    attrs: (() => {
      const a = base({
        current_temperature: 18.1,
        hvac_action: "heating",
        intent: "heat",
        support_active: true,
      });
      delete a.device_modes;
      delete a.support_paused_until;
      return a;
    })(),
  },
  // Backend from before this feature branch: none of the new attributes.
  "old-backend": {
    state: "heat",
    airco: "heat",
    cv: null,
    attrs: (() => {
      const a = base({ current_temperature: 19.5, hvac_action: "heating" });
      for (const k of [
        "schedule", "cooling_mode", "cooling_allowed", "support_enabled", "support_active",
        "support_delta", "warm_threshold", "hard_ceiling", "forecast_high_today",
        "forecast_high_tomorrow", "outdoor_max_24h", "weather_entity", "outdoor_sensor",
        "devices", "intent", "heat_target", "cool_limit", "device_modes", "support_paused_until",
      ]) delete a[k];
      return a;
    })(),
  },
  // New backend, but no schedule has ever been saved: attribute is present and null.
  "schedule-null": { state: "auto", airco: "off", cv: "off", attrs: base({ schedule: null }) },
  // Week schedule (5/2) with support disabled and no cooling data.
  "schedule-52": {
    state: "auto",
    airco: "heat",
    cv: "off",
    attrs: base({
      schedule: {
        mode: "5/2",
        weekday: SCHEDULE.daily,
        weekend: [{ time: "08:30", temp: 20.5, cool_temp: 25 }, { time: "23:00", temp: 17, cool_temp: 26 }],
      },
      support_enabled: false,
      cooling_mode: "off",
      cooling_allowed: false,
      forecast_high_today: null,
      forecast_high_tomorrow: null,
      outdoor_max_24h: null,
    }),
  },
};

export const scenarioNames = Object.keys(SCENARIOS);

const lastCalls = [];

/** Build a stateful mock `hass`; `onChange` is called after every service call. */
export function createHass(name, lang, onChange, dark = false) {
  const sc = SCENARIOS[name] ?? SCENARIOS["autumn-idle"];
  const states = {
    [ENTITY]: { entity_id: ENTITY, state: sc.state, attributes: structuredClone(sc.attrs) },
    "climate.airco": {
      entity_id: "climate.airco",
      state: sc.airco,
      attributes: { friendly_name: "Airco", hvac_modes: ["off", "heat", "cool", "fan_only"] },
    },
    "zone.home": { entity_id: "zone.home", state: "1", attributes: { friendly_name: "Home" } },
    "sensor.smart_climate_presence": {
      entity_id: "sensor.smart_climate_presence",
      state: sc.attrs.presence ?? "home",
      attributes: { friendly_name: "Woonkamer Presence" },
    },
  };
  if (sc.cv !== null) {
    states["climate.cv"] = {
      entity_id: "climate.cv",
      state: sc.cv,
      attributes: { friendly_name: "CV", hvac_modes: ["off", "heat"] },
    };
  }
  const attrs = () => states[ENTITY].attributes;

  const hass = {
    language: lang,
    config: { time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone },
    themes: { darkMode: dark },
    states,
    calls: lastCalls,
    callService(domain, service, data) {
      lastCalls.push({ domain, service, data });
      console.log("callService", domain, service, JSON.stringify(data));
      const a = attrs();
      if (domain === "climate" && service === "set_hvac_mode") {
        states[ENTITY].state = data.hvac_mode;
      } else if (service === "set_cooling_mode") {
        a.cooling_mode = data.mode;
        a.cooling_allowed = data.mode === "on" ? true : data.mode === "off" ? false : a.cooling_allowed;
      } else if (service === "set_heat_support") {
        a.support_enabled = data.enabled;
      } else if (service === "set_device_mode") {
        // Same bookkeeping as the backend: temporary modes carry an end time.
        const until = data.minutes ? inMin(Number(data.minutes)) : data.until ?? null;
        a.device_modes = {
          ...a.device_modes,
          [data.device]: { mode: data.mode, until: data.mode === "auto" ? null : until },
        };
        a.support_paused_until = pausedUntil(a.device_modes);
      } else if (service === "set_support_pause") {
        const end = data.minutes ? inMin(Number(data.minutes)) : data.until_morning ? nextMorning() : null;
        const next = { ...a.device_modes };
        for (const d of DEVICES.filter((x) => x.tier === "support")) {
          next[d.entity_id] = data.enabled === false ? { mode: "auto", until: null } : { mode: "off", until: end };
        }
        a.device_modes = next;
        a.support_paused_until = pausedUntil(next);
      } else if (service === "set_override_timer") {
        Object.assign(a, { mode: "override_timer", override_temperature: data.temperature, remaining_minutes: data.minutes });
      } else if (service === "set_override_next_node") {
        Object.assign(a, { mode: "override_next_node", override_temperature: data.temperature });
      } else if (service === "set_override_infinity") {
        Object.assign(a, { mode: "override_infinity", override_temperature: data.temperature });
      } else if (service === "clear_override") {
        a.mode = "auto";
      } else if (service === "set_schedule") {
        a.schedule = data.schedule;
      }
      onChange?.(structuredClone(hass.states));
      return Promise.resolve();
    },
    /** history/period/<start>?filter_entity_id=..&end_time=.. → plausible data. */
    callApi(method, path) {
      const m = /^history\/period\/([^?]+)\?(.*)$/.exec(path);
      if (!m) return Promise.resolve([]);
      const params = new URLSearchParams(m[2]);
      const id = params.get("filter_entity_id");
      const start = new Date(m[1]);
      const end = params.get("end_time") ? new Date(params.get("end_time")) : new Date();
      const rows = [];
      if (id === "sensor.smart_climate_presence") {
        // away until 07:10, home until 08:40, away until 12:20, home afterwards
        const seg = [[0, "away"], [7.17, "home"], [8.67, "away"], [12.33, "home"]];
        for (const [h, s] of seg) {
          const t = new Date(start.getTime() + h * 3600000);
          if (t <= end) rows.push({ entity_id: id, state: s, last_changed: t.toISOString() });
        }
      } else {
        const yesterday = params.get("end_time") !== null;
        for (let h = 0; start.getTime() + h * 3600000 <= end.getTime(); h += 0.5) {
          const base = yesterday ? 19.5 : 19;
          const t = base + 2.2 * Math.sin(((h - 9) / 24) * 2 * Math.PI) + (h > 7 && h < 9 ? -0.8 : 0);
          rows.push({
            entity_id: id,
            state: "heat",
            attributes: { current_temperature: Math.round(t * 10) / 10 },
            last_changed: new Date(start.getTime() + h * 3600000).toISOString(),
          });
        }
      }
      return Promise.resolve([rows]);
    },
  };
  return hass;
}

// Home Assistant's default light/dark palette (the variables the cards use).
export function applyTheme(theme) {
  const light = {
    "--primary-color": "#03a9f4",
    "--accent-color": "#ff9800",
    "--primary-text-color": "#212121",
    "--secondary-text-color": "#727272",
    "--text-primary-color": "#ffffff",
    "--disabled-text-color": "#bdbdbd",
    "--divider-color": "rgba(0, 0, 0, 0.12)",
    "--ha-card-background": "#ffffff",
    "--card-background-color": "#ffffff",
    "--secondary-background-color": "#e5e5e5",
    "--primary-background-color": "#fafafa",
    "--success-color": "#43a047",
  };
  const dark = {
    "--primary-color": "#03a9f4",
    "--accent-color": "#ff9800",
    "--primary-text-color": "#e1e1e1",
    "--secondary-text-color": "#9b9b9b",
    "--text-primary-color": "#ffffff",
    "--disabled-text-color": "#6f6f6f",
    "--divider-color": "rgba(225, 225, 225, 0.12)",
    "--ha-card-background": "#1c1c1c",
    "--card-background-color": "#1c1c1c",
    "--secondary-background-color": "#282828",
    "--primary-background-color": "#111111",
    "--success-color": "#43a047",
  };
  const vars = theme === "dark" ? dark : light;
  for (const [k, v] of Object.entries(vars)) document.documentElement.style.setProperty(k, v);
  document.documentElement.style.colorScheme = theme === "dark" ? "dark" : "light";
  document.body.style.background = vars["--primary-background-color"];
  document.body.style.color = vars["--primary-text-color"];
}
