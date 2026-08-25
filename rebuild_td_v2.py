#!/usr/bin/env python3
"""
重建 data.json — 2015至今全历史
策略: tushare pro.daily per-trade-date, 1.25s间隔(48次/分<50次限制)
"""
from pathlib import Path
import os
BASE_DIR = str(Path(__file__).resolve().parent)

import tushare as ts
import pandas as pd
import numpy as np
import json, os, time
from datetime import datetime

PRO = ts.pro_api()

si = pd.read_parquet(os.path.join(BASE_DIR, 'stock_industry.parquet'))
code_industry = dict(zip(si['ts_code'], si['industry']))
valid_tscodes = set(si['ts_code'].tolist())
print(f"股票数: {len(valid_tscodes)}")

# ── 交易日历 (从本地json，不用tushare trade_cal) ──
import json as _json
with open(os.path.join(BASE_DIR, 'trade_days.json')) as _f:
    dates = _json.load(_f)
print(f"交易日: {len(dates)} 天 ({dates[0]}~{dates[-1]})")

# ── 缓存 ──
CACHE = os.path.join(BASE_DIR, 'cache_td_v2.parquet')
done = set()
if os.path.exists(CACHE):
    cached = pd.read_parquet(CACHE)
    done = set(cached['trade_date'].unique())
    print(f"缓存: {len(done)} 天")
else:
    cached = None

missing = [d for d in dates if d not in done]
print(f"待下载: {len(missing)} 天")

# ── 逐天下载 ──
all_dfs = [cached] if cached is not None else []
t0 = time.time()
consecutive_err = 0

for i, td in enumerate(missing):
    try:
        df = PRO.daily(trade_date=td, fields='ts_code,trade_date,close,amount,pre_close,vol')
        consecutive_err = 0
        if len(df) > 0:
            all_dfs.append(df)
            done.add(td)
    except Exception as e:
        consecutive_err += 1
        if '频率超限' in str(e) or 'limit' in str(e).lower():
            print(f"  限频! 休息65s... (已完成 {len(done)}/{len(dates)})")
            if all_dfs:
                pd.concat(all_dfs, ignore_index=True).to_parquet(CACHE, index=False)
            time.sleep(65)
            try:
                df = PRO.daily(trade_date=td, fields='ts_code,trade_date,close,amount,pre_close,vol')
                if len(df) > 0:
                    all_dfs.append(df)
                    done.add(td)
                consecutive_err = 0
            except:
                pass
        else:
            print(f"  {td}: {e}")

    if (i+1) % 50 == 0:
        elapsed = time.time() - t0
        pct = len(done) / len(dates) * 100
        eta = (len(dates) - len(done)) / (len(done) / elapsed) if elapsed > 0 else 0
        print(f"  [{pct:.0f}%] {i+1}/{len(missing)} | {td} | {len(done)}/{len(dates)}天 | ETA {eta/60:.0f}min")
        if all_dfs:
            pd.concat(all_dfs, ignore_index=True).to_parquet(CACHE, index=False)

    time.sleep(1.25)  # 48次/分

# ── 最终保存cache ──
if all_dfs:
    full = pd.concat(all_dfs, ignore_index=True)
    full.to_parquet(CACHE, index=False)
    elapsed = time.time() - t0
    print(f"\n下载完成: {len(full)} rows, {len(done)} 天, {elapsed:.0f}s")
else:
    print("ERROR: 无数据")
    exit(1)

# ══ 数据处理 ══
full = full[full['ts_code'].isin(valid_tscodes)].copy()
full['close'] = pd.to_numeric(full['close'], errors='coerce')
full['amount'] = pd.to_numeric(full['amount'], errors='coerce')
full['pre_close'] = pd.to_numeric(full['pre_close'], errors='coerce')
full['ret'] = full['close'] / full['pre_close'] - 1.0
full.loc[abs(full['ret']) > 0.2, 'ret'] = np.nan
full.loc[full['ret'].isna(), 'ret'] = 0.0
full['amount_yuan'] = full['amount'] * 1000.0
full['date_str'] = full['trade_date'].apply(lambda x: f"{x[:4]}-{x[4:6]}-{x[6:8]}")
full['industry'] = full['ts_code'].map(code_industry)
full = full[full['industry'].notna()].copy()
print(f"有效: {len(full)} rows, {full['date_str'].min()}~{full['date_str'].max()}")

# ══ daily ══
print("daily...")
daily_out = []
for date, g in full.groupby('date_str'):
    rets = g['ret'].dropna()
    n, nu = len(g), int((rets > 0).sum())
    daily_out.append({'date_str': date,
        'mean_ret': float(rets.mean()) if len(rets) else 0,
        'median_ret': float(rets.median()) if len(rets) else 0,
        'std_ret': float(rets.std()) if len(rets) > 1 else 0,
        'total_amount': float(g['amount_yuan'].sum()),
        'n_stocks': n, 'n_up': nu, 'n_down': int((rets < 0).sum()),
        'up_pct': nu / max(n, 1)})
daily_out.sort(key=lambda x: x['date_str'])

# ══ industry ══
print("industry...")
industry_out = []
for (date, ind), g in full.groupby(['date_str', 'industry']):
    rets = g['ret'].dropna()
    industry_out.append({'date_str': date, 'industry': str(ind),
        'mean_ret': float(rets.mean()) if len(rets) else 0,
        'total_amount': float(g['amount_yuan'].sum()),
        'n_stocks': len(g), 'n_up': int((rets > 0).sum())})
industry_out.sort(key=lambda x: (x['date_str'], x['industry']))

# ══ decile ══
print("decile...")
decile_out = []
for date, g in full.groupby('date_str'):
    g2 = g[g['amount_yuan'] > 0].sort_values('amount_yuan').copy()
    if len(g2) < 100: continue
    try: g2['decile'] = pd.qcut(g2['amount_yuan'], 10, labels=False, duplicates='drop') + 1
    except: continue
    for d, g3 in g2.groupby('decile'):
        rets = g3['ret'].dropna()
        decile_out.append({'date_str': date, 'decile': int(d),
            'mean_ret': float(rets.mean()) if len(rets) else 0,
            'total_amount': float(g3['amount_yuan'].sum()), 'n_stocks': len(g3)})
decile_out.sort(key=lambda x: (x['date_str'], x['decile']))

out = {'daily': daily_out, 'industry': industry_out, 'decile': decile_out}
OUT = os.path.join(BASE_DIR, 'data.json')
with open(OUT, 'w') as f: json.dump(out, f, ensure_ascii=False, allow_nan=False)
sz = os.path.getsize(OUT) / 1024 / 1024
print(f"\n✅ {OUT} ({sz:.1f}MB)")
print(f"   daily: {len(daily_out)} ({daily_out[0]['date_str']}~{daily_out[-1]['date_str']})")
print(f"   industry: {len(industry_out)}, decile: {len(decile_out)}")
