#!/usr/bin/env python3
"""
场内外流动性数据扩展采集 v2
新增: M2/M1/M0、社融、外汇储备、中美国债收益率曲线
输出: 合并到 liquidity.json
"""
import akshare as ak
import pandas as pd
import numpy as np
import json, os, time, warnings
warnings.filterwarnings('ignore')

CACHE = '/mnt/e/stockSurface/cache_liquidity'
OUT = '/mnt/e/stockSurface/liquidity.json'
os.makedirs(CACHE, exist_ok=True)

def load_csv(name):
    p = os.path.join(CACHE, name)
    if os.path.exists(p):
        return pd.read_csv(p)
    return None

# ════════════════════════════════════
# 加载已有数据
# ════════════════════════════════════
print("加载已有 liquidity.json...")
with open(OUT) as f:
    liq = json.load(f)
df_main = pd.DataFrame(liq['data'])
df_main['date'] = df_main['date'].astype(str)
print(f"  已有: {len(df_main)} 天")

# ════════════════════════════════════
# 1. M2/M1/M0
# ════════════════════════════════════
print("\n1. M2/M1/M0...")
m2 = load_csv('m2.csv')
if m2 is None:
    m2 = ak.macro_china_money_supply()
    m2.to_csv(os.path.join(CACHE, 'm2.csv'), index=False)

# 月份格式: "2008年01月份" → "200801"
def parse_month(s):
    s = str(s)
    import re
    m = re.search(r'(\d{4})年(\d{2})月', s)
    if m: return m.group(1) + m.group(2)
    # 纯数字 "202603"
    if re.match(r'^\d{6}$', s): return s
    return None

m2['month'] = m2['月份'].apply(parse_month)
m2 = m2.dropna(subset=['month']).sort_values('month').reset_index(drop=True)

# 提取数值列
m2_out = pd.DataFrame({
    'month': m2['month'],
    'm2': pd.to_numeric(m2['货币和准货币(M2)-数量(亿元)'], errors='coerce'),
    'm2_yoy': pd.to_numeric(m2['货币和准货币(M2)-同比增长'], errors='coerce'),
    'm1': pd.to_numeric(m2['货币(M1)-数量(亿元)'], errors='coerce'),
    'm1_yoy': pd.to_numeric(m2['货币(M1)-同比增长'], errors='coerce'),
    'm0': pd.to_numeric(m2['流通中的现金(M0)-数量(亿元)'], errors='coerce'),
})
# M1-M2剪刀差
m2_out['m1_m2_scissors'] = m2_out['m1_yoy'] - m2_out['m2_yoy']
m2_out = m2_out.dropna(subset=['m2']).reset_index(drop=True)
print(f"  M2: {len(m2_out)} 月, {m2_out['month'].iloc[0]}~{m2_out['month'].iloc[-1]}")

# 映射到日度 (月度数据forward-fill: 该月所有交易日 + 数据未发布的新月份日期沿用最近已知月)
m2_map = m2_out.set_index('month').to_dict('index')
m2_months = sorted(m2_map.keys())
for _, row in df_main.iterrows():
    ym = row['date'][:6]
    key = ym if ym in m2_map else None
    if key is None:   # 找<=ym的最近月份(跨未发布月沿用)
        prior = [m for m in m2_months if m <= ym]
        key = prior[-1] if prior else None
    if key:
        d = m2_map[key]
        df_main.loc[df_main['date'] == row['date'], 'm2'] = d['m2']
        df_main.loc[df_main['date'] == row['date'], 'm2_yoy'] = d['m2_yoy']
        df_main.loc[df_main['date'] == row['date'], 'm1'] = d['m1']
        df_main.loc[df_main['date'] == row['date'], 'm1_yoy'] = d['m1_yoy']
        df_main.loc[df_main['date'] == row['date'], 'm1_m2_scissors'] = d['m1_m2_scissors']

# ════════════════════════════════════
# 2. 社融
# ════════════════════════════════════
print("\n2. 社融...")
sf = load_csv('social_financing.csv')
if sf is None:
    sf = ak.macro_china_shrzgm()
    sf.to_csv(os.path.join(CACHE, 'social_financing.csv'), index=False)

sf['month'] = sf['月份'].apply(parse_month)
sf = sf.dropna(subset=['month']).sort_values('month').reset_index(drop=True)
sf['sf_total'] = pd.to_numeric(sf['社会融资规模增量'], errors='coerce')
sf['sf_loan'] = pd.to_numeric(sf['其中-人民币贷款'], errors='coerce')
sf['sf_bond'] = pd.to_numeric(sf['其中-企业债券'], errors='coerce')
sf['sf_equity'] = pd.to_numeric(sf['其中-非金融企业境内股票融资'], errors='coerce')
sf_out = sf[['month', 'sf_total', 'sf_loan', 'sf_bond', 'sf_equity']].copy()
sf_out['sf_total_12m'] = sf_out['sf_total'].rolling(12, min_periods=6).mean()
print(f"  社融: {len(sf_out)} 月")

sf_map = sf_out.set_index('month').to_dict('index')
sf_months = sorted(sf_map.keys())
for _, row in df_main.iterrows():
    ym = row['date'][:6]
    if ym not in sf_map:
        prior = [m for m in sf_months if m <= ym]
        ym = prior[-1] if prior else None
    if ym in sf_map:
        d = sf_map[ym]
        for col in ['sf_total', 'sf_loan', 'sf_bond', 'sf_equity', 'sf_total_12m']:
            if col in d and pd.notna(d[col]):
                df_main.loc[df_main['date'] == row['date'], col] = d[col]

# ════════════════════════════════════
# 3. 外汇储备
# ════════════════════════════════════
print("\n3. 外汇储备...")
fx = load_csv('forex_gold.csv')
if fx is None:
    fx = ak.macro_china_fx_gold()
    fx.to_csv(os.path.join(CACHE, 'forex_gold.csv'), index=False)

fx['month'] = fx['月份'].apply(parse_month)
fx = fx.dropna(subset=['month']).sort_values('month').reset_index(drop=True)
fx['fx_reserve'] = pd.to_numeric(fx['国家外汇储备-数值'], errors='coerce')
fx_out = fx[['month', 'fx_reserve']].dropna(subset=['fx_reserve']).reset_index(drop=True)
print(f"  外汇: {len(fx_out)} 月")

fx_map = fx_out.set_index('month').to_dict('index')
fx_months = sorted(fx_map.keys())
for _, row in df_main.iterrows():
    ym = row['date'][:6]
    if ym not in fx_map:
        prior = [m for m in fx_months if m <= ym]
        ym = prior[-1] if prior else None
    if ym and ym in fx_map:
        df_main.loc[df_main['date'] == row['date'], 'fx_reserve'] = fx_map[ym]['fx_reserve']

# ════════════════════════════════════
# 4. 中美国债收益率
# ════════════════════════════════════
print("\n4. 中美国债收益率...")
bond = load_csv('bond_zh_us.csv')
if bond is None:
    bond = ak.bond_zh_us_rate(start_date="20200101")
    bond.to_csv(os.path.join(CACHE, 'bond_zh_us.csv'), index=False)

# 日期格式: "2026-07-28" → "20260728"
bond['date'] = bond['日期'].astype(str).str.replace('-','').str[:8]
bond = bond.sort_values('date').drop_duplicates(subset='date').reset_index(drop=True)

bond_cols_map = {
    '中国国债收益率2年': 'cn_bond_2y',
    '中国国债收益率5年': 'cn_bond_5y',
    '中国国债收益率10年': 'cn_bond_10y',
    '中国国债收益率30年': 'cn_bond_30y',
    '中国国债收益率10年-2年': 'cn_bond_spread_10_2',
    '美国国债收益率2年': 'us_bond_2y',
    '美国国债收益率5年': 'us_bond_5y',
    '美国国债收益率10年': 'us_bond_10y',
    '美国国债收益率30年': 'us_bond_30y',
    '美国国债收益率10年-2年': 'us_bond_spread_10_2',
}
for orig, new in bond_cols_map.items():
    if orig in bond.columns:
        bond[new] = pd.to_numeric(bond[orig], errors='coerce')

# 中美利差
if 'cn_bond_10y' in bond.columns and 'us_bond_10y' in bond.columns:
    bond['cn_us_spread_10y'] = bond['cn_bond_10y'] - bond['us_bond_10y']
if 'cn_bond_2y' in bond.columns and 'us_bond_2y' in bond.columns:
    bond['cn_us_spread_2y'] = bond['cn_bond_2y'] - bond['us_bond_2y']

bond_merge = bond[['date'] + list(bond_cols_map.values()) + ['cn_us_spread_10y', 'cn_us_spread_2y']].copy()
print(f"  国债: {len(bond_merge)} 天, {bond_merge['date'].iloc[0]}~{bond_merge['date'].iloc[-1]}")

# 合并到主表
for col in list(bond_cols_map.values()) + ['cn_us_spread_10y', 'cn_us_spread_2y']:
    if col not in df_main.columns:
        df_main[col] = np.nan
bond_dict = bond_merge.set_index('date').to_dict('index')
for _, row in df_main.iterrows():
    d = row['date']
    if d in bond_dict:
        bd = bond_dict[d]
        for col in bd:
            if pd.notna(bd[col]):
                df_main.loc[df_main['date'] == d, col] = bd[col]

# ════════════════════════════════════
# 补充计算
# ════════════════════════════════════
print("\n计算衍生指标...")

# M2同比的6月变化
if 'm2_yoy' in df_main.columns:
    df_main['m2_yoy_chg'] = df_main['m2_yoy'].diff(120)  # ~6个月交易日

# 社融12月滚动均值/标准差
if 'sf_total' in df_main.columns:
    # 社融是月度, 同一个月内所有交易日值相同, 计算月度Z
    sf_monthly = df_main.drop_duplicates('date').groupby(df_main['date'].str[:6])['sf_total'].first()
    sf_ma12 = sf_monthly.rolling(12, min_periods=6).mean()
    sf_std12 = sf_monthly.rolling(12, min_periods=6).std()
    sf_z = (sf_monthly - sf_ma12) / sf_std12
    sf_z_map = sf_z.to_dict()
    for _, row in df_main.iterrows():
        ym = row['date'][:6]
        if ym in sf_z_map and pd.notna(sf_z_map[ym]):
            df_main.loc[df_main['date'] == row['date'], 'sf_z'] = sf_z_map[ym]

# 替换NaN为null
df_main = df_main.where(pd.notna(df_main), None)

# 统计
out_list = df_main.to_dict('records')
for r in out_list:
    for k, v in list(r.items()):
        if isinstance(v, (np.floating, np.integer)):
            r[k] = float(v)
        elif v is None:
            continue
        elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            r[k] = None

n_m2 = sum(1 for r in out_list if r.get('m2') is not None)
n_sf = sum(1 for r in out_list if r.get('sf_total') is not None)
n_fx = sum(1 for r in out_list if r.get('fx_reserve') is not None)
n_bond = sum(1 for r in out_list if r.get('cn_bond_10y') is not None)

output = {
    'meta': {
        'date_range': liq['meta']['date_range'],
        'n_days': len(out_list),
        'fields': {
            **liq['meta']['fields'],
            'm2_yoy': 'M2同比(%)',
            'm1_yoy': 'M1同比(%)',
            'm1_m2_scissors': 'M1-M2剪刀差(%)',
            'sf_total': '社融增量(亿)',
            'sf_z': '社融月度Z分数',
            'fx_reserve': '外汇储备(万亿美元)',
            'cn_bond_10y': '中国国债10Y(%)',
            'us_bond_10y': '美国国债10Y(%)',
            'cn_us_spread_10y': '中美10Y利差(%)',
            'cn_us_spread_2y': '中美2Y利差(%)',
            'cn_bond_spread_10_2': '国债10Y-2Y利差(%)',
        },
        'coverage': {
            **liq['meta']['coverage'],
            'M2': n_m2,
            '社融': n_sf,
            '外汇': n_fx,
            '国债': n_bond,
        }
    },
    'data': out_list
}

with open(OUT, 'w') as f:
    json.dump(output, f, ensure_ascii=False)
sz = os.path.getsize(OUT) / 1024
print(f"\n✅ {OUT} ({sz:.0f}KB)")
print(f"   M2: {n_m2}天, 社融: {n_sf}天, 外汇: {n_fx}天, 国债: {n_bond}天")
