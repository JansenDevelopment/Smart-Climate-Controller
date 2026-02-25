import { LitElement, html, css } from "https://unpkg.com/lit@3/index.js?module";

class SmartClimateCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
  };

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Entity required");
    }
    this.config = config;
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
    const currentTemp = attrs.current_temperature ?? "—";
    const targetTemp = attrs.temperature ?? 21;
    const mode = attrs.mode ?? "auto";
    const remaining = attrs.remaining_minutes ?? 0;

    const isTimer = mode === "override_timer";
    const isInfinity = mode === "override_infinity";
    const sliderValue = isTimer ? remaining : isInfinity ? 480 : 0;

    return html`
      <ha-card>
        <div class="content">
          <div class="title">SmartClimate</div>

          <div class="temps">
            ${currentTemp}° → ${targetTemp}°
          </div>

          <div class="mode">Mode: ${mode}</div>

          <div class="panel">
            <div class="state">
              ${isTimer
                ? html`Remaining: <strong>${this.formatTime(remaining)}</strong>`
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
        temperature: 22,
      });
    } else {
      this.hass.callService("smart_climate", "set_override_timer", {
        entity_id: entityId,
        minutes: value,
        temperature: 22,
      });
    }
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

    .title {
      font-size: 20px;
      font-weight: 600;
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
    }

    input[type="range"] {
      width: 100%;
      accent-color: var(--accent-color);
    }

    .scale {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: var(--secondary-text-color);
      margin-top: 4px;
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
