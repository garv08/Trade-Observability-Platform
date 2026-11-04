"use strict";

const $ = (id) => document.getElementById(id);
const CHIPS = [["all", "All"], ["nifty50", "Nifty 50"], ["index", "Indices"], ["etf", "ETFs"], ["nse", "NSE"], ["bse", "BSE"]];
const UNIVERSE_LABEL = { nifty50: "Nifty 50", nse_index: "NSE index", bse_index: "BSE index", nse_etf: "NSE ETF", bse_etf: "BSE ETF", nse: "NSE", bse: "BSE" };
const PAGE = 100;
const state = { view: "scripts", universe: "all", offset: 0, strategies: {}, last: null, timer: null, loading: false };

const esc = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (v, d = 1) => (v == null ? "–" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : ""}${num(v, d)}%`);
const cls = (v) => (v == null ? "" : v > 0 ? "up" : v < 0 ? "down" : "");

async function api(path, options) {
  const response = await fetch(path, options);
  let data = {};
  try { data = await response.json(); } catch (_) { /* non-JSON error page */ }
  if (response.status === 404 && path.startsWith("/api/leaderboard")) {
    throw new Error("This TOP server is older than this page. Stop top-platform (Ctrl+C) and start it again after updating.");
  }
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  return data;
}

function setRunnable(enabled, label) {
  $("run-btn").disabled = !enabled;
  $("force-btn").disabled = !enabled;
  $("stop-btn").disabled = enabled;
  if (label) $("run-btn").textContent = label;
}

function params(extra = {}) {
  const q = new URLSearchParams({
    universe: state.universe,
    min_cagr: $("f-cagr").value === "" ? "none" : $("f-cagr").value,
    min_trades: $("f-trades").value || "0",
    min_years: $("f-years").value || "0",
    min_value: $("f-value").value || "0",
    min_dsr: $("f-dsr").value || "0",
    sort: $("f-sort").value,
    limit: String(PAGE),
    offset: String(state.offset),
  });
  if ($("f-strategy").value) q.set("strategy", $("f-strategy").value);
  if ($("f-q").value.trim()) q.set("q", $("f-q").value.trim());
  if ($("f-best").checked) q.set("best", "1");
  for (const [k, v] of Object.entries(extra)) q.set(k, v);
  return q;
}

function saveUrl() {
  const q = params();
  if (state.view === "strategies") { q.set("view", "strategies"); q.set("ssort", $("f-ssort").value); }
  q.delete("limit");
  if (state.offset === 0) q.delete("offset");
  history.replaceState(null, "", `?${q}`);
}

function restoreUrl() {
  const q = new URLSearchParams(location.search);
  if (CHIPS.some(([k]) => k === q.get("universe"))) state.universe = q.get("universe");
  if (q.get("view") === "strategies") state.view = "strategies";
  if (q.has("ssort")) $("f-ssort").value = q.get("ssort");
  if (q.has("min_cagr")) $("f-cagr").value = q.get("min_cagr") === "none" ? "" : q.get("min_cagr");
  if (q.has("min_trades")) $("f-trades").value = q.get("min_trades");
  if (q.has("min_years")) $("f-years").value = q.get("min_years");
  if (q.has("min_value")) $("f-value").value = q.get("min_value");
  if (q.has("min_dsr") && q.get("min_dsr") !== "0") $("f-dsr").value = q.get("min_dsr");
  if (q.has("sort")) $("f-sort").value = q.get("sort");
  if (q.has("q")) $("f-q").value = q.get("q");
  if (q.get("best") === "1") $("f-best").checked = true;
  state.offset = Math.max(0, Number(q.get("offset") || 0));
  state.pendingStrategy = q.get("strategy") || "";
}

function renderChips(counts = {}) {
  $("lb-chips").innerHTML = CHIPS.map(([key, label]) =>
    `<button type="button" data-u="${key}" class="${key === state.universe ? "on" : ""}">${label}<em>${counts[key] != null ? counts[key].toLocaleString("en-IN") : ""}</em></button>`).join("");
}

function renderStatus(st, computed) {
  const running = st.running === true;
  setRunnable(!running, running ? "Running…" : computed && computed.symbols ? "Run / resume" : "Run backtests");
  if (computed) {
    $("st-scripts").textContent = computed.symbols.toLocaleString("en-IN");
    $("st-rows").textContent = computed.rows.toLocaleString("en-IN");
    $("st-data").textContent = computed.data_to || "–";
  }
  if (running) {
    const eta = st.eta_seconds;
    $("st-eta").textContent = eta == null ? "estimating" : eta > 3600 ? `${(eta / 3600).toFixed(1)} h` : `${Math.ceil(eta / 60)} min`;
    $("st-eta-label").textContent = `time left · ${st.rate_per_min ?? "–"}/min`;
    $("st-bar").style.width = st.total ? `${(100 * st.done / st.total).toFixed(1)}%` : "0";
  } else {
    $("st-eta").textContent = st.finished ? st.finished.replace("T", " ").slice(0, 16) : "–";
    $("st-eta-label").textContent = st.finished ? "last run finished" : "time left";
    $("st-bar").style.width = st.total && st.done ? `${(100 * st.done / st.total).toFixed(1)}%` : computed && computed.symbols ? "100%" : "0";
  }
  const hint = !running && !(computed && computed.symbols)
    ? "No results yet. Run backtests computes all strategies on every script in the background (several hours on a slow PC); results appear here as they are stored and the run can be stopped and resumed."
    : "";
  $("st-msg").textContent = [st.message && st.message !== "idle" ? st.message : "", st.skipped ? `${st.skipped.toLocaleString("en-IN")} already current` : "", st.excluded ? `${st.excluded.toLocaleString("en-IN")} skipped for bad or thin data` : "", hint].filter(Boolean).join(" · ");
}

function rowHtml(r, i) {
  const s = state.strategies[r.strategy] || { name: r.strategy, section: "" };
  const universe = r.universe || "nifty50";
  const chip = { nse_index: "index", bse_index: "index", nse_etf: "etf", bse_etf: "etf", nse: "nse", bse: "bse" }[universe] || "nifty50";
  const href = `/?symbol=${encodeURIComponent(r.symbol)}&strategy=${encodeURIComponent(r.strategy)}&universe=${chip}&run=backtest`;
  return `<tr data-href="${esc(href)}" title="Open ${esc(r.symbol)} with ${esc(s.name)} on the chart">
    <td>${state.offset + i + 1}</td>
    <td class="l sym"><b>${esc(r.symbol)}<span class="tag">${esc(UNIVERSE_LABEL[universe] || universe)}</span>${r.in_position ? '<span class="tag in" title="The rule is long on the last bar">in now</span>' : ""}</b><small>${esc(r.name || "")}</small></td>
    <td class="l strat"><b>${esc(s.name)}</b><small>${esc(s.section || "")}${s.creator && s.creator !== s.section ? ` · ${esc(s.creator)}` : ""}</small></td>
    <td class="ratio">${num(r.ratio, 2)}</td>
    <td class="ratio">${num(r.return_dd, 2)}</td>
    <td title="Probabilistic / deflated Sharpe">${r.psr_pct == null ? "–" : `${num(r.psr_pct, 0)}%`} / <b class="${r.dsr_pct >= 95 ? "up" : r.dsr_pct < 50 ? "down" : ""}">${r.dsr_pct == null ? "–" : `${num(r.dsr_pct, 0)}%`}</b></td>
    <td class="${cls(r.cagr_pct)}">${pct(r.cagr_pct)}</td>
    <td class="down">${num(r.max_dd_pct)}%</td>
    <td class="${cls(r.total_return_pct)}">${pct(r.total_return_pct, 0)}</td>
    <td class="${cls(r.buy_hold_pct)}">${pct(r.buy_hold_pct, 0)}</td>
    <td>${r.trades}</td>
    <td>${r.win_rate_pct == null ? "–" : `${num(r.win_rate_pct, 0)}%`}</td>
    <td>${num(r.sharpe, 2)}</td>
    <td>${r.exposure_pct == null ? "–" : `${num(r.exposure_pct, 0)}%`}</td>
    <td>${num(r.years, 1)}</td>
  </tr>`;
}

function renderTable(data) {
  const body = $("lb-body");
  if (!data.rows.length) {
    body.innerHTML = `<tr><td colspan="15" class="empty">${data.computed.rows ? "No backtests pass these filters. Lower the minimum CAGR or history, or pick another universe." : "Nothing computed yet. Press Run backtests above."}</td></tr>`;
  } else {
    body.innerHTML = data.rows.map(rowHtml).join("");
  }
  const sort = $("f-sort").value;
  document.querySelectorAll(".lb-table th[data-sort]").forEach((th) => th.classList.toggle("sorted", th.dataset.sort === sort));
  const end = Math.min(state.offset + PAGE, data.total);
  $("page-label").textContent = data.total ? `${(state.offset + 1).toLocaleString("en-IN")}–${end.toLocaleString("en-IN")} of ${data.total.toLocaleString("en-IN")}` : "";
  $("prev-btn").disabled = state.offset === 0;
  $("next-btn").disabled = end >= data.total;
  const cagr = $("f-cagr").value;
  $("lb-summary").innerHTML = data.computed.rows
    ? `<span><b>${data.total.toLocaleString("en-IN")}</b> backtests on <b>${data.symbols.toLocaleString("en-IN")}</b> scripts pass${cagr !== "" ? ` CAGR &gt; ${esc(cagr)}%` : ""}, ≥ ${esc($("f-trades").value || 0)} trades, ≥ ${esc($("f-years").value || 0)} years tested${Number($("f-value").value) > 0 ? `, ≥ ₹${esc($("f-value").value)} lakh traded a day` : ""}${Number($("f-dsr").value) > 0 ? `, deflated Sharpe ≥ ${esc($("f-dsr").value)}%` : ""}.</span>`
    : "";
}

function renderByStrategy(rows) {
  const box = $("by-strategy");
  if (!rows.length) { box.textContent = "–"; return; }
  box.innerHTML = rows.slice(0, 20).map((r) => {
    const s = state.strategies[r.strategy] || { name: r.strategy, section: "" };
    return `<div class="row" data-strategy="${esc(r.strategy)}" title="Show only ${esc(s.name)}">
      <div><b>${esc(s.name)}</b><small>${esc(s.section)} · median CAGR ${pct(r.median_cagr, 0)}, DD ${num(r.median_dd, 0)}%</small></div>
      <div class="n"><b>${r.scripts.toLocaleString("en-IN")}</b><small>ratio ${num(r.median_ratio, 2)}</small></div>
    </div>`;
  }).join("");
}

function strategyParams() {
  const q = params();
  for (const key of ["min_cagr", "strategy", "q", "best", "limit", "offset", "sort", "min_dsr"]) q.delete(key);
  q.set("sort", $("f-ssort").value);
  return q;
}

function renderView() {
  const strategies = state.view === "strategies";
  document.querySelectorAll("#lb-views [data-view]").forEach((b) => b.classList.toggle("on", b.dataset.view === state.view));
  $("strat-wrap").classList.toggle("hidden", !strategies);
  $("script-wrap").classList.toggle("hidden", strategies);
  document.querySelector(".pager").querySelectorAll("#prev-btn, #next-btn, #page-label").forEach((n) => n.classList.toggle("hidden", strategies));
  for (const id of ["l-cagr", "l-strategy", "l-sort", "l-q", "l-best", "l-dsr"]) $(id).classList.toggle("hidden", strategies);
  $("l-ssort").classList.toggle("hidden", !strategies);
}

function renderStrategies(rows) {
  const body = $("strat-body");
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="14" class="empty">${state.last && state.last.computed.rows ? "No strategy has 50+ scripts passing these filters. Lower Min trades, tested years, or daily value." : "Nothing computed yet. Press Run backtests above."}</td></tr>`;
    $("lb-summary").innerHTML = "";
    return;
  }
  body.innerHTML = rows.map((r) => {
    const s = state.strategies[r.strategy] || {};
    return `<tr data-strategy="${esc(r.strategy)}" title="Show every script for ${esc(r.strategy_name)}">
      <td>${r.rank}</td>
      <td class="l strat"><b>${esc(r.strategy_name)}</b><small>${esc(r.section)}${r.creator && r.creator !== r.section ? ` · ${esc(r.creator)}` : ""}</small></td>
      <td>${Number(r.scripts).toLocaleString("en-IN")}</td>
      <td class="ratio">${num(r.median_return_dd, 2)}</td>
      <td>${num(r.mean_return_dd, 2)}</td>
      <td>${num(r.p25_return_dd, 2)} – ${num(r.p75_return_dd, 2)}</td>
      <td class="${cls(r.median_return_pct)}">${pct(r.median_return_pct, 0)}</td>
      <td class="down">${num(r.median_max_dd_pct, 1)}%</td>
      <td class="${cls(r.median_cagr_pct)}">${pct(r.median_cagr_pct)}</td>
      <td>${num(r.pct_profitable, 0)}%</td>
      <td>${num(r.pct_beat_hold, 0)}%</td>
      <td>${num(r.pct_dsr95, 1)}%</td>
      <td>${num(r.median_trades, 0)}</td>
      <td class="l sym"><b>${esc(r.best_symbol || "")}</b><small>return ÷ DD ${num(r.best_return_dd, 1)}</small></td>
    </tr>`;
  }).join("");
  const n = rows.reduce((max, r) => Math.max(max, r.scripts), 0);
  $("lb-summary").innerHTML = `<span><b>${rows.length}</b> strategies ranked by ${esc($("f-ssort").selectedOptions[0].textContent)} across up to <b>${n.toLocaleString("en-IN")}</b> scripts with ≥ ${esc($("f-trades").value || 0)} trades, ≥ ${esc($("f-years").value || 0)} years tested${Number($("f-value").value) > 0 ? `, ≥ ₹${esc($("f-value").value)} lakh traded a day` : ""}. No CAGR cut: losing scripts count. Click a strategy to see its scripts.</span>`;
}

async function load() {
  if (state.loading) { state.again = true; return; }
  state.loading = true;
  saveUrl();
  renderView();
  try {
    const data = await api(`/api/leaderboard?${params(state.view === "strategies" ? { limit: "1" } : {})}`);
    state.last = data;
    renderChips(data.universes);
    renderStatus(data.status, data.computed);
    if (state.view === "strategies") {
      const ranked = await api(`/api/leaderboard/strategies?${strategyParams()}`);
      renderStrategies(ranked.strategies);
    } else {
      renderTable(data);
    }
    renderByStrategy(data.by_strategy);
    schedule(data.status.running);
  } catch (error) {
    $("lb-body").innerHTML = `<tr><td colspan="15" class="empty">${esc(error.message)}</td></tr>`;
    $("st-msg").textContent = error.message;
    setRunnable(true);
    schedule(true);
  } finally {
    state.loading = false;
    if (state.again) { state.again = false; load(); }
  }
}

function schedule(running) {
  clearTimeout(state.timer);
  if (running) state.timer = setTimeout(load, 15000);
}

function reload() {
  state.offset = 0;
  load();
}

async function control(body) {
  if (body.action !== "stop") setRunnable(false, "Starting…");
  try {
    const st = await api("/api/leaderboard", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    renderStatus(st, state.last && state.last.computed);
  } catch (error) {
    $("st-msg").textContent = `Could not ${body.action === "stop" ? "stop" : "start"} the run: ${error.message}`;
    setRunnable(true, "Run backtests");
  }
  setTimeout(load, 1500);
}

function downloadCsv() {
  if (state.view === "strategies") {
    const link = document.createElement("a");
    link.href = `/api/leaderboard/strategies.csv?${strategyParams()}`;
    link.download = "top-strategy-ranking.csv";
    link.click();
    return;
  }
  const q = params();
  q.delete("limit");
  q.delete("offset");
  const link = document.createElement("a");
  link.href = `/api/leaderboard.csv?${q}`;
  link.download = `top-leaderboard-${state.universe}.csv`;
  link.click();
}

async function init() {
  restoreUrl();
  renderChips();
  try {
    const data = await api("/api/strategies");
    const select = $("f-strategy");
    const sections = {};
    for (const s of data.strategies) {
      state.strategies[s.id] = s;
      (sections[s.section] ||= []).push(s);
    }
    select.innerHTML = '<option value="">All strategies</option>' + Object.entries(sections).map(([section, items]) =>
      `<optgroup label="${esc(section)}">${items.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</optgroup>`).join("");
    select.value = state.pendingStrategy || "";
  } catch (error) {
    $("st-msg").textContent = error.message;
  }
  $("lb-views").addEventListener("click", (event) => {
    const button = event.target.closest("[data-view]");
    if (!button || button.dataset.view === state.view) return;
    state.view = button.dataset.view;
    reload();
  });
  $("f-ssort").addEventListener("change", reload);
  $("strat-body").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-strategy]");
    if (!row) return;
    $("f-strategy").value = row.dataset.strategy;
    $("f-cagr").value = "";
    state.view = "scripts";
    reload();
  });
  $("lb-chips").addEventListener("click", (event) => {
    const button = event.target.closest("[data-u]");
    if (!button) return;
    state.universe = button.dataset.u;
    reload();
  });
  for (const id of ["f-cagr", "f-trades", "f-years", "f-value", "f-dsr"]) {
    let timer;
    $(id).addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(reload, 400); });
  }
  for (const id of ["f-strategy", "f-sort", "f-best"]) $(id).addEventListener("change", reload);
  let searchTimer;
  $("f-q").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(reload, 350); });
  document.querySelectorAll(".lb-table th[data-sort]").forEach((th) => th.addEventListener("click", () => { $("f-sort").value = th.dataset.sort; reload(); }));
  $("lb-body").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-href]");
    if (row) window.open(row.dataset.href, "_blank", "noopener");
  });
  $("by-strategy").addEventListener("click", (event) => {
    const row = event.target.closest("[data-strategy]");
    if (!row) return;
    $("f-strategy").value = row.dataset.strategy;
    reload();
  });
  $("prev-btn").addEventListener("click", () => { state.offset = Math.max(0, state.offset - PAGE); load(); });
  $("next-btn").addEventListener("click", () => { state.offset += PAGE; load(); });
  $("run-btn").addEventListener("click", () => control({ action: "start" }));
  $("stop-btn").addEventListener("click", () => control({ action: "stop" }));
  $("force-btn").addEventListener("click", () => {
    if (confirm("Recompute every strategy on every script? This takes several hours.")) control({ action: "start", force: true });
  });
  $("csv-btn").addEventListener("click", downloadCsv);
  load();
}

init();
