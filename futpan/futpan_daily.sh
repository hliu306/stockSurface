#!/bin/bash
# 期货全局页日更 (新浪源免token, ~3min). 成功静默, 失败报警exit 1
LOG=/tmp/futpan_daily.log
mkdir -p /mnt/e/stockSurface/futpan
/usr/bin/python3.12 /mnt/e/stockSurface/futpan/futpan_build.py > "$LOG" 2>&1
EC=$?
if [ $EC -ne 0 ]; then
  echo "futpan 日更 FAILED (exit=$EC):"; tail -8 "$LOG"; exit 1
fi
# 新鲜度: nodes里的last_date必须>=cache_td_v2最新交易日
TODAY_OK=$(/usr/bin/python3.12 - << 'PY'
import json, pandas as pd
d = json.load(open('/mnt/e/stockSurface/futpan/futpan.json'))
c = pd.read_parquet('/mnt/e/stockSurface/cache_td_v2.parquet', columns=['trade_date'])
td = str(int(c.trade_date.max()))
ld = max(n['last_date'].replace('-','') for n in d['nodes'])
print(1 if ld >= td else 0)
PY
)
if [ "$TODAY_OK" != "1" ]; then
  echo "futpan 数据不新鲜"; tail -3 "$LOG"; exit 1
fi
