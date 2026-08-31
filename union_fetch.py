#!/usr/bin/env python3.12
# Break the 100-cap: multi-field/order union fetch for 15 capped industries.
# Server renders /thshy/detail/code/{code}/field/{f}/order/{asc|desc}/page/{n}/
# Adaptive: keep adding field-pairs until union >= n_true or fields exhausted.
import requests, re, time, json, os
import pandas as pd

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

univ = pd.read_parquet('/mnt/e/stockSurface/ths_universe.parquet')
tc = pd.read_csv('/mnt/e/stockSurface/ths_industry_true_counts.csv')
cap = tc[tc.capped == 1]
os.makedirs('/tmp/union_parts', exist_ok=True)

FIELDS = ['10', '1968584', '19', '3475914', '526792', '1771976', '407', '199112']

def fetch_page(code, field, order, page):
    u = f'http://q.10jqka.com.cn/thshy/detail/code/{code}/field/{field}/order/{order}/page/{page}/'
    for attempt in range(4):
        try:
            r = s.get(u, timeout=25)
            if r.status_code == 401:
                print(f'  401 rate-limit, cooling 90s (attempt {attempt+1})', flush=True)
                time.sleep(90)
                continue
            pairs = re.findall(r'stockpage\.10jqka\.com\.cn/(\d{6})[/"][^>]{0,40}?>([^<]{2,14})</a>', r.text)
            return [(c, n.strip()) for c, n in pairs if n.strip() and not n.strip().isdigit()]
        except Exception as e:
            print('  ERR', repr(e)[:60], flush=True)
            time.sleep(3)
    return None  # hard fail

for _, row in cap.iterrows():
    ths_code, name, n_true = str(row.ths_code), row.industry, int(row.n_true)
    ck = f'/tmp/union_parts/{ths_code}.json'
    if os.path.exists(ck):
        print(f'{name} {ths_code}: checkpoint exists, skip', flush=True)
        continue
    have = set(univ[univ.ths_code == ths_code].code)
    union = dict()  # code -> name
    for c in have:
        nm = univ[(univ.ths_code == ths_code) & (univ.code == c)].stock_name
        union[c] = nm.iloc[0] if len(nm) else ''
    fi = 0
    while len(union) < n_true and fi < len(FIELDS):
        f = FIELDS[fi]; fi += 1
        for order in ['asc', 'desc']:
            for page in range(1, 8):
                pairs = fetch_page(ths_code, f, order, page)
                if pairs is None:
                    print(f'  {name}: HARD FAIL at {f}/{order}/p{page}', flush=True)
                    break
                if not pairs:
                    break
                for c, n in pairs:
                    union[c] = n
                time.sleep(0.8)
            if len(union) >= n_true:
                break
        print(f'  {name}: after field {f} -> union {len(union)}/{n_true}', flush=True)
    json.dump({'industry': name, 'ths_code': ths_code, 'n_true': n_true,
               'stocks': [{'code': c, 'name': n} for c, n in sorted(union.items())]},
              open(ck, 'w'), ensure_ascii=False)
    print(f'{name} {ths_code}: FINAL union {len(union)}/{n_true}', flush=True)

print('ALL DONE')
