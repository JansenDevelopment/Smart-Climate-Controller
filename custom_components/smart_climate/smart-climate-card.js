import { LitElement, html, css } from "https://unpkg.com/lit@3/index.js?module";
import { SmartClimateBaseEditor } from "./smart-climate-base-editor.js";
import {
  translate,
  fmtNum,
  fmtTemp,
  entityName,
  supportDevices,
  supportName,
  deviceMode,
  fmtClock,
  minutesUntilClock,
  minutesLeft,
  supportPause,
  coolingInfo,
  coolingLabel,
  coolingRelevant,
  isUnavailable,
} from "./smart-climate-shared.js";

const OVERRIDE_MIN = 5;
const OVERRIDE_MAX = 25;
const OVERRIDE_STEP = 0.5;
const DEFAULT_SUPPORT_DELTA = 1.5;
// A temporary device mode shows "N min left" below this, "until HH:MM" above it.
const REMAINING_SHOW_MIN = 90;
// A device left on Off/Manual for longer than this (or without an end) is worth a reminder line.

// hvac_action → intent, for backends that do not publish `intent`.
const ACTION_TO_INTENT = { heating: "heat", cooling: "cool", idle: "idle", off: "off" };

const TEXT = {
  nl: {
    entityNotFound: "Entiteit niet gevonden",
    entityNotFoundHint: "Controleer of {entity} bestaat en de Smart Climate-integratie is geladen.",
    coordUnavailable: "Niet beschikbaar",
    coordUnavailableHint: "{entity} reageert niet. De kaart komt terug zodra de integratie weer bereikbaar is.",
    powerOn: "Aanzetten (auto)",
    powerOff: "Uitzetten",
    goal: "doel {t}",
    off: "Uit",
    roomSensor: "Kamer: {name}",
    roomMean: "Kamer: gemiddelde van apparaten",
    roomPrimary: "Kamer: {name}",
    stateOff: "Uit: de regeling stuurt niets aan",
    idleAbove: "Niets actief: de kamer ligt boven het doel",
    idleWarm: "Niets actief: de kamer is warm, maar koelen is niet toegestaan",
    idleOk: "Niets actief: de kamer ligt rond het doel",
    heating: "{names} verwarmt naar {t}",
    heatingMany: "{names} verwarmen naar {t}",
    heatingAny: "Verwarmt naar {t}",
    heatNoDevice: "Wil verwarmen naar {t}, maar geen apparaat staat op Auto",
    coolNoDevice: "Wil koelen naar {t}, maar geen apparaat staat op Auto",
    paused: "{names} gepauzeerd",
    notAvailable: "{names} niet beschikbaar",
    allManual: "Alles handmatig: de coördinator stuurt niets aan",
    noneAuto: "Geen apparaat op Auto: de coördinator stuurt niets aan",
    cooling: "{names} koelt naar {t}",
    coolingMany: "{names} koelen naar {t}",
    coolingAny: "Koelt naar {t}",
    and: " en ",
    home: "Thuis",
    away: "Weg",
    awayIn: "weg over {t}",
    "st.off": "staat uit",
    "st.heat": "verwarmt",
    "st.cool": "koelt",
    "st.auto": "auto",
    "st.heat_cool": "auto",
    "st.fan_only": "ventilator",
    "st.dry": "droogt",
    "st.unavailable": "niet beschikbaar",
    "st.unknown": "onbekend",
    cooling_title: "Koelen",
    coolSummary: "Koelen: {mode} · nu niet nodig",
    coolExpand: "Koelen uitklappen",
    coolCollapse: "Koelen inklappen",
    coolOff: "Er wordt niet gekoeld, ook niet bij warm weer.",
    coolOn: "Koelen is altijd toegestaan; er wordt gekoeld boven {t}.",
    coolOnPlain: "Koelen is altijd toegestaan.",
    coolAllowed: "Toegestaan",
    coolNotAllowed: "Nu niet toegestaan",
    coolCeiling: "Koelen altijd toegestaan boven {t}.",
    supportTitle: "CV-ondersteuning",
    supportText: "Mag bijspringen als de kamer {d} onder het doel zit",
    supportActive: "Actief",
    boostStart: "{Support} erbij (1 uur)",
    boostActive: "{Support} doet mee tot {t} of tot het doel",
    boostStop: "Stoppen",
    noCvMorning: "Geen CV tot morgenochtend",
    noCvUntil: "Geen CV tot {t}",
    noCvOpen: "Geen CV (tot je hem weer aanzet)",
    leavingSoon: "Ik ga zo weg",
    fanTitle: "Ventilator",
    fan_auto: "Slim",
    fan_low: "Laag",
    fan_medium: "Midden",
    fan_high: "Hoog",
    fanSmart: "Smart Climate kiest: hoog als het ver te koud is, dicht bij het doel kiest {d} zelf.",
    fanNow: "nu {f}",
    fanFixed: "{d} blijft op deze stand tot je Slim kiest.",
    cvPaused: "{Support} gepauzeerd, nog {t}",
    cvPausedOpen: "{Support} gepauzeerd (tot je hem hervat)",
    resume: "Hervat",
    leavingHint:
      "Als je zo weg bent is het zonde om de {support} nog aan te zetten; de airco houdt het bij.",
    devMode: "Besturing van {name}",
    devAuto: "Auto",
    devOff: "Niet gebruiken",
    devManual: "Handmatig",
    devExternal: "(afstandsbediening)",
    devAutoHint: "De coördinator stuurt dit apparaat aan.",
    devOffHint: "Blijft uit en wordt niet gebruikt, ook niet als ondersteuning.",
    devManualHint: "Handen af: jij bedient dit apparaat zelf.",
    devHowLong: "Hoe lang?",
    devHour1: "1 uur",
    devUntil: "Tot {t}",
    devForever: "Blijvend",
    devUntilShort: "tot {t}",
    devLeft: "nog {t}",
    close: "Sluiten",
    tileToday: "Verwacht max vandaag",
    tileTomorrow: "Verwacht max morgen",
    tileMeasured: "Gemeten max 24 uur",
    overrideTitle: "Tijdelijk een andere temperatuur",
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
    entityNotFoundHint: "Check that {entity} exists and the Smart Climate integration is loaded.",
    coordUnavailable: "Unavailable",
    coordUnavailableHint: "{entity} is not responding. The card returns once the integration is reachable again.",
    powerOn: "Turn on (auto)",
    powerOff: "Turn off",
    goal: "target {t}",
    off: "Off",
    roomSensor: "Room: {name}",
    roomMean: "Room: average of the devices",
    roomPrimary: "Room: {name}",
    stateOff: "Off: the controller drives nothing",
    idleAbove: "Nothing active: the room is above the target",
    idleWarm: "Nothing active: the room is warm, but cooling is not allowed",
    idleOk: "Nothing active: the room is around the target",
    heating: "{names} heats to {t}",
    heatingMany: "{names} heat to {t}",
    heatingAny: "Heating to {t}",
    heatNoDevice: "Wants to heat to {t}, but no device is set to Auto",
    coolNoDevice: "Wants to cool to {t}, but no device is set to Auto",
    paused: "{names} paused",
    notAvailable: "{names} not available",
    allManual: "Everything manual: the coordinator drives nothing",
    noneAuto: "No device on Auto: the coordinator drives nothing",
    cooling: "{names} cools to {t}",
    coolingMany: "{names} cool to {t}",
    coolingAny: "Cooling to {t}",
    and: " and ",
    home: "Home",
    away: "Away",
    awayIn: "away in {t}",
    "st.off": "off",
    "st.heat": "heating",
    "st.cool": "cooling",
    "st.auto": "auto",
    "st.heat_cool": "auto",
    "st.fan_only": "fan",
    "st.dry": "drying",
    "st.unavailable": "not available",
    "st.unknown": "unknown",
    cooling_title: "Cooling",
    coolSummary: "Cooling: {mode} · not needed now",
    coolExpand: "Expand cooling",
    coolCollapse: "Collapse cooling",
    coolOff: "No cooling, not even in warm weather.",
    coolOn: "Cooling is always allowed; it cools above {t}.",
    coolOnPlain: "Cooling is always allowed.",
    coolAllowed: "Allowed",
    coolNotAllowed: "Not allowed right now",
    coolCeiling: "Cooling always allowed above {t}.",
    supportTitle: "Heat support",
    supportText: "May join in when the room is {d} below the target",
    supportActive: "Active",
    boostStart: "{Support} join now (1 hour)",
    boostActive: "{Support} joins until {t} or the target",
    boostStop: "Stop",
    noCvMorning: "No heating support until tomorrow morning",
    noCvUntil: "No heating support until {t}",
    noCvOpen: "No heating support (until you switch it back on)",
    leavingSoon: "I'm leaving soon",
    fanTitle: "Fan",
    fan_auto: "Smart",
    fan_low: "Low",
    fan_medium: "Medium",
    fan_high: "High",
    fanSmart: "Smart Climate chooses: high when far too cold, near the target {d} chooses itself.",
    fanNow: "now {f}",
    fanFixed: "{d} stays at this speed until you pick Smart.",
    cvPaused: "{Support} paused, {t} left",
    cvPausedOpen: "{Support} paused (until you resume it)",
    resume: "Resume",
    leavingHint:
      "If you are leaving soon there is no point in switching on the {support}; the airco keeps up.",
    devMode: "Control of {name}",
    devAuto: "Auto",
    devOff: "Don't use",
    devManual: "Manual",
    devExternal: "(remote control)",
    devAutoHint: "The coordinator drives this device.",
    devOffHint: "Stays off and is not used, not even as support.",
    devManualHint: "Hands off: you operate this device yourself.",
    devHowLong: "For how long?",
    devHour1: "1 hour",
    devUntil: "Until {t}",
    devForever: "Permanent",
    devUntilShort: "until {t}",
    devLeft: "{t} left",
    close: "Close",
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
    _menu: { state: true }, // { id, mode } while a device's control menu is open
    _coolOpen: { state: true }, // the cooling block is unfolded although cooling is not relevant
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
    this._unlistenMenu();
  }

  updated(changed) {
    if (!changed.has("_menu")) return;
    const prev = changed.get("_menu");
    if (this._menu) {
      this._listenMenu();
      // Move focus into a freshly opened menu (not on every mode pick inside it).
      if (!prev || prev.id !== this._menu.id) {
        this.renderRoot.querySelector('.devmenu [aria-pressed="true"]')?.focus();
      }
    } else {
      this._unlistenMenu();
    }
  }

  // Closing the device menu: Escape or a click anywhere outside the menu and the chips.
  _listenMenu() {
    if (this._menuListening) return;
    this._menuListening = true;
    document.addEventListener("click", this._onDocClick);
    document.addEventListener("keydown", this._onDocKey);
  }

  _unlistenMenu() {
    if (!this._menuListening) return;
    this._menuListening = false;
    document.removeEventListener("click", this._onDocClick);
    document.removeEventListener("keydown", this._onDocKey);
  }

  _onDocClick = (e) => {
    const inside = e
      .composedPath()
      .some((el) => el.classList?.contains("devmenu") || el.dataset?.device !== undefined);
    if (!inside) this._closeMenu();
  };

  _onDocKey = (e) => {
    if (e.key === "Escape" && this._menu) this._closeMenu(true);
  };

  _closeMenu(refocus = false) {
    const id = this._menu?.id;
    this._menu = null;
    if (refocus && id) {
      this.updateComplete.then(() => {
        const chip = [...this.renderRoot.querySelectorAll("button.chip[data-device]")].find(
          (c) => c.dataset.device === id
        );
        chip?.focus();
      });
    }
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

  /** Texts with the support heater's name: `{support}` and `{Support}` (capitalised). */
  _ts(key, attrs, vars = {}) {
    const support = supportName(attrs, this.hass);
    return this._t(key, {
      ...vars,
      support,
      Support: support.charAt(0).toUpperCase() + support.slice(1),
    });
  }

  // ── Render ───────────────────────────────────────────────────────────────

  render() {
    if (!this.hass) return html``;

    const entity = this.hass.states[this.config.entity];
    if (!entity) {
      return this._renderError("entityNotFound", "entityNotFoundHint");
    }
    if (entity.state === "unavailable") {
      return this._renderError("coordUnavailable", "coordUnavailableHint");
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
            ${this._renderOverride(attrs)}
            ${this._renderFan()}
            ${this._renderCooling(attrs)}
            ${this._renderSupport(attrs)}
          </div>
        </div>
      </ha-card>
    `;
  }

  /** Friendly error card instead of a bare line of text. */
  _renderError(titleKey, hintKey) {
    return html`
      <ha-card>
        <div class="content error" role="alert">
          <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
          <div>
            <div class="error-title">${this._t(titleKey)}</div>
            <div class="error-text">${this._t(hintKey, { entity: this.config.entity })}</div>
          </div>
        </div>
      </ha-card>
    `;
  }

  // Header: big room temperature, one-sentence status, chips and power button.
  _renderHeader(entity, attrs, isOff) {
    const name = this.config.name ?? attrs.friendly_name ?? "SmartClimate";
    const source = this._roomSource(attrs);
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
          ${source ? html`<div class="source">${source}</div>` : ""}
        </div>
        <div class="head-right">
          <div class="head-top">
            ${this._renderPresenceChip(attrs)}
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
          <div class="chips">${this._renderDeviceChips(attrs)}</div>
        </div>
      </div>
      <div class="sentence">${this._sentence(attrs, isOff)}</div>
      ${this._renderDeviceMenu(attrs)}
    `;
  }

  /** Where the room temperature comes from (`room_temperature_source`); "" when unknown. */
  _roomSource(attrs) {
    const src = attrs.room_temperature_source;
    if (!src || typeof src !== "object") return "";
    if (src.kind === "mean") return this._t("roomMean");
    if (src.kind === "sensor" && src.entity) {
      return this._t("roomSensor", { name: entityName(this.hass, src.entity) });
    }
    if (src.kind === "primary" && src.entity) {
      return this._t("roomPrimary", { name: entityName(this.hass, src.entity) });
    }
    return "";
  }

  _renderPresenceChip(attrs) {
    const presence = attrs.presence;
    if (presence !== "home" && presence !== "away") return "";
    const delay = Number(attrs.away_delay_seconds_remaining) || 0;
    const leaving = presence === "home" && delay > 0;
    const icon = presence === "home" && !leaving ? "mdi:home" : "mdi:home-export-outline";
    return html`
      <span class="chip chip--static" data-kind="presence" data-presence=${presence}>
        <ha-icon icon=${icon}></ha-icon>
        <span class="chip-text">
          <span class="chip-line">
            <span class="chip-name">${presence === "home" ? this._t("home") : this._t("away")}</span>
            ${leaving
              ? html`<span class="chip-sub">· ${this._t("awayIn", { t: this._clock(delay) })}</span>`
              : ""}
          </span>
        </span>
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

  /** Translated hvac state of a device ("verwarmt", "staat uit", "niet beschikbaar", ...). */
  _stateLabel(state) {
    const key = `st.${isUnavailable(state) ? "unavailable" : state}`;
    const text = this._t(key);
    return text === key ? String(state) : text;
  }

  _renderDeviceChips(attrs) {
    return this._devices(attrs).map((d) => {
      const { mode, until, source } = deviceMode(attrs, d.entity_id);
      const state = this.hass.states[d.entity_id]?.state;
      const unavailable = isUnavailable(state);
      const support = d.tier === "support";
      const kind =
        mode !== "auto" || unavailable ? "" : state === "heat" ? "heat" : state === "cool" ? "cool" : "";
      let icon = support ? "mdi:radiator" : "mdi:air-conditioning";
      if (unavailable) icon = "mdi:alert-circle-outline";
      else if (mode === "manual") icon = "mdi:hand-back-left";
      else if (mode === "off") icon = support ? "mdi:radiator-off" : "mdi:snowflake-off";
      const control = mode !== "auto" ? this._controlLabel(mode, until, source) : "";
      const open = this._menu?.id === d.entity_id;
      return html`
        <button
          class="chip"
          data-device=${d.entity_id}
          data-kind=${kind || "device"}
          data-mode=${mode}
          data-source=${source}
          data-unavailable=${unavailable ? "true" : "false"}
          aria-haspopup="true"
          aria-expanded=${open ? "true" : "false"}
          aria-controls="devmenu"
          @click=${() => this._toggleMenu(d.entity_id)}
        >
          <ha-icon icon=${icon}></ha-icon>
          <span class="chip-text">
            <span class="chip-line">
              <span class="chip-name">${entityName(this.hass, d.entity_id)}</span>
              <span class="chip-sub">· ${this._stateLabel(state)}</span>
            </span>
            ${control ? html`<span class="chip-ctl">${control}</span>` : ""}
          </span>
        </button>
      `;
    });
  }

  /** Control label of a device not on Auto: "Niet gebruiken · nog 25 min", "Handmatig (afstandsbediening)". */
  _controlLabel(mode, until, source) {
    let base = this._t(mode === "off" ? "devOff" : "devManual");
    if (mode === "manual" && source === "external") base += ` ${this._t("devExternal")}`;
    const rest = this._untilLabel(until);
    return rest ? `${base} · ${rest}` : base;
  }

  /** "nog 25 min" (soon) or "tot 10:00"; "" when the mode has no end. */
  _untilLabel(until) {
    const left = minutesLeft(until);
    if (left === null) return "";
    if (left <= REMAINING_SHOW_MIN) return this._t("devLeft", { t: this._minutes(left) });
    return this._t("devUntilShort", { t: fmtClock(until, this.hass) });
  }

  /** Compact panel under the header to pick Auto / Off / Manual for one device. */
  _renderDeviceMenu(attrs) {
    if (!this._menu) return "";
    const dev = this._devices(attrs).find((d) => d.entity_id === this._menu.id);
    if (!dev) return "";
    const current = deviceMode(attrs, dev.entity_id).mode;
    const picked = this._menu.mode ?? current;
    const name = entityName(this.hass, dev.entity_id);
    const modes = [
      ["auto", "devAuto"],
      ["off", "devOff"],
      ["manual", "devManual"],
    ];
    const hint = { auto: "devAutoHint", off: "devOffHint", manual: "devManualHint" }[picked];
    const until10 = minutesUntilClock(this.hass, 10, 0);
    return html`
      <div class="devmenu" id="devmenu" role="group" aria-label=${this._t("devMode", { name })}>
        <div class="devmenu-head">
          <span class="devmenu-title">${this._t("devMode", { name })}</span>
          <button class="close" aria-label=${this._t("close")} @click=${() => this._closeMenu(true)}>
            <ha-icon icon="mdi:close"></ha-icon>
          </button>
        </div>
        <div class="segmented" role="group" aria-label=${this._t("devMode", { name })}>
          ${modes.map(
            ([m, key]) => html`
              <button
                aria-pressed=${picked === m ? "true" : "false"}
                ?active=${picked === m}
                @click=${() => this.onDeviceModePick(dev.entity_id, m)}
              >
                ${this._t(key)}
              </button>
            `
          )}
        </div>
        <div class="hint"><span>${this._t(hint)}</span></div>
        ${picked !== "auto"
          ? html`
              <div class="devmenu-how">${this._t("devHowLong")}</div>
              <div class="choices">
                <button class="choice" @click=${() => this.onDeviceMode(dev.entity_id, picked, 30)}>
                  ${this._t("min30")}
                </button>
                <button class="choice" @click=${() => this.onDeviceMode(dev.entity_id, picked, 60)}>
                  ${this._t("devHour1")}
                </button>
                <button class="choice" @click=${() => this.onDeviceMode(dev.entity_id, picked, until10)}>
                  ${this._t("devUntil", { t: "10:00" })}
                </button>
                <button class="choice choice--quiet" @click=${() => this.onDeviceMode(dev.entity_id, picked)}>
                  ${this._t("devForever")}
                </button>
              </div>
            `
          : ""}
      </div>
    `;
  }

  _toggleMenu(id) {
    this._menu = this._menu?.id === id ? null : { id, mode: null };
  }

  /** "Airco en CV verwarmen naar 20°" etc. — derived from intent, device states and control modes. */
  _sentence(attrs, isOff) {
    if (isOff) return this._t("stateOff");
    const intent = attrs.intent ?? ACTION_TO_INTENT[attrs.hvac_action];
    const target = fmtTemp(attrs.temperature, this.hass);
    const devices = this._devices(attrs);
    const down = (d) => isUnavailable(this.hass.states[d.entity_id]?.state);
    const namesOf = (list) => list.map((d) => entityName(this.hass, d.entity_id)).join(this._t("and"));
    const unavailableText = (list) => this._t("notAvailable", { names: namesOf(list) });

    // Nothing reachable: do not claim anything is heating.
    if (devices.length && devices.every(down)) return unavailableText(devices);

    // Devices on Off/Manual are not driven by the coordinator: never named as active.
    const modeOf = (d) => deviceMode(attrs, d.entity_id).mode;
    const auto = devices.filter((d) => modeOf(d) === "auto");
    if (devices.length && !auto.length) {
      return this._t(devices.every((d) => modeOf(d) === "manual") ? "allManual" : "noneAuto");
    }

    let text;
    let mentioned = [];
    if (intent === "heat" || intent === "cool") {
      const wanted = intent === "heat" ? "heat" : "cool";
      const active = auto.filter((d) => this.hass.states[d.entity_id]?.state === wanted);
      let list = active;
      if (!list.length) {
        // Device states may lag behind the decision: fall back to the roles.
        list = auto.filter(
          (d) => (d.role === "both" || d.role === wanted) && d.tier !== "support"
        );
      }
      if (intent === "heat" && attrs.support_active) {
        for (const s of supportDevices(attrs)) {
          if (modeOf(s) === "auto" && !list.includes(s)) list = [...list, s];
        }
      }
      // An unreachable device cannot be heating or cooling.
      mentioned = list.filter(down);
      list = list.filter((d) => !down(d));
      const base = intent === "heat" ? "heating" : "cooling";
      if (!list.length) {
        if (mentioned.length) return unavailableText(mentioned);
        const noDevice = intent === "heat" ? "heatNoDevice" : "coolNoDevice";
        return this._t(devices.some((d) => modeOf(d) !== "auto") ? noDevice : `${base}Any`, {
          t: target,
        });
      }
      text = this._t(list.length > 1 ? `${base}Many` : base, {
        names: namesOf(list),
        t: target,
      });
      if (intent === "heat" && supportPause(attrs)?.kind) {
        const paused = supportDevices(attrs).map((d) => entityName(this.hass, d.entity_id));
        if (paused.length) text += ` (${this._t("paused", { names: paused.join(this._t("and")) })})`;
      }
    } else {
      // idle (or unknown)
      const room = attrs.current_temperature;
      const coolLimit = attrs.cool_limit;
      if (
        attrs.cooling_allowed === false &&
        typeof room === "number" &&
        typeof coolLimit === "number" &&
        room >= coolLimit
      ) {
        text = this._t("idleWarm");
      } else if (
        typeof room === "number" &&
        typeof attrs.temperature === "number" &&
        room > attrs.temperature
      ) {
        text = this._t("idleAbove");
      } else {
        text = this._t("idleOk");
      }
    }

    // Other devices that are on Auto but unreachable.
    const missing = auto.filter((d) => down(d) && !mentioned.includes(d));
    if (missing.length) text += ` (${unavailableText(missing)})`;
    return text;
  }

  _renderCooling(attrs) {
    const info = coolingInfo(attrs, this.hass);
    if (!info) return this._renderTiles(attrs, false);
    const relevant = coolingRelevant(attrs);
    if (!relevant && !this._coolOpen) {
      return html`
        <section class="block fold-block">
          <button
            class="fold"
            aria-expanded="false"
            aria-label=${this._t("coolExpand")}
            @click=${() => { this._coolOpen = true; }}
          >
            <ha-icon icon="mdi:snowflake"></ha-icon>
            <span class="fold-label">${this._t("coolSummary", { mode: info.label })}</span>
            <ha-icon icon="mdi:chevron-down"></ha-icon>
          </button>
        </section>
      `;
    }

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
          <div class="segmented" role="group" aria-label=${this._t("cooling_title")}>
            ${modes.map(
              (m) => html`
                <button
                  aria-pressed=${info.mode === m ? "true" : "false"}
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
        ${this._renderTiles(attrs, true)}
        ${!relevant
          ? html`<button
              class="fold fold--close"
              aria-expanded="true"
              @click=${() => { this._coolOpen = false; }}
            >
              <ha-icon icon="mdi:chevron-up"></ha-icon>
              <span class="fold-label">${this._t("coolCollapse")}</span>
            </button>`
          : ""}
      </section>
    `;
  }

  /** Fan speed: "auto" = Smart Climate's boost chooses, a fixed speed holds the device there. */
  _renderFan() {
    const st = this.hass.states[this.config.entity];
    const modes = (st?.attributes.fan_modes || []).filter((m) => ["auto", "low", "medium", "high"].includes(m));
    if (!modes.length) return "";
    const current = st.attributes.fan_mode;
    const fanDevice = (st.attributes.devices || []).find(
      (d) => (this.hass.states[d.entity_id]?.attributes.fan_modes || []).length
    );
    const devState = fanDevice ? this.hass.states[fanDevice.entity_id] : undefined;
    const devName = fanDevice ? entityName(this.hass, fanDevice.entity_id) : "";
    const devFan = devState?.attributes.fan_mode;
    const label = (m) => (["auto", "low", "medium", "high"].includes(m) ? this._t(`fan_${m}`) : m);
    return html`
      <section class="block">
        <div class="row">
          <div class="label">${this._t("fanTitle")}</div>
          ${current === "auto" && devFan
            ? html`<div class="status">${this._t("fanNow", { f: devFan === "auto" ? "auto" : label(devFan).toLowerCase() })}</div>`
            : ""}
        </div>
        <div class="choices">
          ${modes.map(
            (m) => html`<button class="choice" ?active=${current === m} @click=${() => this.onFanMode(m)}>
              ${label(m)}
            </button>`
          )}
        </div>
        <div class="hint">
          <span>${current === "auto" ? this._t("fanSmart", { d: devName }) : this._t("fanFixed", { d: devName })}</span>
        </div>
      </section>
    `;
  }

  onFanMode(mode) {
    this.hass.callService("climate", "set_fan_mode", { entity_id: this.config.entity, fan_mode: mode });
  }

  _renderSupport(attrs) {
    const support = supportDevices(attrs);
    if (!support.length) return "";
    // Every support heater on "Niet gebruiken": nothing to set here (its chip in
    // the header says so and leads back to Auto).
    if (support.every((d) => deviceMode(attrs, d.entity_id).mode === "off")) return "";
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
        ${this._renderSupportBoost(attrs)}
        ${this._renderSupportPause(attrs)}
      </section>
    `;
  }

  /** "CV erbij": let the support heater join now; hidden on backends without the boost (no attribute). */
  _renderSupportBoost(attrs) {
    if (!("support_boost_until" in attrs)) return "";
    const until = attrs.support_boost_until;
    return html`
      <div class="boost">
        ${until
          ? html`
              <div class="leaving-active">
                <span>${this._ts("boostActive", attrs, { t: fmtClock(until, this.hass) })}</span>
                <button class="choice" @click=${() => this.onSupportBoost(false)}>
                  <ha-icon icon="mdi:stop"></ha-icon>${this._t("boostStop")}
                </button>
              </div>
            `
          : html`
              <button class="toggle-chip" @click=${() => this.onSupportBoost(true)}>
                <ha-icon icon="mdi:radiator"></ha-icon>${this._ts("boostStart", attrs)}
              </button>
            `}
      </div>
    `;
  }

  /** Shortcuts to pause the support heater; hidden on backends without `support_paused_until`. */
  _renderSupportPause(attrs) {
    const pause = supportPause(attrs);
    if (!pause) return "";
    const morning = pause.kind === "until_morning";
    // `minutes` without an end cannot be counted down: show it as open-ended.
    const leaving = pause.kind === "minutes" && pause.left !== null;
    const open = pause.kind === "open" || (pause.kind === "minutes" && pause.left === null);

    let morningText = this._t("noCvMorning");
    if (morning) {
      const clock = pause.until ? fmtClock(pause.until, this.hass) : "";
      morningText = clock ? this._t("noCvUntil", { t: clock }) : this._t("noCvOpen");
    }

    return html`
      <div class="pause">
        <button
          class="toggle-chip"
          aria-pressed=${morning ? "true" : "false"}
          ?active=${morning}
          @click=${() => this.onSupportMorning(!morning)}
        >
          <ha-icon icon="mdi:radiator-off"></ha-icon>${morningText}
        </button>
        <div class="leaving">
          ${leaving || open
            ? html`
                <div class="leaving-active">
                  <span>
                    ${leaving
                      ? this._ts("cvPaused", attrs, { t: this._minutes(pause.left) })
                      : this._ts("cvPausedOpen", attrs)}
                  </span>
                  <button class="choice" @click=${() => this.onSupportResume()}>
                    <ha-icon icon="mdi:play"></ha-icon>${this._t("resume")}
                  </button>
                </div>
              `
            : html`
                <div class="leaving-label">
                  <ha-icon icon="mdi:run-fast"></ha-icon>${this._t("leavingSoon")}
                </div>
                <div class="choices">
                  ${[
                    [30, "min30"],
                    [60, "devHour1"],
                    [120, "hours2"],
                  ].map(
                    ([n, key]) => html`
                      <button class="choice" @click=${() => this.onSupportPause(n)}>
                        ${this._t(key)}
                      </button>
                    `
                  )}
                </div>
              `}
        </div>
        <div class="hint"><span>${this._ts("leavingHint", attrs)}</span></div>
      </div>
    `;
  }

  /** Outdoor tiles; part of the unfolded cooling block (`inBlock`) or shown alone on old backends. */
  _renderTiles(attrs, inBlock) {
    const warm = attrs.warm_threshold;
    const tiles = [
      { key: "tileToday", v: attrs.forecast_high_today },
      { key: "tileTomorrow", v: attrs.forecast_high_tomorrow },
      { key: "tileMeasured", v: attrs.outdoor_max_24h },
    ].filter((t) => typeof t.v === "number");
    if (!tiles.length) return "";
    return html`
      <section class="tiles ${inBlock ? "tiles--in" : ""}">
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

  /** Set a device's control mode; `minutes` makes it temporary, without it stays until changed. */
  onDeviceMode(device, mode, minutes) {
    const data = { entity_id: this.config.entity, device, mode };
    if (mode !== "auto" && minutes) data.minutes = minutes;
    this.hass.callService("smart_climate", "set_device_mode", data);
    this._menu = null;
  }

  /** Segmented pick in the device menu: Auto applies at once, Off/Manual ask for a duration. */
  onDeviceModePick(device, mode) {
    if (mode === "auto") {
      this.onDeviceMode(device, "auto");
    } else {
      this._menu = { id: device, mode };
    }
  }

  onSupportMorning(on) {
    const entity_id = this.config.entity;
    this.hass.callService(
      "smart_climate",
      "set_support_pause",
      on ? { entity_id, enabled: true, until_morning: true } : { entity_id, enabled: false }
    );
  }

  onSupportBoost(on) {
    this.hass.callService("smart_climate", "set_support_boost", { entity_id: this.config.entity, enabled: on });
  }

  onSupportPause(minutes) {
    this.hass.callService("smart_climate", "set_support_pause", {
      entity_id: this.config.entity,
      enabled: true,
      minutes,
    });
  }

  onSupportResume() {
    this.hass.callService("smart_climate", "set_support_pause", {
      entity_id: this.config.entity,
      enabled: false,
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
      --sc-tap: 44px;
      /* Small text and white-on-colour text need 4.5:1 in light and dark themes;
         the plain theme colours (grey, light blue) fall short, so mix them toward
         the readable side. Browsers without color-mix keep the plain colours. */
      --sc-muted: var(--secondary-text-color);
      --sc-strong: var(--primary-color);
      --sc-link: var(--primary-color);
    }

    @supports (color: color-mix(in srgb, red, blue)) {
      :host {
        --sc-muted: color-mix(in srgb, var(--secondary-text-color) 70%, var(--primary-text-color));
        --sc-strong: color-mix(in srgb, var(--primary-color) 68%, #000);
        --sc-link: color-mix(in srgb, var(--primary-color) 45%, var(--primary-text-color));
      }
    }

    ha-card {
      background: var(--ha-card-background, var(--card-background-color, #fff));
      color: var(--primary-text-color);
    }

    .content {
      padding: 16px;
    }

    .content.error {
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }

    .error ha-icon {
      --mdc-icon-size: 28px;
      color: var(--warning-color, #ffa600);
    }

    .error-title {
      font-size: 16px;
      font-weight: 500;
    }

    .error-text {
      margin-top: 2px;
      font-size: 14px;
      color: var(--sc-muted);
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
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px 12px;
    }

    .temp-block {
      flex: 1 1 120px;
      min-width: 110px;
    }

    .name {
      font-size: 13px;
      color: var(--sc-muted);
    }

    .room {
      font-size: 56px;
      line-height: 1.05;
      font-weight: 300;
      letter-spacing: -0.02em;
    }

    .room[off] {
      color: var(--sc-muted);
    }

    .unit {
      font-size: 0.5em;
      vertical-align: top;
      margin-left: 2px;
      color: var(--sc-muted);
    }

    .goal {
      font-size: 15px;
      color: var(--sc-muted);
    }

    .source {
      margin-top: 2px;
      font-size: 12px;
      color: var(--sc-muted);
    }

    .head-right {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
      flex: 0 1 auto;
      max-width: 66%;
      min-width: 0;
    }

    .head-top {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      max-width: 100%;
    }

    .chips {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
      max-width: 100%;
      min-width: 0;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      max-width: 100%;
      min-height: var(--sc-tap);
      box-sizing: border-box;
      padding: 4px 12px 4px 10px;
      border-radius: 22px;
      font-size: 13px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    button.chip {
      cursor: pointer;
      text-align: left;
    }

    .chip--static .chip-line {
      white-space: nowrap;
    }

    .chip--static {
      min-height: 32px;
      padding-top: 2px;
      padding-bottom: 2px;
    }

    button.chip:hover {
      border-color: var(--primary-color);
    }

    button.chip[aria-expanded="true"] {
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }

    /* A device the coordinator does not drive (Off / Manual): dashed, orange, easy to spot
       (the control label in the chip says it in words, colour is only a hint). */
    .chip[data-mode="off"],
    .chip[data-mode="manual"] {
      border-style: dashed;
      border-color: var(--warning-color, #ffa600);
      background: rgba(255, 166, 0, 0.12);
    }

    .chip[data-mode="off"] ha-icon,
    .chip[data-mode="manual"] ha-icon,
    .chip[data-unavailable="true"] ha-icon {
      color: var(--warning-color, #ffa600);
    }

    .chip[data-unavailable="true"] {
      border-color: var(--error-color, #db4437);
    }

    .chip-text {
      display: flex;
      flex-direction: column;
      min-width: 0;
      line-height: 1.25;
    }

    .chip-name {
      font-weight: 500;
    }

    .chip ha-icon {
      --mdc-icon-size: 18px;
      color: var(--sc-muted);
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
      color: var(--sc-muted);
    }

    .chip-ctl {
      font-size: 12px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    /* Device control menu (inline panel under the header) */
    .devmenu {
      margin-top: 12px;
      padding: 12px;
      border-radius: var(--sc-radius);
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    .devmenu-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
    }

    .devmenu-title {
      font-size: 15px;
      font-weight: 500;
    }

    .devmenu .close {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: var(--sc-tap);
      height: var(--sc-tap);
      margin: -4px -6px -4px 0;
      padding: 0;
      border: none;
      border-radius: 50%;
      background: transparent;
      color: var(--sc-muted);
    }

    .devmenu .close:hover {
      background: rgba(127, 127, 127, 0.15);
    }

    .devmenu .segmented {
      display: flex;
    }

    .devmenu .segmented button {
      flex: 1 1 0;
      min-width: 0;
      padding-left: 6px;
      padding-right: 6px;
    }

    .devmenu-how {
      margin: 10px 0 6px;
      font-size: 13px;
      color: var(--sc-muted);
    }

    /* "CV erbij" */
    .boost {
      margin-top: 12px;
      display: flex;
    }

    /* Support pause shortcuts */
    .pause {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color);
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .pause .hint {
      margin-top: 0;
    }

    .toggle-chip {
      display: inline-flex;
      align-items: center;
      align-self: flex-start;
      gap: 8px;
      max-width: 100%;
      min-height: var(--sc-tap);
      box-sizing: border-box;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color, var(--ha-card-background, #fff));
      font-size: 14px;
      text-align: left;
    }

    .toggle-chip:hover {
      border-color: var(--primary-color);
    }

    .toggle-chip[active] {
      background: var(--sc-strong);
      border-color: var(--sc-strong);
      color: var(--text-primary-color, #fff);
    }

    .toggle-chip ha-icon {
      --mdc-icon-size: 18px;
    }

    .leaving-label {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 6px;
      font-size: 14px;
      font-weight: 500;
    }

    .leaving-active {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 14px;
    }

    .leaving-active .choice {
      flex: none;
    }

    .choice ha-icon {
      --mdc-icon-size: 18px;
      margin-right: 4px;
      vertical-align: middle;
    }

    .power {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      width: var(--sc-tap);
      height: var(--sc-tap);
      padding: 0;
      border: none;
      border-radius: 50%;
      background: var(--secondary-background-color);
      color: var(--sc-muted);
      transition: background 0.2s ease, color 0.2s ease;
    }

    .power[on] {
      background: var(--sc-strong);
      color: var(--text-primary-color, #fff);
    }

    .power:hover {
      filter: brightness(1.1);
    }

    .power ha-icon {
      --mdc-icon-size: 24px;
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
      margin-top: 12px;
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
      color: var(--sc-muted);
    }

    .hint ha-icon {
      --mdc-icon-size: 16px;
      margin-top: 1px;
    }

    .hint[data-allowed="true"] ha-icon {
      color: var(--sc-ok);
    }

    .muted {
      opacity: 1;
    }

    .badge {
      font-size: 12px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 999px;
      background: #b34700;
      color: #fff;
    }

    /* Folded cooling summary / collapse control */
    .fold-block {
      padding: 0;
    }

    .fold {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      min-height: var(--sc-tap);
      box-sizing: border-box;
      padding: 0 12px;
      border: none;
      border-radius: var(--sc-radius);
      background: transparent;
      font-size: 14px;
      text-align: left;
    }

    .fold-label {
      flex: 1 1 auto;
      min-width: 0;
    }

    .fold ha-icon {
      color: var(--sc-muted);
    }

    .fold--close {
      justify-content: center;
      margin-top: 4px;
      padding: 0;
      color: var(--sc-muted);
      font-size: 13px;
    }

    .fold--close .fold-label {
      flex: none;
    }

    .fold:hover {
      background: rgba(127, 127, 127, 0.1);
    }

    /* Segmented control (aria-pressed buttons) */
    .segmented {
      display: inline-flex;
      padding: 2px;
      border-radius: 12px;
      background: var(--card-background-color, var(--ha-card-background, #fff));
      border: 1px solid var(--divider-color);
    }

    .segmented button {
      min-width: 64px;
      min-height: var(--sc-tap);
      padding: 6px 14px;
      border: none;
      border-radius: 10px;
      background: transparent;
      font-size: 14px;
      color: var(--sc-muted);
    }

    .segmented button[active] {
      background: var(--sc-strong);
      color: var(--text-primary-color, #fff);
      font-weight: 500;
    }

    /* Toggle switch: 52x44 hit area around a 46x26 track */
    .switch {
      position: relative;
      flex-shrink: 0;
      width: 52px;
      height: var(--sc-tap);
      padding: 0;
      border: none;
      background: transparent;
    }

    .switch::before {
      content: "";
      position: absolute;
      left: 3px;
      top: 9px;
      width: 46px;
      height: 26px;
      border-radius: 13px;
      background: var(--sc-muted);
      transition: background 0.2s ease;
    }

    .switch[on]::before {
      background: var(--sc-strong);
    }

    .knob {
      position: absolute;
      top: 12px;
      left: 6px;
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

    /* Outdoor tiles (inside the unfolded cooling block) */
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      gap: 8px;
    }

    .tiles--in {
      margin-top: 10px;
    }

    .tile {
      padding: 10px 12px;
      border-radius: var(--sc-radius);
      background: var(--secondary-background-color);
    }

    .tiles--in .tile {
      background: var(--card-background-color, var(--ha-card-background, #fff));
    }

    .tile-value {
      font-size: 24px;
      font-weight: 300;
    }

    .tile-value[warm] {
      color: var(--sc-heat);
    }

    @supports (color: color-mix(in srgb, red, blue)) {
      .tile-value[warm] {
        color: color-mix(in srgb, var(--sc-heat) 70%, var(--primary-text-color));
      }
    }

    .tile-label {
      margin-top: 2px;
      font-size: 12px;
      color: var(--sc-muted);
    }

    /* Override */
    .status {
      font-size: 13px;
      color: var(--sc-muted);
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
      margin: 6px 0 10px;
    }

    .stepper button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: var(--sc-tap);
      height: var(--sc-tap);
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
      min-height: var(--sc-tap);
      box-sizing: border-box;
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
      background: var(--sc-strong);
      border-color: var(--sc-strong);
      color: var(--text-primary-color, #fff);
    }

    /* Tertiary option: lighter than the timed choices */
    .choice--quiet {
      border-style: dashed;
      background: transparent;
      color: var(--sc-muted);
    }

    .back {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: var(--sc-tap);
      margin-top: 6px;
      padding: 6px 12px;
      border: none;
      border-radius: 8px;
      background: transparent;
      font-size: 14px;
      color: var(--sc-link);
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
