import { LitElement, html, css } from "https://unpkg.com/lit@3/index.js?module";

/**
 * Base editor class shared by all three SmartClimate card editors.
 *
 * Renders a single `ha-entity-picker` restricted to the `climate` domain and
 * dispatches a standard `config-changed` event whenever the user selects a
 * different entity. All three card editors are identical in behaviour, so they
 * extend this class instead of repeating the same boilerplate.
 */
class SmartClimateBaseEditor extends LitElement {
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

  /**
   * Fires `config-changed` when the user picks a different entity.
   * @param {CustomEvent} e
   */
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

export { SmartClimateBaseEditor };
