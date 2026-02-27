import { LitElement, html, css, svg } from "https://unpkg.com/lit@3/index.js?module";

// SVG graph layout constants (viewBox units)
const GL = 52;   // graph left x
const GR = 582;  // graph right x
const GT = 22;   // graph top y
const GB = 262;  // graph bottom y
const TMIN = 5;  // min temperature °C
const TMAX = 30; // max temperature °C
const VW = 600;  // viewBox width
const VH = 292;  // viewBox height
const NR = 8;    // node radius

class SmartClimateScheduleCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
    _scheduleMode: { state: true },
    _activeDay: { state: true },
    _schedule: { state: true },
    _draggingIdx: { state: true },
    _history: { state: true },
    _saved: { state: true },
  };

  setConfig(config) {
    if (!config.entity) throw new Error("Entity required");
    this.config = config;
  }

  updated(changedProps) {
    if (changedProps.has("hass") && this.hass) {
      if (this._schedule === undefined) this._syncFromEntity();
      if (this._history === undefined) this._fetchHistory();
    }
  }

  _syncFromEntity() {
    const entity = this.hass?.states[this.config.entity];
    if (!entity) return;
    const raw = entity.attributes.schedule;
    if (raw) {
      this._schedule = raw;
      this._scheduleMode = raw.mode || "daily";
    } else {
      this._scheduleMode = "daily";
      this._schedule = {
        mode: "daily",
        daily: [{ time: "07:00", temp: 21 }, { time: "22:00", temp: 18 }],
      };
    }
    this._activeDay =
      this._scheduleMode === "5/2" ? "weekday"
      : this._scheduleMode === "individual" ? "monday"
      : "daily";
  }

  async _fetchHistory() {
    this._history = [];
    const entity = this.hass?.states[this.config.entity];
    if (!entity) return;
    const wrapped = entity.attributes.wrapped_climate;
    if (!wrapped) return;
    try {
      const start = new Date();
      start.setHours(0, 0, 0, 0);
      const result = await this.hass.callApi(
        "GET",
        `history/period/${start.toISOString()}?filter_entity_id=${wrapped}&minimal_response=true`
      );
      this._history = result?.[0] ?? [];
    } catch (err) {
      console.warn("SmartClimateScheduleCard: failed to fetch history", err);
      this._history = [];
    }
  }

  _getNodes() {
    const key = this._activeDay ?? "daily";
    return (this._schedule ?? {})[key] ?? [];
  }

  _setNodes(nodes) {
    const key = this._activeDay ?? "daily";
    this._schedule = { ...(this._schedule ?? {}), [key]: nodes };
  }

  _toX(h) { return GL + (h / 24) * (GR - GL); }
  _toY(t) { return GB - ((t - TMIN) / (TMAX - TMIN)) * (GB - GT); }
  _fromX(x) { return Math.max(0, Math.min(24, (x - GL) / (GR - GL) * 24)); }
  _fromY(y) {
    const t = TMIN + (GB - y) / (GB - GT) * (TMAX - TMIN);
    return Math.max(TMIN, Math.min(TMAX, Math.round(t * 2) / 2));
  }

  _timeToHour(s) {
    if (!s) return 0;
    const [h, m] = s.split(":").map(Number);
    return h + (m || 0) / 60;
  }

  _hourToTime(h) {
    const hh = Math.floor(h);
    const mm = Math.round((h - hh) * 60);
    return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
  }

  _svgCoords(e) {
    const el = this.shadowRoot?.querySelector("svg.graph");
    if (!el) return { x: 0, y: 0 };
    const pt = el.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    return pt.matrixTransform(el.getScreenCTM().inverse());
  }

  _onNodePointerDown(e, idx) {
    e.stopPropagation();
    e.preventDefault();
    this._draggingIdx = idx;
    const svgEl = this.shadowRoot?.querySelector("svg.graph");
    if (svgEl) svgEl.setPointerCapture(e.pointerId);
  }

  _onSvgPointerMove(e) {
    if (this._draggingIdx == null) return;
    const { x, y } = this._svgCoords(e);
    const nodes = this._getNodes().map((n, i) =>
      i === this._draggingIdx
        ? { time: this._hourToTime(this._fromX(x)), temp: this._fromY(y) }
        : n
    );
    this._setNodes(nodes);
  }

  _onSvgPointerUp(e) {
    if (this._draggingIdx != null) {
      try {
        e.target.releasePointerCapture?.(e.pointerId);
      } catch {}
      const nodes = [...this._getNodes()].sort(
        (a, b) => this._timeToHour(a.time) - this._timeToHour(b.time)
      );
      this._setNodes(nodes);
      this._draggingIdx = null;
      this._saveSchedule();
    }
  }

  _onSvgClick(e) {
    if (e.target.tagName === "circle" && e.target.classList.contains("node-c")) return;
    const { x, y } = this._svgCoords(e);
    if (x < GL || x > GR || y < GT || y > GB) return;
    const nodes = [
      ...this._getNodes(),
      { time: this._hourToTime(this._fromX(x)), temp: this._fromY(y) },
    ].sort((a, b) => this._timeToHour(a.time) - this._timeToHour(b.time));
    this._setNodes(nodes);
    this._saveSchedule();
  }

  _removeNode(e, idx) {
    e.stopPropagation();
    const nodes = this._getNodes().filter((_, i) => i !== idx);
    this._setNodes(nodes);
    this._saveSchedule();
  }

  async _saveSchedule() {
    if (!this.hass) return;
    try {
      await this.hass.callService("smart_climate", "set_schedule", {
        entity_id: this.config.entity,
        schedule: { ...(this._schedule ?? {}), mode: this._scheduleMode ?? "daily" },
      });
      this._saved = true;
      setTimeout(() => { this._saved = false; }, 1500);
    } catch (err) {
      console.error("SmartClimateScheduleCard: failed to save schedule", err);
    }
  }

  _setMode(m) {
    this._scheduleMode = m;
    this._schedule = { ...(this._schedule ?? {}), mode: m };
    this._activeDay =
      m === "5/2" ? "weekday"
      : m === "individual" ? "monday"
      : "daily";
  }

  _stepPath(nodes) {
    if (!nodes?.length) return "";
    const s = [...nodes].sort((a, b) => this._timeToHour(a.time) - this._timeToHour(b.time));
    const lastT = s[s.length - 1].temp;
    const d = [`M${this._toX(0)},${this._toY(lastT)}`];
    for (let i = 0; i < s.length; i++) {
      const h = this._timeToHour(s[i].time);
      const prevT = i === 0 ? lastT : s[i - 1].temp;
      d.push(`L${this._toX(h)},${this._toY(prevT)}`);
      d.push(`L${this._toX(h)},${this._toY(s[i].temp)}`);
    }
    d.push(`L${this._toX(24)},${this._toY(s[s.length - 1].temp)}`);
    return d.join(" ");
  }

  _historyPath() {
    const hist = this._history;
    if (!hist?.length) return "";
    const base = new Date();
    base.setHours(0, 0, 0, 0);
    const baseMs = base.getTime();
    const pts = [];
    for (const h of hist) {
      const t = parseFloat(h.state);
      if (isNaN(t)) continue;
      const hr = (new Date(h.last_changed ?? h.last_updated).getTime() - baseMs) / 3600000;
      if (hr < 0 || hr > 24) continue;
      const x = this._toX(hr);
      const y = this._toY(Math.max(TMIN, Math.min(TMAX, t)));
      pts.push(pts.length ? `L${x},${y}` : `M${x},${y}`);
    }
    return pts.join(" ");
  }

  render() {
    if (!this.hass) return html``;
    const entity = this.hass.states[this.config.entity];
    if (!entity) return html`<ha-card><div class="content">Entity not found</div></ha-card>`;
    if (this._schedule === undefined) return html`<ha-card><div class="content">Loading…</div></ha-card>`;

    const schedMode = this._scheduleMode ?? "daily";
    const activeDay = this._activeDay ?? "daily";
    const nodes = this._getNodes();

    const now = new Date();
    const nowH = now.getHours() + now.getMinutes() / 60;
    const nowX = this._toX(nowH);
    const nowLabel = this._hourToTime(nowH);

    const yTicks = [5, 10, 15, 20, 25, 30];
    const xTicks = Array.from({ length: 24 }, (_, i) => i);

    const dayTabs =
      schedMode === "5/2" ? ["weekday", "weekend"]
      : schedMode === "individual"
        ? ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
      : [];

    const dayLabel = {
      weekday: "Weekday", weekend: "Weekend",
      monday: "Mon", tuesday: "Tue", wednesday: "Wed",
      thursday: "Thu", friday: "Fri", saturday: "Sat", sunday: "Sun",
    };

    const stepPathD = this._stepPath(nodes);
    const histPathD = this._historyPath();
    const sortedNodes = [...nodes].sort((a, b) => this._timeToHour(a.time) - this._timeToHour(b.time));

    return html`
      <ha-card>
        <div class="content">
          <div class="header">
            <div class="title">
              📅 Schedule${activeDay !== "daily" ? ` (${dayLabel[activeDay] ?? activeDay})` : ""}
            </div>
            ${this._saved ? html`<span class="saved-badge">✓ Saved</span>` : ""}
          </div>

          <div class="mode-row">
            ${["daily", "5/2", "individual"].map(m => html`
              <label class="mode-label">
                <input type="radio" name="sc-mode-${this.config.entity}" .value=${m}
                  ?checked=${schedMode === m}
                  @change=${() => this._setMode(m)} />
                ${m === "daily" ? "All Days" : m === "5/2" ? "5/2 (Weekday/Weekend)" : "Individual Days"}
              </label>
            `)}
          </div>

          ${dayTabs.length ? html`
            <div class="day-tabs">
              ${dayTabs.map(d => html`
                <button class="day-tab ${activeDay === d ? "active" : ""}"
                  @click=${() => { this._activeDay = d; }}>
                  ${dayLabel[d] ?? d}
                </button>
              `)}
            </div>
          ` : ""}

          <div class="graph-wrap">
            <svg class="graph" viewBox="0 0 ${VW} ${VH}" preserveAspectRatio="xMidYMid meet"
              @click=${this._onSvgClick}
              @pointermove=${this._onSvgPointerMove}
              @pointerup=${this._onSvgPointerUp}
              @pointercancel=${this._onSvgPointerUp}
            >
              <!-- graph background -->
              <rect x="${GL}" y="${GT}" width="${GR - GL}" height="${GB - GT}"
                fill="rgba(0,0,0,0.25)" rx="3"/>

              <!-- y grid lines + labels -->
              ${yTicks.map(t => {
                const gy = this._toY(t);
                return svg`
                  <line x1="${GL}" y1="${gy}" x2="${GR}" y2="${gy}"
                    stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                  <text x="${GL - 5}" y="${gy + 4}" text-anchor="end" class="ax">${t}°</text>
                `;
              })}

              <!-- x grid lines + labels -->
              ${xTicks.map(h => {
                const gx = this._toX(h);
                return svg`
                  <line x1="${gx}" y1="${GT}" x2="${gx}" y2="${GB}"
                    stroke="rgba(255,255,255,0.07)" stroke-width="1"/>
                  <circle cx="${gx}" cy="${GB + 3}" r="1.5" fill="rgba(255,255,255,0.3)"/>
                  <text x="${gx}" y="${GB + 15}" text-anchor="middle" class="ax">${h}</text>
                `;
              })}

              <!-- y axis title -->
              <text transform="rotate(-90,12,${(GT + GB) / 2})"
                x="12" y="${(GT + GB) / 2}"
                text-anchor="middle" class="ax-title">Temperature (°C)</text>

              <!-- x axis title -->
              <text x="${(GL + GR) / 2}" y="${VH - 1}"
                text-anchor="middle" class="ax-title">Time (24 hours)</text>

              <!-- history background path -->
              ${histPathD ? svg`
                <path d="${histPathD}" fill="none"
                  stroke="rgba(255,160,50,0.45)" stroke-width="1.5" stroke-linejoin="round"/>
              ` : ""}

              <!-- schedule step path -->
              ${stepPathD ? svg`
                <path d="${stepPathD}" fill="none"
                  stroke="var(--accent-color, #f5a623)" stroke-width="2.5" stroke-linejoin="round"/>
              ` : ""}

              <!-- current time marker -->
              <line x1="${nowX}" y1="${GT}" x2="${nowX}" y2="${GB}"
                stroke="#4caf50" stroke-width="1.5" stroke-dasharray="5,4"/>
              <text x="${nowX + 4}" y="${GT + 13}" class="now-label">${nowLabel}</text>

              <!-- schedule nodes -->
              ${sortedNodes.map((node, idx) => {
                const cx = this._toX(this._timeToHour(node.time));
                const cy = this._toY(node.temp);
                const lblY = cy - NR - 3;
                const timeY = cy + NR + 11;
                return svg`
                  <g class="node-g">
                    <circle class="node-c" cx="${cx}" cy="${cy}" r="${NR}"
                      @pointerdown=${(e) => this._onNodePointerDown(e, idx)}
                      @dblclick=${(e) => this._removeNode(e, idx)}
                    />
                    <text x="${cx}" y="${lblY}" text-anchor="middle" class="node-lbl">${node.temp}°C</text>
                    <text x="${cx}" y="${timeY}" text-anchor="middle" class="node-time">${node.time}</text>
                  </g>
                `;
              })}
            </svg>
          </div>

          <div class="hint">Click graph to add node • Drag to move • Double-click to remove</div>
        </div>
      </ha-card>
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
      margin-bottom: 8px;
    }

    .title {
      font-size: 16px;
      font-weight: 600;
    }

    .saved-badge {
      font-size: 11px;
      color: var(--success-color);
      background: rgba(76, 175, 80, 0.15);
      padding: 2px 8px;
      border-radius: 8px;
    }

    .mode-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 8px;
    }

    .mode-label {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      cursor: pointer;
    }

    .day-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-bottom: 8px;
    }

    .day-tab {
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      padding: 3px 10px;
      font-size: 12px;
      cursor: pointer;
    }

    .day-tab.active {
      background: var(--accent-color);
      color: white;
      border-color: var(--accent-color);
    }

    .day-tab:hover {
      opacity: 0.85;
    }

    .graph-wrap {
      width: 100%;
      overflow: hidden;
    }

    svg.graph {
      width: 100%;
      height: auto;
      display: block;
      cursor: crosshair;
      user-select: none;
      touch-action: none;
    }

    .ax {
      font-size: 9px;
      fill: var(--secondary-text-color, #888);
      font-family: sans-serif;
    }

    .ax-title {
      font-size: 9px;
      fill: var(--secondary-text-color, #888);
      font-family: sans-serif;
    }

    .now-label {
      font-size: 10px;
      fill: #4caf50;
      font-weight: 700;
      font-family: sans-serif;
    }

    .node-c {
      fill: #4fc3f7;
      stroke: white;
      stroke-width: 2;
      cursor: grab;
    }

    .node-c:active {
      cursor: grabbing;
    }

    .node-lbl {
      font-size: 9px;
      fill: white;
      font-weight: 700;
      font-family: sans-serif;
      pointer-events: none;
    }

    .node-time {
      font-size: 8px;
      fill: rgba(255, 255, 255, 0.7);
      font-family: sans-serif;
      pointer-events: none;
    }

    .hint {
      font-size: 10px;
      color: var(--secondary-text-color);
      margin-top: 4px;
      text-align: center;
    }
  `;
}

customElements.define("smart-climate-schedule-card", SmartClimateScheduleCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-climate-schedule-card",
  name: "Smart Climate Schedule Card",
  description: "Interactive temperature schedule graph with drag-and-drop nodes",
  preview: true,
});
