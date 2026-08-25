import { LitElement, html, css } from "https://unpkg.com/lit@3/index.js?module";

class SmartClimateCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
    _overrideTemp: { state: true },
  };

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Entity required");
    }
    this.config = config;
    this._overrideTemp = 21;
  }

  render() {
    if (!this.hass) return html``;

    const entity = this.hass.states[this.config.entity];
    if (!entity) {
      return html`
        <ha-card>
          <div class="content">Entity not found</div>
        </ha-card>
      `;
    }

    // The zone's state is its occupancy count, not the string "home".
    const zone = this.hass.states["zone.home"];
    const isHome = Number(zone?.state) > 0;

    // The entity state is the coordinator's HVAC mode; "off" means it drives
    // nothing at all, so say so instead of showing a setpoint that is not used.
    const isOff = entity.state === "off";

    const attrs = entity.attributes;
    const currentTemp = attrs.current_temperature ?? "—";
    const targetTemp = attrs.temperature ?? 21;
    const overrideTemp = attrs.override_temperature ?? this._overrideTemp;
    const mode = attrs.mode ?? "auto";
    const remaining = attrs.remaining_minutes ?? 0;

    if (overrideTemp !== this._overrideTemp) {
      this._overrideTemp = overrideTemp;
    }

    const isTimer = mode === "override_timer";
    const isInfinity = mode === "override_infinity";
    const sliderValue = isTimer ? remaining : isInfinity ? 480 : 0;

    return html`
      <ha-card>
        <div class="content">
          <div class="header">
            <div class="title">SmartClimate</div>
            <div class="header-right">
              <div class="presence" ?away=${!isHome}>
                ${isHome ? "🏠 Home" : "📍 Away"}
              </div>
              <button
                class="power"
                ?on=${!isOff}
                title=${isOff ? "Turn on (auto)" : "Turn off"}
                @click=${this.onPowerClick}
              >
                <ha-icon icon="mdi:power"></ha-icon>
              </button>
            </div>
          </div>

          <div class="temps" ?off=${isOff}>
            ${isOff
              ? html`${currentTemp}° · <span class="off-label">Off</span>`
              : html`${currentTemp}° → ${targetTemp}°`}
          </div>

          <div class="mode">Mode: ${mode}</div>

          <div class="panel" ?dimmed=${isOff}>
            <div class="state">
              ${isTimer
                ? html`<span class="countdown">Remaining: <strong>${this.formatTime(remaining)}</strong></span>`
                : isInfinity
                ? html`<strong>♾ Infinity</strong>`
                : html`Auto`}
            </div>

            <input
              type="range"
              min="0"
              max="480"
              step="15"
              .value=${sliderValue}
              @input=${this.onSliderInput}
              @change=${this.onSliderChange}
            />

            <div class="scale">
              <span>Auto</span>
              <span>2h</span>
              <span>4h</span>
              <span>8h</span>
              <span>∞</span>
            </div>
          </div>

          <div class="temp-slider-panel" ?dimmed=${isOff}>
            <div class="temp-label">Override: <strong>${this._overrideTemp}°</strong></div>
            <input
              type="range"
              min="5"
              max="25"
              step="0.5"
              .value=${this._overrideTemp}
              @input=${this.onTempInput}
              @change=${this.onTempChange}
              class="temp-slider"
            />
            <div class="temp-scale">
              <span>5°</span>
              <span>15°</span>
              <span>25°</span>
            </div>
          </div>
        </div>
      </ha-card>
    `;
  }

  onPowerClick() {
    const entity = this.hass.states[this.config.entity];
    const isOff = entity?.state === "off";
    this.hass.callService("climate", "set_hvac_mode", {
      entity_id: this.config.entity,
      hvac_mode: isOff ? "auto" : "off",
    });
  }

  onSliderChange(e) {
    const value = Number(e.target.value);
    const entityId = this.config.entity;

    if (value === 0) {
      this.hass.callService("smart_climate", "clear_override", {
        entity_id: entityId,
      });
    } else if (value === 480) {
      this.hass.callService("smart_climate", "set_override_infinity", {
        entity_id: entityId,
        temperature: this._overrideTemp,
      });
    } else {
      this.hass.callService("smart_climate", "set_override_timer", {
        entity_id: entityId,
        minutes: value,
        temperature: this._overrideTemp,
      });
    }
  }

  onSliderInput(e) {
    const value = Number(e.target.value);
    const slider = e.target;
    slider.style.setProperty("--slider-value", `${(value / 480) * 100}%`);
  }

  onTempInput(e) {
    this._overrideTemp = Number(e.target.value);
  }

  onTempChange(e) {
    this._overrideTemp = Number(e.target.value);
  }

  formatTime(minutes) {
    if (minutes < 60) return `${minutes}m`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  static styles = css`
    ha-card {
      background: var(--ha-card-background);
      color: var(--primary-text-color);
    }

    .content {
      padding: 16px;
    }

    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
    }

    .title {
      font-size: 20px;
      font-weight: 600;
    }

    .header-right {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .presence {
      font-size: 12px;
      padding: 4px 8px;
      border-radius: 6px;
      background: rgba(76, 175, 80, 0.15);
      color: #4caf50;
      transition: all 0.3s ease;
    }

    .presence[away] {
      background: rgba(244, 67, 54, 0.15);
      color: #f44336;
    }

    .power {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      padding: 0;
      border: none;
      border-radius: 50%;
      cursor: pointer;
      background: var(--secondary-background-color);
      color: var(--secondary-text-color);
      transition: all 0.2s ease;
    }

    .power[on] {
      background: rgba(76, 175, 80, 0.15);
      color: #4caf50;
    }

    .power:hover {
      filter: brightness(1.25);
    }

    .power ha-icon {
      --mdc-icon-size: 20px;
    }

    .temps {
      margin-top: 8px;
      font-size: 16px;
      transition: color 0.3s ease;
    }

    .temps[off] {
      color: var(--secondary-text-color);
    }

    .off-label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    /* The coordinator writes nothing while off, so the sliders are inert. */
    [dimmed] {
      opacity: 0.45;
    }

    .mode {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 6px;
    }

    .panel {
      margin-top: 12px;
      padding: 12px;
      border-radius: 10px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    .state {
      font-size: 12px;
      margin-bottom: 6px;
      min-height: 20px;
    }

    .countdown {
      animation: pulse 1s infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.7; }
    }

    input[type="range"] {
      width: 100%;
      accent-color: var(--accent-color);
      transition: all 0.1s ease;
    }

    input[type="range"]::-webkit-slider-thumb {
      transition: transform 0.1s ease;
    }

    input[type="range"]:hover::-webkit-slider-thumb {
      transform: scale(1.2);
    }

    .scale {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: var(--secondary-text-color);
      margin-top: 4px;
    }

    .temp-slider-panel {
      margin-top: 12px;
      padding: 12px;
      border-radius: 10px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    .temp-label {
      font-size: 12px;
      margin-bottom: 8px;
      color: var(--secondary-text-color);
    }

    .temp-slider {
      width: 100%;
      accent-color: var(--accent-color);
      margin-bottom: 8px;
    }

    .temp-scale {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: var(--secondary-text-color);
    }
  `;
}

customElements.define("smart-climate-card", SmartClimateCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-climate-card",
  name: "Smart Climate Card",
  description: "Future-proof smart climate control",
});