#!/bin/bash
# ══ 两融数据全自动管线 v3 (无人工/无模型交互, 自愈, 成功静默失败报警) ══
# 发布规则(实证+官方):
#   SSE 当日明细 18:00-19:30入库, 次日08:00前再刷新一遍
#   SZSE 明细     T+1发布: 次日 08:30-09:00 之间(官方细则"开市前公布前一交易日明细")
#   → 稳妥拉取窗口 = 次日 08:35 起跑, 守卫等双所齐
# 设计: 每交易日 08:35 拉昨日(双所齐) + 18:25 拉今日SSE(SZSE明早补) + 校验 + 回滚 + 报警落盘
#       全程cron触发, 不依赖任何交互
export XDG_RUNTIME_DIR=/run/user/1000
LOG=/tmp/margin_daily.log
ALERT=/mnt/e/stockSurface/alert.sh
BASE=/mnt/e/stockSurface
BAK=/mnt/e/backup/stockheat_20260919
mkdir -p $BAK

exec 9>/tmp/margin_pipeline.lock
flock -n 9 || exit 0    # 防重入

MODE="${1:-daily}"       # daily(默认) | morning
if [ "$MODE" = "morning" ]; then
  # 早间: 补昨日双所(SZSE T+1 8:30后齐) — 拉-4日窗口自动补漏
  D=$(date -d "-1 day" +%Y%m%d)
else
  # 晚间: 今日SSE已入库(18:25跑), SZSE明日早间morning模式补
  D=$(date +%Y%m%d)
fi
D1=$(date -d "-9 days" +%Y%m%d)

# ① 拉取(幂等, 已有跳过; fetch内部守卫: 深市未发布则不落盘)
/usr/bin/python3.12 $BASE/margin_fetch.py "$D1" "$D" >> $LOG 2>&1 || {
  bash $ALERT FETCH_FAIL "拉取退出码非0 (窗口$D1~$D)"; exit 1; }

# ② 重建
/usr/bin/python3.12 $BASE/margin_build.py >> $LOG 2>&1 || {
  bash $ALERT BUILD_FAIL "build退出码非0"; exit 1; }

# ②b 行业K线日更(90个THS行业指数, bar弹窗蜡烛图数据源; 独立于margin, 失败不阻断主链)
/usr/bin/python3.12 $BASE/ths_kline_daily.py >> $LOG 2>&1 || {
  bash $ALERT KLINE_FAIL "ths_kline日更退出码非0"; }

# ③ 校验(同margin_daily.sh三重)
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
  bash $ALERT VERIFY_FAIL "校验失败 $V"
  cp $BAK/margin_heat_full.json $BASE/ 2>/dev/null && echo "$(date '+%F %T') 已回滚full备份" >> $LOG
  exit 1
fi

# ④ full备份滚动(E盘) — 只在校验OK后覆盖, 防止坏数据污染备份
cp $BASE/margin_heat_full.json $BAK/ 2>/dev/null
echo "$(date '+%F %T') margin_pipeline[$MODE] OK json尾=$( /usr/bin/python3.12 -c "import json;print(json.load(open('$BASE/margin_heat.json'))['dates'][-1])" 2>/dev/null)" >> $LOG
