#!/usr/bin/env python3.12
"""sector_close.json 构建器: 90个THS行业 date+close 轻量json (sector_strength.html 数据源)
幂等: 全量重算覆写. 产出后自检(行业数/尾日=ths_kline最新)."""
import json, glob, os, sys

DIR = '/mnt/e/stockSurface/ths_kline'
OUT = '/mnt/e/stockSurface/sector_close.json'
idx = json.load(open('/mnt/e/stockSurface/stock_heat.json'))
names = {str(c['ths_code']): c['industry'] for c in idx['industries']}
out = {'names': names, 'series': {}}
dates_all = []
latest = ''
for fp in sorted(glob.glob(f'{DIR}/8*.json')):
    code = os.path.basename(fp)[:-5]
    if code == 'all':
        continue
    j = json.load(open(fp))
    rows = j['rows']
    if not rows:
        continue
    dates_all = [r[0] for r in rows] if len(rows) > len(dates_all) else dates_all
    out['series'][code] = [[r[0], round(r[4], 2)] for r in rows]
    latest = max(latest, rows[-1][0])
out['dates'] = dates_all
tmp = OUT + '.tmp'
json.dump(out, open(tmp, 'w'), separators=(',', ':'))
os.replace(tmp, OUT)
n = len(out['series'])
sz = os.path.getsize(OUT) // 1024
# 自检
chk = json.load(open(OUT))
assert len(chk['series']) == n and chk['dates'][-1] == latest, 'self-check failed'
if n < 90:
    print(f'WARN 行业数={n} <90')
print(f'OK 行业{n} dates{len(dates_all)} 尾{latest} {sz}KB')
