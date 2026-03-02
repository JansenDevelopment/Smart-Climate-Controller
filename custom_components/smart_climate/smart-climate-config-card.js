import { LitElement, html, css } from "https://unpkg.com/lit@3/index.js?module";

class SmartClimateConfigCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
    _awayTemp: { state: true },
    _awayDelay: { state: true },
    _overrideMode: { state: true },
    _overrideDuration: { state: true },
    _interruptible: { state: true },
    _saved: { state: true },
    _dirty: { state: true },
  };

  static getConfigElement() {
    return document.createElement("smart-climate-config-card-editor");
  }

  static getStubConfig() {
    return { entity: "" };
  }

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
            <div class="header-actions">
              ${this._dirty ? html`<span class="unsaved-badge">● Unsaved</span>` : ""}
              ${this._saved ? html`<span class="saved-badge">✓ Saved</span>` : ""}
              <button class="save-btn ${this._dirty ? "save-btn--dirty" : ""}"
                @click=${() => this._save()} ?disabled=${!this._dirty}>
                Save
              </button>
            </div>
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
                  @click=${() => { this._overrideMode = "timer"; this._dirty = true; }}
                >Timer</button>
                <button
                  class="toggle-btn ${overrideMode === "infinity" ? "active" : ""}"
                  @click=${() => { this._overrideMode = "infinity"; this._dirty = true; }}
                >♾ Infinity</button>
                <button
                  class="toggle-btn ${overrideMode === "next_node" ? "active" : ""}"
                  @click=${() => { this._overrideMode = "next_node"; this._dirty = true; }}
                >📅 Next node</button>
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
                @click=${() => { this._interruptible = !this._interruptible; this._dirty = true; }}
              >${interruptible ? "✓ Yes" : "✗ No"}</button>
            </div>
          </div>

        </div>
      </ha-card>
    `;
  }

  _adjust(prop, delta, min, max) {
    const current = this[prop] ?? 0;
    this[prop] = Math.min(max, Math.max(min, Math.round((current + delta) * 10) / 10));
    this._dirty = true;
  }

  _formatDuration(minutes) {
    if (minutes < 60) return `${minutes}m`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  async _save() {
    const entityId = this.config.entity;

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

    this._dirty = false;
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
      justify-content: space-between;
      margin-bottom: 8px;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .title {
      font-size: 16px;
      font-weight: 600;
    }

    .unsaved-badge {
      font-size: 11px;
      color: #ff9800;
      font-weight: 600;
    }

    .saved-badge {
      font-size: 11px;
      color: var(--success-color);
      background: rgba(76, 175, 80, 0.15);
      padding: 2px 8px;
      border-radius: 8px;
    }

    .save-btn {
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      padding: 4px 14px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s, border-color 0.2s, color 0.2s;
    }

    .save-btn:disabled {
      opacity: 0.4;
      cursor: default;
    }

    .save-btn--dirty {
      background: var(--accent-color, #f5a623);
      color: white;
      border-color: var(--accent-color, #f5a623);
      animation: pulse-save 1.2s ease-in-out infinite;
    }

    @keyframes pulse-save {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.75; }
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

class SmartClimateConfigCardEditor extends LitElement {
  static properties = {
    hass: {},
    config: {},
  };

  setConfig(config) {
    this.config = config;
  }

  render() {
    return html`
      <div class="card-config">
        <ha-entity-picker
          label="Entity"
          .hass=${this.hass}
          .value=${this.config?.entity ?? ""}
          .includeDomains=${["climate"]}
          @value-changed=${this._entityChanged}
          allow-custom-entity
        ></ha-entity-picker>
      </div>
    `;
  }

  _entityChanged(e) {
    if (e.detail.value === this.config?.entity) return;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: { ...this.config, entity: e.detail.value } },
        bubbles: true,
        composed: true,
      })
    );
  }

  static styles = css`
    .card-config {
      padding: 16px;
    }
    ha-entity-picker {
      width: 100%;
    }
  `;
}

customElements.define("smart-climate-config-card-editor", SmartClimateConfigCardEditor);

customElements.define("smart-climate-config-card", SmartClimateConfigCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-climate-config-card",
  name: "Smart Climate Config Card",
  description: "Configure Smart Climate settings and defaults",
});
