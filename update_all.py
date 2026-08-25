#!/usr/bin/env python3
"""
stockSurface 全量增量更新管道
1. 检查cache_td_v2.parquet最新日期
2. 增量拉取缺失交易日(tushare per-trade-date)
3. 更新 cache → data.json → market_score.json → liquidity.json → market_states.json
4. 自动跳过非交易日和已有数据
"""
from pathlib import Path
import os
BASE_DIR = str(Path(__file__).resolve().parent)

import pandas as pd
import numpy as np
import tushare as ts
import akshare as ak
import json, os, sys, time, re, datetime, warnings
warnings.filterwarnings('ignore')

BASE = BASE_DIR
CACHE = os.path.join(BASE, 'cache_td_v2.parquet')
SI = os.path.join(BASE, 'stock_industry.parquet')
TRADE_DAYS = os.path.join(BASE, 'trade_days.json')
TUSHARE_TOKEN = open(os.path.expanduser('~/.tushare_token')).read().strip() if os.path.exists(os.path.expanduser('~/.tushare_token')) else None

def log(msg):
    ts_str = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{ts_str}] {msg}", flush=True)

def safe_json_dump(data, path):
    """写JSON，确保无NaN/Infinity"""
    raw = json.dumps(data, ensure_ascii=False)
    raw = re.sub(r'\bNaN\b', 'null', raw)
    raw = re.sub(r'\b-Infinity\b', 'null', raw)
    raw = re.sub(r'\bInfinity\b', 'null', raw)
    with open(path, 'w') as f:
        f.write(raw)
    return os.path.getsize(path)

# ════════════════════════════════════
# Step 1: 获取需要更新的交易日列表
# ════════════════════════════════════
def get_missing_dates():
    """返回cache中缺失的交易日列表"""
    df = pd.read_parquet(CACHE, columns=['trade_date'])
    cache_dates = set(df['trade_date'].unique())
    cache_max = max(cache_dates)
    log(f"Cache最新: {cache_max}, 共{len(cache_dates)}交易日")

    # 用tushare直接查最新交易日（比本地trade_days.json可靠）
    pro = ts.pro_api()
    today_str = datetime.date.today().strftime('%Y%m%d')

    # 方法1: 直接尝试拉最近5天，看哪些有数据
    check_dates = []
    test_date = datetime.date.today()
    for _ in range(10):
        d = test_date.strftime('%Y%m%d')
        if d <= today_str:
            check_dates.append(d)
        test_date -= datetime.timedelta(days=1)

    # 验证哪些是有效交易日（有数据返回）
    missing = []
    for d in check_dates:
        if d <= cache_max:
            continue  # 已有
        try:
            df_test = pro.daily(trade_date=d)
            if df_test is not None and len(df_test) > 100:  # 有数据=交易日
                missing.append(d)
                log(f"  发现新交易日: {d} ({len(df_test)} stocks)")
            time.sleep(0.5)
        except:
            time.sleep(1)

    # 去重排序
    missing = sorted(set(missing))
    log(f"需更新交易日: {len(missing)}天" + (f" ({missing[0]}~{missing[-1]})" if missing else ""))
    return missing

# ════════════════════════════════════
# Step 2: 增量拉取日线数据
# ════════════════════════════════════
def fetch_daily_incremental(dates):
    """用tushare per-trade-date拉取缺失的交易日数据"""
    if not dates:
        log("无需更新日线")
        return 0

    pro = ts.pro_api()
    si = pd.read_parquet(SI)
    valid_codes = set(si['ts_code'].values)

    cache = pd.read_parquet(CACHE)
    new_rows = []

    for i, d in enumerate(dates):
        for attempt in range(3):
            try:
                df = pro.daily(trade_date=d)
                if df is not None and len(df) > 0:
                    # 过滤A股
                    df = df[df['ts_code'].isin(valid_codes)]
                    new_rows.append(df)
                    log(f"  [{i+1}/{len(dates)}] {d}: {len(df)} stocks")
                else:
                    log(f"  [{i+1}/{len(dates)}] {d}: 无数据(可能非交易日)")
                break
            except Exception as e:
                if '频率' in str(e) or 'limit' in str(e).lower():
                    log(f"  [{i+1}/{len(dates)}] {d}: 限频，等待60s... (attempt {attempt+1})")
                    time.sleep(60)
                else:
                    log(f"  [{i+1}/{len(dates)}] {d}: ERROR {str(e)[:60]}")
                    time.sleep(5)
        time.sleep(1.3)  # 50次/分钟限制

    if new_rows:
        new_df = pd.concat(new_rows, ignore_index=True)
        combined = pd.concat([cache, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=['ts_code', 'trade_date'])
        combined = combined.sort_values(['ts_code', 'trade_date']).reset_index(drop=True)
        combined.to_parquet(CACHE, index=False)
        log(f"Cache更新: +{len(new_df)} rows → total {len(combined)} rows")
        return len(new_df)
    return 0

# ════════════════════════════════════
# Step 3: 重建 data.json
# ════════════════════════════════════
def rebuild_data_json():
    """从cache重建data.json (日度市场横截面统计)"""
    log("重建 data.json ...")
    df = pd.read_parquet(CACHE)
    si = pd.read_parquet(SI)
    code_ind = dict(zip(si['ts_code'], si['industry']))
    df['industry'] = df['ts_code'].map(code_ind)
    df = df[df['industry'].notna()].copy()
    df['ret'] = df['close'] / df['pre_close'] - 1.0
    df.loc[abs(df['ret']) > 0.2, 'ret'] = np.nan
    df['amount_yuan'] = df['amount'] * 1000.0

    # 日度聚合
    daily = df.groupby('trade_date').agg(
        mean_ret=('ret', 'mean'),
        median_ret=('ret', 'median'),
        cross_vol=('ret', 'std'),
        win_ratio=('ret', lambda x: (x > 0).mean()),
        amount=('amount_yuan', 'sum'),
    ).reset_index().sort_values('trade_date')

    daily['ret_5d'] = daily['mean_ret'].rolling(5, min_periods=2).apply(lambda r: (1+r).prod()-1, raw=True)
    daily['ret_20d'] = daily['mean_ret'].rolling(20, min_periods=10).apply(lambda r: (1+r).prod()-1, raw=True)
    daily['total_amount'] = daily['amount']
    daily['date_str'] = daily['trade_date'].astype(str)
    daily['std_ret'] = daily['cross_vol']
    daily = daily.where(pd.notna(daily), None)
    daily_records = daily[['date_str','mean_ret','median_ret','cross_vol','win_ratio',
                           'amount','ret_5d','ret_20d','total_amount','std_ret']].to_dict('records')

    # 行业聚合
    ind = df.groupby(['trade_date','industry']).agg(
        mean_ret=('ret','mean'), std_ret=('ret','std'),
        amount=('amount_yuan','sum'), n=('ts_code','count'),
        up_ratio=('ret', lambda x: (x>0).mean()),
    ).reset_index()
    # 兼容旧前端: 加 date_str + total_amount
    ind['date_str'] = ind['trade_date'].astype(str)
    ind['total_amount'] = ind['amount']
    ind['industry'] = ind['industry']
    ind_records = ind[['date_str','industry','mean_ret','std_ret','amount','total_amount','n','up_ratio']].to_dict('records')

    # Decile聚合
    df['decile'] = df.groupby('trade_date')['amount_yuan'].transform(
        lambda x: pd.qcut(x.rank(method='first'), 10, labels=range(1,11)))
    dec = df.groupby(['trade_date','decile']).agg(
        mean_ret=('ret','mean'), amount=('amount_yuan','sum'),
    ).reset_index()
    dec_records = dec.to_dict('records')

    for records in [daily_records, ind_records, dec_records]:
        for r in records:
            for k, v in list(r.items()):
                if isinstance(v, (np.floating, np.integer)):
                    r[k] = float(v)
                elif isinstance(v, float) and (np.isnan(v) if isinstance(v, float) else False):
                    r[k] = None

    output = {'daily': daily_records, 'industry': ind_records, 'decile': dec_records}
    sz = safe_json_dump(output, os.path.join(BASE, 'data.json'))
    log(f"  data.json: {len(daily_records)} daily, {len(ind_records)} industry, {sz/1024:.0f}KB")

# ════════════════════════════════════
# Step 4: 重建 market_score.json
# ════════════════════════════════════
def rebuild_market_score():
    """重建market_score.json (简化版，调用现有逻辑)"""
    log("重建 market_score.json ...")
    # 直接调用现有脚本
    import subprocess
    result = subprocess.run([sys.executable, os.path.join(BASE, 'compute_market_score.py')],
                          capture_output=True, text=True, timeout=600, cwd=BASE)
    if result.returncode == 0:
        # 修复NaN
        fix_nan_in_file(os.path.join(BASE, 'market_score.json'))
        log(f"  market_score.json: OK")
    else:
        log(f"  market_score.json: FAILED\n{result.stderr[-200:]}")

# ════════════════════════════════════
# Step 5: 增量更新 liquidity.json
# ════════════════════════════════════
def update_liquidity():
    """增量更新liquidity.json"""
    log("更新 liquidity.json ...")
    import subprocess
    # 运行v2脚本 (会增量拉取akshare数据)
    result = subprocess.run([sys.executable, os.path.join(BASE, 'compute_liquidity_v2.py')],
                          capture_output=True, text=True, timeout=300, cwd=BASE)
    if result.returncode == 0:
        fix_nan_in_file(os.path.join(BASE, 'liquidity.json'))
        log(f"  liquidity.json: OK")
    else:
        log(f"  liquidity.json: FAILED\n{result.stderr[-200:]}")

# ════════════════════════════════════
# Step 6: 重建 market_states.json
# ════════════════════════════════════
def rebuild_market_states():
    """重建market_states.json"""
    log("重建 market_states.json ...")
    import subprocess
    result = subprocess.run([sys.executable, os.path.join(BASE, 'compute_market_states.py')],
                          capture_output=True, text=True, timeout=600, cwd=BASE)
    if result.returncode == 0:
        fix_nan_in_file(os.path.join(BASE, 'market_states.json'))
        log(f"  market_states.json: OK")
    else:
        log(f"  market_states.json: FAILED\n{result.stderr[-200:]}")

def fix_nan_in_file(path):
    """修复JSON文件中的NaN"""
    if not os.path.exists(path):
        return
    with open(path) as f:
        raw = f.read()
    if 'NaN' in raw or 'Infinity' in raw:
        raw = re.sub(r'\bNaN\b', 'null', raw)
        raw = re.sub(r'\b-Infinity\b', 'null', raw)
        raw = re.sub(r'\bInfinity\b', 'null', raw)
        with open(path, 'w') as f:
            f.write(raw)

# ════════════════════════════════════
# 主流程
# ════════════════════════════════════
def main():
    log("=" * 50)
    log("stockSurface 数据增量更新管道启动")
    log("=" * 50)

    # 检查是否交易日
    today = datetime.date.today()
    if today.weekday() >= 5:
        log("今天是周末，跳过更新")
        return

    # 检查时间（只在15:30后运行，确保收盘数据可用）
    now = datetime.datetime.now()
    if now.hour < 15:
        log(f"当前时间{now.strftime('%H:%M')}，未到15:30，盘后数据可能未更新")
        log("继续尝试...")

    try:
        # Step 1: 检查缺失日期
        missing = get_missing_dates()

        if missing:
            # Step 2: 拉取日线增量
            n_new = fetch_daily_incremental(missing)
            if n_new > 0:
                # Step 3-6: 重建所有JSON
                rebuild_data_json()
                rebuild_market_score()
                update_liquidity()
                rebuild_market_states()
                log("=" * 50)
                log(f"✅ 更新完成! 新增{n_new}条日线, {len(missing)}个交易日")
            else:
                log("无新数据写入")
        else:
            log("数据已是最新，无需更新")

        # 即使没有新日线，也更新流动性(akshare数据可能更新)
        log("额外检查流动性数据...")
        update_liquidity()

    except Exception as e:
        import traceback
        log(f"❌ 更新失败: {e}")
        traceback.print_exc()
        sys.exit(1)

    log("=" * 50)
    log("管道执行完毕")

if __name__ == '__main__':
    main()
