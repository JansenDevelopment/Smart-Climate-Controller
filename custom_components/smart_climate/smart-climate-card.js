import { LitElement, html, css } from "https://unpkg.com/lit@3/index.js?module";
import { SmartClimateBaseEditor } from "./smart-climate-base-editor.js";
import {
  translate,
  fmtNum,
  fmtTemp,
  entityName,
  supportDevices,
  coolingInfo,
  coolingLabel,
} from "./smart-climate-shared.js";

const OVERRIDE_MIN = 5;
const OVERRIDE_MAX = 25;
const OVERRIDE_STEP = 0.5;
const DEFAULT_SUPPORT_DELTA = 1.5;

// hvac_action → intent, for backends that do not publish `intent`.
const ACTION_TO_INTENT = { heating: "heat", cooling: "cool", idle: "idle", off: "off" };

const TEXT = {
  nl: {
    entityNotFound: "Entiteit niet gevonden",
    powerOn: "Aanzetten (auto)",
    powerOff: "Uitzetten",
    goal: "doel {t}",
    off: "Uit",
    stateOff: "Uit: de regeling stuurt niets aan",
    idleAbove: "Rust: kamer ligt boven het doel, niets stookt",
    idleWarm: "Rust: kamer is warm, maar koelen is niet toegestaan",
    idleOk: "Rust: kamer ligt rond het doel, niets verwarmt of koelt",
    heating: "{names} verwarmt naar {t}",
    heatingMany: "{names} verwarmen naar {t}",
    heatingAny: "Verwarmt naar {t}",
    cooling: "{names} koelt naar {t}",
    coolingMany: "{names} koelen naar {t}",
    coolingAny: "Koelt naar {t}",
    and: " en ",
    home: "Thuis",
    away: "Weg",
    awayIn: "weg over {t}",
    "hvac.off": "Uit",
    "hvac.heat": "Verwarmt",
    "hvac.cool": "Koelt",
    "hvac.auto": "Auto",
    "hvac.heat_cool": "Auto",
    "hvac.fan_only": "Ventilator",
    "hvac.dry": "Drogen",
    "hvac.unavailable": "Niet beschikbaar",
    "hvac.unknown": "Onbekend",
    cooling_title: "Koelen",
    coolOff: "Er wordt niet gekoeld, ook niet bij warm weer.",
    coolOn: "Koelen is altijd toegestaan; er wordt gekoeld boven {t}.",
    coolOnPlain: "Koelen is altijd toegestaan.",
    coolAllowed: "Toegestaan",
    coolNotAllowed: "Nu niet toegestaan",
    coolCeiling: "Boven {t} is koelen altijd toegestaan.",
    supportTitle: "CV-ondersteuning",
    supportText: "Springt bij als de kamer {d} onder het doel zit",
    supportActive: "Actief",
    tileToday: "Verwacht max vandaag",
    tileTomorrow: "Verwacht max morgen",
    tileMeasured: "Gemeten max 24 uur",
    overrideTitle: "Tijdelijk andere temperatuur",
    followsSchedule: "Volgt het schema",
    remaining: "Nog {t}",
    always: "Altijd",
    untilNext: "Tot volgende schakeltijd",
    min30: "30 min",
    hours2: "2 uur",
    nextNode: "Tot volgende schakeltijd",
    infinity: "Altijd",
    backToSchedule: "Terug naar schema",
    lower: "Lager",
    higher: "Hoger",
    min: "{n} min",
    hm: "{h} u {m} min",
    h: "{h} u",
  },
  en: {
    entityNotFound: "Entity not found",
    powerOn: "Turn on (auto)",
    powerOff: "Turn off",
    goal: "target {t}",
    off: "Off",
    stateOff: "Off: the controller drives nothing",
    idleAbove: "Idle: room is above the target, nothing is heating",
    idleWarm: "Idle: room is warm, but cooling is not allowed",
    idleOk: "Idle: room is around the target, nothing heats or cools",
    heating: "{names} heats to {t}",
    heatingMany: "{names} heat to {t}",
    heatingAny: "Heating to {t}",
    cooling: "{names} cools to {t}",
    coolingMany: "{names} cool to {t}",
    coolingAny: "Cooling to {t}",
    and: " and ",
    home: "Home",
    away: "Away",
    awayIn: "away in {t}",
    "hvac.off": "Off",
    "hvac.heat": "Heating",
    "hvac.cool": "Cooling",
    "hvac.auto": "Auto",
    "hvac.heat_cool": "Auto",
    "hvac.fan_only": "Fan",
    "hvac.dry": "Dry",
    "hvac.unavailable": "Unavailable",
    "hvac.unknown": "Unknown",
    cooling_title: "Cooling",
    coolOff: "No cooling, not even in warm weather.",
    coolOn: "Cooling is always allowed; it cools above {t}.",
    coolOnPlain: "Cooling is always allowed.",
    coolAllowed: "Allowed",
    coolNotAllowed: "Not allowed right now",
    coolCeiling: "Above {t}, cooling is always allowed.",
    supportTitle: "Heat support",
    supportText: "Joins in when the room is {d} below the target",
    supportActive: "Active",
    tileToday: "Forecast high today",
    tileTomorrow: "Forecast high tomorrow",
    tileMeasured: "Measured max 24 h",
    overrideTitle: "Temporary temperature",
    followsSchedule: "Following the schedule",
    remaining: "{t} left",
    always: "Always",
    untilNext: "Until next schedule time",
    min30: "30 min",
    hours2: "2 hours",
    nextNode: "Until next schedule time",
    infinity: "Always",
    backToSchedule: "Back to schedule",
    lower: "Lower",
    higher: "Higher",
    min: "{n} min",
    hm: "{h} h {m} min",
    h: "{h} h",
  },
};

class SmartClimateCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
    _overrideTemp: { state: true },
  };

  static getConfigElement() {
    return document.createElement("smart-climate-card-editor");
  }

  static getStubConfig(hass) {
    const id = Object.keys(hass?.states ?? {}).find(
      (k) => k.startsWith("climate.") && hass.states[k].attributes?.wrapped_climate !== undefined
    );
    return { entity: id ?? "" };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Entity required");
    }
    this.config = config;
    this._touched = false;
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearTimeout(this._reapplyTimer);
  }

  willUpdate(changed) {
    // Once the backend reflects the temperature the user picked, let the
    // backend value drive the stepper again.
    if (changed.has("hass") && this._touched && !this._reapplyTimer) {
      const attrs = this.hass?.states[this.config.entity]?.attributes;
      if (attrs && Number(attrs.override_temperature) === this._overrideTemp) {
        this._touched = false;
      }
    }
  }

  _t(key, vars) {
    return translate(TEXT, this.hass, key, vars);
  }

  // ── Render ───────────────────────────────────────────────────────────────

  render() {
    if (!this.hass) return html``;

    const entity = this.hass.states[this.config.entity];
    if (!entity) {
      return html`
        <ha-card>
          <div class="content">${this._t("entityNotFound")}</div>
        </ha-card>
      `;
    }

    // The entity state is the coordinator's HVAC mode; "off" means it drives
    // nothing at all, so say so instead of showing a setpoint that is not used.
    const isOff = entity.state === "off";
    const attrs = entity.attributes;

    return html`
      <ha-card>
        <div class="content">
          ${this._renderHeader(entity, attrs, isOff)}
          <div class="body" ?dimmed=${isOff}>
            ${this._renderCooling(attrs)}
            ${this._renderSupport(attrs)}
            ${this._renderTiles(attrs)}
            ${this._renderOverride(attrs)}
          </div>
        </div>
      </ha-card>
    `;
  }

  // Header: big room temperature, one-sentence status, chips and power button.
  _renderHeader(entity, attrs, isOff) {
    const name = this.config.name ?? attrs.friendly_name ?? "SmartClimate";
    return html`
      <div class="head">
        <div class="temp-block">
          <div class="name">${name}</div>
          <div class="room" ?off=${isOff}>
            ${fmtNum(attrs.current_temperature, this.hass)}<span class="unit">°</span>
          </div>
          <div class="goal">
            ${isOff
              ? this._t("off")
              : attrs.temperature != null
              ? this._t("goal", { t: fmtTemp(attrs.temperature, this.hass) })
              : ""}
          </div>
        </div>
        <div class="head-right">
          <div class="chips">${this._renderPresenceChip(attrs)}${this._renderDeviceChips(attrs)}</div>
          <button
            class="power"
            ?on=${!isOff}
            title=${isOff ? this._t("powerOn") : this._t("powerOff")}
            aria-label=${isOff ? this._t("powerOn") : this._t("powerOff")}
            @click=${this.onPowerClick}
          >
            <ha-icon icon="mdi:power"></ha-icon>
          </button>
        </div>
      </div>
      <div class="sentence">${this._sentence(attrs, isOff)}</div>
    `;
  }

  _renderPresenceChip(attrs) {
    const presence = attrs.presence;
    if (presence !== "home" && presence !== "away") return "";
    const delay = Number(attrs.away_delay_seconds_remaining) || 0;
    const leaving = presence === "home" && delay > 0;
    const icon = presence === "home" && !leaving ? "mdi:home" : "mdi:home-export-outline";
    return html`
      <span class="chip" data-kind="presence" data-presence=${presence}>
        <ha-icon icon=${icon}></ha-icon>
        <span>${presence === "home" ? this._t("home") : this._t("away")}</span>
        ${leaving
          ? html`<span class="chip-sub">${this._t("awayIn", { t: this._clock(delay) })}</span>`
          : ""}
      </span>
    `;
  }

  /** Devices to show; older backends only know the wrapped climate. */
  _devices(attrs) {
    if (Array.isArray(attrs.devices) && attrs.devices.length) return attrs.devices;
    return attrs.wrapped_climate
      ? [{ entity_id: attrs.wrapped_climate, role: "both", tier: "primary" }]
      : [];
  }

  _renderDeviceChips(attrs) {
    return this._devices(attrs).map((d) => {
      const state = this.hass.states[d.entity_id]?.state ?? "unavailable";
      const label = this._t(`hvac.${state}`);
      const icon = d.tier === "support" ? "mdi:radiator" : "mdi:air-conditioning";
      const kind = state === "heat" ? "heat" : state === "cool" ? "cool" : "";
      return html`
        <span class="chip" data-kind=${kind || "device"}>
          <ha-icon icon=${icon}></ha-icon>
          <span>${entityName(this.hass, d.entity_id)}</span>
          <span class="chip-sub">${label}</span>
        </span>
      `;
    });
  }

  /** "Airco en CV verwarmen naar 20°" etc. — derived from intent and device states. */
  _sentence(attrs, isOff) {
    if (isOff) return this._t("stateOff");
    const intent = attrs.intent ?? ACTION_TO_INTENT[attrs.hvac_action];
    const target = fmtTemp(attrs.temperature, this.hass);
    const devices = this._devices(attrs);

    if (intent === "heat" || intent === "cool") {
      const wanted = intent === "heat" ? "heat" : "cool";
      const active = devices.filter((d) => this.hass.states[d.entity_id]?.state === wanted);
      let list = active;
      if (!list.length) {
        // Device states may lag behind the decision: fall back to the roles.
        list = devices.filter(
          (d) => (d.role === "both" || d.role === wanted) && d.tier !== "support"
        );
      }
      if (intent === "heat" && attrs.support_active) {
        for (const s of supportDevices(attrs)) {
          if (!list.includes(s)) list = [...list, s];
        }
      }
      const names = list.map((d) => entityName(this.hass, d.entity_id));
      const base = intent === "heat" ? "heating" : "cooling";
      if (!names.length) return this._t(`${base}Any`, { t: target });
      return this._t(names.length > 1 ? `${base}Many` : base, {
        names: names.join(this._t("and")),
        t: target,
      });
    }

    // idle (or unknown)
    const room = attrs.current_temperature;
    const coolLimit = attrs.cool_limit;
    if (
      attrs.cooling_allowed === false &&
      typeof room === "number" &&
      typeof coolLimit === "number" &&
      room >= coolLimit
    ) {
      return this._t("idleWarm");
    }
    if (typeof room === "number" && typeof attrs.temperature === "number" && room > attrs.temperature) {
      return this._t("idleAbove");
    }
    return this._t("idleOk");
  }

  _renderCooling(attrs) {
    const info = coolingInfo(attrs, this.hass);
    if (!info) return "";
    const modes = ["off", "auto", "on"];
    let text;
    if (info.mode === "off") {
      text = this._t("coolOff");
    } else if (info.mode === "on") {
      text =
        typeof attrs.cool_limit === "number"
          ? this._t("coolOn", { t: fmtTemp(attrs.cool_limit, this.hass) })
          : this._t("coolOnPlain");
    } else if (info.allowed === true) {
      text = this._t("coolAllowed") + (info.why ? `: ${info.why} (${info.facts})` : "");
    } else if (info.allowed === false) {
      text = `${this._t("coolNotAllowed")}: ${info.facts}`;
    }
    return html`
      <section class="block">
        <div class="row">
          <div class="label">${this._t("cooling_title")}</div>
          <div class="segmented" role="radiogroup" aria-label=${this._t("cooling_title")}>
            ${modes.map(
              (m) => html`
                <button
                  role="radio"
                  aria-checked=${info.mode === m ? "true" : "false"}
                  ?active=${info.mode === m}
                  @click=${() => this.onCoolingMode(m)}
                >
                  ${coolingLabel(this.hass, m)}
                </button>
              `
            )}
          </div>
        </div>
        ${text
          ? html`
              <div class="hint" data-allowed=${info.mode === "auto" ? String(info.allowed) : ""}>
                ${info.mode === "auto" && info.allowed !== null
                  ? html`<ha-icon
                      icon=${info.allowed ? "mdi:check-circle-outline" : "mdi:cancel"}
                    ></ha-icon>`
                  : ""}
                <span>
                  ${text}${info.mode === "auto" ? "." : ""}
                  ${info.mode === "auto" && typeof attrs.hard_ceiling === "number"
                    ? html` <span class="muted">${this._t("coolCeiling", { t: fmtTemp(attrs.hard_ceiling, this.hass) })}</span>`
                    : ""}
                </span>
              </div>
            `
          : ""}
      </section>
    `;
  }

  _renderSupport(attrs) {
    const support = supportDevices(attrs);
    if (!support.length) return "";
    const enabled = attrs.support_enabled !== false;
    const delta = attrs.support_delta ?? DEFAULT_SUPPORT_DELTA;
    return html`
      <section class="block">
        <div class="row">
          <div class="label">
            ${this._t("supportTitle")}
            ${attrs.support_active
              ? html`<span class="badge">${this._t("supportActive")}</span>`
              : ""}
          </div>
          <button
            class="switch"
            role="switch"
            aria-checked=${enabled ? "true" : "false"}
            aria-label=${this._t("supportTitle")}
            ?on=${enabled}
            @click=${() => this.onSupportToggle(!enabled)}
          >
            <span class="knob"></span>
          </button>
        </div>
        <div class="hint">
          <span>
            ${this._t("supportText", { d: fmtTemp(delta, this.hass) })}
            <span class="muted">(${support.map((d) => entityName(this.hass, d.entity_id)).join(", ")})</span>
          </span>
        </div>
      </section>
    `;
  }

  _renderTiles(attrs) {
    const warm = attrs.warm_threshold;
    const tiles = [
      { key: "tileToday", v: attrs.forecast_high_today },
      { key: "tileTomorrow", v: attrs.forecast_high_tomorrow },
      { key: "tileMeasured", v: attrs.outdoor_max_24h },
    ].filter((t) => typeof t.v === "number");
    if (!tiles.length) return "";
    return html`
      <section class="tiles">
        ${tiles.map(
          (t) => html`
            <div class="tile">
              <div class="tile-value" ?warm=${typeof warm === "number" && t.v >= warm}>
                ${fmtTemp(t.v, this.hass)}
              </div>
              <div class="tile-label">${this._t(t.key)}</div>
            </div>
          `
        )}
      </section>
    `;
  }

  _renderOverride(attrs) {
    const mode = attrs.mode ?? "auto";
    const isOverride = mode.startsWith("override");
    const isTimer = mode === "override_timer";
    const isInfinity = mode === "override_infinity";
    const isNext = mode === "override_next_node";
    const value = this._stepValue(attrs);

    let status = this._t("followsSchedule");
    if (isTimer) status = this._t("remaining", { t: this._minutes(attrs.remaining_minutes ?? 0) });
    else if (isInfinity) status = this._t("always");
    else if (isNext) status = this._t("untilNext");

    return html`
      <section class="block override">
        <div class="row">
          <div class="label">${this._t("overrideTitle")}</div>
          <div class="status" ?active=${isOverride}>${status}</div>
        </div>
        <div class="stepper">
          <button
            aria-label=${this._t("lower")}
            ?disabled=${value <= OVERRIDE_MIN}
            @click=${() => this.onStep(-OVERRIDE_STEP)}
          >
            <ha-icon icon="mdi:minus"></ha-icon>
          </button>
          <div class="step-value">${fmtNum(value, this.hass)}<span class="unit">°</span></div>
          <button
            aria-label=${this._t("higher")}
            ?disabled=${value >= OVERRIDE_MAX}
            @click=${() => this.onStep(OVERRIDE_STEP)}
          >
            <ha-icon icon="mdi:plus"></ha-icon>
          </button>
        </div>
        <div class="choices">
          <button class="choice" @click=${() => this.startOverride("timer", 30)}>${this._t("min30")}</button>
          <button class="choice" @click=${() => this.startOverride("timer", 120)}>${this._t("hours2")}</button>
          <button class="choice" ?active=${isNext} @click=${() => this.startOverride("next_node")}>
            ${this._t("nextNode")}
          </button>
          <button class="choice" ?active=${isInfinity} @click=${() => this.startOverride("infinity")}>
            ${this._t("infinity")}
          </button>
        </div>
        ${isOverride
          ? html`<button class="back" @click=${this.onClearOverride}>
              <ha-icon icon="mdi:calendar-clock"></ha-icon>${this._t("backToSchedule")}
            </button>`
          : ""}
      </section>
    `;
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  /** Temperature shown in the stepper: the user's pick, else the backend's. */
  _stepValue(attrs) {
    if (this._touched && this._overrideTemp != null) return this._overrideTemp;
    const v = Number(attrs.override_temperature ?? attrs.temperature ?? 21);
    return Math.min(OVERRIDE_MAX, Math.max(OVERRIDE_MIN, Number.isNaN(v) ? 21 : v));
  }

  _minutes(minutes) {
    const m = Math.round(minutes);
    if (m < 60) return this._t("min", { n: m });
    const h = Math.floor(m / 60);
    const rest = m % 60;
    return rest ? this._t("hm", { h, m: rest }) : this._t("h", { h });
  }

  _clock(seconds) {
    const s = Math.max(0, Math.round(seconds));
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  }

  // ── Actions ──────────────────────────────────────────────────────────────

  onPowerClick() {
    const entity = this.hass.states[this.config.entity];
    const isOff = entity?.state === "off";
    this.hass.callService("climate", "set_hvac_mode", {
      entity_id: this.config.entity,
      hvac_mode: isOff ? "auto" : "off",
    });
  }

  onCoolingMode(mode) {
    this.hass.callService("smart_climate", "set_cooling_mode", {
      entity_id: this.config.entity,
      mode,
    });
  }

  onSupportToggle(enabled) {
    this.hass.callService("smart_climate", "set_heat_support", {
      entity_id: this.config.entity,
      enabled,
    });
  }

  onStep(delta) {
    const attrs = this.hass.states[this.config.entity]?.attributes ?? {};
    const next = Math.min(
      OVERRIDE_MAX,
      Math.max(OVERRIDE_MIN, Math.round((this._stepValue(attrs) + delta) / OVERRIDE_STEP) * OVERRIDE_STEP)
    );
    this._overrideTemp = next;
    this._touched = true;
    // While an override runs, the new temperature applies to it right away.
    if (String(attrs.mode ?? "").startsWith("override")) {
      clearTimeout(this._reapplyTimer);
      this._reapplyTimer = setTimeout(() => {
        this._reapplyTimer = null;
        const a = this.hass.states[this.config.entity]?.attributes ?? {};
        if (a.mode === "override_timer") {
          this.startOverride("timer", Math.max(1, Number(a.remaining_minutes) || 30));
        } else if (a.mode === "override_infinity") {
          this.startOverride("infinity");
        } else if (a.mode === "override_next_node") {
          this.startOverride("next_node");
        }
      }, 600);
    }
  }

  startOverride(kind, minutes) {
    const entity_id = this.config.entity;
    const attrs = this.hass.states[entity_id]?.attributes ?? {};
    const temperature = this._stepValue(attrs);
    this._overrideTemp = temperature;
    this._touched = true;
    if (kind === "timer") {
      this.hass.callService("smart_climate", "set_override_timer", { entity_id, minutes, temperature });
    } else if (kind === "next_node") {
      this.hass.callService("smart_climate", "set_override_next_node", { entity_id, temperature });
    } else {
      this.hass.callService("smart_climate", "set_override_infinity", { entity_id, temperature });
    }
  }

  onClearOverride() {
    clearTimeout(this._reapplyTimer);
    this._reapplyTimer = null;
    this._touched = false;
    this.hass.callService("smart_climate", "clear_override", { entity_id: this.config.entity });
  }

  // ── Styles ───────────────────────────────────────────────────────────────

  static styles = css`
    :host {
      --sc-heat: var(--state-climate-heat-color, #ff8100);
      --sc-cool: var(--state-climate-cool-color, #2b9af9);
      --sc-ok: var(--success-color, #43a047);
      --sc-radius: 12px;
    }

    ha-card {
      background: var(--ha-card-background, var(--card-background-color, #fff));
      color: var(--primary-text-color);
    }

    .content {
      padding: 16px;
    }

    button {
      font: inherit;
      color: inherit;
      cursor: pointer;
    }

    ha-icon {
      --mdc-icon-size: 18px;
      display: inline-flex;
      flex-shrink: 0;
    }

    /* Header */
    .head {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px 12px;
    }

    .name {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .room {
      font-size: 56px;
      line-height: 1.05;
      font-weight: 300;
      letter-spacing: -0.02em;
    }

    .room[off] {
      color: var(--secondary-text-color);
    }

    .unit {
      font-size: 0.5em;
      vertical-align: top;
      margin-left: 2px;
      color: var(--secondary-text-color);
    }

    .goal {
      font-size: 15px;
      color: var(--secondary-text-color);
    }

    .head-right {
      display: flex;
      align-items: flex-start;
      justify-content: flex-end;
      gap: 8px;
      flex: 1 1 200px;
      min-width: 0;
    }

    .chips {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 6px;
      min-width: 0;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      max-width: 100%;
      padding: 4px 10px 4px 8px;
      border-radius: 999px;
      font-size: 13px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    .chip ha-icon {
      --mdc-icon-size: 16px;
      color: var(--secondary-text-color);
    }

    .chip[data-kind="heat"] ha-icon {
      color: var(--sc-heat);
    }

    .chip[data-kind="cool"] ha-icon {
      color: var(--sc-cool);
    }

    .chip[data-kind="presence"][data-presence="home"] ha-icon {
      color: var(--sc-ok);
    }

    .chip-sub {
      color: var(--secondary-text-color);
    }

    .power {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      width: 36px;
      height: 36px;
      padding: 0;
      border: none;
      border-radius: 50%;
      background: var(--secondary-background-color);
      color: var(--secondary-text-color);
      transition: background 0.2s ease, color 0.2s ease;
    }

    .power[on] {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .power:hover {
      filter: brightness(1.1);
    }

    .power ha-icon {
      --mdc-icon-size: 22px;
    }

    .sentence {
      margin-top: 6px;
      font-size: 15px;
    }

    /* Body */
    .body {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-top: 16px;
      transition: opacity 0.2s ease;
    }

    .body[dimmed] {
      opacity: 0.45;
    }

    .block {
      padding: 12px;
      border-radius: var(--sc-radius);
      background: var(--secondary-background-color);
    }

    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .label {
      font-size: 15px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .hint {
      display: flex;
      gap: 6px;
      align-items: flex-start;
      margin-top: 8px;
      font-size: 13px;
      line-height: 1.35;
      color: var(--secondary-text-color);
    }

    .hint ha-icon {
      --mdc-icon-size: 16px;
      margin-top: 1px;
    }

    .hint[data-allowed="true"] ha-icon {
      color: var(--sc-ok);
    }

    .muted {
      opacity: 0.85;
    }

    .badge {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--sc-heat);
      color: #fff;
    }

    /* Segmented control */
    .segmented {
      display: inline-flex;
      padding: 3px;
      border-radius: 10px;
      background: var(--card-background-color, var(--ha-card-background, #fff));
      border: 1px solid var(--divider-color);
    }

    .segmented button {
      min-width: 64px;
      padding: 6px 14px;
      border: none;
      border-radius: 8px;
      background: transparent;
      font-size: 14px;
      color: var(--secondary-text-color);
    }

    .segmented button[active] {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      font-weight: 500;
    }

    /* Toggle switch */
    .switch {
      position: relative;
      flex-shrink: 0;
      width: 46px;
      height: 26px;
      padding: 0;
      border: none;
      border-radius: 13px;
      background: var(--disabled-text-color, #9e9e9e);
      transition: background 0.2s ease;
    }

    .switch[on] {
      background: var(--primary-color);
    }

    .knob {
      position: absolute;
      top: 3px;
      left: 3px;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: #fff;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
      transition: transform 0.2s ease;
    }

    .switch[on] .knob {
      transform: translateX(20px);
    }

    /* Outdoor tiles */
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      gap: 8px;
    }

    .tile {
      padding: 10px 12px;
      border-radius: var(--sc-radius);
      background: var(--secondary-background-color);
    }

    .tile-value {
      font-size: 24px;
      font-weight: 300;
    }

    .tile-value[warm] {
      color: var(--sc-heat);
    }

    .tile-label {
      margin-top: 2px;
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    /* Override */
    .status {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .status[active] {
      color: var(--primary-text-color);
      font-weight: 500;
    }

    .stepper {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 20px;
      margin: 10px 0;
    }

    .stepper button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 44px;
      height: 44px;
      padding: 0;
      border-radius: 50%;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color, var(--ha-card-background, #fff));
    }

    .stepper button:disabled {
      opacity: 0.35;
      cursor: default;
    }

    .stepper ha-icon {
      --mdc-icon-size: 22px;
    }

    .step-value {
      min-width: 90px;
      text-align: center;
      font-size: 34px;
      font-weight: 300;
    }

    .choices {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .choice {
      flex: 1 1 auto;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color, var(--ha-card-background, #fff));
      font-size: 14px;
      white-space: nowrap;
    }

    .choice:hover {
      border-color: var(--primary-color);
    }

    .choice[active] {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .back {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-top: 10px;
      padding: 6px 12px;
      border: none;
      border-radius: 8px;
      background: transparent;
      font-size: 14px;
      color: var(--primary-color);
    }

    .back:hover {
      background: rgba(127, 127, 127, 0.12);
    }

    button:focus-visible {
      outline: 2px solid var(--primary-color);
      outline-offset: 2px;
    }
  `;
}

/** Card editor for smart-climate-card — delegates all behaviour to the shared base. */
class SmartClimateCardEditor extends SmartClimateBaseEditor {}

customElements.define("smart-climate-card-editor", SmartClimateCardEditor);

customElements.define("smart-climate-card", SmartClimateCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-climate-card",
  name: "Smart Climate Card",
  description: "Future-proof smart climate control",
});
