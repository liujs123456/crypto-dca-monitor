#!/bin/bash
# Evening portfolio summary — OKX read-only API → ntfy push
# Runs daily at 20:03 PT via GitHub Actions

set -e

NTFY="https://ntfy.sh/${NTFY_TOPIC}"

# OKX HMAC-SHA256 signed GET
okx_get() {
  local PATH_AND_QUERY="$1"
  local TS
  TS=$(python3 -c "from datetime import datetime,timezone;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.')+f'{datetime.now(timezone.utc).microsecond//1000:03d}Z')")
  local PREHASH="${TS}GET${PATH_AND_QUERY}"
  local SIG
  SIG=$(printf "%s" "$PREHASH" | openssl dgst -sha256 -hmac "$OKX_SECRET" -binary | base64)
  curl -s --max-time 15 "https://www.okx.com${PATH_AND_QUERY}" \
    -H "OK-ACCESS-KEY: ${OKX_API_KEY}" \
    -H "OK-ACCESS-SIGN: ${SIG}" \
    -H "OK-ACCESS-TIMESTAMP: ${TS}" \
    -H "OK-ACCESS-PASSPHRASE: ${OKX_PASSPHRASE}" \
    -H "Content-Type: application/json"
}

# 1) BTC price (public)
PRICE_JSON=$(curl -s --max-time 10 'https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT')
BTC_PRICE=$(echo "$PRICE_JSON" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["data"][0]["last"])' 2>/dev/null || echo "?")
BTC_OPEN24=$(echo "$PRICE_JSON" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["data"][0]["open24h"])' 2>/dev/null || echo "?")

# 2) Account balance
BAL_JSON=$(okx_get "/api/v5/account/balance")
USDT_BAL=$(echo "$BAL_JSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for x in d["data"][0]["details"]:
  if x["ccy"]=="USDT": print(x["cashBal"]); break
else: print("0")
' 2>/dev/null || echo "0")
BTC_HELD=$(echo "$BAL_JSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for x in d["data"][0]["details"]:
  if x["ccy"]=="BTC": print(x["cashBal"]); break
else: print("0")
' 2>/dev/null || echo "0")
BTC_AVG=$(echo "$BAL_JSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for x in d["data"][0]["details"]:
  if x["ccy"]=="BTC": print(x.get("accAvgPx","0") or "0"); break
else: print("0")
' 2>/dev/null || echo "0")

# 3) Earn savings balance
EARN_JSON=$(okx_get "/api/v5/finance/savings/balance?ccy=USDT")
EARN_AMT=$(echo "$EARN_JSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print(d["data"][0]["amt"] if d.get("data") else "0")
' 2>/dev/null || echo "0")
EARN_INT=$(echo "$EARN_JSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print(d["data"][0]["earnings"] if d.get("data") else "0")
' 2>/dev/null || echo "0")

# 4) Today's DCA (last 24h, BTC-USDT, side=buy, sz=20)
NOW_MS=$(python3 -c 'import time;print(int(time.time()*1000))')
DAY_AGO=$((NOW_MS - 86400000))
ORD_JSON=$(okx_get "/api/v5/trade/orders-history?instType=SPOT&instId=BTC-USDT&begin=${DAY_AGO}&limit=20")
DCA_INFO=$(echo "$ORD_JSON" | python3 -c '
import json,sys
try:
  d=json.load(sys.stdin)
  orders=[o for o in d.get("data",[]) if o.get("side")=="buy" and o.get("state")=="filled"]
  if not orders:
    print("0|0|0")
  else:
    n=len(orders)
    total=sum(float(o["accFillSz"])*float(o["avgPx"]) for o in orders)
    avg_px=sum(float(o["avgPx"]) for o in orders)/n
    print(f"{n}|{total:.2f}|{avg_px:.0f}")
except Exception as e:
  print(f"err|{e}|0", file=sys.stderr)
  print("0|0|0")
' 2>/dev/null || echo "0|0|0")

DCA_N=$(echo "$DCA_INFO" | cut -d'|' -f1)
DCA_TOTAL=$(echo "$DCA_INFO" | cut -d'|' -f2)
DCA_AVG=$(echo "$DCA_INFO" | cut -d'|' -f3)

# 5) Compute totals + UPL
TOTAL_USD=$(python3 -c "print(round(float('$USDT_BAL')+float('$BTC_HELD')*float('$BTC_PRICE')+float('$EARN_AMT'), 2))")
BTC_USD=$(python3 -c "print(round(float('$BTC_HELD')*float('$BTC_PRICE'), 2))")
UPL=$(python3 -c "
held=float('$BTC_HELD'); avg=float('$BTC_AVG'); px=float('$BTC_PRICE')
if avg==0: print('0')
else: print(round(held*(px-avg), 2))
")
UPL_PCT=$(python3 -c "
held=float('$BTC_HELD'); avg=float('$BTC_AVG'); px=float('$BTC_PRICE')
if avg==0 or held==0: print('0')
else: print(round((px/avg-1)*100, 2))
")
PRICE_24H_PCT=$(python3 -c "
o=float('$BTC_OPEN24'); p=float('$BTC_PRICE')
if o==0: print('0')
else: print(round((p/o-1)*100, 2))
")

# 6) Format briefing
DATE=$(date +%m/%d)
BODY=$(cat <<EOF
💰 总资产 \$${TOTAL_USD}

BTC \$${BTC_PRICE} (${PRICE_24H_PCT}%)
持仓 ${BTC_HELD} BTC ≈ \$${BTC_USD}
均价 \$${BTC_AVG} | 浮盈 \$${UPL} (${UPL_PCT}%)

USDT 现货: \$${USDT_BAL}
USDT Earn: \$${EARN_AMT} (累计利息 +\$${EARN_INT})

今日 DCA: ${DCA_N} 单, \$${DCA_TOTAL}, 均价 \$${DCA_AVG}
EOF
)

curl -s -X POST \
  -H "Title: 📊 晚报 ${DATE}" \
  -H "Priority: default" \
  -H "Tags: bar_chart" \
  -d "$BODY" \
  "$NTFY"

echo "$BODY"
