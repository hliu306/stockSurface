#!/usr/bin/env python3
import pandas as pd, numpy as np, json, os, glob

MD = '/mnt/e/stockSurface/margin_detail'
OUT = '/mnt/e/stockSurface/margin_heat.json'

dates = sorted(os.path.basename(f).split('.')[0] for f in glob.glob(f'{MD}/*.parquet'))
print(f'两融明细: {len(dates)} 天 ({dates[0]}~{dates[-1]})', flush=True)

# 行业映射(每行业文件)
s2ind, ind_name, name_map = {}, {}, {}
for f in glob.glob('/mnt/e/stockSurface/stock_heat/*.json'):
    j = json.load(open(f))
    tc = str(j['ths_code'])
    ind_name[tc] = j['industry']
    for s in j['stocks']:
        s2ind[s['ts_code']] = tc
        name_map[s['ts_code']] = s.get('name', '')
print(f'映射: {len(s2ind)} 股 / {len(ind_name)} 行业', flush=True)

# close(沪市rq换算)
cd = pd.read_parquet('/mnt/e/stockSurface/cache_td_v2.parquet', columns=['ts_code','trade_date','close'])
cd = cd[cd['trade_date'].isin(set(dates))]
close_map = {(r.ts_code, r.trade_date): r.close for r in cd.itertuples(index=False)}
print(f'close: {len(close_map)}', flush=True)

ind_rz = {tc: [] for tc in ind_name}
ind_rq = {tc: [] for tc in ind_name}
stock_rz, stock_rq = {}, {}

for k, d in enumerate(dates):
    df = pd.read_parquet(f'{MD}/{d}.parquet')
    # 沪市: rqye缺→rq_vol×close
    rq = np.where(df['rqye'].fillna(0) > 0, df['rqye'],
                  [ (v * close_map.get((tc, d), 0) if v == v else 0.0)
                    for tc, v in zip(df['ts_code'], df['rq_vol'].fillna(0)) ])
    df['rqye_v'] = rq
    df['ind'] = df['ts_code'].map(s2ind)
    # 行业聚合(向量化)
    g = df.dropna(subset=['ind']).groupby('ind').agg(rz=('rzye','sum'), rq=('rqye_v','sum'))
    for tc in ind_name:
        ind_rz[tc].append(float(g['rz'].get(tc, 0.0)))
        ind_rq[tc].append(float(g['rq'].get(tc, 0.0)))
    # 个股(dict)
    drz = dict(zip(df['ts_code'], df['rzye']))
    drq = dict(zip(df['ts_code'], df['rqye_v']))
    all_codes = set(stock_rz) | set(drz)
    for tc in all_codes:
        a_rz = stock_rz.setdefault(tc, [])
        a_rq = stock_rq.setdefault(tc, [])
        while len(a_rz) < k: a_rz.append(0.0)
        while len(a_rq) < k: a_rq.append(0.0)
        a_rz.append(float(drz.get(tc, 0.0) or 0))
        a_rq.append(float(drq.get(tc, 0.0) or 0))
    for tc in stock_rz:
        if len(stock_rz[tc]) < k+1: stock_rz[tc].append(0.0)
        if len(stock_rq[tc]) < k+1: stock_rq[tc].append(0.0)
    if (k+1) % 25 == 0: print(f'  {k+1}/{len(dates)}', flush=True)

stock_out = {}
for tc in stock_rz:
    stock_out[tc] = {'name': name_map.get(tc,''), 'ind': s2ind.get(tc),
        'rzye': [round(v,0) for v in stock_rz[tc]],
        'rqye': [round(v,0) for v in stock_rq[tc]],
        'ratio': [round(r/z*100,3) if z else 0 for z,r in zip(stock_rz[tc], stock_rq[tc])]}
ind_out = {}
for tc in ind_name:
    ind_out[tc] = {'name': ind_name[tc],
        'rzye': [round(v,0) for v in ind_rz[tc]],
        'rqye': [round(v,0) for v in ind_rq[tc]],
        'ratio': [round(r/z*100,3) if z else 0 for z,r in zip(ind_rz[tc], ind_rq[tc])]}

out = {'dates': dates, 'stock': stock_out, 'ind': ind_out,
       'meta': {'note': 'rzye/rqye=融资/融券余额(元,沪市融券=余量×close); ratio=融券/融资%(截面对比)', 
                'generated': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}}
with open(OUT,'w') as f: json.dump(out, f, ensure_ascii=False, separators=(',',':'))
print(f'✅ {OUT} ({os.path.getsize(OUT)//1024}KB) 股票{len(stock_out)} 行业{len(ind_out)} 天{len(dates)}', flush=True)

# ── 三层输出(页面轻量版/全程版) ──
import os as _os
BASE = '/mnt/e/stockSurface'
# full版: 千元精度全程
full = {'dates': [str(d) for d in dates], 'ind': ind_out, 'stock': {}}
for tc, r in stock_out.items():
    full['stock'][tc] = {'name': r.get('name',''), 'ind': r.get('ind'),
        'rzye': [None if v is None else int(round(v/1000)) for v in r['rzye']],
        'rqye': [None if v is None else int(round(v/1000)) for v in r['rqye']],
        'ratio': r['ratio']}
with open(BASE+'/margin_heat_full.json','w') as f: json.dump(full, f, ensure_ascii=False, separators=(',',':'))
# 页面版: 行业全程(千元) + 个股近250日
KEEP = 250
page = {'dates': [str(d) for d in dates], 'stockDates': [int(d) for d in dates[-KEEP:]], 'ind': full['ind'], 'stock': {}}
for tc, r in full['stock'].items():
    page['stock'][tc] = {'name': r['name'], 'ind': r['ind'],
        'rzye': r['rzye'][-KEEP:], 'rqye': r['rqye'][-KEEP:], 'ratio': r['ratio'][-KEEP:]}
with open(BASE+'/margin_heat.json','w') as f: json.dump(page, f, ensure_ascii=False, separators=(',',':'))
print(f'✅ 三层输出: page {os.path.getsize(BASE+"/margin_heat.json")//1024}KB / full {os.path.getsize(BASE+"/margin_heat_full.json")//1024}KB', flush=True)
