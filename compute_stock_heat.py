#!/usr/bin/env python3.12
# compute_stock_heat.py — build per-industry stock heatmap JSONs from cache_td_v2.
# Output: /mnt/e/stockSurface/stock_heat.json        (index: 90 industries, sizes, latest-day stats)
#         /mnt/e/stockSurface/stock_heat/{881xxx}.json (per-stock daily series, full history)
#
# Cell metrics kept per stock-day (compact arrays to keep files small):
#   pct_chg, close, amount, turnover_rate  (+ ts_code, name per row)
import pandas as pd, numpy as np, json, os, sys

BASE = '/mnt/e/stockSurface'
OUTDIR = os.path.join(BASE, 'stock_heat')
os.makedirs(OUTDIR, exist_ok=True)

print('loading cache_td_v2.parquet (11.7M rows)...', flush=True)
df = pd.read_parquet(os.path.join(BASE, 'cache_td_v2.parquet'),
                     columns=['ts_code', 'trade_date', 'close', 'pre_close', 'amount', 'vol'])
df['trade_date'] = df['trade_date'].astype(np.int32)   # key cols int32 per repo rule
print('loaded', df.shape, 'range', df['trade_date'].min(), '-', df['trade_date'].max(), flush=True)

print('loading turnover_rate.parquet...', flush=True)
tr = pd.read_parquet(os.path.join(BASE, 'turnover_rate.parquet'))
tr['trade_date'] = tr['trade_date'].astype(np.int32)
df = df.merge(tr, on=['ts_code', 'trade_date'], how='left')
del tr
print('merged turnover, rows:', len(df), flush=True)

# cache pct_chg column is 98.9% NaN (upstream import defect) -> recompute from close/pre_close
df['pct_chg'] = (df['close'] / df['pre_close'] - 1.0) * 100.0
df.loc[~np.isfinite(df['pct_chg']), 'pct_chg'] = np.nan

print('loading ths_universe.parquet...', flush=True)
u = pd.read_parquet(os.path.join(BASE, 'ths_universe.parquet'))
# universe: ths_industry, ths_code, code (6-digit), stock_name -> ts_code = code + .SZ/.SH/.BJ
def to_ts(c):
    c = str(c).zfill(6)
    if c.startswith(('6', '9', '5')):
        return c + '.SH'
    if c.startswith(('4', '8')):
        return c + '.BJ'
    return c + '.SZ'
u['ts_code'] = u['code'].apply(to_ts)
print('universe stocks:', len(u), 'matched industries:', u['ths_industry'].nunique(), flush=True)

m = df.merge(u[['ts_code', 'stock_name', 'ths_industry', 'ths_code']], on='ts_code', how='inner')
print('merged rows:', len(m), flush=True)

# limit to A-share main boards in universe (bj.* already filtered by universe itself)
missing = u[~u['ts_code'].isin(df['ts_code'].unique())]
if len(missing) > 0:
    print('universe stocks missing from cache:', len(missing), missing['stock_name'].head(5).tolist(), flush=True)

# ── per-industry files ──
LAST = int(m['trade_date'].max())
print('last trade date:', LAST, flush=True)

index_rows = []
for (ind, code881), g in m.groupby(['ths_industry', 'ths_code']):
    last_day = g[g['trade_date'] == LAST]
    n_stocks = g['ts_code'].nunique()
    # latest-day 5-tier momentum split for the index preview (20d return)
    idx = {
        'industry': ind, 'ths_code': str(code881), 'n_stocks': n_stocks,
        'last_date': LAST,
        'up_ratio': round(float((last_day['pct_chg'] > 0).mean()), 4) if len(last_day) else None,
        'med_pct': round(float(last_day['pct_chg'].median()), 4) if len(last_day) else None,
    }
    index_rows.append(idx)

    sub = g.sort_values(['ts_code', 'trade_date'])
    stocks = []
    for ts, gg in sub.groupby('ts_code'):
        stocks.append({
            'ts_code': ts,
            'name': str(gg['stock_name'].iloc[0]),
            'dates': gg['trade_date'].astype(int).tolist(),
            'pct': [None if pd.isna(v) else round(float(v), 3) for v in gg['pct_chg']],
            'close': [None if pd.isna(v) else round(float(v), 3) for v in gg['close']],
            'amount': [None if pd.isna(v) else round(float(v) / 1e3, 1) for v in gg['amount']],  # tushare 千元->万元
            'turn': [None if pd.isna(v) else round(float(v), 3) for v in gg['turnover_rate']],
        })
    out = {'industry': ind, 'ths_code': str(code881), 'last_date': LAST, 'stocks': stocks}
    fn = os.path.join(OUTDIR, str(code881) + '.json')
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    index_rows[-1]['file'] = str(code881) + '.json'
    print('wrote', ind, code881, n_stocks, 'stocks,', round(os.path.getsize(fn)/1e6, 2), 'MB', flush=True)

with open(os.path.join(BASE, 'stock_heat.json'), 'w', encoding='utf-8') as f:
    json.dump({'last_date': LAST, 'industries': index_rows}, f, ensure_ascii=False, separators=(',', ':'))
print('DONE index:', len(index_rows), 'industries, last_date', LAST, flush=True)
