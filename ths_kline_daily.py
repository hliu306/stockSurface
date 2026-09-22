#!/usr/bin/env python3.12
"""ths_kline 日更: 90个THS行业指数K线 增量拉当日新行 (源: 同花顺 d.10jqka.com.cn)
幂等: 每个code只拉当年文件, 追加json里没有的尾部日期; 失败alert落盘(经margin_pipeline日志)
"""
import json, re, time, os, glob, urllib.request, datetime

DIR = '/mnt/e/stockSurface/ths_kline'
os.makedirs(DIR, exist_ok=True)
today = datetime.date.today()
year = today.strftime('%Y')

fails = []
for fp in sorted(glob.glob(f'{DIR}/8*.json')):
    if os.path.basename(fp) == 'all.json':
        continue
    code = os.path.basename(fp)[:-5]
    try:
        j = json.load(open(fp))
        rows = j.get('rows', [])
        have = {str(r[0]) for r in rows}
        url = f'https://d.10jqka.com.cn/v4/line/bk_{code}/01/{year}.js'
        req = urllib.request.Request(url, headers={'Referer': 'https://q.10jqka.com.cn/', 'User-Agent': 'Mozilla/5.0'})
        t = urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'ignore')
        m = re.search(r'\({"data":"(.*?)"\}\)', t, re.S)
        if not m:
            continue
        added = 0
        for rec in m.group(1).split(';'):
            p = rec.split(',')
            if len(p) >= 7 and p[0] not in have:
                rows.append([p[0], float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[6])])
                added += 1
        if added:
            rows.sort(key=lambda r: r[0])
            json.dump({'code': code, 'name': j.get('name'), 'rows': rows}, open(fp, 'w'))
        print(f'{code}: +{added} → 尾{rows[-1][0] if rows else "-"}', flush=True)
    except Exception as e:
        fails.append((code, str(e)[:50]))
    time.sleep(0.15)

print(f'DONE fails={len(fails)}', fails[:5] if fails else '', flush=True)
