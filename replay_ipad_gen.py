#!/usr/bin/env python3.12
"""iPad离线部署包生成器: 全量预生成个股gz + 静态化改造
- stock/*.json.gz: 5,533只, 服务端同款逻辑(cache_td_v2+ohlc_full merge, NaN规则一致)
- 版本A(纯静态iOS本地服务器): 需页面自带DecompressionStream解压 + localStorage存档
"""
import pandas as pd, json, gzip, io, os, time, sys

BASE = '/mnt/e/stockSurface'; RP = f'{BASE}/replay'
t0 = time.time()
_tdc = pd.read_parquet(f'{BASE}/cache_td_v2.parquet', columns=['ts_code','trade_date','close','vol','amount'])
_ohl  = pd.read_parquet(f'{RP}/ohlc_full.parquet', columns=['ts_code','trade_date','open','high','low'])
TD = _tdc.merge(_ohl, on=['ts_code','trade_date'], how='left')
TD['trade_date'] = TD['trade_date'].astype(str)
print('merge', TD.shape, f'{time.time()-t0:.0f}s', flush=True)

os.makedirs(f'{RP}/stock', exist_ok=True)
n = 0; tot = 0
for ts, g in TD.groupby('ts_code', sort=False):
    g = g.sort_values('trade_date')
    rows = []
    for r in g.itertuples():
        if not (r.close == r.close): continue
        o_, h_, l_ = r.open, r.high, r.low
        if not (o_ == o_): o_ = h_ = l_ = r.close
        if not (h_ == h_): h_ = max(o_, r.close)
        if not (l_ == l_): l_ = min(o_, r.close)
        rows.append([r.trade_date, round(float(o_),3), round(float(h_),3),
                     round(float(l_),3), round(float(r.close),3),
                     float(r.vol) if r.vol == r.vol else 0,
                     float(r.amount) if r.amount == r.amount else 0])
    buf = io.BytesIO()
    with gzip.open(buf, 'wt', encoding='utf-8') as f:
        json.dump({'code': ts, 'rows': rows}, f, separators=(',',':'), allow_nan=False)
    tmp = f'{RP}/stock/{ts}.json.gz.tmp'
    open(tmp, 'wb').write(buf.getvalue())
    os.replace(tmp, f'{RP}/stock/{ts}.json.gz')
    n += 1; tot += len(rows)
    if n % 1000 == 0: print(n, f'{time.time()-t0:.0f}s', flush=True)
print(f'DONE {n}只 {tot}行 {time.time()-t0:.0f}s', flush=True)
