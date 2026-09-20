#!/usr/bin/env python3
"""逐日拉取两所逐股票两融明细 → /mnt/e/stockSurface/margin_detail/{yyyymmdd}.parquet
SSE: stock_margin_detail_sse (融资余额 + 融券余量, 需×价格换算余额)
SZSE: stock_margin_detail_szse (融资余额 + 融券余额 直给; T+1发布当日空)
幂等: 已存在文件跳过; 两所全空不落盘(下次重试)
"""
import akshare as ak
import numpy as np
import pandas as pd, os, sys, time

OUT = '/mnt/e/stockSurface/margin_detail'
os.makedirs(OUT, exist_ok=True)

cal = pd.read_parquet('/mnt/e/stockSurface/cache_td_v2.parquet', columns=['trade_date'])['trade_date'].unique()
cal = sorted(str(d) for d in cal)
start, end = sys.argv[1], sys.argv[2]
todo = [d for d in cal if start <= d <= end and not os.path.exists(f'{OUT}/{d}.parquet')]
print(f'待拉: {len(todo)} 天 ({todo[0] if todo else "-"} ~ {todo[-1] if todo else "-"})', flush=True)

ok = fail = 0
for i, d in enumerate(todo):
    parts = []
    try:
        s = ak.stock_margin_detail_sse(date=d)
        if len(s):
            parts.append(pd.DataFrame({
                'code': s['标的证券代码'].astype(str).str.zfill(6),
                'rzye': pd.to_numeric(s['融资余额'], errors='coerce'),
                'rq_vol': pd.to_numeric(s['融券余量'], errors='coerce')}))
    except Exception:
        pass
    try:
        z = ak.stock_margin_detail_szse(date=d)
        if len(z):
            parts.append(pd.DataFrame({
                'code': z['证券代码'].astype(str).str.zfill(6),
                'rzye': pd.to_numeric(z['融资余额'], errors='coerce'),
                'rqye': pd.to_numeric(z['融券余额'], errors='coerce')}))
    except Exception:
        pass
    has_sz = any('rqye' in p.columns for p in parts) and any(
        p['code'].str.startswith(('0','3')).any() for p in parts if 'rqye' in p.columns)
    if not parts or not has_sz:
        # 深市T+1未发布 → 不落盘, 次日重试补全(除非是回填历史第2次)
        fail += 1
        time.sleep(0.2)
        continue
    df = pd.concat(parts, ignore_index=True)
    for _c in ['rq_vol', 'rqye']:
        if _c not in df.columns: df[_c] = np.nan

    def to_ts(c):
        # 仅保留A股股票: 60/68沪, 00/30深, 8/4/9北; 基金(51/56/58/15/16/11/5)剔除
        if c.startswith(('60', '68')): return c + '.SH'
        if c.startswith(('00', '30')): return c + '.SZ'
        if c.startswith(('83', '87', '92', '43')): return c + '.BJ'
        return None
    df['ts_code'] = df['code'].apply(to_ts)
    df = df[df['ts_code'].notna()]
    # 同一code双所不会重复; 合并同code多行(理论无)
    df = df.groupby('ts_code', as_index=False).agg(
        rzye=('rzye', 'sum'), rq_vol=('rq_vol', 'sum'), rqye=('rqye', 'sum'))
    df.to_parquet(f'{OUT}/{d}.parquet', index=False)
    ok += 1
    if i % 25 == 0:
        print(f'{i+1}/{len(todo)} ok={ok} fail={fail}', flush=True)
    time.sleep(0.25)
print(f'DONE ok={ok} fail={fail}', flush=True)
