#!/bin/bash
# 当日两融发布监控: SSE可拉后 自动fetch+build+校验 (当日数据发布时间不定, cron 18:10常赶不上)
# flock防重入: 同时只跑一份(手动+cron并起会堆重型akshare进程, CPU尖峰拖慢宿主鼠标)
exec 9>/tmp/margin_watch.lock
flock -n 9 || { echo "$(date '+%F %T') margin_watch: 已有实例在跑, 退出" >> /tmp/margin_daily.log; exit 0; }
export XDG_RUNTIME_DIR=/run/user/1000
D=$(date +%Y%m%d)
D1=$(date -d "-9 days" +%Y%m%d)
for i in $(seq 1 120); do
  OK=$(/usr/bin/python3.12 -c "
import akshare as ak
try:
    s = ak.stock_margin_detail_sse(date='$D')
    print('yes' if len(s)>0 else 'no')
except Exception:
    print('no')
" 2>/dev/null)
  if [ "$OK" = "yes" ]; then
    /usr/bin/python3.12 /mnt/e/stockSurface/margin_fetch.py "$D1" "$D" >> /tmp/margin_daily.log 2>&1
    /usr/bin/python3.12 /mnt/e/stockSurface/margin_build.py >> /tmp/margin_daily.log 2>&1
    T=$(/usr/bin/python3.12 -c "
import json
try:
    j = json.load(open('/mnt/e/stockSurface/margin_heat.json'))
    print(j['dates'][-1] == '$D')
except Exception:
    print('False')
" 2>/dev/null)
    if [ "$T" = "True" ]; then
      echo "$(date '+%F %T') margin_watch: 当日$D已入json OK" >> /tmp/margin_daily.log
    else
      echo "MARGIN_WATCH_BUILD_BAD" | mail -s "[stockheat] margin_watch 当日未入json $D" hongbo_liu@163.com
    fi
    exit 0
  fi
  sleep 60
done
echo "MARGIN_WATCH_TIMEOUT" | mail -s "[stockheat] margin_watch 2小时未见当日数据 $D" hongbo_liu@163.com
