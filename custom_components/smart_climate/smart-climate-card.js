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
    const remainingMinutes = attrs.remaining_minutes ?? 0;
    const isTimer = mode === "override_timer";
    const isInfinity = mode === "override_infinity";
    const isOverride = isTimer || isInfinity;

    const sliderValue = isTimer ? remainingMinutes : isInfinity ? 481 : 0;

    this.innerHTML = `
      <ha-card>
        <div style="padding:16px">
          <div style="font-size:20px;font-weight:bold">SmartClimate</div>
          <div style="margin-top:8px">${currentTemp}° → ${targetTemp}°</div>
          <div style="font-size:12px;color:#888;margin-top:8px">Mode: ${mode}</div>

          ${isOverride ? `
            <div style="background:#FFF3E0;padding:12px;border-radius:8px;margin-top:12px">
              <div style="font-size:12px;margin-bottom:8px">${isTimer ? `Remaining: <strong>${this.formatTime(remainingMinutes)}</strong>` : `<strong>♾️ Infinity</strong>`}</div>
              <input type="range" id="slider" min="0" max="480" step="15" value="${sliderValue}" style="width:100%;margin-bottom:8px">
              <div style="display:flex;gap:8px;font-size:10px;justify-content:space-between">
                <span>Auto</span><span>2h</span><span>4h</span><span>8h</span><span>∞</span>
              </div>
            </div>
          ` : `
            <div style="margin-top:12px">
              <input type="range" id="slider" min="0" max="480" step="15" value="0" style="width:100%;margin-bottom:8px">
              <div style="display:flex;gap:8px;font-size:10px;justify-content:space-between">
                <span>Auto</span><span>2h</span><span>4h</span><span>8h</span><span>∞</span>
              </div>
            </div>
          `}
        </div>
      </ha-card>
    `;

    const slider = this.querySelector("#slider");
    if (slider) {
      slider.addEventListener("change", (e) => {
        const value = parseInt(e.target.value);
        if (value === 0) {
          hass.callService("smart_climate", "clear_override", { entity_id: entityId });
        } else if (value >= 481) {
          hass.callService("smart_climate", "set_override_infinity", { entity_id: entityId, temperature: 22 });
        } else {
          hass.callService("smart_climate", "set_override_timer", { entity_id: entityId, minutes: value, temperature: 22 });
        }
      });
    }
  }

  formatTime(minutes) {
    if (minutes === 0) return "0m";
    if (minutes >= 60) {
      const h = Math.floor(minutes / 60);
      const m = minutes % 60;
      return m > 0 ? `${h}h ${m}m` : `${h}h`;
    }
    return `${minutes}m`;
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