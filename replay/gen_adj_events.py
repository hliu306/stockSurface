#!/usr/bin/env python3.12
"""replay前复权改造 ①: 生成除权事件表 adj_events.parquet
源 = cache_td_v2(close, pre_close): 除权日 factor = pre_close[t]/close[t-1]
后续 ohlc_full 日增也取 pre_close, 新事件增量并入本表.
qfq价格 = raw × ∏_{s>t} factor[s] (以最新交易日为基准的前复权)
"""
import pandas as pd, numpy as np, os

td = pd.read_parquet('/mnt/e/stockSurface/cache_td_v2.parquet',
                     columns=['ts_code', 'trade_date', 'close', 'pre_close'])
td['trade_date'] = td['trade_date'].astype(str)
td = td.sort_values(['ts_code', 'trade_date'])
td['prev_close'] = td.groupby('ts_code')['close'].shift(1)
ev = td[td.prev_close.notna() & td.pre_close.notna() & (td.prev_close > 0)]
ev = ev[(ev.pre_close / ev.prev_close - 1).abs() > 0.0005]      # 偏离>0.05%才算除权(排除四舍五入噪声)
ev = ev.assign(factor=(ev.pre_close / ev.prev_close).round(8))
ev = ev[['ts_code', 'trade_date', 'factor']]
ev['trade_date'] = ev['trade_date'].astype('int32')              # ★键列纪律: int32
assert not ev.duplicated(['ts_code', 'trade_date']).any()
ev.to_parquet('/mnt/e/stockSurface/replay/adj_events.parquet', index=False)
print('adj_events:', len(ev), '只', ev.ts_code.nunique(), '尾日', int(ev.trade_date.max()))

# 回读验证
chk = pd.read_parquet('/mnt/e/stockSurface/replay/adj_events.parquet')
assert len(chk) == len(ev)
m = chk[chk.ts_code == '600519.SH']
print('茅台事件数:', len(m), '| 20240619因子:', m[m.trade_date==20240619].factor.iloc[0])
z = chk[chk.ts_code == '688110.SH']
print('688110 20261012因子:', z[z.trade_date==20261012].factor.iloc[0].round(6))
