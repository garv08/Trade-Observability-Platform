"use strict";

const $ = (id) => document.getElementById(id);
const esc = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (v, d = 1) => (v == null ? "–" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : ""}${num(v, d)}%`);
const cls = (v) => (v == null ? "" : v > 0 ? "up" : v < 0 ? "down" : "");
const CHART = {
  autoSize: true,
  layout: { background: { color: "#131722" }, textColor: "#8b90a0" },
  grid: { vertLines: { color: "#1c2030" }, horzLines: { color: "#1c2030" } },
  rightPriceScale: { borderColor: "#2a2e39" },
  timeScale: { borderColor: "#2a2e39" },
};
const state = { strategies: [], charts: null };

async function api(path, body) {
  const response = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  let data = {};
  try { data = await response.json(); } catch (_) { /* non-JSON */ }
  if (response.status === 404) throw new Error("This TOP server is older than this page. Restart top-platform after updating.");
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  return data;
}

function spec() {
  return state.strategies.find((s) => s.id === $("pf-strategy").value) || state.strategies[0];
}

function onStrategy() {
  const s = spec();
  $("pf-universe").value = s.universe;
  $("pf-n").value = s.top_n;
  $("pf-value").value = ["sectors", "nifty50"].includes(s.universe) ? 0 : 10;
  $("pf-blurb").innerHTML = `${esc(s.blurb)} Idea from ${s.sources.map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(s.creator)}${s.sources.length > 1 ? ` (${i + 1})` : ""}</a>`).join(", ")}, re-implemented by TOP.`;
}

function body(sweep) {
  return {
    strategy: $("pf-strategy").value, universe: $("pf-universe").value, top_n: Number($("pf-n").value),
    min_value: $("pf-value").value === "" ? null : Number($("pf-value").value), gate: $("pf-gate").value,
    cost_bps: Number($("pf-cost").value), capital: Number($("pf-capital").value), sweep,
  };
}

function charts() {
  if (state.charts) return state.charts;
  const eq = LightweightCharts.createChart($("pf-equity"), CHART);
  const uw = LightweightCharts.createChart($("pf-underwater"), CHART);
  state.charts = {
    eq, uw,
    equity: eq.addAreaSeries({ lineColor: "#2962ff", topColor: "rgba(41,98,255,0.28)", bottomColor: "rgba(41,98,255,0.02)", priceLineVisible: false }),
    bench: eq.addLineSeries({ color: "#8b90a0", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
    under: uw.addAreaSeries({ lineColor: "#f23645", topColor: "rgba(242,54,69,0.05)", bottomColor: "rgba(242,54,69,0.35)", priceLineVisible: false, invertFilledArea: true }),
  };
  return state.charts;
}

function render(out) {
  const m = out.metrics || {};
  const b = m.benchmark || {};
  const cards = [
    ["CAGR", pct(m.cagr_pct), m.cagr_pct, `Nifty ${pct(b.cagr_pct)}`],
    ["Max drawdown", pct(m.max_drawdown_pct), m.max_drawdown_pct, `Nifty ${pct(b.max_drawdown_pct)}`],
    ["CAGR ÷ |DD|", num(m.cagr_dd, 2), null, `Nifty ${num(b.cagr_dd, 2)}`],
    ["Total return", pct(m.total_return_pct, 0), m.total_return_pct, `Nifty ${pct(b.total_return_pct, 0)}`],
    ["Sharpe", num(m.sharpe, 2), null, `Nifty ${num(b.sharpe, 2)}`],
    ["Turnover / month", `${num(m.avg_turnover_pct, 0)}%`, null, `${m.rebalances || 0} rebalances`],
    ["Names held", num(m.avg_holdings, 1), null, `of ${num(out.members, 0)} in ${esc(out.universe_label)}`],
    ["Period", `${num(m.years, 1)} y`, null, `${esc(out.start)} → ${esc(out.end)}`],
  ];
  $("pf-metrics").innerHTML = cards.map(([label, value, signed, sub]) => `<div class="card"><span>${label}</span><b class="${typeof signed === "number" ? cls(signed) : ""}">${value}</b><span>${sub}</span></div>`).join("");
  const c = charts();
  c.equity.setData(out.equity);
  c.bench.setData(out.benchmark || []);
  c.under.setData(out.underwater || []);
  c.eq.timeScale().fitContent();
  c.uw.timeScale().fitContent();
  const deskUniverse = out.universe === "sectors" ? "index" : out.universe === "etf" ? "etf" : out.universe === "nifty50" ? "nifty50" : "bse";
  $("pf-holdings").innerHTML = (out.holdings || []).map((h) => `<tr data-href="/?symbol=${encodeURIComponent(h.symbol)}&universe=${deskUniverse}">
    <td class="l"><b>${esc(h.symbol)}</b><small>${esc(h.name)}</small></td><td>${num(h.close, 2)}</td><td class="${cls(h.ret_since_pct)}">${pct(h.ret_since_pct)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="empty">In cash.</td></tr>`;
  $("pf-log").innerHTML = (out.rebalances || []).slice().reverse().map((r) => `<tr title="${esc(r.holdings.join(", "))}">
    <td class="l">${esc(r.decided)}</td><td class="l">${esc(r.traded)}</td><td>${r.holdings.length}</td><td>${num(r.cash_pct, 0)}%</td></tr>`).join("");
  $("pf-method").textContent = out.methodology || "";
  if (out.sweep) {
    $("pf-sweep-card").style.display = "";
    $("pf-sweep-body").innerHTML = out.sweep.map((r) => `<tr class="${r.top_n === out.top_n ? "amber" : ""}"><td>${r.top_n}</td>
      <td class="${cls(r.cagr_pct)}">${pct(r.cagr_pct)}</td><td class="down">${pct(r.max_drawdown_pct)}</td><td>${num(r.cagr_dd, 2)}</td><td>${num(r.return_dd, 2)}</td>
      <td>${num(r.sharpe, 2)}</td><td>${num(r.avg_turnover_pct, 0)}%</td></tr>`).join("");
  }
  const q = new URLSearchParams({ strategy: out.strategy, universe: out.universe, n: out.top_n, gate: out.gate });
  history.replaceState(null, "", `?${q}`);
}

async function run(sweep) {
  const button = sweep ? $("pf-sweep") : $("pf-run");
  const label = button.textContent;
  $("pf-run").disabled = $("pf-sweep").disabled = true;
  button.textContent = sweep ? "Sweeping…" : "Running…";
  $("pf-method").textContent = "Loading prices for the whole universe can take 10–20 seconds the first time.";
  try {
    render(await api("/api/portfolio", body(sweep)));
  } catch (error) {
    $("pf-metrics").innerHTML = `<div class="card down">${esc(error.message)}</div>`;
  } finally {
    $("pf-run").disabled = $("pf-sweep").disabled = false;
    button.textContent = label;
  }
}

async function init() {
  $("pf-sweep-card").style.display = "none";
  try {
    const cat = await api("/api/portfolio/strategies");
    state.strategies = cat.strategies;
    $("pf-strategy").innerHTML = cat.strategies.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
    $("pf-universe").innerHTML = Object.entries(cat.universes).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("");
    $("pf-gate").innerHTML = Object.entries(cat.gates).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("");
    const q = new URLSearchParams(location.search);
    if (q.get("strategy") && cat.strategies.some((s) => s.id === q.get("strategy"))) $("pf-strategy").value = q.get("strategy");
    onStrategy();
    if (q.get("universe") && cat.universes[q.get("universe")]) $("pf-universe").value = q.get("universe");
    if (q.get("n")) $("pf-n").value = q.get("n");
    if (q.get("gate") && cat.gates[q.get("gate")]) $("pf-gate").value = q.get("gate");
  } catch (error) {
    $("pf-metrics").innerHTML = `<div class="card down">${esc(error.message)}</div>`;
    return;
  }
  $("pf-strategy").addEventListener("change", onStrategy);
  $("pf-form").addEventListener("submit", (event) => { event.preventDefault(); run(false); });
  $("pf-sweep").addEventListener("click", () => run(true));
  document.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-href]");
    if (row) window.open(row.dataset.href, "_blank", "noopener");
  });
  run(false);
}

init();
