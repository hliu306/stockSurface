#!/usr/bin/env python3
"""
bootstrap.py — stockSurface 一键自举（新机器从零到有全流程）

前置条件:
  1) pip install -r requirements.txt
  2) 设置 tushare token (三选一):
       export TUSHARE_TOKEN=xxx
       或写入 ~/.tushare_token
       或项目目录下 .tushare_token
  3) tushare 积分 >= 120 (需 pro.daily 权限)

流程 (全部幂等, 可断点续跑):
  Step 1  股票-行业映射      (tushare stock_basic + stock_company, ~1 min)
  Step 2  交易日历          (tushare trade_cal, ~10 s)
  Step 3  全历史日线缓存     (tushare pro.daily 按交易日, 2015-今, ~2-4 h 首次)
  Step 4  data.json         (市场/行业/成交额十分位日度统计)
  Step 5  liquidity.json    (compute_liquidity.py: 两融/北向/SHIBOR/国债, akshare)
  Step 6  liquidity v2 扩展  (M2/M1/社融/中美国债曲线, akshare)
  Step 7  market_score.json (市场评分/板块评分/周期阶段)
  Step 8  market_states.json (Münnix 市场状态聚类)
  Step 9  启动说明          (如何 serve / 挂 cron)

用法:
  python bootstrap.py            # 全流程
  python bootstrap.py --from 4   # 从 Step 4 开始 (缓存已有)
"""
import os, sys, subprocess, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

def log(msg):
    print(f"[bootstrap {time.strftime('%H:%M:%S')}] {msg}", flush=True)

def run(label, script, required=True):
    log(f"── {label} ...")
    r = subprocess.run([sys.executable, "-u", script], cwd=BASE_DIR)
    if r.returncode != 0:
        msg = f"{label} FAILED (exit={r.returncode}) — 检查上方日志; 幂等可重跑"
        if required:
            print(msg); sys.exit(1)
        print(f"  (非致命) {msg}")
    else:
        log(f"── {label} OK")

def check_token():
    tok = (os.environ.get("TUSHARE_TOKEN")
           or _read(os.path.join(BASE_DIR, ".tushare_token"))
           or _read(os.path.expanduser("~/.tushare_token")))
    if not tok:
        print("缺少 tushare token: export TUSHARE_TOKEN=... (或 ~/.tushare_token)")
        sys.exit(1)
    log(f"tushare token: {tok[:4]}...{tok[-4:]}")
    return tok

def _read(p):
    try:
        return open(p).read().strip()
    except Exception:
        return None

# ── Step 1: 股票-行业映射 ──
def step1():
    import tushare as ts
    import pandas as pd
    out = os.path.join(BASE_DIR, "stock_industry.parquet")
    if os.path.exists(out):
        log("stock_industry.parquet 已存在, 跳过 (删除可强制重建)")
        return
    pro = ts.pro_api()
    basic = pro.stock_basic(exchange="", list_status="L",
                            fields="ts_code,name,list_date,industry")
    basic = basic[basic["industry"].notna()]
    basic.to_parquet(out, index=False)
    log(f"Step1 OK: {len(basic)} stocks -> stock_industry.parquet")

# ── Step 2: 交易日历 ──
def step2():
    import tushare as ts
    import json
    out = os.path.join(BASE_DIR, "trade_days.json")
    if os.path.exists(out):
        log("trade_days.json 已存在, 跳过")
        return
    pro = ts.pro_api()
    cal = pro.trade_cal(exchange="SSE", start_date="20150101",
                        end_date="20301231", is_open="1")
    days = sorted(cal["cal_date"].tolist())
    json.dump(days, open(out, "w"))
    log(f"Step2 OK: {len(days)} trade days -> trade_days.json")

if __name__ == "__main__":
    start = 1
    if "--from" in sys.argv:
        start = int(sys.argv[sys.argv.index("--from") + 1])
    check_token()
    if start <= 1: step1()
    if start <= 2: step2()
    # Step3 同时产出 cache_td_v2.parquet + data.json (脚本尾部直接写 data.json)
    if start <= 3: run("Step3 全历史日线+data.json (首次约 2-4 小时)", "rebuild_td_v2.py")
    if start <= 4: run("Step4 liquidity.json", "compute_liquidity.py", required=False)
    if start <= 5: run("Step5 liquidity v2", "compute_liquidity_v2.py", required=False)
    if start <= 6: run("Step6 market_score.json", "compute_market_score.py", required=False)
    if start <= 7: run("Step7 market_states.json", "compute_market_states.py", required=False)
    print("\n" + "=" * 50)
    print("bootstrap 完成! 接下来:")
    print("  本地看图:  python serve_nocache.py   -> http://localhost:8765/index.html")
    print("  每日更新:  python update_all.py")
    print("  (建议 cron: 收盘后 16:00 运行 update_all.py)")
