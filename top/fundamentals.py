"""Public Screener.in company snapshot. One polite fetch, then a short cache."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

_CACHE = {}
_TTL = 6 * 60 * 60
_ALIASES = {"M&M": ["M&M", "MM"]}


def _clean(fragment):
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", text).replace("₹", "Rs").strip()


def _candidates(symbol):
    names = _ALIASES.get(symbol, [symbol])
    out = []
    for name in names:
        if name not in out:
            out.append(name)
    return out


def _fetch_html(symbol):
    last_error = None
    names = _candidates(symbol)
    urls = [f"https://www.screener.in/company/{urllib.parse.quote(name)}/consolidated/" for name in names]
    urls += [f"https://www.screener.in/company/{urllib.parse.quote(name)}/" for name in names]
    for url in urls:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return url, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 404:
                raise
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Screener.in is unreachable: {exc.reason}") from exc
    raise RuntimeError(f"No public Screener.in page for {symbol}: {last_error}")


def parse_html(symbol, html, url):
    ratios = []
    for name, value in re.findall(
        r'<li[^>]*class="flex flex-space-between"[^>]*>.*?<span class="name">\s*(.*?)\s*</span>.*?<span class="nowrap value">(.*?)</span>',
        html,
        flags=re.S,
    ):
        label = _clean(name)
        amount = _clean(value)
        if label and amount and not any(row["label"] == label for row in ratios):
            ratios.append({"label": label, "value": amount})
    notes = {}
    for kind in ("pros", "cons"):
        match = re.search(rf'class="{kind}".*?<ul>(.*?)</ul>', html, flags=re.S)
        notes[kind] = [_clean(item) for item in re.findall(r"<li>(.*?)</li>", match.group(1) if match else "", flags=re.S)]
        notes[kind] = [item for item in notes[kind] if item]
    if not ratios:
        raise RuntimeError(f"Screener.in returned no ratios for {symbol}")
    return {
        "symbol": symbol,
        "source": "Screener.in public company page",
        "url": url,
        "ratios": ratios[:12],
        "pros": notes["pros"],
        "cons": notes["cons"],
        "note": "Machine-written pros and cons come from Screener.in. This is not advice and not a filing.",
    }


def load(symbol, screener_id=None):
    """Screener.in snapshot. screener_id is the NSE symbol, or the BSE scrip code for BSE listings."""
    now = time.time()
    cached = _CACHE.get(symbol)
    if cached and now - cached[0] < _TTL:
        return cached[1]
    url, html = _fetch_html(screener_id or symbol)
    payload = parse_html(symbol, html, url)
    _CACHE[symbol] = (now, payload)
    return payload


def parse_cached_file(path, symbol="RELIANCE"):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return parse_html(symbol, handle.read(), "file://" + path)
