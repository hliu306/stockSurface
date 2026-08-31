#!/usr/bin/env python3.12
# Extract lightweight sector-score file for stockheat.html tier panels.
# Input : /mnt/e/stockSurface/market_score_ths_full.json  (~55MB, git-ignored)
# Output: /mnt/e/stockSurface/stock_heat_tier.json        (compact, two panels share it)
# Schema: {
#   meta: {...},
#   dates: [...sorted...],
#   series: { "881xxx": [ {"d":idx,"s":score,"r":rank}, ... ], ... }   # 90 industries
# }
# Only date/score/rank are kept: the two new panels only need tier color + rank.

import json, os

SRC = '/mnt/e/stockSurface/market_score_ths_full.json'
DST = '/mnt/e/stockSurface/stock_heat_tier.json'

with open(SRC) as f:
    full = json.load(f)

sr = full['sector_rankings']

# group by industry code -> per-date score/rank
dates_all = sorted({e['date'] for e in sr})
dpos = {d: i for i, d in enumerate(dates_all)}

series = {}
names = {}
for e in sr:
    code = str(e['ths_code'])
    names[code] = e['industry']
    lst = series.setdefault(code, [])
    lst.append({'d': dpos[e['date']], 's': round(e['score'], 4), 'r': e['rank']})

# keep arrays sorted by date index
for code in series:
    series[code].sort(key=lambda x: x['d'])

out = {
    'meta': {
        'source': 'market_score_ths_full.json',
        'generated': __import__('time').strftime('%Y-%m-%d %H:%M'),
        'note': 's=SectorScore(THS), r=rank among 90 industries, d=index into dates[]',
        'components': full.get('meta', {}).get('components', {}),
    },
    'dates': dates_all,
    'names': names,
    'series': series,
}

tmp = DST + '.tmp'
with open(tmp, 'w') as f:
    json.dump(out, f, separators=(',', ':'), ensure_ascii=False)
os.replace(tmp, DST)
sz = os.path.getsize(DST)
print('OK', DST, sz, 'bytes,', len(series), 'industries,', len(dates_all), 'dates',
      dates_all[0], '~', dates_all[-1])
# verify roundtrip
with open(DST) as f:
    chk = json.load(f)
assert len(chk['series']) == len(series)
n_pts = sum(len(v) for v in chk['series'].values())
print('points:', n_pts, 'sample 881121 last:', chk['series']['881121'][-1])
