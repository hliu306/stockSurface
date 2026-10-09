#!/usr/bin/env python3.12
"""replay服务: 静态页 + 动态API
- GET /replay/            → index.html (replay主页面)
- GET /replay/universe.json
- GET /replay/ind/{code}.json     → 行业OHLC (ths_kline原样)
- GET /replay/stock/{ts}.json.gz  → 个股OHLC (按需生成缓存: date,o,h,l,c,vol,amount)
- 交易记录POST/GET /replay/trade  → 本地JSON持久化(按场景分文件)
仅绑定127.0.0.1:8791"""
import json, gzip, os, io, glob, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import pandas as pd

BASE = '/mnt/e/stockSurface'
RP = f'{BASE}/replay'
os.makedirs(f'{RP}/stock', exist_ok=True)
os.makedirs(f'{RP}/saves', exist_ok=True)

# close/vol/amount源(cache_td_v2) + OHLC源(ohlc_full, 2015-2026零缺口)
# 只取OHLC三列: parquet可能含close/vol/amount(日更产物), 全merge会成close_x/close_y崩itertuples
_tdc = pd.read_parquet(f'{BASE}/cache_td_v2.parquet',
                       columns=['ts_code','trade_date','close','vol','amount'])
_ohl = pd.read_parquet(f'{RP}/ohlc_full.parquet',
                       columns=['ts_code','trade_date','open','high','low'])
TD = _tdc.merge(_ohl, on=['ts_code','trade_date'], how='left')
TD['trade_date'] = TD['trade_date'].astype(str)
CODES = set(TD.ts_code.unique())

IND_NAME = {}
for fp in glob.glob(f'{BASE}/stock_heat/881*.json'):
    h = json.load(open(fp))
    IND_NAME[str(h['ths_code'])] = h['industry']

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype='application/json', extra=None):
        if isinstance(body, str): body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k,v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        try:
            if p in ('/replay', '/replay/'):
                self._send(200, open(f'{RP}/index.html','rb').read(), 'text/html; charset=utf-8')
            elif p == '/replay/universe.json':
                self._send(200, open(f'{RP}/universe.json','rb').read())
            elif p.startswith('/replay/ind/'):
                code = re.sub(r'\D','', p.split('/')[-1].split('.')[0])
                fp = f'{BASE}/ths_kline/{code}.json'
                if not os.path.exists(fp): return self._send(404, '{"e":"no ind"}')
                j = json.load(open(fp))
                j['name'] = IND_NAME.get(code) or j.get('name') or code
                self._send(200, json.dumps(j, separators=(',',':')).encode())
            elif p.startswith('/replay/stock/'):
                ts = p.split('/')[-1].replace('.json.gz','').upper()
                if ts not in CODES: return self._send(404, '{"e":"no stock"}')
                fp = f'{RP}/stock/{ts}.json.gz'
                if not os.path.exists(fp):
                    g = TD[TD.ts_code==ts].sort_values('trade_date')
                    rows = []
                    for r in g.itertuples():
                        if not (r.close==r.close): continue     # close NaN→跳过
                        o_,h_,l_ = r.open, r.high, r.low
                        if not (o_==o_): o_ = h_ = l_ = r.close  # OHLC缺→平盘蜡烛
                        if not (h_==h_): h_ = max(o_, r.close)
                        if not (l_==l_): l_ = min(o_, r.close)
                        rows.append([r.trade_date, round(float(o_),3), round(float(h_),3),
                                     round(float(l_),3), round(float(r.close),3),
                                     float(r.vol) if r.vol==r.vol else 0,
                                     float(r.amount) if r.amount==r.amount else 0])
                    buf = io.BytesIO()
                    with gzip.open(buf,'wt',encoding='utf-8') as f:
                        json.dump({'code':ts,'rows':rows}, f, separators=(',',':'), allow_nan=False)
                    tmp = fp+'.tmp'
                    open(tmp,'wb').write(buf.getvalue())
                    os.replace(tmp, fp)
                self._send(200, open(fp,'rb').read(), 'application/json',
                           extra={'Content-Encoding':'gzip'})
            elif p.startswith('/replay/trade'):
                qs = parse_qs(u.query)
                scene = re.sub(r'[^a-zA-Z0-9_-]','', qs.get('scene',['default'])[0]) or 'default'
                fp = f'{RP}/saves/{scene}.json'
                data = open(fp,'rb').read() if os.path.exists(fp) else b'{"trades":[],"cash":1000000}'
                self._send(200, data)
            elif p.startswith('/replay/') and '/' not in p[len('/replay/'):]:
                fp = f'{RP}/{os.path.basename(p)}'
                if not os.path.exists(fp): return self._send(404, '{"e":"nf"}')
                self._send(200, open(fp,'rb').read(),
                           'application/json' if fp.endswith('.json') else 'text/html; charset=utf-8')
            else:
                self._send(404, '{"e":"nf"}')
        except Exception as e:
            self._send(500, json.dumps({'e':str(e)}).encode())

    def do_POST(self):
        u = urlparse(self.path)
        if u.path.startswith('/replay/trade'):
            n = int(self.headers.get('Content-Length','0'))
            body = json.loads(self.rfile.read(n) or b'{}')
            scene = re.sub(r'[^a-zA-Z0-9_-]','', str(body.get('scene','default')))
            fp = f'{RP}/saves/{scene}.json'
            tmp = fp+'.tmp'
            open(tmp,'w').write(json.dumps(body, ensure_ascii=False, separators=(',',':')))
            os.replace(tmp, fp)
            self._send(200, b'{"ok":1}')
        else:
            self._send(404, b'{"e":"nf"}')

if __name__ == '__main__':
    srv = HTTPServer(('127.0.0.1', 8791), H)
    print('replay server on 127.0.0.1:8791', flush=True)
    srv.serve_forever()
