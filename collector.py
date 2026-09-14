"""ARGUS TELEMETRY COLLECTOR - the eye's first live nerve. Stage B.

Runs on GitHub Actions every ~30 minutes. Reads PUBLIC market data
only, writes one JSON line per pass to data/telemetry.jsonl, and
touches nothing else. No keys, no wallet, no trading - the worst this
file could ever leak is public numbers.

What it records per pass (the tempo-bridge diet, factory queue #9):
  - meme sector total cap, 24h volume, 24h cap change (CoinGecko
    category "meme-token")
  - breadth: of the top 50 meme coins, how many are green on 24h
  - average 7d change of the top 50, and the top 10 symbols
Failures are recorded INSIDE the row (an _errors list), never hidden:
silence is informative, so a blind pass testifies to its blindness.

  python3 collector.py             # one pass (the Action runs this)
  python3 collector.py --selftest  # fixtures only, no network
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "telemetry.jsonl"
UA = {"User-Agent": "argus-telemetry/0.1 (research; contact via repo)"}
DEDUP_SECONDS = 20 * 60

CATEGORIES_URL = "https://api.coingecko.com/api/v3/coins/categories"
MARKETS_URL = ("https://api.coingecko.com/api/v3/coins/markets"
               "?vs_currency=usd&category=meme-token"
               "&order=market_cap_desc&per_page=50&page=1"
               "&price_change_percentage=24h,7d")


MAX_BODY = 4 * 1024 * 1024   # a category list is kilobytes; megabytes is an attack


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(MAX_BODY + 1)
    if len(body) > MAX_BODY:
        raise ValueError("response too large")
    # NaN/Infinity are not JSON; a source that sends them gets None, not
    # a number that poisons every comparison downstream
    return json.loads(body.decode(), parse_constant=lambda _c: None)


def _num(x):
    """A finite number or None. Strings, bools, NaN, and objects are None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return x if x == x and abs(x) != float("inf") else None


def sector_fields(categories):
    """The meme category row from /coins/categories."""
    if not isinstance(categories, list):
        raise ValueError("categories: not a list")
    for c in categories:
        if isinstance(c, dict) and (c.get("id") == "meme-token"
                                    or c.get("name") == "Meme"):
            return {"sector_cap": _num(c.get("market_cap")),
                    "sector_vol24": _num(c.get("volume_24h")),
                    "sector_cap_chg24_pct": _num(c.get("market_cap_change_24h"))}
    raise ValueError("meme category not found in response")


def breadth_fields(markets):
    """Breadth and leaders from the top-50 meme coins."""
    if not isinstance(markets, list):
        raise ValueError("markets: not a list")
    rows = [m for m in markets if isinstance(m, dict)]
    if not rows:
        raise ValueError("empty markets response")
    chg24 = [_num(m.get("price_change_percentage_24h")) for m in rows]
    chg24 = [x for x in chg24 if x is not None]
    chg7 = [_num(m.get("price_change_percentage_7d_in_currency")) for m in rows]
    chg7 = [x for x in chg7 if x is not None]
    return {"n_tracked": len(rows),
            "breadth_pos24": sum(1 for x in chg24 if x > 0),
            "avg_chg7_pct": round(sum(chg7) / len(chg7), 3) if chg7 else None,
            "top10": [str(m.get("symbol", "?"))[:16].upper() for m in rows[:10]]}


def build_row(now=None, fetch=_get_json):
    """One telemetry line. Every source failure lands in _errors, and
    the row is written anyway - a half-blind pass is still a pass."""
    row = {"ts": now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "source": "coingecko-public", "_errors": []}
    try:
        row.update(sector_fields(fetch(CATEGORIES_URL)))
    except Exception as e:
        row["_errors"].append("sector: %s %s" % (type(e).__name__, str(e)[:60]))
    try:
        row.update(breadth_fields(fetch(MARKETS_URL)))
    except Exception as e:
        row["_errors"].append("breadth: %s %s" % (type(e).__name__, str(e)[:60]))
    return row


def last_row_ts(path):
    if not path.exists():
        return None
    last = ""
    with open(path) as f:
        for last in f:
            pass
    try:
        return json.loads(last)["ts"]
    except Exception:
        return None


def append_row(row, path=None):
    """Torn-line safe, duplicate-shy: a re-run inside the dedup window
    writes nothing. Returns True when a line landed."""
    p = Path(path) if path else OUT
    prev = last_row_ts(p)
    if prev:
        try:
            prev_t = time.mktime(time.strptime(prev, "%Y-%m-%dT%H:%M:%SZ"))
            now_t = time.mktime(time.strptime(row["ts"], "%Y-%m-%dT%H:%M:%SZ"))
            if 0 <= now_t - prev_t < DEDUP_SECONDS:
                return False
        except Exception:
            pass
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    return True


def run():
    row = build_row()
    landed = append_row(row)
    ok = "ok" if not row["_errors"] else "PARTIAL(%d errs)" % len(row["_errors"])
    print("argus-telemetry: %s cap=%s breadth=%s/%s %s landed=%s"
          % (row["ts"], row.get("sector_cap"), row.get("breadth_pos24"),
             row.get("n_tracked"), ok, landed))
    for e in row["_errors"]:
        print("  err:", e)


# ---------------------------------------------------------------- selftest

FIX_CATS = [{"id": "ai-agents", "name": "AI Agents", "market_cap": 1.0},
            {"id": "meme-token", "name": "Meme", "market_cap": 31e9,
             "volume_24h": 2.4e9, "market_cap_change_24h": -4.3}]
FIX_MKTS = ([{"symbol": "doge", "price_change_percentage_24h": 2.0,
              "price_change_percentage_7d_in_currency": 11.7}] * 30
            + [{"symbol": "bonk", "price_change_percentage_24h": -3.0,
                "price_change_percentage_7d_in_currency": -5.0}] * 20)


def selftest():
    import tempfile
    s = sector_fields(FIX_CATS)
    assert s["sector_cap"] == 31e9 and s["sector_cap_chg24_pct"] == -4.3
    b = breadth_fields(FIX_MKTS)
    assert b["n_tracked"] == 50 and b["breadth_pos24"] == 30
    assert abs(b["avg_chg7_pct"] - (30 * 11.7 - 20 * 5.0) / 50) < 1e-6
    assert b["top10"][0] == "DOGE"

    def fake(url):
        return FIX_CATS if "categories" in url else FIX_MKTS
    row = build_row(now="2026-08-31T20:00:00Z", fetch=fake)
    assert row["_errors"] == [] and row["sector_cap"] == 31e9

    def broken(url):
        raise OSError("network down")
    blind = build_row(now="2026-08-31T20:00:00Z", fetch=broken)
    assert len(blind["_errors"]) == 2, "a blind pass testifies to blindness"

    # hostile shapes: strings, NaN, objects where numbers belong -> None,
    # never a number that lies (audit hardening, 2026-09-02)
    hostile_cats = [{"id": "meme-token", "market_cap": "31e9",
                     "volume_24h": float("nan"), "market_cap_change_24h": {"x": 1}}]
    hs = sector_fields(hostile_cats)
    assert hs == {"sector_cap": None, "sector_vol24": None,
                  "sector_cap_chg24_pct": None}, hs
    hostile_mkts = [{"symbol": "x" * 80, "price_change_percentage_24h": "9",
                     "price_change_percentage_7d_in_currency": float("inf")}] * 6
    hb = breadth_fields(hostile_mkts)
    assert hb["breadth_pos24"] == 0 and hb["avg_chg7_pct"] is None
    assert len(hb["top10"][0]) == 16
    assert json.loads('{"a": NaN}', parse_constant=lambda _c: None) == {"a": None}

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        tmp = tf.name
    assert append_row(dict(row), tmp) is True
    near = dict(row, ts="2026-08-31T20:10:00Z")
    assert append_row(near, tmp) is False, "inside dedup window: no line"
    later = dict(row, ts="2026-08-31T20:31:00Z")
    assert append_row(later, tmp) is True
    print("SELFTEST OK - parser, blindness testimony, and dedup behave; "
          "no network was touched.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run()
