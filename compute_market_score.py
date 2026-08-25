#!/usr/bin/env python3
"""
计算市场状态评分 + 板块评分 + 周期阶段
输出: market_score.json
"""
from pathlib import Path
import os
BASE_DIR = str(Path(__file__).resolve().parent)

import pandas as pd
import numpy as np
import json, os, sys
from collections import defaultdict

CACHE = os.path.join(BASE_DIR, 'cache_td_v2.parquet')
SI = os.path.join(BASE_DIR, 'stock_industry.parquet')
OUT = os.path.join(BASE_DIR, 'market_score.json')

print("加载数据...")
df = pd.read_parquet(CACHE)
si = pd.read_parquet(SI)
code_ind = dict(zip(si['ts_code'], si['industry']))
code_name = dict(zip(si['ts_code'], si['name']))
df['industry'] = df['ts_code'].map(code_ind)
df = df[df['industry'].notna()].copy()

# 基础字段
df['ret'] = df['close'] / df['pre_close'] - 1.0
df.loc[abs(df['ret']) > 0.2, 'ret'] = np.nan
df['amount_yuan'] = df['amount'] * 1000.0  # 千元→元
df = df.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)

# ── 每只股票的20日均线 ──
print("计算20日均线...")
df['ma20'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(20, min_periods=10).mean())
df['above_ma20'] = (df['close'] > df['ma20']).astype(float)
df.loc[df['ma20'].isna(), 'above_ma20'] = np.nan

# ── 20日收益率 ──
df['ret_20d'] = df.groupby('ts_code')['close'].transform(lambda x: x.pct_change(20))

# ── 60日最高/最低 (用于NHNL) ──
df['high_60d'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(60, min_periods=20).max())
df['low_60d'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(60, min_periods=20).min())
df['new_high'] = (df['close'] >= df['high_60d']).astype(float)
df['new_low'] = (df['close'] <= df['low_60d']).astype(float)
df.loc[df['high_60d'].isna(), 'new_high'] = np.nan
df.loc[df['low_60d'].isna(), 'new_low'] = np.nan

print("计算日度市场指标...")
# ════════════════════════════════════
# 1. 市场状态评分 (日度)
# ════════════════════════════════════
daily_mkt = df.groupby('trade_date').agg(
    B20=('above_ma20', 'mean'),          # 站上20日线比例
    Ravg20=('ret_20d', 'mean'),           # 平均20日收益
    total_amount=('amount_yuan', 'sum'),  # 全市场成交额
    mean_ret=('ret', 'mean'),
    median_ret=('ret', 'median'),
    std_ret=('ret', 'std'),
    n_new_high=('new_high', 'sum'),
    n_new_low=('new_low', 'sum'),
    n_stocks=('ts_code', 'count'),
    n_up=('ret', lambda x: (x > 0).sum()),
    n_down=('ret', lambda x: (x < 0).sum()),
).reset_index()

daily_mkt = daily_mkt.sort_values('trade_date').reset_index(drop=True)

# NHNL 归一化
daily_mkt['NHNL'] = (daily_mkt['n_new_high'] - daily_mkt['n_new_low']) / daily_mkt['n_stocks']

# 成交额Z分数 (60日滚动)
daily_mkt['amt_ma60'] = daily_mkt['total_amount'].rolling(60, min_periods=20).mean()
daily_mkt['amt_std60'] = daily_mkt['total_amount'].rolling(60, min_periods=20).std()
daily_mkt['Zturnover'] = (daily_mkt['total_amount'] - daily_mkt['amt_ma60']) / daily_mkt['amt_std60']
daily_mkt['Zturnover'] = daily_mkt['Zturnover'].clip(-3, 3) / 3  # 归一化到[-1,1]

# 波动率 (20日滚动std_ret的年化)
daily_mkt['Vol'] = daily_mkt['std_ret'].rolling(20, min_periods=10).mean() * np.sqrt(250)
daily_mkt['Vol_norm'] = daily_mkt['Vol'] / daily_mkt['Vol'].rolling(252, min_periods=60).quantile(0.95)
daily_mkt['Vol_norm'] = daily_mkt['Vol_norm'].clip(0, 2) - 1  # 中心化

# 趋势: mean_ret的20日均值方向
daily_mkt['Trend'] = daily_mkt['mean_ret'].rolling(20, min_periods=10).mean() * 50  # scale
daily_mkt['Trend'] = daily_mkt['Trend'].clip(-1, 1)

# 各分量归一化到[-1,1]
daily_mkt['B20_s'] = daily_mkt['B20'] * 2 - 1        # [0,1]→[-1,1]
daily_mkt['Ravg20_s'] = daily_mkt['Ravg20'].clip(-0.2, 0.2) / 0.2  # ±20%→[-1,1]
daily_mkt['NHNL_s'] = daily_mkt['NHNL'].clip(-1, 1)
daily_mkt['Vol_s'] = daily_mkt['Vol_norm'].clip(-1, 1)

# MarketScore
daily_mkt['MarketScore'] = (
    0.25 * daily_mkt['B20_s'] +
    0.20 * daily_mkt['Ravg20_s'] +
    0.20 * daily_mkt['Zturnover'] +
    0.15 * daily_mkt['NHNL_s'] -
    0.10 * daily_mkt['Vol_s'] +
    0.10 * daily_mkt['Trend']
)

# 市场状态分类 (5档)
def classify_market(score):
    if score > 0.4: return '强上涨'
    if score > 0.15: return '弱上涨'
    if score > -0.15: return '平衡轮动'
    if score > -0.4: return '弱下降'
    return '强下降'
daily_mkt['market_state'] = daily_mkt['MarketScore'].apply(classify_market)

print(f"  市场评分: {len(daily_mkt)} 天")
for state, g in daily_mkt.groupby('market_state'):
    pct = len(g) / len(daily_mkt) * 100
    print(f"    {state}: {len(g)}天 ({pct:.1f}%)")

# ════════════════════════════════════
# 2. 板块评分 (日度, 110个行业)
# ════════════════════════════════════
print("计算板块评分...")
# 行业日度数据
ind_daily = df.groupby(['trade_date', 'industry']).agg(
    ind_ret=('ret', 'mean'),
    ind_amount=('amount_yuan', 'sum'),
    n_up=('ret', lambda x: (x > 0).sum()),
    n_stocks=('ts_code', 'count'),
    above_ma20=('above_ma20', 'mean'),
).reset_index()

# 20日超额收益
ind_daily = ind_daily.sort_values(['industry', 'trade_date']).reset_index(drop=True)
ind_daily['ind_ret_20d'] = ind_daily.groupby('industry')['ind_ret'].transform(
    lambda x: x.rolling(20, min_periods=10).apply(lambda r: (1 + r).prod() - 1))
mkt_ret_20d = daily_mkt.set_index('trade_date')['Ravg20'].to_dict()
ind_daily['mkt_ret_20d'] = ind_daily['trade_date'].map(mkt_ret_20d)
ind_daily['ER20'] = ind_daily['ind_ret_20d'] - ind_daily['mkt_ret_20d']

# 成交额份额 + 变化
total_amt = daily_mkt.set_index('trade_date')['total_amount'].to_dict()
ind_daily['amt_share'] = ind_daily['ind_amount'] / ind_daily['trade_date'].map(total_amt)
ind_daily['amt_share_5d_ago'] = ind_daily.groupby('industry')['amt_share'].transform(
    lambda x: x.shift(5))
ind_daily['delta_share'] = ind_daily['amt_share'] - ind_daily['amt_share_5d_ago']

# 广度 (板块内上涨比例)
ind_daily['breadth'] = ind_daily['n_up'] / ind_daily['n_stocks']

# 持续性: 过去5日ER20的符号一致性
ind_daily['ER20_sign'] = np.sign(ind_daily['ER20'])
ind_daily['persistence'] = ind_daily.groupby('industry')['ER20_sign'].transform(
    lambda x: x.rolling(5, min_periods=3).mean())

# 龙头强度: 板块内top3股票当日收益率均值 (代理)
# 用ind_ret vs 全市场mean_ret的差作为简化
ind_daily['leader_strength'] = (ind_daily['ind_ret'] - ind_daily['trade_date'].map(
    daily_mkt.set_index('trade_date')['mean_ret'].to_dict())).rolling(5, min_periods=3, on='trade_date').mean() if False else 0

# 简化: 用板块ret的5日均值作为leader代理
ind_daily['ind_ret_5d'] = ind_daily.groupby('industry')['ind_ret'].transform(
    lambda x: x.rolling(5, min_periods=3).mean())
ind_daily['leader'] = ind_daily['ind_ret_5d'] - ind_daily['trade_date'].map(
    daily_mkt.set_index('trade_date')['mean_ret'].to_dict())
ind_daily['leader'] = ind_daily['leader'].clip(-0.05, 0.05) / 0.05

# 流动性: amt_share的20日均值的归一化
ind_daily['liq_ma20'] = ind_daily.groupby('industry')['amt_share'].transform(
    lambda x: x.rolling(20, min_periods=10).mean())

# 归一化分量
ind_daily['ER20_s'] = ind_daily['ER20'].clip(-0.15, 0.15) / 0.15
ind_daily['delta_share_s'] = ind_daily['delta_share'].clip(-0.02, 0.02) / 0.02
ind_daily['breadth_s'] = ind_daily['breadth'] * 2 - 1
ind_daily['persistence_s'] = ind_daily['persistence'].clip(-1, 1)

# SectorScore
ind_daily['SectorScore'] = (
    0.25 * ind_daily['ER20_s'].fillna(0) +
    0.20 * ind_daily['delta_share_s'].fillna(0) +
    0.20 * ind_daily['breadth_s'].fillna(0) +
    0.15 * ind_daily['persistence_s'].fillna(0) +
    0.10 * ind_daily['leader'].fillna(0) +
    0.10 * ind_daily['liq_ma20'].fillna(0).clip(-1, 1)
)

# ════════════════════════════════════
# 3. 周期阶段识别
# ════════════════════════════════════
print("识别周期阶段...")

def classify_cycle(row, industry_df):
    """根据板块的ER20, delta_share, breadth趋势判断周期阶段"""
    er = row.get('ER20_s', 0) or 0
    ds = row.get('delta_share_s', 0) or 0
    br = row.get('breadth_s', 0) or 0
    score = row.get('SectorScore', 0) or 0

    # 成交额份额趋势: 扩张 or 收缩
    share_expanding = ds > 0.1
    share_contracting = ds < -0.1
    # 广度趋势
    high_breadth = br > 0.2
    breadth_collapsing = br < -0.1
    # 价格趋势
    price_leading = er > 0.05

    if price_leading and not share_expanding and not high_breadth:
        return '发现期'
    if price_leading and share_expanding and high_breadth:
        return '扩散期'
    if price_leading and share_expanding and not breadth_collapsing:
        return '共识期'
    if not price_leading and share_expanding and breadth_collapsing:
        return '拥挤期'
    if not price_leading and share_contracting:
        return '衰退期'
    return '过渡期'

# 用滑窗趋势判断更稳健
# 对每个行业每天, 取5日趋势
for col in ['ER20_s', 'delta_share_s', 'breadth_s', 'SectorScore']:
    ind_daily[f'{col}_trend5'] = ind_daily.groupby('industry')[col].transform(
        lambda x: x.rolling(5, min_periods=3).mean())

ind_daily['cycle_stage'] = ind_daily.apply(
    lambda r: classify_cycle(r, None), axis=1)

print(f"  板块评分: {len(ind_daily)} 行")
for stage, g in ind_daily.groupby('cycle_stage'):
    pct = len(g) / len(ind_daily) * 100
    print(f"    {stage}: {len(g)} ({pct:.1f}%)")

# ════════════════════════════════════
# 4. 输出JSON
# ════════════════════════════════════
print("保存JSON...")

# 4a. 市场评分日度
market_out = []
for _, r in daily_mkt.iterrows():
    market_out.append({
        'date': r['trade_date'],
        'score': round(float(r['MarketScore']), 4),
        'state': r['market_state'],
        'B20': round(float(r['B20']), 4) if pd.notna(r['B20']) else 0,
        'Ravg20': round(float(r['Ravg20']), 4) if pd.notna(r['Ravg20']) else 0,
        'Zturnover': round(float(r['Zturnover']), 4) if pd.notna(r['Zturnover']) else 0,
        'NHNL': round(float(r['NHNL']), 4) if pd.notna(r['NHNL']) else 0,
        'Vol': round(float(r['Vol']), 4) if pd.notna(r['Vol']) else 0,
        'Trend': round(float(r['Trend']), 4) if pd.notna(r['Trend']) else 0,
        'total_amount': round(float(r['total_amount']), 0) if pd.notna(r['total_amount']) else 0,
        'up_pct': round(float(r['n_up'] / max(r['n_stocks'], 1)), 4),
        'n_stocks': int(r['n_stocks']),
    })

# 4b. 板块评分: 取最近250天输出 (减少体积)
recent_dates = sorted(daily_mkt['trade_date'].unique())[-250:]
ind_recent = ind_daily[ind_daily['trade_date'].isin(recent_dates)].copy()

# 板块排名矩阵: 每日top/bottom
sector_rankings = []
for date in recent_dates:
    day_data = ind_recent[ind_recent['trade_date'] == date].sort_values('SectorScore', ascending=False)
    for rank, (_, r) in enumerate(day_data.iterrows(), 1):
        sector_rankings.append({
            'date': r['trade_date'],
            'industry': r['industry'],
            'rank': rank,
            'score': round(float(r['SectorScore']), 4) if pd.notna(r['SectorScore']) else 0,
            'ER20': round(float(r['ER20']), 4) if pd.notna(r['ER20']) else 0,
            'amt_share': round(float(r['amt_share']), 4) if pd.notna(r['amt_share']) else 0,
            'delta_share': round(float(r['delta_share']), 6) if pd.notna(r['delta_share']) else 0,
            'breadth': round(float(r['breadth']), 4) if pd.notna(r['breadth']) else 0,
            'cycle': r['cycle_stage'],
            'n_stocks': int(r['n_stocks']),
        })

# 4c. 板块排名变化
latest_date = max(recent_dates)
top_sectors_now = ind_recent[ind_recent['trade_date'] == latest_date].sort_values('SectorScore', ascending=False).head(20)
sector_detail = []
for _, r in top_sectors_now.iterrows():
    d = {'industry': str(r['industry']),
         'score': round(float(r['SectorScore']), 4) if pd.notna(r['SectorScore']) else 0.0,
         'ER20': round(float(r['ER20']), 4) if pd.notna(r['ER20']) else 0.0,
         'amt_share': round(float(r['amt_share']), 4) if pd.notna(r['amt_share']) else 0.0,
         'delta_share': round(float(r['delta_share']), 6) if pd.notna(r['delta_share']) else 0.0,
         'breadth': round(float(r['breadth']), 4) if pd.notna(r['breadth']) else 0.0,
         'cycle': str(r['cycle_stage']),
         'n_stocks': int(r['n_stocks'])}
    sector_detail.append(d)

output = {
    'meta': {
        'date_range': f"{daily_mkt['trade_date'].min()}~{daily_mkt['trade_date'].max()}",
        'n_days': len(daily_mkt),
        'n_industries': int(ind_daily['industry'].nunique()),
        'recent_window': 250,
        'components': {
            'MarketScore': '0.25*B20 + 0.20*Ravg20 + 0.20*Zturnover + 0.15*NHNL - 0.10*Vol + 0.10*Trend',
            'SectorScore': '0.25*ER20 + 0.20*ΔShare + 0.20*Breadth + 0.15*Persistence + 0.10*Leader + 0.10*Liquidity'
        }
    },
    'market': market_out,
    'sector_rankings': sector_rankings,
    'sector_detail': sector_detail,
    'latest_date': latest_date
}

# 深度清除所有NaN/Infinity (allow_nan=False会报错，必须提前清除)
def deep_clean_nan(obj):
    """递归清除所有NaN/Infinity"""
    import math
    if isinstance(obj, dict):
        return {k: deep_clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_clean_nan(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj

output = deep_clean_nan(output)

with open(OUT, 'w') as f:
    json.dump(output, f, ensure_ascii=False, allow_nan=False)
sz = os.path.getsize(OUT) / 1024
print(f"\n✅ {OUT} ({sz:.0f}KB)")
print(f"   market: {len(market_out)} days")
print(f"   sector_rankings: {len(sector_rankings)} rows")
print(f"   latest: {latest_date}")
