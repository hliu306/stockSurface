#!/usr/bin/env python3
"""
基于 Münnix et al. (2012) "Identifying States of a Financial Market"
计算A股市场的:
  1. 滚动相关矩阵 C(t)
  2. 相似度矩阵 ζ(t1,t2)
  3. 市场状态聚类 (top-down / hierarchical)
  4. 相关分布演化
  5. 月度状态分配 (dense timeline)

输出: market_states.json
"""
from pathlib import Path
import os
BASE_DIR = str(Path(__file__).resolve().parent)

import pandas as pd
import numpy as np
import json, os, sys
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

OUT = os.path.join(BASE_DIR, 'market_states.json')
CACHE = os.path.join(BASE_DIR, 'cache_td_v2.parquet')
SI = os.path.join(BASE_DIR, 'stock_industry.parquet')

print("加载数据...")
df = pd.read_parquet(CACHE)
si = pd.read_parquet(SI)
code_ind = dict(zip(si['ts_code'], si['industry']))
df['industry'] = df['ts_code'].map(code_ind)
df = df[df['industry'].notna()].copy()

# 收益率
df['ret'] = df['close'] / df['pre_close'] - 1.0
df.loc[abs(df['ret']) > 0.2, 'ret'] = np.nan
df.loc[df['ret'].isna(), 'ret'] = 0.0

# 日度行业收益率 (行业内股票均值)
print("构建行业收益率矩阵...")
ind_daily = df.groupby(['trade_date', 'industry'])['ret'].mean().reset_index()
ret_mat = ind_daily.pivot(index='trade_date', columns='industry', values='ret')
ret_mat = ret_mat.sort_index()

# 过滤数据覆盖>80%的行业
valid = ret_mat.columns[ret_mat.notna().sum() > len(ret_mat) * 0.8]
ret_mat = ret_mat[valid].fillna(0)
industries = list(ret_mat.columns)
n_ind = len(industries)
dates = ret_mat.index.tolist()
n_days = len(dates)
print(f"  {n_ind} 个行业, {n_days} 天 ({dates[0]}~{dates[-1]})")

# ── 局部归一化 (n=13, 论文方法) ──
print("局部归一化 (n=13)...")
rmat = ret_mat.values.astype(np.float64)  # (n_days, n_ind)
n_local = 13
rmat_norm = np.zeros_like(rmat)
for t in range(n_days):
    lo = max(0, t - n_local + 1)
    window = rmat[lo:t+1]  # (<=13, n_ind)
    mu = window.mean(axis=0)
    sigma = window.std(axis=0)
    sigma[sigma < 1e-8] = 1.0
    rmat_norm[t] = (rmat[t] - mu) / sigma
rmat_norm = np.nan_to_num(rmat_norm, nan=0.0)

# ── 非重叠 2月窗口 (40交易日) → ζ矩阵 ──
WINDOW = 40
window_starts = list(range(0, n_days - WINDOW + 1, WINDOW))
n_w = len(window_starts)
print(f"非重叠窗口: {n_w} 个 (window={WINDOW}天)")

corr_matrices = []
window_end_dates = []
for ws in window_starts:
    we = ws + WINDOW
    block = rmat_norm[ws:we]  # (40, n_ind)
    c = np.corrcoef(block.T)  # (n_ind, n_ind)
    c = np.nan_to_num(c, nan=0.0)
    corr_matrices.append(c)
    window_end_dates.append(dates[we - 1])

corr_matrices = np.array(corr_matrices)  # (n_w, n_ind, n_ind)

# ── ζ相似度矩阵 ──
print(f"计算 ζ 矩阵 ({n_w}×{n_w})...")
zeta = np.zeros((n_w, n_w))
for i in range(n_w):
    for j in range(i + 1, n_w):
        z = np.mean(np.abs(corr_matrices[i] - corr_matrices[j]))
        zeta[i, j] = z
        zeta[j, i] = z
    if (i + 1) % 10 == 0:
        print(f"  ζ进度: {i+1}/{n_w}")

np.fill_diagonal(zeta, 0.0)

# ── 聚类: 层次聚类 ──
print("层次聚类...")
condensed = squareform(zeta)
Z = linkage(condensed, method='average')
N_STATES_TARGET = 8
labels = fcluster(Z, t=N_STATES_TARGET, criterion='maxclust')
# 重编号: 按首次出现顺序
uniq_order = sorted(set(labels), key=lambda x: np.where(labels == x)[0][0])
remap = {old: new for new, old in enumerate(uniq_order, 1)}
labels = np.array([remap[l] for l in labels])
n_states = len(set(labels))
print(f"  识别出 {n_states} 个市场状态")

# ── 每个状态的平均相关矩阵 ──
state_info = {}
for s in range(1, n_states + 1):
    mask = labels == s
    avg_corr = corr_matrices[mask].mean(axis=0)
    # 行业排序: 按行业名
    periods = [window_end_dates[i] for i in range(n_w) if labels[i] == s]
    state_info[str(s)] = {
        'avg_corr': avg_corr.tolist(),
        'n_windows': int(mask.sum()),
        'first_date': periods[0] if periods else '',
        'last_date': periods[-1] if periods else '',
        'periods': periods
    }

# ── 相关分布演化 (每月一个直方图) ──
print("相关分布演化...")
corr_hists = []
for i in range(n_w):
    c = corr_matrices[i]
    upper = c[np.triu_indices(n_ind, k=1)]
    counts, bin_edges = np.histogram(upper, bins=40, range=(-1, 1))
    corr_hists.append({
        'date': window_end_dates[i],
        'counts': counts.tolist(),
        'mean': float(upper.mean()),
        'std': float(upper.std())
    })

# ── 密集月度状态分配 (用滑窗→最近状态质心) ──
print("密集状态分配 (月度滑窗)...")
state_centroids = {}
for s in range(1, n_states + 1):
    state_centroids[s] = corr_matrices[labels == s].mean(axis=0)

monthly_timeline = []
STEP = 20  # 月度步长
for ms in range(0, n_days - WINDOW + 1, STEP):
    me = ms + WINDOW
    block = rmat_norm[ms:me]
    c = np.corrcoef(block.T)
    c = np.nan_to_num(c, nan=0.0)
    # 找最近状态
    best_s, best_d = 1, 1e9
    for s in range(1, n_states + 1):
        d = np.mean(np.abs(c - state_centroids[s]))
        if d < best_d:
            best_d = d
            best_s = s
    monthly_timeline.append({
        'date': dates[me - 1],
        'state': best_s,
        'dist': float(best_d)
    })

# ── 行业色阶排序 (聚类行业使块结构更清晰) ──
print("行业重排序...")
# 用全期平均相关矩阵对行业做层次聚类
full_corr = corr_matrices.mean(axis=0)
from scipy.cluster.hierarchy import linkage as hlink, leaves_list
dist_ind = 1 - full_corr
dist_ind = (dist_ind + dist_ind.T) / 2  # 强制对称
np.fill_diagonal(dist_ind, 0.0)
dist_cond = squareform(dist_ind)
Z_ind = hlink(dist_cond, method='average')
ind_order = leaves_list(Z_ind).tolist()
ind_order_names = [industries[i] for i in ind_order]

# ── 保存 ──
print("保存JSON...")
output = {
    'meta': {
        'method': 'Münnix et al. 2012',
        'data_range': f"{dates[0]}~{dates[-1]}",
        'n_industries': n_ind,
        'n_windows': n_w,
        'window_size': WINDOW,
        'n_states': n_states,
        'local_norm_n': n_local
    },
    'window_dates': window_end_dates,
    'zeta_matrix': zeta.tolist(),
    'state_labels': labels.tolist(),
    'industries': industries,
    'ind_order': ind_order,  # 聚类排序索引
    'states': state_info,
    'corr_hists': corr_hists,
    'monthly_timeline': monthly_timeline,
    'full_avg_corr': full_corr.tolist()
}

with open(OUT, 'w') as f:
    json.dump(output, f, ensure_ascii=False, allow_nan=False)
sz = os.path.getsize(OUT) / 1024
print(f"\n✅ {OUT} ({sz:.0f}KB)")
print(f"   {n_w} 窗口 × {n_ind} 行业 → {n_states} 状态")
print(f"   月度时间线: {len(monthly_timeline)} 点")
for s in range(1, n_states + 1):
    w = state_info[str(s)]
    print(f"   State {s}: {w['n_windows']}窗口, {w['first_date']}~{w['last_date']}")
