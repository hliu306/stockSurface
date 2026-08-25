#!/usr/bin/env python3
from pathlib import Path
import os
BASE_DIR = str(Path(__file__).resolve().parent)

"""
场内外流动性数据采集 + 计算
数据源: akshare (免费无限制) + 已有tushare缓存
输出: <repo>/liquidity.json
"""
import akshare as ak
import pandas as pd
import numpy as np
import json, os, sys, time, warnings
warnings.filterwarnings('ignore')

OUT = os.path.join(BASE_DIR, 'liquidity.json')
CACHE_DIR = os.path.join(BASE_DIR, 'cache_liquidity')
os.makedirs(CACHE_DIR, exist_ok=True)

def cache_path(name):
    return os.path.join(CACHE_DIR, name)

def load_or_fetch(name, fetch_fn, ttl_days=1):
    """缓存加载，超过ttl_days重新获取"""
    p = cache_path(name)
    if os.path.exists(p):
        mtime = os.path.getmtime(p)
        age = (time.time() - mtime) / 86400
        if age < ttl_days:
            return pd.read_csv(p)
    try:
        df = fetch_fn()
        if df is not None and len(df) > 0:
            df.to_csv(p, index=False)
            return df
    except Exception as e:
        print(f"  {name} fetch error: {e}")
        if os.path.exists(p):
            return pd.read_csv(p)
    return None

# ════════════════════════════════════
# 1. 两融余额 (全市场汇总)
# ════════════════════════════════════
print("1. 两融余额...")
def fetch_margin():
    # 上交所+深交所逐日汇总
    df = ak.stock_margin_detail_sse(date='20260725')  # 最新一期
    return df
# 两融需要逐日拉取，但只能拉个股明细。改用汇总接口
def fetch_margin_total():
    """沪深两市融资融券汇总"""
    try:
        df = ak.stock_margin_sse(start_date='20150101', end_date='20260728')
        return df
    except:
        return None
margin = load_or_fetch('margin_sse.csv', fetch_margin_total, ttl_days=7)
if margin is not None:
    print(f"  两融(SSE): {len(margin)} rows, cols={list(margin.columns)[:8]}")
    print(f"  sample: {margin.tail(1).to_dict('records')[0]}")
else:
    print("  两融获取失败")

# ════════════════════════════════════
# 2. 北向资金
# ════════════════════════════════════
print("\n2. 北向资金...")
def fetch_hsgt():
    """沪深股通历史净流入"""
    sh = ak.stock_hsgt_hist_em(symbol="沪股通")
    sz = ak.stock_hsgt_hist_em(symbol="深股通")
    # 合并
    sh['channel'] = '沪股通'
    sz['channel'] = '深股通'
    combined = pd.concat([sh, sz], ignore_index=True)
    return combined
hsgt = load_or_fetch('hsgt.csv', fetch_hsgt, ttl_days=7)
if hsgt is not None:
    print(f"  北向资金: {len(hsgt)} rows, cols={list(hsgt.columns)[:8]}")
else:
    print("  北向资金获取失败")

# ════════════════════════════════════
# 3. SHIBOR
# ════════════════════════════════════
print("\n3. SHIBOR...")
def fetch_shibor():
    return ak.macro_china_shibor_all()
shibor = load_or_fetch('shibor.csv', fetch_shibor, ttl_days=7)
if shibor is not None:
    print(f"  SHIBOR: {len(shibor)} rows, cols={list(shibor.columns)[:8]}")

# ════════════════════════════════════
# 4. 国债收益率
# ════════════════════════════════════
print("\n4. 国债收益率...")
def fetch_bond_yield():
    return ak.bond_china_yield(start_date="20150101", end_date="20260728")
bond = load_or_fetch('bond_yield.csv', fetch_bond_yield, ttl_days=7)
if bond is not None:
    print(f"  国债收益率: {len(bond)} rows, cols={list(bond.columns)[:8]}")

# ════════════════════════════════════
# 5. 全市场成交额 (已有缓存)
# ════════════════════════════════════
print("\n5. 全市场成交额...")
df_all = pd.read_parquet(os.path.join(BASE_DIR, 'cache_td_v2.parquet'))
df_all['amount_yuan'] = df_all['amount'] * 1000.0
daily_amt = df_all.groupby('trade_date')['amount_yuan'].sum().reset_index()
daily_amt.columns = ['date', 'total_amount']
daily_amt = daily_amt.sort_values('date').reset_index(drop=True)
print(f"  成交额: {len(daily_amt)} days")

# 全市场市值代理: 用当日股价*股本 (简化为成交额的50日均值*缩放)
# 更好的是直接用指数
print("\n6. 指数数据...")
def fetch_index():
    idx = ak.stock_zh_index_daily_em(symbol="sh000001")
    return idx
idx_data = load_or_fetch('index_sh.csv', fetch_index, ttl_days=1)
if idx_data is not None:
    print(f"  上证指数: {len(idx_data)} rows, cols={list(idx_data.columns)[:8]}")

# ════════════════════════════════════
# 数据整合 → JSON
# ════════════════════════════════════
print("\n=== 整合数据 ===")

# 时间轴: 以全市场成交额为准
dates_all = sorted(daily_amt['date'].unique())
print(f"时间轴: {len(dates_all)} days ({dates_all[0]}~{dates_all[-1]})")

# --- 两融处理 ---
margin_daily = None
if margin is not None:
    print(f"  margin cols: {list(margin.columns)}")
    # stock_margin_sse 返回信用交易汇总
    # 列: 日期, 信用交易融资余额, 信用交易融券余量, ...
    if '信用交易日期' in margin.columns:
        margin = margin.rename(columns={'信用交易日期': 'date'})
    elif '日期' in margin.columns:
        margin = margin.rename(columns={'日期': 'date'})

    # 尝试聚合
    if '融资余额' in margin.columns:
        margin_daily = margin.groupby('date').agg(
            rzye=('融资余额', 'sum'),
            rqyl=('融券余量', 'sum'),
        ).reset_index().sort_values('date')
    elif '信用交易融资余额' in margin.columns:
        margin_daily = margin.groupby('date').agg(
            rzye=('信用交易融资余额', 'sum'),
        ).reset_index().sort_values('date')
    elif '融资' in margin.columns:
        margin_daily = margin.groupby('date').agg(
            rzye=('融资', 'sum'),
        ).reset_index().sort_values('date')
    if margin_daily is not None:
        print(f"  两融日度: {len(margin_daily)} days")

# --- 北向资金处理 ---
hsgt_daily = None
if hsgt is not None:
    print(f"  hsgt cols: {list(hsgt.columns)}")
    if '日期' in hsgt.columns:
        hsgt = hsgt.rename(columns={'日期': 'date'})
    # 按日汇总沪深合计
    agg_dict = {}
    for c in ['当日成交净买额', '当日资金流入', '买入成交额', '卖出成交额']:
        if c in hsgt.columns:
            agg_dict[c] = 'sum'
    if agg_dict:
        hsgt_daily = hsgt.groupby('date').agg(agg_dict).reset_index().sort_values('date')
        print(f"  北向日度: {len(hsgt_daily)} days")

# --- SHIBOR处理 ---
shibor_daily = None
if shibor is not None:
    print(f"  shibor cols: {list(shibor.columns)}")
    if '日期' in shibor.columns:
        shibor = shibor.rename(columns={'日期': 'date'})
    shibor_daily = shibor.sort_values('date')
    print(f"  SHIBOR日度: {len(shibor_daily)} days")

# --- 国债收益率处理 ---
bond_daily = None
if bond is not None:
    print(f"  bond cols: {list(bond.columns)}")
    if '日期' in bond.columns:
        bond = bond.rename(columns={'日期': 'date'})
    # 只取国债收益率曲线
    bond_gov = bond[bond['曲线名称'].str.contains('国债', na=False)] if '曲线名称' in bond.columns else bond
    bond_daily = bond_gov.sort_values('date')
    print(f"  国债日度: {len(bond_daily)} days")

# --- 指数处理 ---
idx_daily = None
if idx_data is not None:
    print(f"  idx cols: {list(idx_data.columns)}")
    if '日期' in idx_data.columns:
        idx_data = idx_data.rename(columns={'日期': 'date'})
    elif 'trade_date' in idx_data.columns:
        idx_data = idx_data.rename(columns={'trade_date': 'date'})
    idx_daily = idx_data.sort_values('date')
    print(f"  指数日度: {len(idx_daily)} days")

# ════════════════════════════════════
# 构建统一JSON输出
# ════════════════════════════════════
print("\n构建JSON...")

# 把所有日度数据对齐到统一时间轴
def date_to_str(d):
    """各种日期格式统一为 YYYYMMDD"""
    d = str(d).strip()
    if '-' in d:
        return d.replace('-', '').replace('/', '')[:8]
    return d[:8]

# 对齐所有数据
timeline = {}
for d in dates_all:
    ds = date_to_str(d)
    timeline[ds] = {'date': ds}

# 成交额
amt_map = {date_to_str(r['date']): r['total_amount'] for _, r in daily_amt.iterrows()}
for ds in timeline:
    timeline[ds]['total_amount'] = float(amt_map.get(ds, 0))

# 两融
if margin_daily is not None:
    for _, r in margin_daily.iterrows():
        ds = date_to_str(r['date'])
        if ds in timeline:
            timeline[ds]['margin_balance'] = float(r.get('rzye', 0))
            if 'rqyl' in r:
                timeline[ds]['short_balance'] = float(r.get('rqyl', 0))

# 北向
if hsgt_daily is not None:
    for _, r in hsgt_daily.iterrows():
        ds = date_to_str(r['date'])
        if ds in timeline:
            net = r.get('当日成交净买额', 0)
            if pd.notna(net):
                timeline[ds]['north_net'] = float(net)

# SHIBOR
if shibor_daily is not None:
    for _, r in shibor_daily.iterrows():
        ds = date_to_str(r['date'])
        if ds in timeline:
            for col_label, out_key in [('O/N-定价','shibor_on'), ('1W-定价','shibor_1w'),
                                        ('1M-定价','shibor_1m'), ('3M-定价','shibor_3m'),
                                        ('1Y-定价','shibor_1y')]:
                if col_label in r and pd.notna(r[col_label]):
                    timeline[ds][out_key] = float(r[col_label])

# 国债
if bond_daily is not None:
    for _, r in bond_daily.iterrows():
        ds = date_to_str(r['date'])
        if ds in timeline:
            for col, key in [('1年','bond_1y'), ('3年','bond_3y'), ('10年','bond_10y')]:
                if col in r and pd.notna(r[col]):
                    timeline[ds][key] = float(r[col])

# 指数
if idx_daily is not None:
    close_col = '收盘' if '收盘' in idx_daily.columns else ('close' if 'close' in idx_daily.columns else None)
    vol_col = '成交量' if '成交量' in idx_daily.columns else ('vol' if 'vol' in idx_daily.columns else None)
    if close_col:
        for _, r in idx_daily.iterrows():
            ds = date_to_str(r['date'])
            if ds in timeline and pd.notna(r[close_col]):
                timeline[ds]['index_close'] = float(r[close_col])
            if vol_col and ds in timeline and pd.notna(r.get(vol_col)):
                timeline[ds]['index_vol'] = float(r[vol_col])

# 转为有序列表
out_list = []
for ds in sorted(timeline.keys()):
    out_list.append(timeline[ds])

# 补充计算: 滚动指标
print("计算滚动指标...")
df_out = pd.DataFrame(out_list)
df_out = df_out.sort_values('date').reset_index(drop=True)

# 成交额20日均量
if 'total_amount' in df_out.columns:
    df_out['amt_ma20'] = df_out['total_amount'].rolling(20, min_periods=5).mean()
    df_out['amt_ma5'] = df_out['total_amount'].rolling(5, min_periods=2).mean()
    # 成交额Z分数
    df_out['amt_z'] = (df_out['total_amount'] - df_out['amt_ma20']) / \
                      df_out['total_amount'].rolling(20, min_periods=5).std()
    df_out['amt_z'] = df_out['amt_z'].clip(-4, 4)

# 两融变化
if 'margin_balance' in df_out.columns:
    df_out['margin_ma5'] = df_out['margin_balance'].rolling(5, min_periods=2).mean()
    df_out['margin_chg'] = df_out['margin_balance'].diff()
    # 两融/成交额比率
    df_out['margin_to_amt'] = df_out['margin_balance'] / df_out['amt_ma20'] / 10

# 北向累计
if 'north_net' in df_out.columns:
    df_out['north_net_ma5'] = df_out['north_net'].rolling(5, min_periods=2).mean()
    df_out['north_cum'] = df_out['north_net'].cumsum()

# 期限利差
if 'bond_10y' in df_out.columns and 'bond_1y' in df_out.columns:
    df_out['bond_spread_10_1'] = df_out['bond_10y'] - df_out['bond_1y']
if 'shibor_3m' in df_out.columns and 'shibor_on' in df_out.columns:
    df_out['shibor_spread_3m_on'] = df_out['shibor_3m'] - df_out['shibor_on']

# 指数
if 'index_close' in df_out.columns:
    df_out['index_ret'] = df_out['index_close'].pct_change()
    df_out['index_ma20'] = df_out['index_close'].rolling(20, min_periods=5).mean()

# 替换NaN为null
df_out = df_out.where(pd.notna(df_out), None)

out_list = df_out.to_dict('records')
for r in out_list:
    for k, v in r.items():
        if isinstance(v, (np.floating, np.integer)):
            r[k] = float(v)

# 统计
n_margin = sum(1 for r in out_list if r.get('margin_balance') is not None)
n_north = sum(1 for r in out_list if r.get('north_net') is not None)
n_shibor = sum(1 for r in out_list if r.get('shibor_on') is not None)
n_bond = sum(1 for r in out_list if r.get('bond_10y') is not None)

output = {
    'meta': {
        'date_range': f"{out_list[0]['date']}~{out_list[-1]['date']}",
        'n_days': len(out_list),
        'fields': {
            'total_amount': '全市场成交额(元)',
            'margin_balance': '融资余额(元)',
            'north_net': '北向净流入(元)',
            'shibor_on': 'SHIBOR隔夜(%)',
            'shibor_3m': 'SHIBOR 3M(%)',
            'bond_10y': '国债10Y(%)',
            'bond_spread_10_1': '国债10Y-1Y利差(%)',
            'index_close': '上证指数',
        },
        'coverage': {
            '成交额': len(out_list),
            '两融': n_margin,
            '北向': n_north,
            'SHIBOR': n_shibor,
            '国债': n_bond,
        }
    },
    'data': out_list
}

with open(OUT, 'w') as f:
    json.dump(output, f, ensure_ascii=False, allow_nan=False)
sz = os.path.getsize(OUT) / 1024
print(f"\n✅ {OUT} ({sz:.0f}KB)")
print(f"   {len(out_list)} 天 ({out_list[0]['date']}~{out_list[-1]['date']})")
print(f"   覆盖: 两融={n_margin}天, 北向={n_north}天, SHIBOR={n_shibor}天, 国债={n_bond}天")
