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

    const attrs = entity.attributes;
    const isHome = attrs.presence === "home";
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
            <div class="presence" ?away=${!isHome}>
              ${isHome ? "🏠 Aanwezig" : "📍 Afwezig"}
            </div>
          </div>

          <div class="temps">
            ${currentTemp}° → ${targetTemp}°
          </div>

          <div class="mode">Mode: ${mode}</div>

          ${isTimer ? html`
          <div class="timer-row">
            <span class="timer-icon">⏱</span>
            <span class="timer-value countdown">${this.formatTime(remaining)}</span>
            <span class="timer-label">resterend</span>
          </div>
          ` : ""}

          <div class="panel">
            <div class="state">
              ${isTimer
                ? html`<span>Timer actief</span>`
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

          ${isTimer || isInfinity ? html`
          <div class="temp-slider-panel">
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
          ` : ""}
        </div>
      </ha-card>
    `;
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

    .temps {
      margin-top: 8px;
      font-size: 16px;
    }

    .mode {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 6px;
    }

    .timer-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 10px;
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(255, 152, 0, 0.12);
      border: 1px solid rgba(255, 152, 0, 0.3);
    }

    .timer-icon {
      font-size: 16px;
    }

    .timer-value {
      font-size: 18px;
      font-weight: 700;
      color: #ff9800;
    }

    .timer-label {
      font-size: 12px;
      color: var(--secondary-text-color);
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