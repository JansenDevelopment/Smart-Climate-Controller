import { LitElement, html, css } from "https://unpkg.com/lit@3/index.js?module";

/**
 * Base editor class shared by all three SmartClimate card editors.
 *
 * Renders a `ha-form` driven by a schema. Subclasses can override `_schema`
 * to append card-specific fields after the required entity picker row.
 * A standard `config-changed` event is dispatched on every change.
 */
class SmartClimateBaseEditor extends LitElement {
  static properties = {
    hass: {},
    config: {},
  };

  setConfig(config) {
    this.config = config;
  }

  /**
   * Base schema: just the entity selector. Subclasses extend this array.
   * @returns {Array}
   */
  get _schema() {
    return [
      {
        name: "entity",
        required: true,
        selector: { entity: { domain: "climate" } },
      },
    ];
  }

  render() {
    return html`
      <div class="card-config">
        <ha-form
          .hass=${this.hass}
          .data=${this.config ?? {}}
          .schema=${this._schema}
          .computeLabel=${this._computeLabel}
          @value-changed=${this._valueChanged}
        ></ha-form>
      </div>
    `;
  }

  /**
   * Provides human-readable labels for schema fields.
   * @param {Object} schema
   * @returns {string}
   */
  _computeLabel(schema) {
    const labels = {
      entity: "Entity",
      show_temperature_control: "Show temperature control",
      show_presence: "Show presence badge",
      tap_action: "Tap action",
      hold_action: "Hold action",
      double_tap_action: "Double-tap action",
    };
    return labels[schema.name] ?? schema.name;
  }

  /**
   * Fires `config-changed` whenever any field in the form changes.
   * @param {CustomEvent} e
   */
  _valueChanged(e) {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: e.detail.value },
        bubbles: true,
        composed: true,
      })
    );
  }

  static styles = css`
    .card-config {
      padding: 16px;
    }
    ha-form {
      display: block;
    }
  `;
}

export { SmartClimateBaseEditor };
