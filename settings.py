"""Load configuration from config.ini with sensible defaults."""
import configparser
import os

DEFAULTS = {
    "wallet": {
        "address": "bc1qexampleexampleexampleexampleexampleexample",
    },
    "pool": {
        "url": "stratum+tcp://solo.ckpool.org:3333",
        "worker": "pizero",
        "password": "x",
        "stats_api": "https://solo.ckpool.org/users/{address}",
        "stats_api_type": "ckpool",  # ckpool | public-pool | none
    },
    "miner": {
        "binary": "/usr/local/bin/minerd",
        "algo": "sha256d",
        "threads": "1",
        "log_file": "/var/log/pizero-miner/cpuminer.log",
    },
    "display": {
        "brightness": "60",       # backlight 0-100
        "refresh_seconds": "2",   # LCD redraw cadence (keep >=1 on a single core)
    },
    "network": {
        "mempool_api": "https://mempool.space/api",
        "fiat": "USD",            # USD | BRL | none
        "poll_seconds": "120",    # how often to hit pool/chain APIs
    },
}


class Settings:
    def __init__(self, path="config.ini"):
        # inline_comment_prefixes lets values carry trailing "; ..." comments
        self._cp = configparser.ConfigParser(inline_comment_prefixes=(";",))
        # seed defaults
        self._cp.read_dict(DEFAULTS)
        if os.path.exists(path):
            self._cp.read(path)
        else:
            print(f"[settings] {path} not found, using built-in defaults "
                  f"(copy config.example.ini to config.ini).")

    def get(self, section, key):
        return self._cp.get(section, key)

    def getint(self, section, key):
        return self._cp.getint(section, key)

    @property
    def address(self):
        return self.get("wallet", "address")

    @property
    def pool_user(self):
        worker = self.get("pool", "worker").strip()
        return f"{self.address}.{worker}" if worker else self.address

    @property
    def stats_api_url(self):
        tmpl = self.get("pool", "stats_api")
        return tmpl.format(address=self.address) if tmpl else ""
