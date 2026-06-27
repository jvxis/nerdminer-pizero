# pizero-lottery-miner

A [NerdMiner](https://github.com/bitmaker-hub/nerdminer_v2)-style **Bitcoin solo
"lottery" miner** for the **Raspberry Pi Zero W** + **Waveshare 1.3" LCD HAT**
(ST7789 240×240, 5-way joystick + 3 buttons).

It does SHA256d solo mining against a solo pool and shows live stats on the LCD —
hashrate, shares, your **best share difficulty**, block height and BTC price —
navigable with the joystick.

> ### ⚠️ This is a lottery, not an investment
> A Pi Zero W hashes at roughly **0.2–0.3 MH/s**. The Bitcoin network runs at
> hundreds of **EH/s**, so the expected time for this device to solo-mine a block
> is on the order of **tens of billions of years**. If you ever do hit one (solo),
> you keep the *whole* block reward — but you almost certainly never will. Build
> this for fun and to learn how mining works, the same way the NerdMiner is meant
> to be a "lottery ticket." It costs ~1 W to run.

## Why a Pi Zero?

| Hardware | ~Hashrate | vs ESP32 NerdMiner |
|---|---|---|
| ESP32 (NerdMiner v2) | 40–78 KH/s | 1× |
| **Pi Zero W v1.1** (ARMv6, 1 core, no NEON) | **~0.2–0.3 MH/s** | ~4–6× |
| Pi Zero 2 W (4× Cortex-A53, NEON) | ~1.5–2 MH/s | ~25–40× |

The actual hashing is done by **pooler's [cpuminer](https://github.com/pooler/cpuminer)**
(optimized C). Python only drives the LCD UI — never hash in Python, it's far slower.

## Architecture

```
 cpuminer (minerd)  --stratum-->  solo pool        \
        |  writes log                                |  dashboard.py reads
        v                                            |  all three and renders
  /var/log/.../cpuminer.log  ---------------------->  the LCD screens
                                                      |
 pool stats API (best share)  ---------------------->|
 mempool.space (height/price/difficulty) ----------->/
```

- **`cpuminer`** runs as a service, pointed at a solo pool with your BTC address.
  `install.sh` builds it from source with a one-line patch (`patches/`) that lets it
  request a low share difficulty (`mining.suggest_difficulty`) the Pi can meet.
- **`dashboard.py`** reuses the vendored Waveshare driver (`st7789.py`,
  `lcd_hardware.py`) to draw NerdMiner-style screens and read inputs.
- **`stats.py`** merges three sources, each degrading gracefully if offline.

## Hardware

- Raspberry Pi Zero W (this targets the **v1.1**, BCM2835 / ARMv6 / single core).
- Waveshare 1.3inch LCD HAT (ST7789, 240×240). It seats on the 40-pin header — no
  wiring needed. GPIO map (BCM): joystick UP=6 DOWN=19 LEFT=5 RIGHT=26 PRESS=13;
  buttons KEY1=21 KEY2=20 KEY3=16; display RST=27 DC=25 BL=24, SPI0.

## Install

```bash
git clone <your-repo-url> pizero-lottery-miner
cd pizero-lottery-miner
bash scripts/install.sh        # builds cpuminer, installs deps, enables SPI
cp config.example.ini config.ini
nano config.ini                # set your wallet address + pool
```

## Configure

Edit `config.ini`:

- `[wallet] address` — your bech32 BTC address (block reward destination).
- `[pool]` — a **solo** pool. Defaults to `solo.ckpool.org:3333` (no signup, 1%
  fee); [public-pool.io](https://web.public-pool.io) (zero fee) also works — set
  `url`, `stats_api` and `stats_api_type = public-pool`. Don't use
  `pool.nerdminers.org`: it whitelists NerdMiner/Bitaxe firmware by user-agent and
  rejects cpuminer.
- `[pool] suggest_difficulty` — the share difficulty the miner asks the pool for
  (via `mining.suggest_difficulty`). Leave at `1`, the lowest pools accept: a Pi
  Zero can't meet a pool's default (~10000–100000), so without this the dashboard's
  share/lottery numbers would never move. Requires the **patched `minerd`** that
  `install.sh` builds (a stock `minerd` doesn't send the request and ignores it).
- `[display] refresh_seconds` — keep ≥ 1 so the single core isn't starved.

## Run

Quick test (two terminals):

```bash
bash scripts/run-cpuminer.sh     # starts hashing, writes the log
python3 dashboard.py             # draws the LCD
```

As auto-starting services:

```bash
sudo cp systemd/*.service /etc/systemd/system/   # edit paths/User inside first
sudo systemctl daemon-reload
sudo systemctl enable --now pizero-cpuminer pizero-dashboard
```

## Controls

| Input | Action |
|---|---|
| Joystick ◀ / ▶ (or ▲ / ▼) | previous / next screen |
| Joystick press | force data refresh |
| KEY1 | next screen |
| KEY2 | toggle backlight |
| KEY3 | quit dashboard |

Screens: **Miner** (hashrate / shares), **Lottery** (best share difficulty vs
network difficulty), **Bitcoin** (price / height / difficulty), **System**
(IP / temp / load / uptime).

## Notes & tips

- Single core: the miner runs at `Nice=10` so the UI stays responsive.
- **Share difficulty drives the dashboard.** A pool's share difficulty sets how
  often you submit a share. At ~0.25 MH/s a pool's default (ckpool ~10000,
  public-pool ~100000) needs *years* per share, so the share/best-share screens
  would sit at 0 forever. `install.sh` patches `minerd` to send
  `mining.suggest_difficulty` so it can request difficulty `1` (set via
  `[pool] suggest_difficulty`), bringing shares down to ~hours apart. Either way
  your odds of actually *finding a block* are identical — only the on-screen stats
  differ. Inspect the negotiated difficulty with `minerd ... -P` (protocol dump).
- The Pi Zero W's WiFi is enough; no Ethernet/dongle needed.
- ARMv6 has no NEON, so cpuminer uses the generic C path (the lower hashrate above).
- Thermals are gentle on the original Zero; a heatsink is optional.

## Credits & license

- LCD driver vendored/adapted from the Waveshare example code (its MIT-style header
  is retained in `lcd_hardware.py`).
- Inspired by [NerdMiner v2](https://github.com/bitmaker-hub/nerdminer_v2).
- Mining by [pooler/cpuminer](https://github.com/pooler/cpuminer).

Project code is MIT licensed — see [LICENSE](LICENSE).
