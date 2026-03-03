import { LitElement, html, css, svg } from "https://unpkg.com/lit@3/index.js?module";
import { SmartClimateBaseEditor } from "./smart-climate-base-editor.js";

// SVG graph layout constants (viewBox units)
const GL = 52;   // graph left x
const GR = 582;  // graph right x
const GT = 22;   // graph top y
const GB = 262;  // graph bottom y
const PBAR_H = 8;              // presence bar height (SVG units)
const PBAR_Y = GB - PBAR_H;   // presence bar top y (inside graph area)
const TMIN = 5;  // min temperature °C
const TMAX = 30; // max temperature °C
const VW = 600;  // viewBox width
const VH = 292;  // viewBox height
const NR = 8;    // node radius
const MIN_NODE_DISTANCE_HOURS = 0.25; // minimum 15 minutes between nodes
// Friendly-name suffix used to identify a presence sensor when the derived ID
// (sensor.<name>_presence) is not found in hass.states.
const PRESENCE_FRIENDLY_NAME_SUFFIX = " Presence";

class SmartClimateScheduleCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
    _scheduleMode: { state: true },
    _activeDay: { state: true },
    _schedule: { state: true },
    _draggingIdx: { state: true },
    _history: { state: true },
    _yesterdayHistory: { state: true },
    _presenceHistory: { state: true },
    _saved: { state: true },
    _dirty: { state: true },
    _selectedIdx: { state: true },
  };

  static getConfigElement() {
    return document.createElement("smart-climate-schedule-card-editor");
  }

  static getStubConfig() {
    return { entity: "" };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Entity required");
    this.config = config;
  }

  updated(changedProps) {
    if (changedProps.has("hass") && this.hass) {
      if (this._schedule === undefined) this._syncFromEntity();
      if (this._history === undefined) this._fetchHistory();
      if (this._yesterdayHistory === undefined) this._fetchYesterdayHistory();
      if (this._presenceHistory === undefined) this._fetchPresenceHistory();
    }
  }

  // ── Component lifecycle / state ──────────────────────────────────────────

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
        `history/period/${start.toISOString()}?filter_entity_id=${wrapped}&significant_changes_only=true`
      );
      this._history = result?.[0] ?? [];
    } catch (err) {
      console.warn("SmartClimateScheduleCard: failed to fetch history", err);
      this._history = [];
    }
  }

  async _fetchYesterdayHistory() {
    this._yesterdayHistory = [];
    const entity = this.hass?.states[this.config.entity];
    if (!entity) return;
    const wrapped = entity.attributes.wrapped_climate;
    if (!wrapped) return;
    try {
      const end = new Date();
      end.setHours(0, 0, 0, 0);
      const start = new Date(end.getTime() - 86400000);
      const result = await this.hass.callApi(
        "GET",
        `history/period/${start.toISOString()}?filter_entity_id=${wrapped}&end_time=${end.toISOString()}&significant_changes_only=true`
      );
      this._yesterdayHistory = result?.[0] ?? [];
    } catch (err) {
      console.warn("SmartClimateScheduleCard: failed to fetch yesterday's history", err);
      this._yesterdayHistory = [];
    }
  }

  async _fetchPresenceHistory() {
    this._presenceHistory = [];
    const entity = this.hass?.states[this.config.entity];
    if (!entity) return;
    // Derive the presence sensor entity_id from the climate entity_id.
    // Convention: climate.my_room → sensor.my_room_presence.
    // NOTE: If the user renamed the sensor in HA's entity registry, the
    // derived ID will not exist. As a fallback we scan hass.states for a
    // sensor whose friendly name ends with PRESENCE_FRIENDLY_NAME_SUFFIX and
    // whose entity ID starts with "sensor." – this makes the lookup more
    // resilient to renames. The resolved ID is cached on the instance to avoid
    // repeated full-state scans on subsequent calls.
    if (!this._resolvedPresenceId) {
      const derivedId = this.config.entity.replace(/^climate\./, "sensor.") + "_presence";
      if (this.hass.states[derivedId]) {
        this._resolvedPresenceId = derivedId;
      } else {
        // Fallback: scan states for a sensor whose friendly name ends with the known suffix.
        const candidate = Object.keys(this.hass.states).find(id => {
          if (!id.startsWith("sensor.")) return false;
          const friendlyName = this.hass.states[id].attributes?.friendly_name ?? "";
          return friendlyName.endsWith(PRESENCE_FRIENDLY_NAME_SUFFIX);
        });
        this._resolvedPresenceId = candidate ?? null;
      }
    }

    if (!this._resolvedPresenceId) return;
    try {
      const start = new Date();
      start.setHours(0, 0, 0, 0);
      const result = await this.hass.callApi(
        "GET",
        `history/period/${start.toISOString()}?filter_entity_id=${this._resolvedPresenceId}&significant_changes_only=true`
      );
      this._presenceHistory = result?.[0] ?? [];
    } catch (err) {
      console.warn("SmartClimateScheduleCard: failed to fetch presence history", err);
      this._presenceHistory = [];
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

  _onNodePointerDown(e, idx) {
    e.stopPropagation();
    // Do NOT call e.preventDefault() here — it suppresses click/dblclick synthesis
    this._draggingIdx = idx;
    this._dragStartX = e.clientX;
    this._dragStartY = e.clientY;
    this._dragMoved = false;
    const svgEl = this.shadowRoot?.querySelector("svg.graph");
    if (svgEl) svgEl.setPointerCapture(e.pointerId);
  }

  _onSvgPointerMove(e) {
    if (this._draggingIdx == null) return;
    const dx = e.clientX - this._dragStartX;
    const dy = e.clientY - this._dragStartY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) this._dragMoved = true;
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
      if (this._dragMoved) {
        // Actual drag — mark as dirty, clear selection
        this._dirty = true;
        this._selectedIdx = null;
      } else {
        // Single click on node — select it for editing
        this._selectedIdx = this._draggingIdx;
      }
      this._draggingIdx = null;
      this._dragMoved = false;
    }
  }

  _onSvgClick(e) {
    if (e.target.tagName === "circle" && e.target.classList.contains("node-c")) return;
    this._selectedIdx = null;
  }

  _onSvgDblClick(e) {
    if (e.target.tagName === "circle" && e.target.classList.contains("node-c")) return;
    const { x, y } = this._svgCoords(e);
    if (x < GL || x > GR || y < GT || y > GB) return;
    const newHour = this._fromX(x);
    const nodes = this._getNodes();
    // Require at least 15 minutes distance from any existing node (check both direct and midnight wraparound)
    const tooClose = nodes.some(n => {
      const diff = Math.abs(this._timeToHour(n.time) - newHour);
      return Math.min(diff, 24 - diff) < MIN_NODE_DISTANCE_HOURS;
    });
    if (tooClose) return;
    const newNodes = [
      ...nodes,
      { time: this._hourToTime(newHour), temp: this._fromY(y) },
    ].sort((a, b) => this._timeToHour(a.time) - this._timeToHour(b.time));
    this._setNodes(newNodes);
    this._selectedIdx = null;
    this._dirty = true;
  }

  _removeNode(e, idx) {
    if (e) e.stopPropagation();
    const nodes = this._getNodes().filter((_, i) => i !== idx);
    this._setNodes(nodes);
    this._selectedIdx = null;
    this._dirty = true;
  }

  async _saveSchedule() {
    if (!this.hass) return;
    try {
      await this.hass.callService("smart_climate", "set_schedule", {
        entity_id: this.config.entity,
        schedule: { ...(this._schedule ?? {}), mode: this._scheduleMode ?? "daily" },
      });
      this._dirty = false;
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
    this._selectedIdx = null;
    this._dirty = true;
  }

  _editNodeTime(idx, newTime) {
    const currentNodes = this._getNodes();
    const nodeTemp = currentNodes[idx]?.temp;
    const nodes = currentNodes.map((n, i) => i === idx ? { ...n, time: newTime } : n);
    const sorted = [...nodes].sort((a, b) => this._timeToHour(a.time) - this._timeToHour(b.time));
    this._setNodes(sorted);
    const newIdx = sorted.findIndex(n => n.time === newTime && n.temp === nodeTemp);
    this._selectedIdx = newIdx >= 0 ? newIdx : null;
    this._dirty = true;
  }

  _editNodeTemp(idx, newTemp) {
    const raw = parseFloat(newTemp);
    if (isNaN(raw)) return;
    const t = Math.max(TMIN, Math.min(TMAX, raw));
    const nodes = this._getNodes().map((n, i) => i === idx ? { ...n, temp: t } : n);
    this._setNodes(nodes);
    this._dirty = true;
  }

  // ── Graph / SVG helpers ──────────────────────────────────────────────────

  /** Convert an hour value (0–24) to an SVG x coordinate. @param {number} h */
  _toX(h) { return GL + (h / 24) * (GR - GL); }

  /** Convert a temperature value to an SVG y coordinate. @param {number} t */
  _toY(t) { return GB - ((t - TMIN) / (TMAX - TMIN)) * (GB - GT); }

  /** Convert an SVG x coordinate back to an hour value (0–24). @param {number} x */
  _fromX(x) { return Math.max(0, Math.min(24, (x - GL) / (GR - GL) * 24)); }

  /** Convert an SVG y coordinate back to a temperature value, snapped to 0.5°. @param {number} y */
  _fromY(y) {
    const t = TMIN + (GB - y) / (GB - GT) * (TMAX - TMIN);
    return Math.max(TMIN, Math.min(TMAX, Math.round(t * 2) / 2));
  }

  /** Parse a "HH:MM" time string into a fractional hour number. @param {string} s */
  _timeToHour(s) {
    if (!s) return 0;
    const [h, m] = s.split(":").map(Number);
    return h + (m || 0) / 60;
  }

  /** Convert a fractional hour number back to a "HH:MM" string. @param {number} h */
  _hourToTime(h) {
    const hh = Math.floor(h);
    const mm = Math.round((h - hh) * 60);
    return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
  }

  /**
   * Map a pointer event to SVG coordinate space.
   * @param {PointerEvent} e
   * @returns {{ x: number, y: number }}
   */
  _svgCoords(e) {
    const el = this.shadowRoot?.querySelector("svg.graph");
    if (!el) return { x: 0, y: 0 };
    const pt = el.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    return pt.matrixTransform(el.getScreenCTM().inverse());
  }

  /**
   * Build an SVG path string for the step-wise temperature schedule.
   * @param {Array<{time: string, temp: number}>} nodes
   * @returns {string}
   */
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

  /**
   * Build an SVG path string from the actual temperature history fetched from HA.
   * @returns {string}
   */
  _historyPath() {
    const hist = this._history;
    if (!hist?.length) return "";
    const base = new Date();
    base.setHours(0, 0, 0, 0);
    const baseMs = base.getTime();
    const pts = [];
    for (const h of hist) {
      const t = parseFloat(h.attributes?.current_temperature ?? h.state);
      if (isNaN(t)) continue;
      const hr = (new Date(h.last_changed ?? h.last_updated).getTime() - baseMs) / 3600000;
      if (hr < 0 || hr > 24) continue;
      const x = this._toX(hr);
      const y = this._toY(Math.max(TMIN, Math.min(TMAX, t)));
      pts.push(pts.length ? `L${x},${y}` : `M${x},${y}`);
    }
    return pts.join(" ");
  }

  /**
   * Build an SVG path string from yesterday's temperature history for future time slots.
   * Only includes data points at hours >= the current time, so the line covers the
   * portion of today's graph that hasn't happened yet.
   * @returns {string}
   */
  _yesterdayHistoryPath() {
    const hist = this._yesterdayHistory;
    if (!hist?.length) return "";
    const now = new Date();
    const nowH = now.getHours() + now.getMinutes() / 60;
    const todayMidnightMs = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterdayBaseMs = todayMidnightMs - 86400000;
    const pts = [];
    for (const h of hist) {
      const t = parseFloat(h.attributes?.current_temperature ?? h.state);
      if (isNaN(t)) continue;
      const hr = (new Date(h.last_changed ?? h.last_updated).getTime() - yesterdayBaseMs) / 3600000;
      if (hr < nowH || hr >= 24) continue;
      const x = this._toX(hr);
      const y = this._toY(Math.max(TMIN, Math.min(TMAX, t)));
      pts.push(pts.length ? `L${x},${y}` : `M${x},${y}`);
    }
    return pts.join(" ");
  }

  /**
   * Build an array of SVG `<rect>` elements representing presence history segments.
   * @returns {import('lit').TemplateResult[]}
   */
  _presenceBar() {
    const hist = this._presenceHistory;
    if (!hist?.length) return [];

    const base = new Date();
    base.setHours(0, 0, 0, 0);
    const baseMs = base.getTime();
    const nowMs = Math.min(Date.now(), baseMs + 24 * 3600000);

    const COLOR = { home: "#4caf50", leaving: "#ff9800", away: "#f44336" };

    const entries = hist
      .map(h => ({
        state: h.state,
        ms: new Date(h.last_changed ?? h.last_updated).getTime(),
      }))
      .filter(e => e.ms >= baseMs && e.ms <= nowMs);

    if (!entries.length) return [];

    // Best-effort: backfill from midnight using the first known state.
    // If HA's history retention didn't capture the state before this point,
    // we simply assume the earliest recorded state was also active at midnight.
    if (entries[0].ms > baseMs) {
      entries.unshift({ state: entries[0].state, ms: baseMs });
    }

    return entries.map((entry, i) => {
      const color = COLOR[entry.state];
      if (!color) return "";
      const startHr = Math.max(0, (entry.ms - baseMs) / 3600000);
      const endHr = Math.min(
        24,
        ((i + 1 < entries.length ? entries[i + 1].ms : nowMs) - baseMs) / 3600000
      );
      if (startHr >= endHr) return "";
      const x = this._toX(startHr);
      const w = this._toX(endHr) - x;
      return svg`<rect x="${x}" y="${PBAR_Y}" width="${w}" height="${PBAR_H}"
        fill="${color}" opacity="0.85" rx="1"/>`;
    });
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
    const yesterdayHistPathD = this._yesterdayHistoryPath();
    const sortedNodes = [...nodes].sort((a, b) => this._timeToHour(a.time) - this._timeToHour(b.time));

    // Determine next upcoming node index (in sortedNodes)
    let nextNodeIdx = sortedNodes.findIndex(n => this._timeToHour(n.time) > nowH);
    if (nextNodeIdx === -1 && sortedNodes.length > 0) nextNodeIdx = 0;

    const selectedNode = this._selectedIdx != null ? sortedNodes[this._selectedIdx] : null;

    return html`
      <ha-card>
        <div class="content">
          <div class="header">
            <div class="title">
              📅 Schedule${activeDay !== "daily" ? ` (${dayLabel[activeDay] ?? activeDay})` : ""}
            </div>
            <div class="header-actions">
              ${this._dirty ? html`<span class="unsaved-badge">● Unsaved</span>` : ""}
              ${this._saved ? html`<span class="saved-badge">✓ Saved</span>` : ""}
              <button class="save-btn ${this._dirty ? "save-btn--dirty" : ""}"
                @click=${this._saveSchedule} ?disabled=${!this._dirty}>
                Save
              </button>
            </div>
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
                  @click=${() => { this._activeDay = d; this._selectedIdx = null; }}>
                  ${dayLabel[d] ?? d}
                </button>
              `)}
            </div>
          ` : ""}

          <div class="graph-wrap">
            <svg class="graph" viewBox="0 0 ${VW} ${VH}" preserveAspectRatio="xMidYMid meet"
              @click=${this._onSvgClick}
              @dblclick=${this._onSvgDblClick}
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

              <!-- presence history bar -->
              ${this._presenceBar()}

              <!-- history background path -->
              ${histPathD ? svg`
                <path d="${histPathD}" fill="none"
                  stroke="rgba(255,160,50,0.45)" stroke-width="1.5" stroke-linejoin="round"/>
              ` : ""}

              <!-- yesterday history path (shown for future hours as a dashed reference) -->
              ${yesterdayHistPathD ? svg`
                <path d="${yesterdayHistPathD}" fill="none"
                  stroke="rgba(255,160,50,0.25)" stroke-width="1.5" stroke-linejoin="round"
                  stroke-dasharray="4,3"/>
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
                const isNext = idx === nextNodeIdx;
                const isSelected = idx === this._selectedIdx;
                const r = isNext ? NR + 3 : NR;
                const lblY = cy - r - 3;
                const timeY = cy + r + 11;
                return svg`
                  <g class="node-g">
                    ${isNext ? svg`
                      <circle cx="${cx}" cy="${cy}" r="${r + 4}"
                        fill="none" stroke="#ff9800" stroke-width="1.5"
                        stroke-dasharray="4,3" opacity="0.7"/>
                    ` : ""}
                    ${isSelected ? svg`
                      <circle cx="${cx}" cy="${cy}" r="${r + 5}"
                        fill="none" stroke="white" stroke-width="2" opacity="0.6"/>
                    ` : ""}
                    <circle class="node-c ${isNext ? "node-c--next" : ""} ${isSelected ? "node-c--selected" : ""}"
                      cx="${cx}" cy="${cy}" r="${r}"
                      @pointerdown=${(e) => this._onNodePointerDown(e, idx)}
                    />
                    <text x="${cx}" y="${lblY}" text-anchor="middle" class="node-lbl">${node.temp}°C</text>
                    <text x="${cx}" y="${timeY}" text-anchor="middle" class="node-time">${node.time}</text>
                    ${isNext ? svg`
                      <text x="${cx}" y="${cy + 4}" text-anchor="middle" class="next-badge">▶</text>
                    ` : ""}
                  </g>
                `;
              })}
            </svg>
          </div>

          ${selectedNode != null ? html`
            <div class="edit-panel">
              <span class="edit-panel-title">Edit Node</span>
              <label class="edit-field">
                <span>Time</span>
                <input type="time" class="edit-input" .value=${selectedNode.time}
                  @input=${(e) => this._editNodeTime(this._selectedIdx, e.target.value)} />
              </label>
              <label class="edit-field">
                <span>Temp (°C)</span>
                <input type="number" class="edit-input" min="${TMIN}" max="${TMAX}" step="0.5"
                  .value=${String(selectedNode.temp)}
                  @input=${(e) => this._editNodeTemp(this._selectedIdx, e.target.value)} />
              </label>
              <button class="edit-remove-btn"
                @click=${() => this._removeNode(null, this._selectedIdx)}>
                🗑 Remove
              </button>
              <button class="edit-close-btn"
                @click=${() => { this._selectedIdx = null; }}>
                ✕
              </button>
            </div>
          ` : ""}

          ${this._presenceHistory?.length ? html`
            <div class="presence-legend">
              <span class="presence-legend-item">
                <span class="presence-dot presence-dot--home"></span>🏠 Home
              </span>
              <span class="presence-legend-item">
                <span class="presence-dot presence-dot--leaving"></span>⏳ Leaving
              </span>
              <span class="presence-legend-item">
                <span class="presence-dot presence-dot--away"></span>🏃 Away
              </span>
            </div>
          ` : ""}

          <div class="hint">Double-click to add node • Drag to move • Select then remove to delete</div>
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

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
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

    .unsaved-badge {
      font-size: 11px;
      color: #ff9800;
      font-weight: 600;
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
      min-height: 180px;
      display: block;
      cursor: crosshair;
      user-select: none;
      touch-action: none;
    }

    .ax {
      font-size: 14px;
      fill: var(--secondary-text-color, #888);
      font-family: sans-serif;
    }

    .ax-title {
      font-size: 13px;
      fill: var(--secondary-text-color, #888);
      font-family: sans-serif;
    }

    .now-label {
      font-size: 14px;
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

    .node-c--next {
      fill: #ff9800;
      stroke: white;
    }

    .node-c--selected {
      stroke: #fff;
      stroke-width: 3;
    }

    .node-c:active {
      cursor: grabbing;
    }

    .next-badge {
      font-size: 11px;
      fill: white;
      font-weight: 700;
      font-family: sans-serif;
      pointer-events: none;
    }

    .edit-panel {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      background: var(--secondary-background-color);
      border: 1px solid var(--accent-color, #f5a623);
      border-radius: 8px;
      padding: 8px 12px;
      margin-top: 6px;
      font-size: 12px;
    }

    .edit-panel-title {
      font-weight: 600;
      font-size: 12px;
    }

    .edit-field {
      display: flex;
      align-items: center;
      gap: 4px;
      cursor: default;
    }

    .edit-input {
      background: var(--ha-card-background);
      color: var(--primary-text-color);
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      padding: 2px 6px;
      font-size: 12px;
      width: auto;
    }

    .edit-remove-btn {
      background: rgba(244, 67, 54, 0.15);
      color: #f44336;
      border: 1px solid #f44336;
      border-radius: 6px;
      padding: 3px 10px;
      font-size: 12px;
      cursor: pointer;
    }

    .edit-remove-btn:hover {
      background: rgba(244, 67, 54, 0.3);
    }

    .edit-close-btn {
      background: transparent;
      color: var(--secondary-text-color);
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      padding: 3px 8px;
      font-size: 12px;
      cursor: pointer;
      margin-left: auto;
    }

    .edit-close-btn:hover {
      opacity: 0.75;
    }

    .node-lbl {
      font-size: 13px;
      fill: white;
      font-weight: 700;
      font-family: sans-serif;
      pointer-events: none;
    }

    .node-time {
      font-size: 12px;
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

    .presence-legend {
      display: flex;
      gap: 12px;
      font-size: 10px;
      color: var(--secondary-text-color);
      margin-top: 3px;
      justify-content: center;
    }

    .presence-legend-item {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .presence-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
      flex-shrink: 0;
    }

    .presence-dot--home    { background: #4caf50; }
    .presence-dot--leaving { background: #ff9800; }
    .presence-dot--away    { background: #f44336; }
  `;
}

/** Card editor for smart-climate-schedule-card — delegates all behaviour to the shared base. */
class SmartClimateScheduleCardEditor extends SmartClimateBaseEditor {}

customElements.define("smart-climate-schedule-card-editor", SmartClimateScheduleCardEditor);

customElements.define("smart-climate-schedule-card", SmartClimateScheduleCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-climate-schedule-card",
  name: "Smart Climate Schedule Card",
  description: "Interactive temperature schedule graph with drag-and-drop nodes",
  preview: true,
});
