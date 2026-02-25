class SmartClimateCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
  }

  set hass(hass) {
    this.hass = hass;
    this.render();
  }

  getCardSize() {
    return 4;
  }

  render() {
    if (!this.hass || !this.config) {
      this.innerHTML = `<ha-card><div style="padding: 16px;">Loading...</div></ha-card>`;
      return;
    }

    const entityId = this.config.entity;
    if (!entityId) {
      this.innerHTML = `<ha-card><div style="padding: 16px;">⚠️ Please set entity</div></ha-card>`;
      return;
    }

    const state = this.hass.states[entityId];
    if (!state) {
      this.innerHTML = `<ha-card><div style="padding: 16px;">⚠️ Entity ${entityId} not found</div></ha-card>`;
      return;
    }

    const attrs = state.attributes;
    const mode = attrs.mode || "auto";
    const presence = attrs.presence || "away";
    const remainingMinutes = attrs.remaining_minutes || 0;
    const overrideTemp = attrs.override_temperature || 21;
    const currentTemp = attrs.current_temperature || "—";
    const targetTemp = attrs.temperature || 21;

    const presenceColor = presence === "home" ? "#4CAF50" : "#ff9800";
    const presenceIcon = presence === "home" ? "🏠" : "📍";
    const presenceLabel = presence === "home" ? "Thuis" : "Afwezig";

    const modeAuto = mode === "auto";
    const modeTimer = mode === "override_timer";
    const modeInfinity = mode === "override_infinity";
    const sliderValue = modeTimer ? remainingMinutes : modeInfinity ? 121 : 0;

    const html = `
      <ha-card>
        <div style="padding: 16px;">
          <div style="font-size: 20px; font-weight: bold; margin-bottom: 12px;">SmartClimate</div>
          
          <div style="background: #f5f5f5; padding: 12px; border-radius: 8px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between;">
              <div><div style="font-size: 10px; color: #888;">Huida</div><div style="font-size: 18px; font-weight: bold;">${currentTemp}°C</div></div>
              <div style="text-align: right;"><div style="font-size: 10px; color: #888;">Doel</div><div style="font-size: 18px; font-weight: bold;">${targetTemp}°C</div></div>
            </div>
          </div>

          <div style="padding: 8px 12px; background: ${presenceColor}22; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid ${presenceColor};">
            ${presenceIcon} <strong style="color: ${presenceColor};">${presenceLabel}</strong>
          </div>

          <div style="display: flex; gap: 8px; margin-bottom: 12px;">
            <button id="btn-auto" style="flex: 1; padding: 8px; border: 2px solid ${modeAuto ? '#4CAF50' : '#ddd'}; background: ${modeAuto ? '#4CAF5022' : 'white'}; border-radius: 4px; cursor: pointer; font-weight: bold;">Auto</button>
            <button id="btn-manual" style="flex: 1; padding: 8px; border: 2px solid ${modeTimer || modeInfinity ? '#FF9800' : '#ddd'}; background: ${modeTimer || modeInfinity ? '#FF980022' : 'white'}; border-radius: 4px; cursor: pointer; font-weight: bold;">Manual</button>
          </div>

          ${modeTimer || modeInfinity ? `
            <div style="background: #FFF3E0; padding: 12px; border-radius: 8px; margin-bottom: 12px;">
              <div style="font-size: 12px; margin-bottom: 8px;">Override: <strong>${overrideTemp}°C</strong></div>
              <div style="text-align: center; font-size: 16px; color: #FF9800; font-weight: bold; margin-bottom: 8px;">${modeTimer ? this.formatTime(remainingMinutes) : '♾️'}</div>
              <input type="range" id="slider" min="0" max="121" value="${sliderValue}" style="width: 100%; margin-bottom: 8px;">
              <button id="btn-cancel" style="width: 100%; padding: 8px; background: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">Annuleer</button>
            </div>
          ` : ''}

          <div style="font-size: 9px; color: #aaa; padding-top: 12px; border-top: 1px solid #eee;">Mode: ${mode} | Presence: ${presence}</div>
        </div>
      </ha-card>
    `;

    this.innerHTML = html;
    this.attachListeners(entityId);
  }

  formatTime(minutes) {
    if (minutes === 0) return "0m";
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
  }

  attachListeners(entityId) {
    const btnAuto = this.querySelector("#btn-auto");
    const btnCancel = this.querySelector("#btn-cancel");
    const slider = this.querySelector("#slider");

    if (btnAuto) {
      btnAuto.addEventListener("click", () => {
        this.hass.callService("smart_climate", "clear_override", { entity_id: entityId });
      });
    }

    if (btnCancel) {
      btnCancel.addEventListener("click", () => {
        this.hass.callService("smart_climate", "clear_override", { entity_id: entityId });
      });
    }

    if (slider) {
      slider.addEventListener("change", (e) => {
        const value = parseInt(e.target.value);
        if (value === 0) {
          this.hass.callService("smart_climate", "clear_override", { entity_id: entityId });
        } else if (value === 121) {
          this.hass.callService("smart_climate", "set_override_infinity", { entity_id: entityId, temperature: 22 });
        } else {
          this.hass.callService("smart_climate", "set_override_timer", { entity_id: entityId, minutes: value, temperature: 22 });
        }
      });
    }
  }
}

customElements.define("smart-climate-card", SmartClimateCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-climate-card",
  name: "Smart Climate Card",
  description: "Smart climate controller",
});
