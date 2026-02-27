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
    const presence = attrs.presence ?? "away";
    const isHome = presence === "home";
    const awayDelayRemaining = attrs.away_delay_seconds_remaining ?? 0;
    const isLeaving = !isHome && awayDelayRemaining > 0;
    const currentTemp = attrs.current_temperature ?? "—";
    const targetTemp = attrs.temperature ?? 21;
    const overrideTemp = attrs.override_temperature ?? this._overrideTemp;
    const mode = attrs.mode ?? "auto";
    const remaining = attrs.remaining_minutes ?? 0;
    const history = attrs.temperature_history ?? [];

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
            <div class="presence" ?away=${!isHome} ?leaving=${isLeaving}>
              ${isHome ? "🏠 Home" : isLeaving ? `🚶 Leaving (${Math.ceil(awayDelayRemaining / 60)}m)` : "📍 Away"}
            </div>
          </div>

          <div class="temps">
            ${currentTemp}° → ${targetTemp}°
          </div>

          <div class="mode">Mode: ${mode}</div>

          <div class="temp-control">
            <div class="temp-control-label">Temperatuur instellen</div>
            <div class="temp-control-row">
              <button class="temp-btn" @click=${() => this.adjustTemp(-0.5)}>−</button>
              <span class="temp-control-value">${this._overrideTemp}°</span>
              <button class="temp-btn" @click=${() => this.adjustTemp(0.5)}>+</button>
            </div>
          </div>

          ${isLeaving ? html`
          <div class="away-delay-row">
            <span class="away-delay-icon">🚶</span>
            <span class="away-delay-value countdown">${this.formatSeconds(awayDelayRemaining)}</span>
            <span class="away-delay-label">tot afwezig</span>
          </div>
          ` : ""}

          ${isTimer ? html`
          <div class="timer-row">
            <span class="timer-icon">⏱</span>
            <span class="timer-value countdown">${this.formatTime(remaining)}</span>
            <span class="timer-label">resterend</span>
            <button class="restore-btn" @click=${() => this.clearOverride()}>Herstel schema</button>
          </div>
          ` : ""}

          ${isInfinity ? html`
          <div class="timer-row">
            <span class="timer-icon">♾</span>
            <span class="timer-label">Infinity actief</span>
            <button class="restore-btn" @click=${() => this.clearOverride()}>Herstel schema</button>
          </div>
          ` : ""}

          ${(isTimer || isInfinity) ? html`
          <div class="panel">
            <div class="state">
              ${isTimer
                ? html`<span>Timer actief</span>`
                : html`<strong>♾ Infinity</strong>`}
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
          ` : ""}

          <div class="history-panel">
            <div class="history-label">Temperatuurgeschiedenis</div>
            ${this.renderHistoryGraph(history)}
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

  clearOverride() {
    this.hass.callService("smart_climate", "clear_override", {
      entity_id: this.config.entity,
    });
  }

  adjustTemp(delta) {
    const newTemp = Math.min(25, Math.max(5, this._overrideTemp + delta));
    this._overrideTemp = newTemp;
    this.hass.callService("climate", "set_temperature", {
      entity_id: this.config.entity,
      temperature: newTemp,
    });
  }

  formatSeconds(seconds) {
    const total = Math.max(0, seconds);
    const m = Math.floor(total / 60);
    const rem = Math.ceil(total % 60);
    return m ? `${m}m ${rem}s` : `${rem}s`;
  }

  formatTime(minutes) {
    if (minutes < 60) return `${minutes}m`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  renderHistoryGraph(history) {
    if (!history || history.length < 2) {
      return html`<div class="history-empty">Nog geen gegevens beschikbaar</div>`;
    }

    const W = 300;
    const H = 80;
    const PAD = { top: 6, right: 4, bottom: 18, left: 28 };
    const plotW = W - PAD.left - PAD.right;
    const plotH = H - PAD.top - PAD.bottom;

    const allTemps = history.flatMap(e => [e.current, e.target].filter(v => v != null));
    const minTemp = Math.min(...allTemps) - 0.5;
    const maxTemp = Math.max(...allTemps) + 0.5;
    // Prevent division by zero when all temperatures are identical
    const tempRange = maxTemp - minTemp || 1;

    const xScale = i => PAD.left + (i / (history.length - 1)) * plotW;
    const yScale = v => PAD.top + plotH - ((v - minTemp) / tempRange) * plotH;

    const currentPoints = history
      .map((e, i) => e.current != null ? `${xScale(i)},${yScale(e.current)}` : null)
      .filter(Boolean).join(" ");
    const targetPoints = history
      .map((e, i) => `${xScale(i)},${yScale(e.target)}`).join(" ");

    const firstLabel = history[0].time;
    const lastLabel = history[history.length - 1].time;
    const midIdx = Math.floor((history.length - 1) / 2);
    const midLabel = history[midIdx].time;

    const gridTemps = [
      Math.round(minTemp + 0.5),
      Math.round((minTemp + maxTemp) / 2),
      Math.round(maxTemp - 0.5),
    ].filter((v, i, a) => a.indexOf(v) === i);

    return html`
      <svg viewBox="0 0 ${W} ${H}" class="history-svg" aria-label="Temperatuurgeschiedenis">
        ${gridTemps.map(t => {
          const y = yScale(t);
          return html`
            <line x1="${PAD.left}" y1="${y}" x2="${W - PAD.right}" y2="${y}"
                  stroke="var(--divider-color)" stroke-width="0.5" stroke-dasharray="3,3"/>
            <text x="${PAD.left - 2}" y="${y + 3}" text-anchor="end" class="graph-label">${t}°</text>
          `;
        })}

        ${currentPoints ? html`
          <polyline points="${currentPoints}"
                    fill="none" stroke="var(--info-color, #2196f3)" stroke-width="1.5"
                    stroke-linejoin="round" stroke-linecap="round"/>
        ` : ""}

        <polyline points="${targetPoints}"
                  fill="none" stroke="var(--warning-color, #ff9800)" stroke-width="1.5"
                  stroke-dasharray="4,2"
                  stroke-linejoin="round" stroke-linecap="round"/>

        <text x="${xScale(0)}" y="${H - 2}" text-anchor="middle" class="graph-label">${firstLabel}</text>
        <text x="${xScale(midIdx)}" y="${H - 2}" text-anchor="middle" class="graph-label">${midLabel}</text>
        <text x="${xScale(history.length - 1)}" y="${H - 2}" text-anchor="middle" class="graph-label">${lastLabel}</text>
      </svg>
      <div class="history-legend">
        <span class="legend-current">— huidig</span>
        <span class="legend-target">- - doel</span>
      </div>
    `;
  }

  static styles = css`
    ha-card {
      background: var(--ha-card-background);
      color: var(--primary-text-color);
    }

    .content {
      padding: 10px 12px;
    }

    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 2px;
    }

    .title {
      font-size: 16px;
      font-weight: 600;
    }

    .presence {
      font-size: 11px;
      padding: 3px 6px;
      border-radius: 6px;
      background: rgba(var(--rgb-success-color, 76, 175, 80), 0.15);
      color: var(--success-color);
      transition: all 0.3s ease;
    }

    .presence[away] {
      background: rgba(var(--rgb-error-color, 244, 67, 54), 0.15);
      color: var(--error-color);
    }

    .presence[leaving] {
      background: rgba(var(--rgb-warning-color, 255, 152, 0), 0.15);
      color: var(--warning-color);
    }

    .temps {
      margin-top: 4px;
      font-size: 14px;
    }

    .mode {
      font-size: 11px;
      color: var(--secondary-text-color);
      margin-top: 2px;
    }

    .away-delay-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 10px;
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(var(--rgb-info-color, 33, 150, 243), 0.12);
      border: 1px solid rgba(var(--rgb-info-color, 33, 150, 243), 0.3);
    }

    .away-delay-icon {
      font-size: 16px;
    }

    .away-delay-value {
      font-size: 18px;
      font-weight: 700;
      color: var(--info-color);
    }

    .away-delay-label {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .timer-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 6px;
      padding: 6px 10px;
      border-radius: 8px;
      background: rgba(var(--rgb-warning-color, 255, 152, 0), 0.12);
      border: 1px solid rgba(var(--rgb-warning-color, 255, 152, 0), 0.3);
    }

    .timer-icon {
      font-size: 14px;
    }

    .timer-value {
      font-size: 15px;
      font-weight: 700;
      color: var(--warning-color);
    }

    .timer-label {
      font-size: 11px;
      color: var(--secondary-text-color);
      flex: 1;
    }

    .restore-btn {
      background: none;
      border: 1px solid var(--accent-color);
      color: var(--accent-color);
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
      cursor: pointer;
      white-space: nowrap;
    }

    .restore-btn:hover {
      background: var(--accent-color);
      color: white;
    }

    .panel {
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 10px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    .state {
      font-size: 11px;
      margin-bottom: 4px;
      min-height: 16px;
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
      margin-top: 2px;
    }

    .temp-control {
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 10px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    .temp-control-label {
      font-size: 11px;
      color: var(--secondary-text-color);
      margin-bottom: 4px;
    }

    .temp-control-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .temp-control-value {
      font-size: 20px;
      font-weight: 600;
    }

    .temp-btn {
      background: var(--accent-color);
      color: white;
      border: none;
      border-radius: 50%;
      width: 30px;
      height: 30px;
      font-size: 18px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .temp-btn:hover {
      opacity: 0.85;
    }

    .history-panel {
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 10px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    .history-label {
      font-size: 11px;
      color: var(--secondary-text-color);
      margin-bottom: 4px;
    }

    .history-svg {
      width: 100%;
      height: auto;
      display: block;
      overflow: visible;
    }

    .graph-label {
      font-size: 8px;
      fill: var(--secondary-text-color);
    }

    .history-empty {
      font-size: 11px;
      color: var(--secondary-text-color);
      text-align: center;
      padding: 12px 0;
    }

    .history-legend {
      display: flex;
      gap: 12px;
      justify-content: flex-end;
      margin-top: 2px;
    }

    .legend-current {
      font-size: 10px;
      color: var(--info-color, #2196f3);
    }

    .legend-target {
      font-size: 10px;
      color: var(--warning-color, #ff9800);
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