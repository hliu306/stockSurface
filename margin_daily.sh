#!/bin/bash
# 两融日日更: 增量拉取+聚合+重建margin_heat.json (成功静默/失败邮件)
# 加固v2: -9日窗口(自动补缺口/漏跑) + 产物三重校验(dates尾部/文件数/json可读+行内归一)
export XDG_RUNTIME_DIR=/run/user/1000
LOG=/tmp/margin_daily.log
D1=$(date -d "-9 days" +%Y%m%d)
D2=$(date +%Y%m%d)
BAK=/mnt/e/backup/stockheat_20260919
mkdir -p $BAK
/usr/bin/python3.12 /mnt/e/stockSurface/margin_fetch.py "$D1" "$D2" >> $LOG 2>&1 || { /mnt/e/stockSurface/alert.sh FETCH_FAIL "margin_daily 拉取失败 $(date +%F)"; exit 1; }
/usr/bin/python3.12 /mnt/e/stockSurface/margin_build.py >> $LOG 2>&1 || { /mnt/e/stockSurface/alert.sh BUILD_FAIL "margin_daily 聚合失败 $(date +%F)"; exit 1; }
N=$(ls /mnt/e/stockSurface/margin_detail/*.parquet 2>/dev/null | wc -l)
J=$(stat -c %s /mnt/e/stockSurface/margin_heat.json 2>/dev/null || echo 0)
# 三重校验: json可读+dates尾对齐最新parquet+两文件大小合理
V=$(/usr/bin/python3.12 - << 'PYCHK'
import json, os, glob
try:
    j = json.load(open('/mnt/e/stockSurface/margin_heat.json'))
    dates = [str(d) for d in j['dates']]
    latest_pq = max(os.path.basename(f)[:8] for f in glob.glob('/mnt/e/stockSurface/margin_detail/*.parquet'))
    tail_ok = dates[-1] >= latest_pq
    sz_full = os.path.getsize('/mnt/e/stockSurface/margin_heat_full.json') > 50e6
    sz_page = len(dates) > 2500 and os.path.getsize('/mnt/e/stockSurface/margin_heat.json') > 10e6
    sd_ok = all(str(x) == x for x in j.get('stockDates', [])) if 'stockDates' in j else True
    print('OK' if (tail_ok and sz_full and sz_page and sd_ok) else 'BAD ' + str({'tail': dates[-1], 'latest': latest_pq, 'full': sz_full, 'page': sz_page, 'sd': sd_ok}))
except Exception as e:
    print(f'BAD {e}')
PYCHK
)
if [ "$V" != "OK" ]; then
  /mnt/e/stockSurface/alert.sh VERIFY_FAIL "margin_daily 校验失败 $(date +%F) $V"
  cp $BAK/margin_heat_full.json /mnt/e/stockSurface/ 2>/dev/null && echo "$(date '+%F %T') 已回滚full备份" >> $LOG
  exit 1
fi
echo "$(date '+%F %T') margin_daily OK files=$N json=$J" >> $LOG
