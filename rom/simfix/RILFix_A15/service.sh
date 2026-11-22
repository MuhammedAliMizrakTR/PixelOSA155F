#!/system/bin/sh
# A15 RIL Watchdog Fix + A155F GSI presets — service loop.
#
# 1) SIM bug: on SM-A155F with an unlocked bootloader, stock ril-daemon hangs
#    the modem after ~7h25m of runtime (XDA 4688638/4703177; vendor-side, no
#    root-cause fix exists). Restarting ril-daemon on a timer is the
#    community-proven workaround (method: rev.s; concept: itsfaris' module).
# 2) Presets: applies researched phh/Treble props for the A15 (see
#    a155f-presets.prop) with resetprop -n — user toggles always win.
MODDIR=${0%/*}
LOG="$MODDIR/rilfix.log"
INTERVAL=21600   # 6h — safely below the 7h25m crash window

echo "[$(date)] rilfix service started" >> "$LOG"

# --- apply A155F presets once (resetprop -n = only if unset) ---
if [ -f "$MODDIR/a155f-presets.prop" ]; then
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue;; esac
    resetprop -n "$k" "$v" 2>/dev/null || \
      { [ -z "$(getprop "$k")" ] && setprop "$k" "$v"; }
  done < "$MODDIR/a155f-presets.prop"
  echo "[$(date)] a155f presets applied (non-destructive)" >> "$LOG"
fi

# --- wait for boot, then keep ril-daemon under the crash window ---
while [ "$(getprop sys.boot_completed)" != "1" ]; do sleep 10; done
sleep 120
while true; do
  if pidof ril-daemon >/dev/null 2>&1 || pidof rild >/dev/null 2>&1; then
    stop ril-daemon
    sleep 5
    start ril-daemon
    echo "[$(date)] ril-daemon restarted" >> "$LOG"
  else
    echo "[$(date)] ril-daemon not running, skip" >> "$LOG"
  fi
  sleep "$INTERVAL"
done
