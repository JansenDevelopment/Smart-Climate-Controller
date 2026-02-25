class SmartClimateCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  render() {
    const hass = this._hass;
    const entityId = this.config?.entity;
    if (!hass || !entityId) return;

    const state = hass.states[entityId];
    if (!state) {
      this.innerHTML = `<ha-card><div style="padding:16px">Entity not found</div></ha-card>`;
      return;
    }

    const attrs = state.attributes;
    const currentTemp = attrs.current_temperature ?? "—";
    const targetTemp = attrs.temperature ?? 21;
    const mode = attrs.mode ?? "auto";

    this.innerHTML = `
      <ha-card>
        <div style="padding:16px">
          <div style="font-size:20px;font-weight:bold">SmartClimate</div>
          <div style="margin-top:8px">${currentTemp}° → ${targetTemp}°</div>
          <div style="font-size:12px;color:#888;margin-top:8px">Mode: ${mode}</div>
        </div>
      </ha-card>
    `;
  }
}

if (!customElements.get("smart-climate-card")) {
  customElements.define("smart-climate-card", SmartClimateCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-climate-card",
  name: "Smart Climate Card",
  description: "Clean base card",
});