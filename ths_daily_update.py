#!/usr/bin/python3
# THS chain daily update: cache increment -> heat/score full/slice/tier regen -> index refresh
# Iron rules: only CONCAT new rows; atomic writes; read-back verify; silent on success.
import subprocess, sys, os, re, json, datetime, shutil

BASE = '/mnt/e/stockSurface'
LOG = []
def log(m):
    line = f'[{datetime.datetime.now().strftime("%H:%M:%S")}] {m}'
    print(line, flush=True); LOG.append(line)

def run(script, tag, timeout=3500):
    r = subprocess.run(['/usr/bin/python3.12', os.path.join(BASE, script)],
                       capture_output=True, text=True, timeout=timeout, cwd=BASE)
    tail = (r.stdout or '').strip().splitlines()[-3:]
    if r.returncode != 0:
        log(f'{tag} FAIL exit={r.returncode}: {(r.stderr or "").strip()[-300:]}')
        return False
    log(f'{tag} OK: {" | ".join(tail)}')
    return True

# ── Step 0: weekday guard
today = datetime.date.today()
if today.weekday() >= 5:
    log('weekend, skip'); sys.exit(0)

# ── Step 1: fetch incremental daily bars (tushare per-date)
import pandas as pd, tushare as ts, time
CACHE = os.path.join(BASE, 'cache_td_v2.parquet')
dates_old = set(pd.read_parquet(CACHE, columns=['trade_date'])['trade_date'].unique())
cache_max = int(max(dates_old))
log(f'cache max={cache_max}, {len(dates_old)} days')

pro = ts.pro_api()
missing = []
d = today
for _ in range(8):
    ds = d.strftime('%Y%m%d')
    if int(ds) > cache_max:
        try:
            tdf = pro.daily(trade_date=ds)
            if tdf is not None and len(tdf) > 100:
                missing.append(ds); log(f'  new trade day {ds}: {len(tdf)} rows')
            time.sleep(0.4)
        except Exception as e:
            log(f'  probe {ds} err {str(e)[:60]}')
    d -= datetime.timedelta(days=1)
missing.sort()

if not missing:
    log('cache already latest'); sys.exit(0)

# ── Step 2: append new rows (CONCAT only; never rewrite columns-subset)
import numpy as np
si = pd.read_parquet(os.path.join(BASE, 'ths_universe.parquet'))
valid = set(si['code'])
new_rows = []
for ds in missing:
    for att in range(3):
        try:
            tdf = pro.daily(trade_date=ds)
            if tdf is not None and len(tdf) > 0:
                # ts_code -> bare 6-digit code for universe matching
                tdf = tdf[tdf['ts_code'].str[:6].isin(valid)]
                new_rows.append(tdf)
                log(f'  fetched {ds}: {len(tdf)} rows')
                break
        except Exception as e:
            if '频率' in str(e) or 'limit' in str(e).lower():
                time.sleep(60)
            else:
                time.sleep(5)

if not new_rows:
    log('no rows fetched'); sys.exit(1)

new_df = pd.concat(new_rows, ignore_index=True)
cache = pd.read_parquet(CACHE)
# align schema: cache has ONLY these 6 cols; keep exactly them, dtypes str/int32/float32
COLS = ['ts_code', 'trade_date', 'close', 'amount', 'pre_close', 'vol']
new_df = new_df[COLS].copy()
new_df['trade_date'] = new_df['trade_date'].astype('int32')
for col in ['close', 'amount', 'pre_close', 'vol']:
    new_df[col] = new_df[col].astype('float32')
new_df['ts_code'] = new_df['ts_code'].astype(str)
combined = pd.concat([cache, new_df], ignore_index=True)
combined = combined.drop_duplicates(subset=['ts_code','trade_date'])
combined = combined.sort_values(['ts_code','trade_date']).reset_index(drop=True)
# verify BEFORE replace
assert len(combined) > len(cache), 'no growth after concat'
assert combined['close'].isna().sum() == 0, 'close nulls after concat'
tmp = CACHE + '.tmp'
combined.to_parquet(tmp, index=False)
# read-back verify
chk = pd.read_parquet(tmp, columns=['trade_date','close'])
assert max(chk['trade_date']) == int(missing[-1]), f'last date mismatch {max(chk["trade_date"])} vs {missing[-1]}'
os.replace(tmp, CACHE)
log(f'cache updated: +{len(new_df)} rows -> {len(combined)} rows, last={missing[-1]}')

# ── Step 3: regen downstream chain
ok = run('compute_stock_heat.py', 'heat')
ok = run('compute_market_score_ths_full.py', 'score_full') and ok
ok = run('mk_tier_json.py', 'tier') and ok
ok = run('compute_market_score_ths.py', 'score_slice') and ok
if not ok:
    log('CHAIN FAILED'); sys.exit(1)

# ── Step 4: refresh index n_true/last_date from universe + heat files
idx_path = os.path.join(BASE, 'stock_heat.json')
idx = json.load(open(idx_path))
sizes = si.groupby('ths_code')['code'].count().to_dict()
for it in idx['industries']:
    c = str(it.get('ths_code', ''))
    if c in sizes:
        it['n_stocks'] = int(sizes[c])
    if 'n_true' in it:
        it['n_true'] = int(sizes.get(c, it['n_true']))
ldates = set()
for it in idx['industries'][:3]:
    c = str(it.get('ths_code', ''))
    fp = os.path.join(BASE, 'stock_heat', c + '.json')
    if os.path.exists(fp):
        d2 = json.load(open(fp))
        for st in d2['stocks']:
            ldates.update(st.get('dates', []))
if ldates:
    idx['last_date'] = max(ldates)
t2 = idx_path + '.tmp'
json.dump(idx, open(t2, 'w'), ensure_ascii=False, separators=(',', ':'))
chk2 = json.load(open(t2))
assert chk2['last_date'] == idx['last_date']
os.replace(t2, idx_path)
log(f'index refreshed: last_date={idx["last_date"]}')

log(f'ALL DONE cache_last={missing[-1]}')
