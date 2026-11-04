"use strict";

const $ = (id) => document.getElementById(id);
const esc = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (v, d = 1) => (v == null ? "–" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : ""}${num(v, d)}%`);
const cls = (v) => (v == null ? "" : v > 0 ? "up" : v < 0 ? "down" : "");
const state = { scan: new URLSearchParams(location.search).get("scan") || "bloodbath", scans: [], counts: {} };
const CHART = {
  autoSize: true,
  layout: { background: { color: "#131722" }, textColor: "#8b90a0" },
  grid: { vertLines: { color: "#1c2030" }, horzLines: { color: "#1c2030" } },
  rightPriceScale: { borderColor: "#2a2e39" },
  timeScale: { borderColor: "#2a2e39" },
};
const SHADE = { calm: "rgba(8,153,129,0.16)", normal: "rgba(139,144,160,0.06)", stressed: "rgba(242,54,69,0.18)" };

async function api(path) {
  const response = await fetch(path);
  let data = {};
  try { data = await response.json(); } catch (_) { /* non-JSON */ }
  if (response.status === 404) throw new Error("This TOP server is older than this page. Restart top-platform after updating.");
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  return data;
}

function renderRegime(regime, breadth) {
  const r = regime.latest;
  const b = breadth[breadth.length - 1] || {};
  if (!r) {
    $("regime-cards").innerHTML = `<div class="card muted">No Nifty 50 index history yet. Run Sync history on the desk.</div>`;
    return;
  }
  const stateCls = r.state === "calm" ? "up" : r.state === "stressed" ? "down" : "amber";
  const cards = [
    ["Volatility regime", `<b class="${stateCls}">${esc(r.state || "–")}</b>`, `20-day vol ${num(r.vol)}% · ${num(r.vol_pct, 0)}th pct of 1 year`],
    ["Nifty 50", `<b>${num(r.close, 0)}</b>`, `${pct(r.dd_pct)} from 52-week high · ${r.above200 ? "above" : "below"} 200-day avg`],
    ["Above 200-day avg", `<b class="${b.pct_above200 >= 50 ? "up" : "down"}">${num(b.pct_above200, 0)}%</b>`, `of ${num(b.stocks, 0)} BSE A/B stocks`],
    ["Above 50-day avg", `<b class="${b.pct_above50 >= 50 ? "up" : "down"}">${num(b.pct_above50, 0)}%</b>`, "short-term breadth"],
    ["New highs / lows", `<b class="${cls(b.nh_nl)}">${num(b.new_highs, 0)} / ${num(b.new_lows, 0)}</b>`, "52-week, today"],
    ["Advances / declines", `<b class="${cls((b.advances || 0) - (b.declines || 0))}">${num(b.advances, 0)} / ${num(b.declines, 0)}</b>`, `as of ${esc(b.time || r.time)}`],
  ];
  $("regime-cards").innerHTML = cards.map(([label, value, sub]) => `<div class="card"><span>${label}</span>${value}<span>${sub}</span></div>`).join("");
  const chart = LightweightCharts.createChart($("regime-chart"), CHART);
  const shade = chart.addHistogramSeries({ priceScaleId: "shade", priceLineVisible: false, lastValueVisible: false });
  chart.priceScale("shade").applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
  shade.setData(regime.series.filter((x) => x.state).map((x) => ({ time: x.time, value: 1, color: SHADE[x.state] })));
  const line = chart.addLineSeries({ color: "#d1d4dc", lineWidth: 2, priceLineVisible: false });
  line.setData(regime.series.map((x) => ({ time: x.time, value: x.close })));
  chart.timeScale().fitContent();
}

function renderBreadth(breadth) {
  const rows = breadth.filter((x) => x.pct_above200 != null);
  const a = LightweightCharts.createChart($("pct-chart"), CHART);
  a.addLineSeries({ color: "#2962ff", lineWidth: 2, title: "> 200d", priceLineVisible: false })
    .setData(rows.map((x) => ({ time: x.time, value: x.pct_above200 })));
  a.addLineSeries({ color: "#f2a900", lineWidth: 1, title: "> 50d", priceLineVisible: false })
    .setData(rows.filter((x) => x.pct_above50 != null).map((x) => ({ time: x.time, value: x.pct_above50 })));
  a.timeScale().fitContent();
  const b = LightweightCharts.createChart($("nhnl-chart"), CHART);
  b.addHistogramSeries({ priceLineVisible: false })
    .setData(breadth.filter((x) => x.base252 > 0).map((x) => ({ time: x.time, value: x.nh_nl, color: x.nh_nl >= 0 ? "rgba(8,153,129,0.8)" : "rgba(242,54,69,0.8)" })));
  b.timeScale().fitContent();
}

function renderSectors(rows) {
  $("sector-body").innerHTML = rows.map((r) => `<tr data-href="/?symbol=${encodeURIComponent(r.symbol)}&universe=index">
    <td class="l">${esc(r.name)}</td>
    <td class="${cls(r.rel_21)}">${pct(r.rel_21)}</td><td class="${cls(r.rel_63)}"><b>${pct(r.rel_63)}</b></td><td class="${cls(r.rel_126)}">${pct(r.rel_126)}</td>
    <td class="${cls(r.ret_63)}">${pct(r.ret_63)}</td>
    <td class="l ${r.quadrant === "Leading" ? "up" : r.quadrant === "Lagging" ? "down" : "amber"}">${esc(r.quadrant || "–")}</td></tr>`).join("")
    || `<tr><td colspan="6" class="empty">No sector index history yet. Run Sync history.</td></tr>`;
}

function renderFii(rows) {
  const byDay = {};
  for (const r of rows) (byDay[r.day] ||= {})[r.category] = r;
  const days = Object.keys(byDay).sort().reverse();
  $("fii-body").innerHTML = days.map((d) => {
    const f = byDay[d].FII || {}, k = byDay[d].DII || {};
    return `<tr><td class="l">${esc(d)}</td><td class="${cls(f.net)}">${num(f.net, 0)}</td><td class="${cls(k.net)}">${num(k.net, 0)}</td><td>${num(f.buy, 0)}</td><td>${num(f.sell, 0)}</td></tr>`;
  }).join("") || `<tr><td colspan="5" class="empty">No snapshots yet. They are saved on each Sync history.</td></tr>`;
}

function renderChips() {
  $("scan-chips").innerHTML = state.scans.map((s) =>
    `<button type="button" data-scan="${esc(s.name)}" class="${s.name === state.scan ? "on" : ""}" title="${esc(s.rule)}">${esc(s.title.split(":")[0])}<em>${state.counts[s.name] ?? ""}</em></button>`).join("");
}

async function loadScan() {
  const body = $("scan-body");
  body.innerHTML = `<tr><td colspan="9" class="empty">Scanning…</td></tr>`;
  renderChips();
  history.replaceState(null, "", `?scan=${encodeURIComponent(state.scan)}`);
  try {
    const out = await api(`/api/markets/scan?name=${encodeURIComponent(state.scan)}&min_value=${encodeURIComponent($("scan-value").value || 0)}`);
    let rule = `<b>${esc(out.title)}</b>: ${esc(out.rule)} ${out.count} found, as of ${esc(out.as_of)}.`;
    if (out.context && out.context.nifty_dd_pct != null) rule += ` Nifty is ${pct(out.context.nifty_dd_pct)} from its 52-week high${out.context.nifty_dd_pct > -5 ? " (less than 5% off, so 'leaders' means less right now)" : ""}.`;
    if (out.context && out.context.delivery_to) rule += ` Delivery data up to ${esc(out.context.delivery_to)}.`;
    $("scan-rule").innerHTML = rule;
    body.innerHTML = out.rows.map((r) => `<tr data-href="/?symbol=${encodeURIComponent(r.symbol)}&universe=bse">
      <td class="l"><b>${esc(r.symbol)}</b><span class="tag">${esc(r.group || "")}</span><small>${esc(r.name)}</small></td>
      <td>${num(r.close, 2)}</td><td class="${cls(r.change_pct)}">${pct(r.change_pct)}</td>
      <td class="${cls(r.from_high_pct)}">${pct(r.from_high_pct)}</td><td>${pct(r.from_low_pct)}</td>
      <td class="${cls(r.ret_252_pct)}">${pct(r.ret_252_pct, 0)}</td><td>${num(r.vol_ratio, 2)}×</td>
      <td>${num(r.value_lakh, 0)}</td><td>${r.delivery_pct == null ? "–" : `${num(r.delivery_pct, 0)}%`}</td></tr>`).join("")
      || `<tr><td colspan="9" class="empty">No stocks match right now.</td></tr>`;
  } catch (error) {
    body.innerHTML = `<tr><td colspan="9" class="empty">${esc(error.message)}</td></tr>`;
  }
}

async function init() {
  document.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-href]");
    if (row) window.open(row.dataset.href, "_blank", "noopener");
    const chip = event.target.closest("[data-scan]");
    if (chip) { state.scan = chip.dataset.scan; loadScan(); }
  });
  let timer;
  $("scan-value").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(async () => {
    try { state.counts = (await api(`/api/markets/overview?min_value=${encodeURIComponent($("scan-value").value || 0)}`)).counts; } catch (_) { /* keep old counts */ }
    loadScan();
  }, 500); });
  try {
    const [overview, breadth] = await Promise.all([api("/api/markets/overview"), api("/api/markets/breadth")]);
    state.scans = overview.scans;
    state.counts = overview.counts;
    if (!state.scans.some((s) => s.name === state.scan)) state.scan = state.scans[0].name;
    renderRegime(overview.regime, breadth.breadth);
    renderBreadth(breadth.breadth);
    renderSectors(overview.sectors);
    renderFii(overview.fii_dii);
    loadScan();
  } catch (error) {
    $("regime-cards").innerHTML = `<div class="card down">${esc(error.message)}</div>`;
  }
}

init();
