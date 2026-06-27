"""NerdMiner-style screens rendered onto the 240x240 ST7789.

Each screen is a function (img, draw, data, fonts, ctx) -> None that draws a
full frame. Kept text-only (no emoji) so it renders cleanly with DejaVu fonts.

Text never overflows the 240px width: long values (a full IP, a wide hashrate
string, a six-figure price) are auto-shrunk to fit via ``Fonts.fit`` before
they are drawn, so nothing gets clipped on the small panel.
"""
import os
import socket

from PIL import ImageFont

BG = (10, 10, 14)
ORANGE = (247, 147, 26)      # bitcoin orange
WHITE = (235, 235, 235)
GREEN = (0, 255, 163)
DIM = (168, 172, 188)        # labels -- bright enough to read on the dark BG
RED = (255, 96, 96)

W = H = 240
MARGIN = 14                  # left/right text inset


# ---------- fonts ----------

class Fonts:
    """Caches TrueType faces and shrinks them on demand to fit a width.

    Drawn screens look it up two ways:
      * ``fonts["big"]`` -> the face for a named role at its default size.
      * ``fonts.fit("big", text, max_w)`` -> the largest size <= the role's
        default whose rendered ``text`` is no wider than ``max_w``.
    """

    CANDIDATES = {
        "bold": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ],
        "regular": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ],
    }
    # role -> (kind, default size)
    ROLES = {
        "title": ("bold", 22),
        "big": ("bold", 34),
        "body": ("regular", 20),
        "small": ("regular", 15),
    }

    def __init__(self, extra_candidates=None):
        # extra_candidates lets a host without DejaVu (e.g. a dev box running
        # the local render test) prepend its own font files per kind.
        self.candidates = {k: list(v) for k, v in self.CANDIDATES.items()}
        if extra_candidates:
            for kind, paths in extra_candidates.items():
                self.candidates[kind] = list(paths) + self.candidates.get(kind, [])
        self._paths = {}
        self._cache = {}

    def _path(self, kind):
        if kind not in self._paths:
            self._paths[kind] = next(
                (p for p in self.candidates[kind] if os.path.exists(p)), None)
        return self._paths[kind]

    def load(self, kind, size):
        key = (kind, size)
        face = self._cache.get(key)
        if face is None:
            path = self._path(kind)
            try:
                face = ImageFont.truetype(path, size) if path \
                    else ImageFont.load_default()
            except OSError:
                face = ImageFont.load_default()
            self._cache[key] = face
        return face

    def __getitem__(self, role):
        kind, size = self.ROLES[role]
        return self.load(kind, size)

    def fit(self, role, text, max_width):
        kind, size = self.ROLES[role]
        min_size = max(11, size - 16)
        for s in range(size, min_size - 1, -1):
            face = self.load(kind, s)
            if _text_w(face, text) <= max_width:
                return face
        return self.load(kind, min_size)


# ---------- formatting helpers ----------

def fmt_hashrate(hs):
    for unit, div in (("GH/s", 1e9), ("MH/s", 1e6), ("kH/s", 1e3)):
        if hs >= div:
            return f"{hs / div:.2f} {unit}"
    return f"{hs:.0f} H/s"


def fmt_suffix(value):
    """Big number -> short suffix form (e.g. 83.1T)."""
    for suffix, div in (("E", 1e18), ("P", 1e15), ("T", 1e12),
                        ("G", 1e9), ("M", 1e6), ("K", 1e3)):
        if value >= div:
            return f"{value / div:.1f}{suffix}"
    return f"{value:.0f}"


def fmt_uptime(seconds):
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    return f"{h:02d}h {m:02d}m"


# ---------- drawing helpers ----------

def _text_w(font, text):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _centered(draw, font, text, y, fill):
    draw.text(((W - _text_w(font, text)) // 2, y), text, font=font, fill=fill)


def _centered_fit(draw, fonts, role, text, y, fill, margin=MARGIN):
    """Center ``text`` on row ``y``, shrinking the face so it never clips."""
    font = fonts.fit(role, text, W - 2 * margin)
    _centered(draw, font, text, y, fill)


def _value(draw, fonts, role, text, x, y, fill):
    """Left-aligned value that auto-shrinks to fit between ``x`` and the edge."""
    font = fonts.fit(role, text, W - x - MARGIN)
    draw.text((x, y), text, font=font, fill=fill)


def _header(draw, fonts, title, page_idx, page_count):
    draw.rectangle([(0, 0), (W - 1, 40)], fill=ORANGE)
    draw.text((10, 8), title, font=fonts["title"], fill=BG)
    dots = " ".join("o" if i == page_idx else "." for i in range(page_count))
    draw.text((W - _text_w(fonts["small"], dots) - 10, 14), dots,
              font=fonts["small"], fill=BG)


# ---------- screens ----------

def screen_miner(img, draw, data, fonts, ctx):
    _header(draw, fonts, "MINER", ctx["page"], ctx["pages"])
    _centered(draw, fonts["small"], "local hashrate", 52, DIM)
    _centered_fit(draw, fonts, "big", fmt_hashrate(data["hashrate_hs"]), 70, GREEN)

    acc, tot = data["accepted"], data["total"]
    rej = max(tot - acc, 0)
    draw.text((MARGIN, 130), "shares", font=fonts["small"], fill=DIM)
    _value(draw, fonts, "body", f"{acc} ok / {rej} rej", MARGIN, 148,
           WHITE if rej == 0 else RED)

    draw.text((MARGIN, 180), "pool hashrate", font=fonts["small"], fill=DIM)
    _value(draw, fonts, "body", fmt_hashrate(data["pool_hashrate_hs"]),
           MARGIN, 198, WHITE)


def screen_lottery(img, draw, data, fonts, ctx):
    _header(draw, fonts, "LOTTERY", ctx["page"], ctx["pages"])
    _centered(draw, fonts["small"], "best share difficulty", 50, DIM)
    _centered_fit(draw, fonts, "big", fmt_suffix(data["best_share"]), 66, ORANGE)

    net = data["difficulty"]
    draw.text((MARGIN, 126), "network difficulty", font=fonts["small"], fill=DIM)
    _value(draw, fonts, "body", fmt_suffix(net), MARGIN, 144, WHITE)

    if net > 0 and data["best_share"] > 0:
        ratio = data["best_share"] / net
        pct = min(ratio * 100, 100.0)
        draw.text((MARGIN, 176), "block progress", font=fonts["small"], fill=DIM)
        _value(draw, fonts, "body", f"{pct:.6f}%", MARGIN, 194, GREEN)
    else:
        draw.text((MARGIN, 184), "waiting for first share...",
                  font=fonts["small"], fill=DIM)


def screen_bitcoin(img, draw, data, fonts, ctx):
    _header(draw, fonts, "BITCOIN", ctx["page"], ctx["pages"])
    fiat = data.get("fiat", "USD")
    price = data["price"]
    _centered(draw, fonts["small"], f"price ({fiat})", 54, DIM)
    price_txt = f"{price:,.0f}" if price else "--"
    _centered_fit(draw, fonts, "big", price_txt, 72, GREEN)

    draw.text((MARGIN, 134), "block height", font=fonts["small"], fill=DIM)
    _value(draw, fonts, "body", f"{data['block_height']:,}", MARGIN, 152, ORANGE)

    draw.text((MARGIN, 184), "difficulty", font=fonts["small"], fill=DIM)
    _value(draw, fonts, "body", fmt_suffix(data["difficulty"]), MARGIN, 202, WHITE)


def _sys_metric(parse):
    try:
        return parse()
    except Exception:
        return "--"


def screen_system(img, draw, data, fonts, ctx):
    _header(draw, fonts, "SYSTEM", ctx["page"], ctx["pages"])

    def ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()

    def temp():
        with open("/sys/class/thermal/thermal_zone0/temp") as fh:
            return f"{int(fh.read().strip()) / 1000:.1f} C"

    def load():
        return os.getloadavg()[0]

    rows = [
        ("IP", _sys_metric(ip)),
        ("CPU temp", _sys_metric(temp)),
        ("load (1m)", _sys_metric(lambda: f"{load():.2f}")),
        ("session", fmt_uptime(ctx["uptime"])),
        ("pool", ctx["pool_name"]),
    ]
    val_x = 104
    y = 56
    for label, value in rows:
        draw.text((MARGIN, y), label, font=fonts["small"], fill=DIM)
        _value(draw, fonts, "body", str(value), val_x, y - 3, WHITE)
        y += 34


SCREENS = [screen_miner, screen_lottery, screen_bitcoin, screen_system]
