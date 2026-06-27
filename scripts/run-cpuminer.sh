#!/usr/bin/env bash
# Launch cpuminer using values from config.ini and tee its output to the log
# that the dashboard parses. Used by the systemd service.
set -euo pipefail

cd "$(dirname "$0")/.."

# Pull settings out of config.ini using Python (robust ini parsing).
eval "$(python3 - <<'PY'
import configparser, shlex
c = configparser.ConfigParser(inline_comment_prefixes=(";",))
c.read("config.ini")
addr   = c.get("wallet", "address")
worker = c.get("pool", "worker", fallback="pizero").strip()
user   = f"{addr}.{worker}" if worker else addr
vals = {
    "BINARY":  c.get("miner", "binary", fallback="/usr/local/bin/minerd"),
    "ALGO":    c.get("miner", "algo", fallback="sha256d"),
    "THREADS": c.get("miner", "threads", fallback="1"),
    "URL":     c.get("pool", "url"),
    "USER":    user,
    "PASS":    c.get("pool", "password", fallback="x"),
    "LOG":     c.get("miner", "log_file", fallback="/var/log/pizero-miner/cpuminer.log"),
}
for k, v in vals.items():
    print(f"{k}={shlex.quote(v)}")
PY
)"

mkdir -p "$(dirname "$LOG")"
: > "$LOG"   # truncate on start so the log stays small

echo "Starting cpuminer: $BINARY -a $ALGO -o $URL -u $USER -t $THREADS"
exec "$BINARY" -a "$ALGO" -o "$URL" -u "$USER" -p "$PASS" -t "$THREADS" \
    > >(tee -a "$LOG") 2>&1
