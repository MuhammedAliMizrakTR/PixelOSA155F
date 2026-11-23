#!/system/bin/sh
# Manual one-shot restart (root-manager action button).
stop ril-daemon
sleep 5
start ril-daemon
echo "ril-daemon restarted. Network should re-register within ~30s."
