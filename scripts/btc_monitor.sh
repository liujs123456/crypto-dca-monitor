#!/bin/bash
# BTC Dip Ladder Monitor — runs every 2h via GitHub Actions
# State stored in ntfy itself (poll past 12h messages for prev state)

set -e

NTFY="https://ntfy.sh/${NTFY_TOPIC}"
REF=${BTC_REF_PRICE:-79500}

LAST=$(curl -s --max-time 10 'https://api.coinbase.com/v2/prices/BTC-USD/spot' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["amount"])' 2>/dev/null)

if [ -z "$LAST" ]; then
  CG=$(curl -s --max-time 10 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true')
  LAST=$(echo "$CG" | python3 -c 'import json,sys;print(json.load(sys.stdin)["bitcoin"]["usd"])')
  CHANGE24=$(echo "$CG" | python3 -c 'import json,sys;print(round(json.load(sys.stdin)["bitcoin"]["usd_24h_change"], 2))')
else
  CG24=$(curl -s --max-time 10 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true')
  CHANGE24=$(echo "$CG24" | python3 -c 'import json,sys;print(round(json.load(sys.stdin)["bitcoin"]["usd_24h_change"], 2))')
fi

if [ -z "$LAST" ]; then
  curl -s -X POST -H "Title: ⚠️ Monitor 失败" -H "Priority: low" \
    -d "BTC 价格源全部不可达，跳过本次。" "$NTFY"
  exit 1
fi

T1=$(python3 -c "print(round($REF * 0.90))")
T2=$(python3 -c "print(round($REF * 0.85))")
T3=$(python3 -c "print(round($REF * 0.78))")
T4=$(python3 -c "print(round($REF * 0.68))")
WATCH=$(python3 -c "print(round($REF * 0.92))")

STATE='GREEN'
if python3 -c "exit(0 if $LAST < $T4 else 1)"; then STATE='T4'
elif python3 -c "exit(0 if $LAST < $T3 else 1)"; then STATE='T3'
elif python3 -c "exit(0 if $LAST < $T2 else 1)"; then STATE='T2'
elif python3 -c "exit(0 if $LAST < $T1 else 1)"; then STATE='T1'
elif python3 -c "exit(0 if $LAST < $WATCH else 1)"; then STATE='WATCH'
fi

FLASH='NORMAL'
if python3 -c "exit(0 if abs($CHANGE24) > 8 else 1)"; then FLASH='FLASH'; fi

PREV='GREEN'
LAST_MSGS=$(curl -s --max-time 10 "${NTFY}/json?poll=1&since=12h" 2>/dev/null || echo "")
if [ -n "$LAST_MSGS" ]; then
  TITLES=$(echo "$LAST_MSGS" | python3 -c '
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        t = json.loads(line).get("title","")
        print(t)
    except: pass
' 2>/dev/null || echo "")
  for marker in T4 T3 T2 T1 WATCH RECOVERED; do
    if echo "$TITLES" | grep -qE "(^|[^A-Za-z0-9])$marker([^A-Za-z0-9]|$)"; then
      PREV=$marker
      break
    fi
  done
fi

_rank() {
  case "$1" in
    GREEN|RECOVERED) echo 0;;
    WATCH) echo 1;;
    T1) echo 2;;
    T2) echo 3;;
    T3) echo 4;;
    T4) echo 5;;
    *) echo 0;;
  esac
}
CUR_ORD=$(_rank "$STATE")
PREV_ORD=$(_rank "$PREV")

NOTIFY=''
if [ $CUR_ORD -gt $PREV_ORD ]; then
  NOTIFY="escalate-$STATE"
elif [ $CUR_ORD -lt $PREV_ORD ] && [ "$STATE" = 'GREEN' ]; then
  NOTIFY='recovered'
fi

case "$NOTIFY" in
  escalate-WATCH)
    curl -s -X POST -H "Title: 🟡 WATCH: BTC 接近 Tier 1" -H "Priority: low" -H "Tags: eyes" \
      -d "BTC \$$LAST (ref \$$REF). 接近 Tier 1 (\$$T1)." "$NTFY"
    ;;
  escalate-T1)
    curl -s -X POST -H "Title: 🟠 T1 触发" -H "Priority: high" -H "Tags: chart_with_downwards_trend" \
      -d "BTC \$$LAST. Tier 1 触发. 加 \$100. 开 Claude 确认." "$NTFY"
    ;;
  escalate-T2)
    curl -s -X POST -H "Title: 🟠 T2 触发" -H "Priority: high" -H "Tags: chart_with_downwards_trend" \
      -d "BTC \$$LAST. Tier 2 触发. 加 \$200. 开 Claude 确认." "$NTFY"
    ;;
  escalate-T3)
    curl -s -X POST -H "Title: 🔴 T3: 深度修正" -H "Priority: high" -H "Tags: rotating_light" \
      -d "BTC \$$LAST. Tier 3 触发. 加 \$400. 尽快开 Claude." "$NTFY"
    ;;
  escalate-T4)
    curl -s -X POST -H "Title: 🚨 T4: CAPITULATION" -H "Priority: max" -H "Tags: rotating_light,fire" \
      -d "🚨 BTC \$$LAST. Tier 4 触发. 加 \$800." "$NTFY"
    ;;
  recovered)
    curl -s -X POST -H "Title: ✅ RECOVERED" -H "Priority: low" -H "Tags: white_check_mark" \
      -d "BTC 回到 \$$LAST. 已从触发恢复." "$NTFY"
    ;;
esac

if [ "$FLASH" = 'FLASH' ] && ! echo "$LAST_MSGS" | grep -q 'FLASH'; then
  curl -s -X POST -H "Title: ⚡ FLASH: 异常波动" -H "Priority: default" -H "Tags: zap" \
    -d "BTC 24h ${CHANGE24}%. 现价 \$$LAST." "$NTFY"
fi

echo "BTC: \$$LAST | 24h: $CHANGE24% | REF: \$$REF | State: $STATE | Prev: $PREV | Notify: ${NOTIFY:-none}"
