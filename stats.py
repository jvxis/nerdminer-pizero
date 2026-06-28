"""Collect miner / pool / chain statistics.

Three independent sources, each fails gracefully:
  * cpuminer log  -> live hashrate + accepted/rejected shares (fork-agnostic)
  * pool stats API -> best share difficulty (the "lottery" number) + pool hashrate
  * mempool.space  -> block height, network difficulty, BTC price
"""
import os
import re
import time
import collections

import requests

# Matches "250.12 khash/s", "0.25 Mhash/s", "12345 H/s", "1.2 kH/s" ...
_HASHRATE_RE = re.compile(r"([\d.]+)\s*([kMG]?)[Hh]ash/s|([\d.]+)\s*([kMG]?)H/s")
# Matches "accepted: 12/13" (accepted / total submitted)
_ACCEPTED_RE = re.compile(r"accepted:\s*(\d+)\s*/\s*(\d+)")

_UNIT = {"": 1.0, "k": 1e3, "M": 1e6, "G": 1e9}


def _to_hs(value, unit):
    return float(value) * _UNIT.get(unit, 1.0)


def parse_cpuminer_log(path, tail_bytes=8192):
    """Return {'hashrate_hs', 'accepted', 'total'} from the tail of the log."""
    result = {"hashrate_hs": 0.0, "accepted": 0, "total": 0}
    if not path or not os.path.exists(path):
        return result
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > tail_bytes:
                fh.seek(-tail_bytes, os.SEEK_END)
            chunk = fh.read().decode("utf-8", "replace")
    except OSError:
        return result

    for line in reversed(chunk.splitlines()):
        if result["hashrate_hs"] == 0.0:
            m = _HASHRATE_RE.search(line)
            if m:
                if m.group(1) is not None:
                    result["hashrate_hs"] = _to_hs(m.group(1), m.group(2))
                else:
                    result["hashrate_hs"] = _to_hs(m.group(3), m.group(4))
        if result["total"] == 0:
            a = _ACCEPTED_RE.search(line)
            if a:
                result["accepted"] = int(a.group(1))
                result["total"] = int(a.group(2))
        if result["hashrate_hs"] and result["total"]:
            break
    return result


def fetch_pool_stats(url, api_type, timeout=15):
    """Return {'best_share', 'pool_hashrate_hs', 'workers'} from the pool API."""
    out = {"best_share": 0.0, "pool_hashrate_hs": 0.0, "workers": 0}
    if not url or api_type == "none":
        return out
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return out

    if api_type == "ckpool":
        # ckpool /users/<addr>: hashrate strings like "1.05T", bestshare float
        out["best_share"] = float(data.get("bestshare", 0) or 0)
        out["pool_hashrate_hs"] = _suffixed_to_hs(data.get("hashrate1m", "0"))
        out["workers"] = int(data.get("workers", 0) or 0)
    elif api_type == "public-pool":
        # Handles both public-pool endpoints (bestDifficulty arrives as a string on
        # one and a number on the other; float() copes with both):
        #   /api/client/<addr>          -> the whole address (all your workers)
        #   /api/client/<addr>/<worker> -> just one worker (e.g. only the Pi)
        out["best_share"] = float(data.get("bestDifficulty", 0) or 0)
        if "workers" in data:
            # address endpoint: workersCount + workers[] each with hashRate (H/s)
            out["workers"] = int(data.get("workersCount", 0) or 0)
            out["pool_hashrate_hs"] = sum(
                float(w.get("hashRate", 0) or 0) for w in (data.get("workers") or []))
        else:
            # worker endpoint: hashrate/shares live under "accounting"
            acc = data.get("accounting") or {}
            out["pool_hashrate_hs"] = float(acc.get("hashRateLast10Minutes", 0) or 0)
            out["workers"] = 1 if (out["pool_hashrate_hs"] or out["best_share"]) else 0
    return out


def _suffixed_to_hs(s):
    """ckpool hashrate like '1.05T', '930G', '12.3M' -> H/s float."""
    s = str(s).strip()
    if not s:
        return 0.0
    mult = {"K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15, "E": 1e18}
    if s[-1].upper() in mult:
        try:
            return float(s[:-1]) * mult[s[-1].upper()]
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch_chain_info(mempool_api, fiat="USD", timeout=15):
    """Return {'block_height', 'difficulty', 'price', 'fiat'}."""
    out = {"block_height": 0, "difficulty": 0.0, "price": 0.0, "fiat": fiat}
    try:
        r = requests.get(f"{mempool_api}/blocks/tip/height", timeout=timeout)
        r.raise_for_status()
        out["block_height"] = int(r.text.strip())
    except Exception:
        pass
    try:
        r = requests.get(f"{mempool_api}/v1/mining/hashrate/3d", timeout=timeout)
        r.raise_for_status()
        out["difficulty"] = float(r.json().get("currentDifficulty", 0) or 0)
    except Exception:
        pass
    if fiat and fiat != "none":
        try:
            r = requests.get(f"{mempool_api}/v1/prices", timeout=timeout)
            r.raise_for_status()
            usd = float(r.json().get("USD", 0) or 0)
            if fiat == "BRL":
                fx = requests.get(
                    "https://economia.awesomeapi.com.br/last/USD-BRL", timeout=timeout)
                fx.raise_for_status()
                usd *= float(fx.json()["USDBRL"]["bid"])
            out["price"] = usd
        except Exception:
            pass
    return out


class MinerStats:
    """Aggregates all sources and caches the slow (network) ones."""

    def __init__(self, settings):
        self.s = settings
        self.start_time = time.time()
        self.poll_seconds = settings.getint("network", "poll_seconds")
        self._last_poll = 0.0
        self.data = {
            "hashrate_hs": 0.0,
            "accepted": 0,
            "total": 0,
            "best_share": 0.0,
            "pool_hashrate_hs": 0.0,
            "workers": 0,
            "block_height": 0,
            "difficulty": 0.0,
            "price": 0.0,
            "fiat": settings.get("network", "fiat"),
        }
        # keep a short history for a sparkline
        self.hashrate_history = collections.deque(maxlen=60)

    @property
    def uptime_seconds(self):
        return time.time() - self.start_time

    def refresh(self):
        # cheap: always parse the local log
        log = parse_cpuminer_log(self.s.get("miner", "log_file"))
        self.data.update(log)
        self.hashrate_history.append(log["hashrate_hs"])

        # expensive: throttle the API calls
        now = time.time()
        if now - self._last_poll >= self.poll_seconds or self._last_poll == 0.0:
            self._last_poll = now
            pool = fetch_pool_stats(self.s.stats_api_url,
                                    self.s.get("pool", "stats_api_type"))
            self.data.update(pool)
            chain = fetch_chain_info(self.s.get("network", "mempool_api"),
                                     self.s.get("network", "fiat"))
            self.data.update(chain)
        return self.data
