#!/usr/bin/env python3.12
# ══ Replay 数据日更 (无人工/无模型交互, 幂等, 成功静默失败报警) ══
# 链路:
#   ① tushare daily 逐交易日补 ohlc_full.parquet (节假日自动跳过)
#   ② cross.json 重建: 90行业×全日期 [日涨跌幅%, 20日动量%] (源=ths_kline/*.json)
#   ③ tier.json 重建: SectorScore 矩阵 (源=stock_heat_tier.json → 轻量mat)
#   ④ 清 replay/stock/*.json.gz 按需缓存 (旧日期缺新股数据)
#   ⑤ 重启 replay-serve (内存持有 ohlc_full)
# 用法: replay_daily_update.py [--check]   --check=只校验不落盘
import json, os, glob, sys, subprocess, requests
import pandas as pd, numpy as np

RP   = '/mnt/e/stockSurface/replay'
OHLC = f'{RP}/ohlc_full.parquet'
CROSS= f'{RP}/cross.json'
TIER = f'{RP}/tier.json'
ADJ  = f'{RP}/adj_events.parquet'
THS  = '/mnt/e/stockSurface/ths_kline'
HEAT = '/mnt/e/stockSurface/stock_heat_tier.json'
LOG_TAG = 'replay_daily'

def log(*a): print(*a, flush=True)

# ── ① 个股OHLC日更 ─────────────────────────────
def update_ohlc():
    tk = open('/home/hongbo/tk.csv').read().split('\n')[1].strip()
    cur = pd.read_parquet(OHLC)
    mx = int(cur.trade_date.max())
    today = int(__import__('time').strftime('%Y%m%d'))
    frames = [cur]; added = 0
    for d in range(mx+1, today+1):
        try:
            r = requests.post('http://api.tushare.pro', json={
                "api_name":"daily","token":tk,"params":{"trade_date":str(d)},
                "fields":"ts_code,trade_date,open,high,low,close,vol,amount,pre_close"}, timeout=60)
            j = r.json(); items = (j.get('data') or {}).get('items')
        except Exception as e:
            log(f'  {d} 拉取异常: {e}'); continue
        if not items: continue          # 休市/未发布 → 跳
        df = pd.DataFrame(items, columns=['ts_code','trade_date','open','high','low','close','vol','amount','pre_close'])
        df['trade_date']=df['trade_date'].astype('int32')
        for c in ['open','high','low','close','vol','amount','pre_close']: df[c]=df[c].astype('float64')
        frames.append(df); added += len(df); log(f'  {d} +{len(df)}行')
    if not added:
        log('  无新交易日'); return False
    new = pd.concat(frames, ignore_index=True)
    assert not new.duplicated(['ts_code','trade_date']).any(), '键重复!'
    new.to_parquet(OHLC+'.tmp', index=False)
    os.replace(OHLC+'.tmp', OHLC)
    chk = pd.read_parquet(OHLC, columns=['trade_date'])
    log(f'  落盘 {len(chk)} 行, max={int(chk.trade_date.max())}'); return True

# ── ①b 除权因子表增量: 新交易日里 pre_close≠前日close(>0.05%)的事件并入 ──
def update_adj_events():
    cur = pd.read_parquet(OHLC)
    new = cur[cur.trade_date > int(pd.read_parquet(ADJ).trade_date.max())] if os.path.exists(ADJ) else cur.iloc[0:0]
    if not len(new): return
    prev = cur[cur.trade_date <= int(new.trade_date.min())-1]  # 粗过滤: 取新数据最小日前全部(内存换简单)
    # 逐日: 当日pre_close vs 该股前一交易日close
    evs = []
    for d in sorted(new.trade_date.unique()):
        day = new[new.trade_date==d][['ts_code','pre_close']]
        pc = prev.sort_values('trade_date').groupby('ts_code').close.last().rename('prev_close')
        m = day.join(pc, on='ts_code')
        m = m[m.pre_close.notna() & m.prev_close.notna() & (m.prev_close>0)]
        m = m[((m.pre_close/m.prev_close-1).abs()>0.0005)]
        for r in m.itertuples():
            evs.append({'ts_code':r.ts_code,'trade_date':int(d),'factor':round(float(r.pre_close)/float(r.prev_close),8)})
        prev = pd.concat([prev, new[new.trade_date==d][['ts_code','trade_date','close']]])
    if not evs: return
    add = pd.DataFrame(evs); add['trade_date']=add['trade_date'].astype('int32')
    old_ev = pd.read_parquet(ADJ)
    out = pd.concat([old_ev, add]).drop_duplicates(['ts_code','trade_date'], keep='last')
    assert not out.duplicated(['ts_code','trade_date']).any()
    out.to_parquet(ADJ+'.tmp', index=False); os.replace(ADJ+'.tmp', ADJ)
    log(f'  adj_events +{len(add)} (总{len(out)})')

# ── ② cross.json 重建 (90×dates×[ret, mom20]) ──
def build_cross():
    files = sorted(glob.glob(f'{THS}/*.json'))
    codes, dates, per = [], [], {}
    for fp in files:
        code = os.path.basename(fp)[:-5]
        j = json.load(open(fp))
        rows = [(str(r[0]), r[4]) for r in j['rows'] if r[4] is not None]
        per[code] = dict(rows); codes.append(code)
    dates = sorted({d for m in per.values() for d in m})
    mat = [[[None]*len(codes) for _ in range(2)] for _ in range(len(dates))]
    for ci, code in enumerate(codes):
        m = per[code]; hist = []   # [(di, close)]
        for di, d in enumerate(dates):
            v = m.get(d)
            if v is None: continue
            if hist:
                prev = hist[-1][1]
                if prev: mat[di][0][ci] = round((v/prev-1)*100, 3)
            hist.append((di, v))
            # 20日动量: 当前收盘 vs 20个有效值前
            if len(hist) >= 21:
                base = hist[len(hist)-21][1]
                if base: mat[di][1][ci] = round((v/base-1)*100, 3)
    out = {'codes': codes, 'dates': dates, 'mat': mat}
    with open(CROSS+'.tmp','w') as f: json.dump(out, f, separators=(',',':'))
    os.replace(CROSS+'.tmp', CROSS)
    log(f'  cross.json: {len(codes)}行业 × {len(dates)}日, 尾={dates[-1]}')
    return True

# ── ③ tier.json 重建 (SectorScore mat) ─────────
def build_tier():
    t = json.load(open(HEAT))
    dates = t['dates']; names = t['names']; sr = t['series']
    codes = sorted(sr.keys())
    dpos = {d:i for i,d in enumerate(dates)}
    mat = [[None]*len(codes) for _ in range(len(dates))]
    for ci, code in enumerate(codes):
        for e in sr[code]:
            mat[e['d']][ci] = e['s']
    out = {'dates': dates, 'codes': codes, 'names': names, 'mat': mat}
    with open(TIER+'.tmp','w') as f: json.dump(out, f, separators=(',',':'))
    os.replace(TIER+'.tmp', TIER)
    log(f'  tier.json: {len(codes)}行业 × {len(dates)}日, 尾={dates[-1]}')
    return True

# ── ④ 清按需gz缓存 ─────────────────────────────
def clear_cache():
    n = 0
    for f in glob.glob(f'{RP}/stock/*.json.gz'): os.remove(f); n += 1
    if n: log(f'  清gz缓存 {n} 个')
    return True

# ── ⑤ 重启服务 ─────────────────────────────────
def restart_server():
    env = dict(os.environ, XDG_RUNTIME_DIR='/run/user/1000')
    r = subprocess.run(['systemctl','--user','restart','replay-serve'], env=env, capture_output=True, text=True, timeout=60)
    if r.returncode: raise RuntimeError(r.stderr)
    # 等就绪(冷启动合并~20s+)
    import time as _t
    for i in range(30):
        _t.sleep(3)
        try:
            rr = requests.get('http://127.0.0.1:8791/replay/universe.json', timeout=5)
            if rr.status_code == 200: log('  replay-serve 就绪'); return True
        except Exception: pass
    raise RuntimeError('服务90s未就绪')

if __name__ == '__main__':
    if '--check' in sys.argv:
        cur = pd.read_parquet(OHLC, columns=['trade_date'])
        j1 = json.load(open(CROSS)); j2 = json.load(open(TIER))
        log('ohlc max:', int(cur.trade_date.max()), '| cross尾:', j1['dates'][-1], '| tier尾:', j2['dates'][-1])
        sys.exit(0)
    changed = update_ohlc()
    if changed: update_adj_events()
    build_cross(); build_tier(); clear_cache()
    restart_server()
    log('DONE')
