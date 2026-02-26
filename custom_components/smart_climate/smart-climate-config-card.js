import { LitElement, html, css } from "https://unpkg.com/lit@3/index.js?module";

class SmartClimateConfigCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
    _autoTemp: { state: true },
    _awayTemp: { state: true },
    _awayDelay: { state: true },
    _overrideMode: { state: true },
    _overrideDuration: { state: true },
    _interruptible: { state: true },
    _saved: { state: true },
  };

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Entity required");
    }
    this.config = config;
  }

  updated(changedProps) {
    if (changedProps.has("hass")) {
      this._syncFromEntity();
    }
  }

  _syncFromEntity() {
    const entity = this.hass?.states[this.config.entity];
    if (!entity) return;
    const attrs = entity.attributes;
    if (this._autoTemp === undefined) this._autoTemp = attrs.auto_temperature ?? 21;
    if (this._awayTemp === undefined) this._awayTemp = attrs.away_temperature ?? 14;
    if (this._awayDelay === undefined) this._awayDelay = attrs.away_delay_minutes ?? 5;
    if (this._overrideMode === undefined) this._overrideMode = attrs.default_override_mode ?? "timer";
    if (this._overrideDuration === undefined) this._overrideDuration = attrs.default_override_duration ?? 30;
    if (this._interruptible === undefined) this._interruptible = attrs.interruptible ?? true;
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

    const autoTemp = this._autoTemp ?? entity.attributes.auto_temperature ?? 21;
    const awayTemp = this._awayTemp ?? entity.attributes.away_temperature ?? 14;
    const awayDelay = this._awayDelay ?? entity.attributes.away_delay_minutes ?? 5;
    const overrideMode = this._overrideMode ?? entity.attributes.default_override_mode ?? "timer";
    const overrideDuration = this._overrideDuration ?? entity.attributes.default_override_duration ?? 30;
    const interruptible = this._interruptible ?? entity.attributes.interruptible ?? true;
    const wrappedClimate = entity.attributes.wrapped_climate ?? "—";
    const zoneHome = entity.attributes.zone_home ?? "—";

    return html`
      <ha-card>
        <div class="content">
          <div class="header">
            <div class="title">⚙️ SmartClimate Config</div>
          </div>

          <div class="section">
            <div class="section-title">🔗 Integration</div>

            <div class="row">
              <label>Wrapped climate</label>
              <span class="info-value">${wrappedClimate}</span>
            </div>

            <div class="row">
              <label>Zone home</label>
              <span class="info-value">${zoneHome}</span>
            </div>

            <div class="row">
              <span class="info-hint">To change these, use Settings → Integrations → Smart Climate → Configure</span>
            </div>
          </div>

          <div class="section">
            <div class="section-title">🌡️ Temperatures</div>

            <div class="row">
              <label>Auto (home)</label>
              <div class="temp-control">
                <button class="temp-btn" @click=${() => this._adjust("_autoTemp", -0.5, 5, 25)}>−</button>
                <span class="temp-value">${autoTemp}°C</span>
                <button class="temp-btn" @click=${() => this._adjust("_autoTemp", 0.5, 5, 25)}>+</button>
              </div>
            </div>

            <div class="row">
              <label>Away</label>
              <div class="temp-control">
                <button class="temp-btn" @click=${() => this._adjust("_awayTemp", -0.5, 5, 25)}>−</button>
                <span class="temp-value">${awayTemp}°C</span>
                <button class="temp-btn" @click=${() => this._adjust("_awayTemp", 0.5, 5, 25)}>+</button>
              </div>
            </div>
          </div>

          <div class="section">
            <div class="section-title">🚶 Away Delay</div>

            <div class="row">
              <label>Delay before away</label>
              <div class="temp-control">
                <button class="temp-btn" @click=${() => this._adjust("_awayDelay", -1, 0, 60)}>−</button>
                <span class="temp-value">${awayDelay} min</span>
                <button class="temp-btn" @click=${() => this._adjust("_awayDelay", 1, 0, 60)}>+</button>
              </div>
            </div>
          </div>

          <div class="section">
            <div class="section-title">⏱️ Default Override</div>

            <div class="row">
              <label>Mode</label>
              <div class="toggle-group">
                <button
                  class="toggle-btn ${overrideMode === "timer" ? "active" : ""}"
                  @click=${() => { this._overrideMode = "timer"; }}
                >Timer</button>
                <button
                  class="toggle-btn ${overrideMode === "infinity" ? "active" : ""}"
                  @click=${() => { this._overrideMode = "infinity"; }}
                >♾ Infinity</button>
              </div>
            </div>

            ${overrideMode === "timer" ? html`
            <div class="row">
              <label>Duration</label>
              <div class="temp-control">
                <button class="temp-btn" @click=${() => this._adjust("_overrideDuration", -15, 15, 480)}>−</button>
                <span class="temp-value">${this._formatDuration(overrideDuration)}</span>
                <button class="temp-btn" @click=${() => this._adjust("_overrideDuration", 15, 15, 480)}>+</button>
              </div>
            </div>
            ` : ""}
          </div>

          <div class="section">
            <div class="section-title">🔔 Interruptible</div>

            <div class="row">
              <label>Allow presence to interrupt override</label>
              <button
                class="toggle-btn ${interruptible ? "active" : ""}"
                @click=${() => { this._interruptible = !this._interruptible; }}
              >${interruptible ? "✓ Yes" : "✗ No"}</button>
            </div>
          </div>

          <div class="actions">
            <button class="save-btn" @click=${() => this._save()}>
              ${this._saved ? "✓ Saved" : "Save"}
            </button>
          </div>
        </div>
      </ha-card>
    `;
  }

  _adjust(prop, delta, min, max) {
    const current = this[prop] ?? 0;
    this[prop] = Math.min(max, Math.max(min, Math.round((current + delta) * 10) / 10));
  }

  _formatDuration(minutes) {
    if (minutes < 60) return `${minutes}m`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  async _save() {
    const entityId = this.config.entity;

    await this.hass.callService("smart_climate", "set_auto_temperature", {
      entity_id: entityId,
      temperature: this._autoTemp,
    });
    await this.hass.callService("smart_climate", "set_away_temperature", {
      entity_id: entityId,
      temperature: this._awayTemp,
    });
    await this.hass.callService("smart_climate", "set_away_delay", {
      entity_id: entityId,
      minutes: this._awayDelay,
    });
    await this.hass.callService("smart_climate", "set_default_override_mode", {
      entity_id: entityId,
      mode: this._overrideMode,
      duration: this._overrideDuration,
    });
    await this.hass.callService("smart_climate", "set_interruptible", {
      entity_id: entityId,
      interruptible: this._interruptible,
    });

    this._saved = true;
    setTimeout(() => { this._saved = false; }, 2000);
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
      align-items: center;
      margin-bottom: 8px;
    }

    .title {
      font-size: 16px;
      font-weight: 600;
    }

    .section {
      margin-bottom: 10px;
      padding: 8px 10px;
      border-radius: 10px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
    }

    .section-title {
      font-size: 11px;
      font-weight: 600;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
    }

    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 4px;
    }

    .row:last-child {
      margin-bottom: 0;
    }

    label {
      font-size: 13px;
      flex: 1;
    }

    .temp-control {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .temp-value {
      font-size: 14px;
      font-weight: 600;
      min-width: 52px;
      text-align: center;
    }

    .temp-btn {
      background: var(--accent-color);
      color: white;
      border: none;
      border-radius: 50%;
      width: 26px;
      height: 26px;
      font-size: 16px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
    }

    .temp-btn:hover {
      opacity: 0.85;
    }

    .toggle-group {
      display: flex;
      gap: 4px;
    }

    .toggle-btn {
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      padding: 3px 10px;
      font-size: 12px;
      cursor: pointer;
    }

    .toggle-btn.active {
      background: var(--accent-color);
      color: white;
      border-color: var(--accent-color);
    }

    .toggle-btn:hover {
      opacity: 0.85;
    }

    .actions {
      display: flex;
      justify-content: flex-end;
      margin-top: 6px;
    }

    .save-btn {
      background: var(--accent-color);
      color: white;
      border: none;
      border-radius: 8px;
      padding: 6px 20px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
    }

    .save-btn:hover {
      opacity: 0.85;
    }

    .info-value {
      font-size: 13px;
      color: var(--secondary-text-color);
      text-align: right;
      word-break: break-all;
    }

    .info-hint {
      font-size: 11px;
      color: var(--secondary-text-color);
      font-style: italic;
    }
  `;
}

customElements.define("smart-climate-config-card", SmartClimateConfigCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-climate-config-card",
  name: "Smart Climate Config Card",
  description: "Configure Smart Climate settings and defaults",
});
