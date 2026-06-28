#!/usr/bin/env python3
"""pizero-lottery-miner dashboard.

Renders NerdMiner-style screens on the Waveshare 1.3" LCD HAT and lets you
navigate them with the joystick. It does NOT mine itself -- cpuminer does the
hashing (see scripts/run-cpuminer.sh); this reads its log + pool/chain APIs.

Controls:
  joystick LEFT / RIGHT ... previous / next screen
  joystick UP / DOWN ...... previous / next screen
  joystick PRESS .......... force a data refresh now
  KEY1 .................... next screen
  KEY2 .................... toggle backlight
  KEY3 .................... quit
"""
import sys
import time

from PIL import Image, ImageDraw

import st7789
import screens
from settings import Settings
from stats import MinerStats

POLL_TICK = 0.05  # joystick sampling period (s)


def pool_name(settings):
    url = settings.get("pool", "url")
    host = url.split("//")[-1].split(":")[0]
    return host


def main():
    settings = Settings()
    disp = st7789.ST7789()
    disp.Init()
    disp.clear()
    brightness = settings.getint("display", "brightness")
    disp.bl_DutyCycle(brightness)
    backlight_on = True

    fonts = screens.Fonts()

    stats = MinerStats(settings)
    refresh_seconds = settings.getint("display", "refresh_seconds")
    page = 0
    n_pages = len(screens.SCREENS)

    # edge-detection state for the inputs we care about
    inputs = {
        "left": disp.GPIO_KEY_LEFT_PIN,
        "right": disp.GPIO_KEY_RIGHT_PIN,
        "up": disp.GPIO_KEY_UP_PIN,
        "down": disp.GPIO_KEY_DOWN_PIN,
        "press": disp.GPIO_KEY_PRESS_PIN,
        "key1": disp.GPIO_KEY1_PIN,
        "key2": disp.GPIO_KEY2_PIN,
        "key3": disp.GPIO_KEY3_PIN,
    }
    prev = {name: False for name in inputs}

    def pressed(name):
        """True only on the press edge (released -> pressed)."""
        now = disp.digital_read(inputs[name]) == 1
        edge = now and not prev[name]
        prev[name] = now
        return edge

    def render():
        data = stats.refresh()
        img = Image.new("RGB", (screens.W, screens.H), screens.BG)
        draw = ImageDraw.Draw(img)
        ctx = {
            "page": page,
            "pages": n_pages,
            "uptime": stats.uptime_seconds,
            "pool_name": pool_name(settings),
            "worker": settings.get("pool", "worker").strip(),
        }
        screens.SCREENS[page](img, draw, data, fonts, ctx)
        disp.ShowImage(img)

    try:
        render()
        last_render = time.time()
        while True:
            time.sleep(POLL_TICK)
            dirty = False

            if pressed("left") or pressed("up"):
                page = (page - 1) % n_pages
                dirty = True
            if pressed("right") or pressed("down") or pressed("key1"):
                page = (page + 1) % n_pages
                dirty = True
            if pressed("press"):
                stats._last_poll = 0.0  # force API refresh on next render
                dirty = True
            if pressed("key2"):
                backlight_on = not backlight_on
                disp.bl_DutyCycle(brightness if backlight_on else 0)
            if pressed("key3"):
                break

            if dirty or (time.time() - last_render) >= refresh_seconds:
                render()
                last_render = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        disp.clear()
        disp.module_exit()
        sys.exit(0)


if __name__ == "__main__":
    main()
