const PALETTE = ["#2962ff", "#f2a900", "#e040fb", "#26a69a", "#ff6d00", "#42a5f5", "#ab47bc", "#66bb6a"];
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const state = {
  symbols: [],
  sector: "All",
  active: "RELIANCE",
  bars: [],
  barCache: new Map(),
  indicators: [],
  sections: [],
  strategies: [],
  activeStudies: [],
  harmonics: [],
  focus: null,
  explainToken: 0,
  explainOpen: true,
  request: 0,
  range: "504",
};

const $ = (id) => document.getElementById(id);
const chartHost = $("price-chart");
const chart = LightweightCharts.createChart(chartHost, {
  autoSize: true,
  layout: { background: { color: "#0c0e13" }, textColor: "#d1d4dc", fontFamily: "Segoe UI, sans-serif" },
  grid: { vertLines: { color: "#1c2030" }, horzLines: { color: "#1c2030" } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor: "#2a2e39" },
  timeScale: { borderColor: "#2a2e39", rightOffset: 6 },
  handleScroll: true,
  handleScale: true,
});
const candles = chart.addCandlestickSeries({
  upColor: "#089981", downColor: "#f23645", borderUpColor: "#089981", borderDownColor: "#f23645",
  wickUpColor: "#089981", wickDownColor: "#f23645",
});
const volume = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "volume", color: "#35507a" });
chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
const overlaySeries = new Map();
const oscCharts = [];
let equityChart = null;
let equitySeries = null;
let benchSeries = null;

chart.subscribeCrosshairMove((param) => {
  const bar = param.time ? state.bars.find((item) => item.time === param.time) : state.bars.at(-1);
  if (!bar) return;
  const change = bar.close - bar.open;
  $("ohlc-legend").innerHTML = `O ${fmt(bar.open)}  H ${fmt(bar.high)}  L ${fmt(bar.low)}  C ${fmt(bar.close)}  <span class="${change >= 0 ? "up" : "down"}">${fmt(change)}</span>  Vol ${Math.round(bar.volume).toLocaleString("en-IN")}`;
});

function fmt(value) {
  return value == null || Number.isNaN(value) ? "—" : inr.format(value);
}
function pct(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value > 0 ? "+" : ""}${Number(value).toFixed(2)}%`;
}
function cls(value) {
  return value > 0 ? "up" : value < 0 ? "down" : "";
}

async function api(path, options) {
  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(path, options);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || response.statusText);
      return payload;
    } catch (error) {
      lastError = error;
      if (error.name !== "TypeError") throw error;
      await new Promise((resolve) => setTimeout(resolve, 400 * (attempt + 1)));
    }
  }
  throw new Error(lastError && lastError.message === "Failed to fetch"
    ? "The desk did not answer. Wait a second and pick the name again."
    : lastError.message);
}

const esc = (text) => String(text ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const SECTOR_SHORT = { "Information Technology": "IT", "Communication Services": "Telecom", "Consumer Discretionary": "Discretionary", "Consumer Staples": "Staples" };
const combos = [];
const menu = { combo: null, rows: [], index: 0 };

function makeCombo(host, options) {
  host.innerHTML = `
    ${options.title ? `<div class="combo-title"><span>${esc(options.title)}</span><em class="combo-badge"></em></div>` : ""}
    <div class="combo-field">
      <input type="search" autocomplete="off" spellcheck="false" placeholder="${esc(options.placeholder)}" aria-haspopup="listbox" />
      <button type="button" class="combo-caret" tabindex="-1" aria-label="Open list">▾</button>
    </div>`;
  const combo = { host, options, input: host.querySelector("input"), badge: host.querySelector(".combo-badge"), typed: false };
  combo.input.addEventListener("focus", () => { combo.typed = false; combo.input.select(); openCombo(combo); });
  combo.input.addEventListener("click", () => { if (menu.combo !== combo) openCombo(combo); });
  combo.input.addEventListener("input", () => { combo.typed = true; menu.index = 0; openCombo(combo); });
  combo.input.addEventListener("keydown", (event) => comboKey(combo, event));
  combo.input.addEventListener("blur", () => setTimeout(() => {
    if (menu.combo === combo && !$("combo-menu").contains(document.activeElement)) closeCombo();
  }, 120));
  host.querySelector(".combo-caret").addEventListener("mousedown", (event) => {
    event.preventDefault();
    if (menu.combo === combo) closeCombo();
    else combo.input.focus();
  });
  combos.push(combo);
  syncCombo(combo);
  return combo;
}

function syncCombo(combo) {
  const { options } = combo;
  if (!options.multi && menu.combo !== combo) combo.input.value = options.current ? options.current() : "";
  if (combo.badge) {
    const on = options.items().filter((item) => options.isOn(item.value)).length;
    combo.badge.textContent = on ? `${on} on` : "";
  }
}

function syncCombos() {
  combos.forEach(syncCombo);
  if (menu.combo) renderMenu();
}

function openCombo(combo) {
  if (menu.combo !== combo) menu.index = 0;
  menu.combo = combo;
  renderMenu();
}

function closeCombo() {
  const combo = menu.combo;
  menu.combo = null;
  $("combo-menu").classList.add("hidden");
  if (combo) { combo.typed = false; if (combo.options.multi) combo.input.value = ""; syncCombo(combo); }
}

function renderMenu() {
  const combo = menu.combo;
  if (!combo) return;
  const { options } = combo;
  const query = combo.typed ? combo.input.value.trim().toLowerCase() : "";
  const terms = query.split(/\s+/).filter(Boolean);
  const rows = options.items().filter((item) => {
    const text = `${item.label} ${item.value} ${item.group || ""} ${item.search || ""}`.toLowerCase();
    return terms.every((term) => text.includes(term));
  });
  menu.rows = rows;
  menu.index = Math.min(menu.index, Math.max(rows.length - 1, 0));
  let group = null;
  const html = [];
  rows.forEach((item, index) => {
    if (item.group && item.group !== group) {
      group = item.group;
      html.push(`<div class="combo-group">${esc(group)}</div>`);
    }
    const on = options.isOn(item.value);
    html.push(`<div class="combo-row ${on ? "on" : ""} ${index === menu.index ? "hot" : ""}" role="option" aria-selected="${on}" data-index="${index}">
      <span class="combo-check">${on ? "✓" : ""}</span>
      <span class="combo-label">${item.html || esc(item.label)}</span>
      <span class="combo-meta ${item.metaCls || ""}">${esc(item.meta || "")}</span>
    </div>`);
  });
  const box = $("combo-menu");
  box.innerHTML = html.join("") || `<div class="combo-empty">No match for “${esc(combo.input.value)}”</div>`;
  const rect = combo.input.getBoundingClientRect();
  const below = window.innerHeight - rect.bottom - 12;
  const above = rect.top - 12;
  const height = Math.min(360, Math.max(below, above));
  box.style.left = `${rect.left}px`;
  box.style.width = `${Math.max(rect.width + 28, 280)}px`;
  box.style.maxHeight = `${height}px`;
  if (below >= Math.min(260, above) || below >= 260) {
    box.style.top = `${rect.bottom + 4}px`;
    box.style.bottom = "auto";
  } else {
    box.style.top = "auto";
    box.style.bottom = `${window.innerHeight - rect.top + 4}px`;
  }
  box.classList.remove("hidden");
  const hot = box.querySelector(".hot");
  if (hot) hot.scrollIntoView({ block: "nearest" });
}

function pickRow(index) {
  const combo = menu.combo;
  const item = menu.rows[index];
  if (!combo || !item) return;
  combo.options.onPick(item.value);
  if (combo.options.multi) {
    menu.index = index;
    syncCombos();
    if (document.activeElement !== combo.input) combo.input.focus();
  } else {
    closeCombo();
    combo.input.blur();
  }
}

function comboKey(combo, event) {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    if (menu.combo !== combo) openCombo(combo);
    const step = event.key === "ArrowDown" ? 1 : -1;
    menu.index = Math.max(0, Math.min(menu.rows.length - 1, menu.index + step));
    renderMenu();
  } else if (event.key === "Enter") {
    event.preventDefault();
    if (menu.combo === combo) pickRow(menu.index);
  } else if (event.key === "Escape") {
    closeCombo();
    combo.input.blur();
  }
}

function bindComboMenu() {
  const box = $("combo-menu");
  box.addEventListener("mousedown", (event) => event.preventDefault());
  box.addEventListener("click", (event) => {
    const row = event.target.closest("[data-index]");
    if (row) pickRow(Number(row.dataset.index));
  });
  box.addEventListener("mousemove", (event) => {
    const row = event.target.closest("[data-index]");
    if (!row || Number(row.dataset.index) === menu.index) return;
    box.querySelector(".hot")?.classList.remove("hot");
    row.classList.add("hot");
    menu.index = Number(row.dataset.index);
  });
  document.addEventListener("mousedown", (event) => {
    if (menu.combo && !menu.combo.host.contains(event.target) && !box.contains(event.target)) closeCombo();
  });
  $("controls").addEventListener("scroll", () => { if (menu.combo) renderMenu(); });
  window.addEventListener("resize", () => { if (menu.combo) renderMenu(); });
}

function stockItems() {
  return state.symbols.map((row) => ({
    value: row.symbol,
    label: `${row.symbol} ${row.name}`,
    html: `<b>${esc(row.symbol)}</b> <small>${esc(row.name)}</small>`,
    group: SECTOR_SHORT[row.sector] || row.sector,
    search: row.sector,
    meta: row.last == null ? "no bars" : `${fmt(row.last)}  ${pct(row.change_pct)}`,
    metaCls: cls(row.change_pct),
  })).sort((a, b) => (a.group < b.group ? -1 : a.group > b.group ? 1 : 0));
}

function buildControls() {
  makeCombo($("stock-combo"), {
    placeholder: "Search 50 NSE names or sectors",
    items: stockItems,
    isOn: (value) => value === state.active,
    current: () => {
      const row = state.symbols.find((item) => item.symbol === state.active);
      return row ? `${row.symbol} · ${row.name}` : state.active;
    },
    onPick: (value) => loadBars(value).catch((error) => { $("ohlc-legend").textContent = error.message; }),
  });
  $("stock-count").textContent = `${state.symbols.length} Nifty names`;

  const host = $("section-combos");
  host.innerHTML = "";
  for (const section of state.sections) {
    const items = state.indicators.filter((item) => item.section === section);
    if (!items.length) continue;
    const node = document.createElement("div");
    node.className = "combo";
    node.dataset.section = section;
    host.append(node);
    makeCombo(node, {
      title: section,
      multi: true,
      placeholder: `Search ${items.length} ${section.toLowerCase()} studies`,
      items: () => items.map((item) => ({ value: item.id, label: item.name, meta: item.pane === "price" ? "Overlay" : "Pane" })),
      isOn: (value) => state.activeStudies.some((item) => item.id === value),
      onPick: (value) => toggleStudy(value),
    });
  }
  $("indicator-count").textContent = `${state.indicators.length} studies`;

  makeCombo($("strategy-combo"), {
    placeholder: `Search ${state.strategies.length} strategies`,
    items: () => {
      const order = ["Trend", "Breakout", "Trend reversal", "Harmonics", "@neurotrader888", "@UnbiasedTradingGoshawk", "Oscillator", "Mean reversion", "Price action", "Volume"];
      const rank = (section) => (order.includes(section) ? order.indexOf(section) : order.length);
      return state.strategies
        .map((item, index) => ({ value: item.id, label: item.name, group: item.section, search: item.blurb, index }))
        .sort((a, b) => rank(a.group) - rank(b.group) || a.index - b.index);
    },
    isOn: (value) => value === $("strategy-select").value,
    current: () => (selectedStrategy() ? `${selectedStrategy().name} · ${selectedStrategy().section}` : ""),
    onPick: (value) => {
      $("strategy-select").value = value;
      renderStrategyParams();
      scheduleExplain(value);
    },
  });
  $("strategy-count").textContent = `${state.strategies.length} rules`;
}

function renderSymbols() {
  syncCombos();
}

function renderStrategies() {
  if (!$("strategy-select").value && state.strategies.length) $("strategy-select").value = state.strategies[0].id;
  renderStrategyParams();
}

function selectedStrategy() {
  return state.strategies.find((item) => item.id === $("strategy-select").value) || state.strategies[0];
}

function renderStrategyParams() {
  const item = selectedStrategy();
  if (!item) return;
  const links = (item.sources || []).map((url, n) => `<a href="${esc(url)}" target="_blank" rel="noreferrer">source ${n + 1}</a>`).join(" · ");
  $("strategy-blurb").innerHTML = esc(item.blurb) + (item.creator
    ? `<span class="provenance">From <a href="${esc(item.channel)}" target="_blank" rel="noreferrer">${esc(item.creator)}</a> · confidence ${esc(item.confidence || "—")}${links ? ` · ${links}` : ""}${item.notes ? `<br>${esc(item.notes)}` : ""}</span>`
    : "");
  $("strategy-params").innerHTML = item.params.map((param) => `<label>${esc(param.label)}<input data-strategy-param="${param.key}" type="number" value="${param.default}" min="${param.min}" max="${param.max}" step="${param.step}" /></label>`).join("");
  syncCombos();
}

function strategyParams() {
  const params = {};
  for (const input of document.querySelectorAll("[data-strategy-param]")) params[input.dataset.strategyParam] = Number(input.value);
  return params;
}

let studySeq = 0;
const PERIOD_PRESETS = [5, 9, 10, 14, 20, 21, 30, 50, 100, 150, 200];

function newStudy(spec, values) {
  studySeq += 1;
  return {
    uid: `s${studySeq}`,
    id: spec.id,
    name: spec.name,
    section: spec.section,
    params: spec.params,
    values: values || Object.fromEntries(spec.params.map((param) => [param.key, param.default])),
  };
}

function studyLabel(item) {
  const length = item.values.length;
  return length != null ? `${item.name} ${length}` : item.name;
}

function presetRow(item) {
  const length = item.params.find((param) => param.key === "length");
  if (!length) return "";
  const values = PERIOD_PRESETS.filter((v) => v >= length.min && v <= length.max);
  return `<div class="presets" title="Quick periods">${values.map((v) => `<button type="button" class="${Number(item.values.length) === v ? "on" : ""}" data-preset="${item.uid}:${v}">${v}</button>`).join("")}</div>`;
}

function renderLibrary() {
  $("active-studies").innerHTML = state.activeStudies.length
    ? `<div class="combo-title"><span>On the chart</span></div>` + state.activeStudies.map((item, index) => `
    <div class="active-card">
      <header><span><i style="background:${PALETTE[index % PALETTE.length]}"></i>${esc(studyLabel(item))}</span>
        <span class="card-actions">${item.params.some((param) => param.key === "length") ? `<button type="button" data-copy="${item.uid}" title="Add another ${esc(item.name)} with a different period">+ Another</button>` : ""}<button type="button" data-remove="${item.uid}">Remove</button></span></header>
      ${presetRow(item)}
      ${item.params.length ? `<div class="param-grid">${item.params.map((param) => `<label>${esc(param.label)}<input data-study-param="${item.uid}:${param.key}" type="number" value="${item.values[param.key]}" min="${param.min}" max="${param.max}" step="${param.step}" /></label>`).join("")}</div>` : ""}
    </div>`).join("")
    : `<p class="blurb">Nothing on the chart yet. Pick a study above.</p>`;
  syncCombos();
}

function points(times, values, histogram = false) {
  const out = [];
  for (let i = 0; i < times.length; i += 1) {
    const value = values[i];
    if (value == null || Number.isNaN(value)) {
      if (!histogram) out.push({ time: times[i] });
    } else out.push({ time: times[i], value });
  }
  return out;
}

// Light fill between a study's upper and lower lines, drawn beneath the candles (series primitive, zOrder bottom).
class BandFill {
  constructor(times, upper, lower, color) {
    this.rows = times.map((time, i) => [time, upper[i], lower[i]]);
    this.color = color;
    this.series = null;
    this.chartApi = null;
    const source = this;
    this.view = {
      zOrder: () => "bottom",
      renderer: () => ({ draw: (target) => source.draw(target) }),
    };
  }
  attached({ chart: chartApi, series }) { this.chartApi = chartApi; this.series = series; }
  detached() { this.chartApi = null; this.series = null; }
  updateAllViews() {}
  paneViews() { return [this.view]; }
  draw(target) {
    if (!this.chartApi || !this.series) return;
    const timeScale = this.chartApi.timeScale();
    const runs = [];
    let run = [];
    for (const [time, up, lo] of this.rows) {
      const x = up == null || lo == null ? null : timeScale.timeToCoordinate(time);
      const yUp = x == null ? null : this.series.priceToCoordinate(up);
      const yLo = x == null ? null : this.series.priceToCoordinate(lo);
      if (x == null || yUp == null || yLo == null) {
        if (run.length > 1) runs.push(run);
        run = [];
      } else run.push([x, yUp, yLo]);
    }
    if (run.length > 1) runs.push(run);
    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
      context.fillStyle = this.color;
      for (const pts of runs) {
        context.beginPath();
        context.moveTo(pts[0][0] * hr, pts[0][1] * vr);
        for (const [x, yUp] of pts) context.lineTo(x * hr, yUp * vr);
        for (let i = pts.length - 1; i >= 0; i -= 1) context.lineTo(pts[i][0] * hr, pts[i][2] * vr);
        context.closePath();
        context.fill();
      }
    });
  }
}
const bandFills = [];

function clearStudies() {
  while (bandFills.length) candles.detachPrimitive(bandFills.pop());
  for (const series of overlaySeries.values()) chart.removeSeries(series);
  overlaySeries.clear();
  for (const pane of oscCharts) pane.remove();
  oscCharts.length = 0;
  $("osc-stack").innerHTML = "";
  candles.setMarkers([]);
}

function applyRange() {
  if (state.range === "all" || !state.bars.length) {
    chart.timeScale().fitContent();
    return;
  }
  const count = Number(state.range);
  const from = Math.max(state.bars.length - count, 0);
  chart.timeScale().setVisibleLogicalRange({ from, to: state.bars.length + 4 });
}

async function loadBars(symbol) {
  const token = ++state.request;
  state.active = symbol;
  const row = state.symbols.find((item) => item.symbol === symbol);
  $("active-symbol").textContent = symbol;
  $("active-name").textContent = row ? row.name : "";
  $("active-price").textContent = row && row.last != null ? fmt(row.last) : "";
  $("active-change").textContent = row && row.change_pct != null ? pct(row.change_pct) : "";
  $("active-change").className = cls(row && row.change_pct);
  renderSymbols();
  if (!state.barCache.has(symbol)) {
    const payload = await api(`/api/bars?symbol=${encodeURIComponent(symbol)}`);
    state.barCache.set(symbol, payload.bars);
  }
  if (token !== state.request) return;
  state.bars = state.barCache.get(symbol) || [];
  $("chart-empty").classList.toggle("hidden", state.bars.length > 0);
  candles.setData(state.bars.map((bar) => ({ time: bar.time, open: bar.open, high: bar.high, low: bar.low, close: bar.close })));
  volume.setData(state.bars.map((bar) => ({
    time: bar.time,
    value: bar.volume,
    color: bar.close >= bar.open ? "rgba(8,153,129,0.45)" : "rgba(242,54,69,0.45)",
  })));
  applyRange();
  if (state.bars.length) {
    const last = state.bars.at(-1);
    $("ohlc-legend").textContent = `${symbol}  ${last.time}  C ${fmt(last.close)}`;
  }
  try {
    await refreshStudies();
  } catch (error) {
    $("ohlc-legend").textContent = `${symbol} chart is loaded. Study failed: ${error.message}`;
  }
}

let studyToken = 0;

async function refreshStudies() {
  const token = ++studyToken;
  const barsToken = state.request;
  scheduleExplain();
  if (!state.activeStudies.length || !state.bars.length) {
    clearStudies();
    return;
  }
  const payload = await api("/api/studies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbol: state.active,
      studies: state.activeStudies.map((item) => ({ id: item.id, params: item.values })),
    }),
  });
  // Only the newest request draws; older responses from quick clicks are dropped.
  if (token !== studyToken || barsToken !== state.request) return;
  clearStudies();
  const markers = [];
  state.harmonics = [];
  let harmonicStudies = 0;
  payload.studies.forEach((study, index) => {
    for (const marker of study.markers || []) markers.push(marker);
    if (study.id === "carney" || study.id.startsWith("harm_")) {
      harmonicStudies += 1;
      drawHarmonics(study, markers);
    }
    const color = PALETTE[index % PALETTE.length];
    const keys = Object.keys(study.series);
    const instance = state.activeStudies[index] || { uid: `${study.id}${index}`, name: study.name, values: {} };
    if (study.pane === "price") {
      if (keys.includes("upper") && keys.includes("lower")) {
        const fill = new BandFill(payload.time, study.series.upper, study.series.lower, "rgba(178, 181, 190, 0.13)");
        candles.attachPrimitive(fill);
        bandFills.push(fill);
      }
      keys.forEach((key, offset) => {
        const series = chart.addLineSeries({ color: PALETTE[(index + offset) % PALETTE.length], lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, title: offset === 0 && keys.length === 1 ? studyLabel(instance) : "" });
        series.setData(points(payload.time, study.series[key]));
        overlaySeries.set(`${instance.uid}:${key}`, series);
      });
      return;
    }
    const host = document.createElement("div");
    host.className = "osc-pane";
    host.innerHTML = `<span>${esc(studyLabel(instance))}</span>`;
    $("osc-stack").append(host);
    const pane = LightweightCharts.createChart(host, {
      autoSize: true,
      layout: { background: { color: "#0c0e13" }, textColor: "#8b90a0" },
      grid: { vertLines: { color: "#1c2030" }, horzLines: { color: "#1c2030" } },
      rightPriceScale: { borderColor: "#2a2e39" },
      timeScale: { visible: false, borderColor: "#2a2e39" },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });
    keys.forEach((key, offset) => {
      const series = key === "hist" || key === "ao"
        ? pane.addHistogramSeries({ color, priceLineVisible: false })
        : pane.addLineSeries({ color: PALETTE[(index + offset) % PALETTE.length], lineWidth: 1.4, priceLineVisible: false, lastValueVisible: key === keys[0] });
      series.setData(points(payload.time, study.series[key], key === "hist"));
    });
    oscCharts.push(pane);
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) pane.timeScale().setVisibleLogicalRange(range);
    });
  });
  markers.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
  candles.setMarkers(markers);
  if (harmonicStudies) {
    const bull = state.harmonics.filter((item) => item.side === "bull").length;
    $("ohlc-legend").textContent = state.harmonics.length
      ? `${state.active}  Carney harmonics: ${state.harmonics.length} latest patterns drawn (${bull} bullish, ${state.harmonics.length - bull} bearish). Click Harmonics for the list.`
      : `${state.active}: no Carney pattern completed at these settings. Lower Swing % or raise Tolerance.`;
  }
}

const TONE = { bull: ["up", "Bullish"], "bull-hot": ["up", "Bullish, stretched"], bear: ["down", "Bearish"], "bear-cold": ["down", "Bearish, stretched"], neutral: ["", "Neutral"] };
let explainTimer = 0;
const planLines = [];

function scheduleExplain(focus) {
  if (focus) state.focus = focus;
  window.clearTimeout(explainTimer);
  explainTimer = window.setTimeout(() => refreshExplain().catch((error) => {
    $("explain-sub").textContent = `Interpretation failed: ${error.message}`;
  }), 250);
}

async function refreshExplain() {
  if (!state.active || !state.bars.length) return;
  const token = ++state.explainToken;
  const strategy = selectedStrategy();
  $("explain-sub").textContent = `Reading ${state.active}…`;
  const payload = await api("/api/explain", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbol: state.active,
      studies: state.activeStudies.map((item) => ({ id: item.id, params: item.values })),
      strategy: strategy ? { id: strategy.id, params: strategyParams() } : null,
      capital: Number($("capital").value),
      cost_bps: Number($("cost-bps").value),
      focus: state.focus,
    }),
  });
  if (token !== state.explainToken || payload.symbol !== state.active) return;
  renderExplain(payload);
  drawPlanLines(payload.plan);
}

function drawPlanLines(plan) {
  while (planLines.length) candles.removePriceLine(planLines.pop());
  if (!plan || plan.entry == null) return;
  const lines = [
    [plan.entry, "#2962ff", "Entry"],
    [plan.stop, "#f23645", "Stop"],
    [plan.t1, "#089981", "T1"],
    [plan.t2, "#089981", "T2"],
  ];
  for (const [price, color, title] of lines) {
    if (price == null) continue;
    planLines.push(candles.createPriceLine({ price, color, lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title }));
  }
}

function renderExplain(data) {
  const plan = data.plan || {};
  const rating = data.rating || {};
  const tone = (t) => TONE[t] || TONE.neutral;
  const biasCls = plan.bias === "Bullish" ? "up" : plan.bias === "Bearish" ? "down" : "";
  const ratingCls = (label) => (/buy/i.test(label) ? "up" : /sell/i.test(label) ? "down" : "");
  const odds = plan.odds;
  const base = plan.base;
  const levels = plan.entry != null ? `<div class="levels">
      <span><em>Entry</em>${fmt(plan.entry)}</span>
      <span class="down"><em>Stop</em>${fmt(plan.stop)}</span>
      <span class="up"><em>T1 · ${plan.r1}R</em>${fmt(plan.t1)}</span>
      <span class="up"><em>T2 · ${plan.r2}R</em>${fmt(plan.t2)}</span>
      <span><em>Risk</em>${plan.risk_pct}%</span>
    </div>` : "";
  const oddsText = odds && odds.win != null
    ? `<p><b>Same plan on ${esc(data.symbol)}'s past:</b> ${odds.n} similar setups. T1 was reached before the stop ${odds.win.toFixed(0)}% of the time; average result ${odds.expectancy >= 0 ? "+" : ""}${odds.expectancy.toFixed(2)}R per trade.</p>`
    : odds ? `<p class="muted">Too few similar setups in this stock's history (${odds.n}) to give odds.</p>` : "";
  const baseText = base && base.up != null
    ? `<p><b>Base rate:</b> after ${base.n} past sessions in the same trend state with a similar RSI, ${esc(data.symbol)} was higher ${base.horizon} sessions later ${base.up.toFixed(0)}% of the time (median ${pct(base.median)}, middle half ${pct(base.p25)} to ${pct(base.p75)}).</p>`
    : "";
  const items = (data.items || []).map((item) => {
    const [cls_, label] = tone(item.tone);
    return `<article class="explain-item ${item.id === state.focus ? "focus" : ""}">
      <header><b>${esc(item.title)}</b><small>${esc(item.section || item.kind)}</small><span class="tone ${cls_}">${label}</span></header>
      <p>${esc(item.now)}</p>
      ${item.what ? `<details><summary>What is this?</summary><p class="muted">${esc(item.what)}</p></details>` : ""}
    </article>`;
  }).join("") || `<p class="muted">Nothing selected yet. Add a study or pick a strategy on the left and its reading appears here.</p>`;
  $("explain-sub").textContent = `${data.symbol} · ${data.snapshot.date} · close ${fmt(data.snapshot.close)}`;
  $("explain-body").innerHTML = `
    <section class="outlook">
      <p class="headline">${esc(data.headline)}</p>
      <div class="badges">
        <span class="badge ${biasCls}">Swing bias: ${esc(plan.bias || "—")}</span>
        <span class="badge ${ratingCls(rating.overall?.label || "")}" title="Moving averages ${rating.ma?.buy} buy / ${rating.ma?.sell} sell; oscillators ${rating.osc?.buy} buy / ${rating.osc?.sell} sell / ${rating.osc?.neutral} neutral">Technical rating: ${esc(rating.overall?.label || "—")}</span>
        <span class="badge ${ratingCls(rating.ma?.label || "")}">MAs: ${esc(rating.ma?.label || "—")} (${rating.ma?.buy}/${(rating.ma?.buy || 0) + (rating.ma?.sell || 0)})</span>
        <span class="badge ${ratingCls(rating.osc?.label || "")}">Oscillators: ${esc(rating.osc?.label || "—")}</span>
      </div>
      <h4>Swing plan: ${esc(plan.setup || "—")}</h4>
      ${levels}
      <ol>${(plan.steps || []).map((step) => `<li>${esc(step)}</li>`).join("")}</ol>
      ${oddsText}${baseText}
      <p class="disclaimer">${esc(data.disclaimer)}</p>
    </section>
    <section class="readings">
      <h4>What your selections say</h4>
      ${items}
    </section>`;
}

function drawHarmonics(study, markers) {
  (study.drawings || []).forEach((drawing, n) => {
    state.harmonics.push(drawing);
    const legs = chart.addLineSeries({ color: drawing.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    legs.setData(drawing.legs.map((p) => ({ time: p.time, value: p.value })));
    overlaySeries.set(`${study.id}:legs:${n}`, legs);
    drawing.guides.forEach((guide, g) => {
      const line = chart.addLineSeries({ color: drawing.color, lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      line.setData(guide.map((p) => ({ time: p.time, value: p.value })));
      overlaySeries.set(`${study.id}:guide:${n}:${g}`, line);
    });
    drawing.legs.forEach((p, i) => {
      const prev = drawing.legs[i - 1] || drawing.legs[i + 1];
      const high = prev ? p.value > prev.value : true;
      markers.push({ time: p.time, position: high ? "aboveBar" : "belowBar", color: drawing.color, shape: "circle", size: 0.4, text: p.label });
    });
  });
}

async function runHarmonics() {
  if (!state.activeStudies.some((item) => item.id === "carney")) {
    const spec = state.indicators.find((item) => item.id === "carney");
    state.activeStudies.push(newStudy(spec));
    renderLibrary();
    try { await refreshStudies(); } catch (error) { showInsight("Harmonics", `<p>${esc(error.message)}</p>`); return; }
  }
  const rows = [...state.harmonics].reverse();
  const ratio = (r) => Object.entries(r || {}).map(([k, v]) => `${k.toUpperCase()} ${v}`).join(" · ");
  showInsight(`${state.active} Scott Carney harmonics`, rows.length ? `
    <p class="muted">Latest ${rows.length} completed patterns are drawn on the chart. Solid lines are X-A-B-C-D; dashed lines join X-B-D and A-C. D is the potential reversal zone. Change Swing % and Tolerance under Carney all harmonics.</p>
    <table><thead><tr><th>D date</th><th>Pattern</th><th>Side</th><th>PRZ</th><th>Ratios</th></tr></thead><tbody>
    ${rows.map((row) => `<tr><td>${esc(row.time)}</td><td>${esc(row.name)}</td><td class="${row.side === "bull" ? "up" : "down"}">${row.side === "bull" ? "Bullish" : "Bearish"}</td><td>${fmt(row.prz)}</td><td>${ratio(row.ratios)}</td></tr>`).join("")}
    </tbody></table>` : `<p>No Carney pattern completed on ${state.active} at these settings. Lower Swing % or raise Tolerance under Carney all harmonics.</p>`);
}

function toggleStudy(id) {
  // From a dropdown: picking a study that is on removes every copy of it.
  if (state.activeStudies.some((item) => item.id === id)) {
    state.activeStudies = state.activeStudies.filter((item) => item.id !== id);
  } else {
    state.focus = id;
    const spec = state.indicators.find((item) => item.id === id);
    if (!spec) return;
    state.activeStudies.push(newStudy(spec));
  }
  renderLibrary();
  refreshStudies().catch((error) => { $("ohlc-legend").textContent = error.message; });
}

function removeInstance(uid) {
  state.activeStudies = state.activeStudies.filter((item) => item.uid !== uid);
  renderLibrary();
  refreshStudies().catch((error) => { $("ohlc-legend").textContent = error.message; });
}

function copyInstance(uid) {
  const item = state.activeStudies.find((study) => study.uid === uid);
  if (!item) return;
  const used = new Set(state.activeStudies.filter((study) => study.id === item.id).map((study) => Number(study.values.length)));
  const length = item.params.find((param) => param.key === "length");
  const chain = [9, 20, 50, 100, 200];
  const fits = (v) => !used.has(v) && v >= length.min && v <= length.max;
  const next = chain.find((v) => v > Number(item.values.length) && fits(v))
    ?? chain.find(fits) ?? PERIOD_PRESETS.find(fits) ?? item.values.length;
  const spec = state.indicators.find((study) => study.id === item.id);
  const copy = newStudy(spec, { ...item.values, length: next });
  state.activeStudies.splice(state.activeStudies.indexOf(item) + 1, 0, copy);
  state.focus = item.id;
  renderLibrary();
  refreshStudies().catch((error) => { $("ohlc-legend").textContent = error.message; });
}

function drawEquity(result) {
  if (!equityChart) {
    equityChart = LightweightCharts.createChart($("equity-chart"), {
      autoSize: true,
      layout: { background: { color: "#10141d" }, textColor: "#8b90a0" },
      grid: { vertLines: { color: "#1c2030" }, horzLines: { color: "#1c2030" } },
      rightPriceScale: { borderColor: "#2a2e39" },
      timeScale: { borderColor: "#2a2e39" },
    });
    equitySeries = equityChart.addAreaSeries({ lineColor: "#2962ff", topColor: "rgba(41,98,255,0.28)", bottomColor: "rgba(41,98,255,0.02)", priceLineVisible: false });
    benchSeries = equityChart.addLineSeries({ color: "#8b90a0", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
  }
  equitySeries.setData(result.equity);
  benchSeries.setData(result.benchmark);
  equityChart.timeScale().fitContent();
}

function renderMetrics(metrics) {
  const cards = [
    ["Return", pct(metrics.total_return_pct), metrics.total_return_pct],
    ["CAGR", pct(metrics.cagr_pct), metrics.cagr_pct],
    ["Max DD", pct(metrics.max_drawdown_pct), metrics.max_drawdown_pct],
    ["Buy & hold", pct(metrics.buy_hold_pct), metrics.buy_hold_pct],
    ["Sharpe", metrics.sharpe ?? "—", metrics.sharpe],
    ["Sortino", metrics.sortino ?? "—", metrics.sortino],
    ["Win rate", metrics.win_rate_pct == null ? "—" : `${metrics.win_rate_pct}%`, metrics.win_rate_pct],
    ["Profit factor", metrics.profit_factor ?? "—", metrics.profit_factor],
    ["Trades", metrics.trades, null],
    ["Avg trade", metrics.avg_trade_pct == null ? "—" : pct(metrics.avg_trade_pct), metrics.avg_trade_pct],
    ["Exposure", `${metrics.exposure_pct}%`, null],
    ["Ending", fmt(metrics.ending_equity), null],
  ];
  $("metrics").innerHTML = cards.map(([label, value, signed]) => `<div class="metric"><span>${label}</span><b class="${typeof signed === "number" ? cls(signed) : ""}">${value}</b></div>`).join("");
}

async function runBacktest(event) {
  event.preventDefault();
  const button = $("run-backtest");
  button.disabled = true;
  button.textContent = "Running";
  try {
    const result = await api("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: state.active,
        strategy: $("strategy-select").value,
        params: strategyParams(),
        capital: Number($("capital").value),
        cost_bps: Number($("cost-bps").value),
      }),
    });
    renderMetrics(result.metrics);
    drawEquity(result);
    $("trades").innerHTML = result.trades.slice().reverse().map((trade) => `<tr>
      <td>${trade.entry}</td><td>${trade.exit}${trade.open ? " open" : ""}</td>
      <td>${fmt(trade.entry_px)}</td><td>${fmt(trade.exit_px)}</td>
      <td class="${cls(trade.return_pct)}">${pct(trade.return_pct)}</td>
      <td class="${cls(trade.pnl)}">${fmt(trade.pnl)}</td></tr>`).join("") || `<tr><td colspan="6">No trades</td></tr>`;
    $("tester-note").textContent = `${state.active} · ${selectedStrategy().name}. ${result.methodology}`;
    if ($("tester").classList.contains("collapsed")) $("tester-toggle").click();
  } catch (error) {
    $("tester-note").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Run backtest";
  }
}

async function refreshStatus() {
  const payload = await api("/api/status");
  const sync = payload.sync;
  const coverage = payload.coverage;
  const pill = $("sync-pill");
  pill.textContent = sync.syncing ? `Sync ${sync.done}/${sync.total}` : `DuckDB ${coverage.symbols_with_bars}/50`;
  pill.className = `pill ${sync.syncing ? "warn" : coverage.symbols_with_bars === 50 ? "live" : ""}`;
  if (!sync.syncing) {
    const symbols = await api("/api/symbols");
    state.symbols = symbols.symbols;
    renderSymbols();
    const current = state.symbols.find((row) => row.symbol === state.active);
    if (current && current.last != null && !state.bars.length) {
      state.barCache.delete(state.active);
      await loadBars(state.active);
    }
  }
  if (sync.syncing) setTimeout(refreshStatus, 1200);
}

function showInsight(title, html) {
  $("insight-title").textContent = title;
  $("insight-body").innerHTML = html;
  $("insight").classList.remove("hidden");
}

function moneyRows(rows, extra) {
  return `<table><thead><tr><th>Name</th><th>State</th><th>Return</th><th>Max DD</th>  <th>Trades</th>${extra ? "<th>Section</th>" : ""}</tr></thead><tbody>${rows.map((row) => `<tr>
    <td>${row.symbol ? `${esc(row.symbol)} ` : ""}${esc(row.name || row.id)}</td>
    <td class="${row.in_position ? "up" : ""}">${row.error ? esc(row.error) : row.in_position ? "Long" : "Flat"}</td>
    <td class="${cls(row.return_pct)}">${row.return_pct == null ? "—" : pct(row.return_pct)}</td>
    <td class="${cls(row.max_drawdown_pct)}">${row.max_drawdown_pct == null ? "—" : pct(row.max_drawdown_pct)}</td>
    <td>${row.trades ?? "—"}</td>
    ${extra ? `<td>${esc(row.section || "")}</td>` : ""}
  </tr>`).join("")}</tbody></table>`;
}

async function runTrend() {
  const button = $("trend-btn");
  button.disabled = true;
  try {
    const payload = await api("/api/trend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: state.active, capital: Number($("capital").value), cost_bps: Number($("cost-bps").value) }),
    });
    showInsight(`${state.active} trend, breakout, reversal`, `<p class="muted">${esc(payload.note)}</p>${moneyRows(payload.rows, true)}`);
  } catch (error) {
    showInsight("Trend scan", `<p>${esc(error.message)}</p>`);
  } finally {
    button.disabled = false;
  }
}

async function runScan() {
  const button = $("scan-50");
  button.disabled = true;
  button.textContent = "Scanning";
  try {
    const payload = await api("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        strategy: $("strategy-select").value,
        params: strategyParams(),
        capital: Number($("capital").value),
        cost_bps: Number($("cost-bps").value),
      }),
    });
    const name = selectedStrategy() ? selectedStrategy().name : payload.strategy;
    showInsight(`${name} on all 50`, moneyRows(payload.rows));
  } catch (error) {
    showInsight("Backtest 50", `<p>${esc(error.message)}</p>`);
  } finally {
    button.disabled = false;
    button.textContent = "Backtest 50";
  }
}

async function runFundamentals() {
  const button = $("fund-btn");
  button.disabled = true;
  try {
    const payload = await api(`/api/fundamentals?symbol=${encodeURIComponent(state.active)}`);
    const ratios = payload.ratios.map((row) => `<div><span>${esc(row.label)}</span><b>${esc(row.value)}</b></div>`).join("");
    const list = (items) => items.length ? `<ul>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : "<p class='muted'>None listed</p>";
    showInsight(`${state.active} fundamentals`, `
      <p class="muted">${esc(payload.source)}. <a href="${esc(payload.url)}" target="_blank" rel="noreferrer">Open Screener.in</a></p>
      <div class="ratio-grid">${ratios}</div>
      <p><b>Pros</b></p>${list(payload.pros)}
      <p><b>Cons</b></p>${list(payload.cons)}
      <p class="muted">${esc(payload.note)}</p>`);
  } catch (error) {
    showInsight("Fundamentals", `<p>${esc(error.message)}</p>`);
  } finally {
    button.disabled = false;
  }
}

async function runVerify() {
  const button = $("verify-btn");
  button.disabled = true;
  button.textContent = "Checking";
  const client = [];
  const add = (name, ok, detail) => client.push({ name, ok, detail });
  try {
    add("symbol list", state.symbols.length === 50, String(state.symbols.length));
    add("chart canvas", document.querySelectorAll("#price-chart canvas").length > 0, state.active);
    add("strategy menu", state.strategies.length >= 55, String(state.strategies.length));
    add("indicator menu", state.indicators.length >= 124, String(state.indicators.length));
    const bars = await api(`/api/bars?symbol=${encodeURIComponent(state.active)}`);
    add("selected bars", bars.bars.length > 50, String(bars.bars.length));
    const report = await api("/api/verify");
    const hooks = [...client, ...report.hooks];
    showInsight(report.ok && client.every((item) => item.ok) ? "Verification passed" : "Verification found gaps", `
      <table><thead><tr><th>Hook</th><th>Result</th><th>Detail</th></tr></thead><tbody>
      ${hooks.map((item) => `<tr><td>${esc(item.name)}</td><td class="${item.ok ? "hook-ok" : "hook-bad"}">${item.ok ? "Pass" : "Fail"}</td><td>${esc(item.detail ?? "")}</td></tr>`).join("")}
      </tbody></table>`);
  } catch (error) {
    showInsight("Verification", `<p>${esc(error.message)}</p>`);
  } finally {
    button.disabled = false;
    button.textContent = "Verify";
  }
}

function bind() {
  bindComboMenu();
  $("active-studies").addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove]");
    if (remove) return removeInstance(remove.dataset.remove);
    const copy = event.target.closest("[data-copy]");
    if (copy) return copyInstance(copy.dataset.copy);
    const preset = event.target.closest("[data-preset]");
    if (preset) {
      const [uid, value] = preset.dataset.preset.split(":");
      const study = state.activeStudies.find((item) => item.uid === uid);
      if (!study) return;
      study.values.length = Number(value);
      state.focus = study.id;
      renderLibrary();
      refreshStudies().catch((error) => { $("ohlc-legend").textContent = error.message; });
    }
  });
  $("active-studies").addEventListener("change", (event) => {
    const input = event.target.closest("[data-study-param]");
    if (!input) return;
    const [uid, key] = input.dataset.studyParam.split(":");
    const study = state.activeStudies.find((item) => item.uid === uid);
    if (!study) return;
    const param = study.params.find((item) => item.key === key);
    let value = Number(input.value);
    if (!Number.isFinite(value)) value = param.default;
    value = Math.min(param.max, Math.max(param.min, value));
    study.values[key] = value;
    state.focus = study.id;
    renderLibrary();
    refreshStudies().catch((error) => { $("ohlc-legend").textContent = error.message; });
  });
  $("ranges").addEventListener("click", (event) => {
    const button = event.target.closest("[data-range]");
    if (!button) return;
    state.range = button.dataset.range;
    for (const node of $("ranges").querySelectorAll("button")) node.classList.toggle("on", node === button);
    applyRange();
  });
  $("backtest-form").addEventListener("submit", runBacktest);
  $("backtest-form").addEventListener("change", (event) => {
    if (event.target.closest("[data-strategy-param], #capital, #cost-bps")) scheduleExplain($("strategy-select").value);
  });
  $("explain-toggle").addEventListener("click", () => {
    state.explainOpen = !state.explainOpen;
    $("explain").classList.toggle("collapsed", !state.explainOpen);
    $("explain-toggle").textContent = state.explainOpen ? "Hide" : "Show";
  });
  $("harm-btn").addEventListener("click", runHarmonics);
  $("trend-btn").addEventListener("click", runTrend);
  $("scan-50").addEventListener("click", runScan);
  $("fund-btn").addEventListener("click", runFundamentals);
  $("verify-btn").addEventListener("click", runVerify);
  $("insight-close").addEventListener("click", () => $("insight").classList.add("hidden"));
  $("studies-toggle").addEventListener("click", () => {
    $("controls").classList.toggle("open");
  });
  $("sync-btn").addEventListener("click", async () => {
    await api("/api/sync", { method: "POST" });
    state.barCache.clear();
    refreshStatus();
  });
  $("tester-toggle").addEventListener("click", () => {
    $("tester").classList.toggle("collapsed");
    $("tester-body").classList.toggle("hidden");
    $("tester-toggle").textContent = $("tester").classList.contains("collapsed") ? "Show" : "Hide";
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement.tagName !== "INPUT") {
      event.preventDefault();
      $("stock-combo").querySelector("input").focus();
    }
  });
}

async function boot() {
  bind();
  const [symbols, indicators, strategies] = await Promise.all([
    api("/api/symbols"),
    api("/api/indicators"),
    api("/api/strategies"),
  ]);
  state.symbols = symbols.symbols;
  state.indicators = indicators.indicators;
  state.sections = indicators.sections;
  state.strategies = strategies.strategies;
  const carney = state.indicators.find((item) => item.id === "carney");
  if (carney && !state.activeStudies.some((item) => item.id === "carney")) {
    state.activeStudies.push(newStudy(carney));
  }
  buildControls();
  renderLibrary();
  renderStrategies();
  await loadBars(state.symbols.some((row) => row.symbol === "RELIANCE") ? "RELIANCE" : state.symbols[0].symbol);
  refreshStatus();
}

boot().catch((error) => {
  $("ohlc-legend").textContent = error.message;
});
