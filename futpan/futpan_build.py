#!/usr/bin/python3.12
# futpan_build.py — 期货全局分析页数据管线 v2 (akshare新浪源,免token)
# L1 产业链拓扑热图 + L2 期限结构墙 + L3 状态流形(动量x展期收益)
# 输出: futpan.json — 页面唯一数据源
import json, time, urllib.request
import pandas as pd

BASE = '/mnt/e/stockSurface/futpan'
import akshare as ak

# ═══ 产业链拓扑: (sina_main_code, 展示名, stage 0=原料/1=中游/2=下游) ═══
CHAINS = {
    '黑色建材': [
        ('I',  '铁矿',   0), ('JM', '焦煤',   0), ('J',  '焦炭',   1),
        ('RB', '螺纹',   2), ('HC', '热卷',   2), ('SS', '不锈钢', 2),
        ('SF', '硅铁',   1), ('SM', '锰硅',   1), ('FG', '玻璃',   2),
        ('SA', '纯碱',   1), ('UR', '尿素',   2), ('LC', '碳酸锂', 0),
    ],
    '能源化工': [
        ('SC', '原油',   0), ('PG', 'LPG',    1), ('TA', 'PTA',    1),
        ('EG', '乙二醇', 1), ('PF', '短纤',   2), ('MA', '甲醇',   1),
        ('PP', 'PP',     2), ('L',  '塑料',   2), ('V',  'PVC',    2),
        ('EB', '苯乙烯', 1), ('RU', '橡胶',   0), ('NR', '20号胶', 0),
        ('SP', '纸浆',   2), ('FU', '燃料油', 1), ('BU', '沥青',   2),
        ('LU', '低硫油', 1), ('PX', '对二甲苯',1), ('SH', '烧碱',  1),
    ],
    '油脂油料': [
        ('A',  '豆一',   0), ('M',  '豆粕',   1), ('Y',  '豆油',   2),
        ('OI', '菜油',   2), ('RM', '菜粕',   1), ('RS', '菜籽',   0),
        ('P',  '棕榈油', 0),
    ],
    '谷物农副': [
        ('C',  '玉米',   0), ('CS', '淀粉',   2), ('CF', '棉花',   0),
        ('CY', '棉纱',   2), ('JD', '鸡蛋',   2), ('AP', '苹果',   0),
        ('CJ', '红枣',   0), ('PK', '花生',   0), ('SR', '白糖',   0),
    ],
    '有色金属': [
        ('CU', '铜',     0), ('AL', '铝',     0), ('AO', '氧化铝', 0),
        ('ZN', '锌',     0), ('PB', '铅',     0), ('NI', '镍',     0),
        ('SN', '锡',     0), ('SI', '工业硅', 0),
    ],
    '贵金属': [
        ('AU', '黄金',   0), ('AG', '白银',   0),
    ],
    '金融航运': [
        ('EC', '集运欧线',0), ('IF', '沪深300',2), ('IH', '上证50', 2),
        ('IC', '中证500',2), ('IM', '中证1000',2), ('T',  '十年国债',2),
        ('TF', '五年国债',2), ('TS', '两年国债',2), ('TL', '三十年国债',2),
    ],
}


def qt_batch(codes):
    """新浪期货实时批量: code -> [name, latest(f8), oi(f13), prev_settle(f10)]"""
    url = 'https://hq.sinajs.cn/list=' + ','.join('nf_' + c for c in codes)
    req = urllib.request.Request(url, headers={'Referer': 'https://finance.sina.com.cn'})
    raw = urllib.request.urlopen(req, timeout=15).read().decode('gbk', 'ignore')
    out = {}
    for line in raw.strip().split('\n'):
        parts = line.split('=', 1)
        k = parts[0].replace('var hq_str_nf_', '')
        f = parts[1].split('"')[1].split(',')
        if len(f) < 14:
            continue
        try:
            out[k] = dict(name=f[0], last=float(f[8]), oi=float(f[13]),
                          prev_settle=float(f[10] or 0), date=f[17])
        except ValueError:
            continue
    return out


def month_span(mcode):
    """'2701' -> 月数(用于曲线x轴)"""
    return (int(mcode[:2]) * 12 + int(mcode[2:]))


def main():
    probe = json.load(open(f'{BASE}/term_probe.json'))
    TODAY = pd.Timestamp.now().strftime('%Y%m%d')

    nodes, curves, daily_ok, daily_fail = [], [], [], []
    px_cache = {}
    for chain, members in CHAINS.items():
        for var, nm, stage in members:
            # ---- 主力日线 (akshare 新浪, 500天) ----
            df = None
            try:
                df = ak.futures_main_sina(symbol=var + '0', start_date='20241001', end_date=TODAY)
            except Exception:
                pass
            if df is None or len(df) == 0:
                daily_fail.append(var)
                continue
            df = df.sort_values('日期')
            closes = df['收盘价'].astype(float).values
            ois = df['持仓量'].astype(float).values
            vols = df['成交量'].astype(float).values
            dates = df['日期'].astype(str).tolist()
            px_cache[var] = df
            last, prev = closes[-1], closes[-2] if len(closes) > 1 else closes[-1]
            m5 = closes[-1] / closes[-6] - 1 if len(closes) > 5 else 0.0
            m20 = closes[-1] / closes[-21] - 1 if len(closes) > 20 else 0.0
            m60 = closes[-1] / closes[-61] - 1 if len(closes) > 60 else 0.0
            chg_oi5 = ois[-1] / ois[-6] - 1 if len(ois) > 5 and ois[-6] > 0 else 0.0
            chg_oi20 = ois[-1] / ois[-21] - 1 if len(ois) > 20 and ois[-21] > 0 else 0.0
            vol20 = vols[-20:].mean() if len(vols) >= 20 else (sum(vols) / len(vols) if vols else 0)
            daily_ok.append(var)

            # ---- 期限结构 (probe已含活跃合约: [code,last,oi,prev_settle]) ----
            term = []
            for c, px, oi, ps in probe.get(var, []):
                mc = c[len(var):]
                term.append(dict(m=mc, span=month_span(mc), px=px, oi=oi))
            term.sort(key=lambda t: t['span'])
            # 展期收益: 到期升序前三个有流动性(oi>1万手)合约中, 主力与下一活跃月
            roll = None
            liq = [t for t in term if t['oi'] > 10000]
            if len(liq) >= 2:
                # 主力=持仓最大; 若主力是近交割月, 展期对象=它之后最近的活跃月
                c1 = max(liq, key=lambda t: t['oi'])
                nxt = [t for t in liq if t['span'] > c1['span']]
                c2 = min(nxt, key=lambda t: t['span']) if nxt else max(
                    [t for t in liq if t['span'] < c1['span']], key=lambda t: t['span'])
                dspan = abs(c2['span'] - c1['span'])
                if dspan >= 1 and c1['px'] > 0:
                    # 展期收益(近月买→次月卖): (c1-c2)/c1 正=backward(现货强)
                    roll = (c1['px'] / c2['px'] - 1) * 12.0 / dspan
            nodes.append(dict(var=var, name=nm, chain=chain, stage=stage,
                              px=round(float(last), 1), chg1=round(last / prev - 1, 5),
                              m5=round(float(m5), 5), m20=round(float(m20), 5),
                              m60=round(float(m60), 5),
                              oi=int(ois[-1]), oi5=round(float(chg_oi5), 4),
                              oi20=round(float(chg_oi20), 4),
                              vol20=int(vol20), roll=roll,
                              curve=term, n_days=len(dates), last_date=dates[-1]))
            time.sleep(0.35)

    # ---- L3 状态流形: 20日动量 x 展期收益, 5日位移 ----
    flow = []
    for n in nodes:
        df = px_cache[n['var']]
        closes = df['收盘价'].astype(float).values
        m20_now = closes[-1] / closes[-21] - 1
        m20_5ago = closes[-6] / closes[-26] - 1
        flow.append(dict(var=n['var'], name=n['name'], chain=n['chain'],
                         x=round(float(m20_now), 4),
                         x0=round(float(m20_5ago), 4),
                         y=n['roll'] if n['roll'] is not None else 0.0))

    # ---- 日历对齐历史序列(下钻面板用): calendar + 每品种 c/o/v 三序列 ----
    all_dates = sorted({d for df in px_cache.values()
                        for d in df['日期'].astype(str).tolist()})
    for n in nodes:
        df = px_cache[n['var']]
        d2i = {d: i for i, d in enumerate(all_dates)}
        c = [None] * len(all_dates)
        o = [None] * len(all_dates)
        v = [None] * len(all_dates)
        for _, row in df.iterrows():
            i = d2i[str(row['日期'])]
            c[i] = round(float(row['收盘价']), 2)
            o[i] = int(float(row['持仓量']))
            v[i] = int(float(row['成交量']))
        n['hist'] = dict(c=c, o=o, v=v)

    # ---- 全市场截面统计(配色标尺用) ----
    chgs = [n['chg1'] for n in nodes]
    chains_list = []
    for chain, members in CHAINS.items():
        mm = [n for n in nodes if n['chain'] == chain]
        chains_list.append([chain, mm])
    out = dict(
        updated=TODAY,
        updated_at=pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        calendar=all_dates,
        chains=CHAINS_OUT, chains_list=chains_list, nodes=nodes, flow=flow,
        stats=dict(n=len(nodes), fail=daily_fail),
    )
    json.dump(out, open(f'{BASE}/futpan.json', 'w'), ensure_ascii=False)
    print('OK nodes:', len(nodes), 'fail:', daily_fail)


CHAINS_OUT = {k: [m[1] for m in v] for k, v in CHAINS.items()}

if __name__ == '__main__':
    main()
