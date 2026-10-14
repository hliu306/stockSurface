#!/usr/bin/env python3.12
"""Mac包: 数据取自replay_windows.zip(qfq最新), 页面=当前index_static.html+划线条件单, 启动器=python3"""
import zipfile, os, time, shutil

WIN_ZIP = '/mnt/c/Users/hongb/Desktop/replay_windows.zip'
OUT = '/mnt/e/stockSurface/replay_mac.zip'
TMP = '/tmp/mac_pack'
t0 = time.time()

# 静态页: 用当前最新(含划线条件单) — 从线上index.html重新生成静态版(同前逻辑: 相对路径+DecompressionStream/localStorage)
src = open('/mnt/e/stockSurface/replay/index.html').read()
# (页面此前静态化改造在index_static.html; 当前线上版的服务端fetch绝对路径需要替换 — 直接以现index_static.html为基底? 它没有条件单.
#  正确做法: 把线上版按同一规则转静态)
s = src
old = """  var url = STK ? ('/replay/stock/'+STK+'.json.gz') : ('/replay/ind/'+IND+'.json');
  fetch(url).then(r=>r.json()).then(j=>{"""
new = """  var url = STK ? ('stock/'+STK+'.json.gz') : ('ind/'+IND+'.json');
  var pj = STK ? fetch(url).then(r=>r.arrayBuffer()).then(function(ab){
        if(ab.byteLength<2 || new Uint8Array(ab)[0]!==0x1f) return JSON.parse(new TextDecoder().decode(ab));
        return new Response(new Blob([ab]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
      }) : fetch(url).then(r=>r.json());
  pj.then(j=>{"""
assert old in s, 'load块'
s = s.replace(old, new)
for a, b in [("/replay/cross.json", "cross.json"), ("/replay/indmap.json", "indmap.json"),
             ("/replay/tier.json", "tier.json"), ("/replay/universe.json", "universe.json"),
             ("'/replay/ind/'+IND+'.json'", "'ind/'+IND+'.json'"),
             ("'/replay/ind/881169.json'", "'ind/881169.json'")]:
    assert a in s, a; s = s.replace(a, b)
old = """function save(){
  fetch('/replay/trade?scene='+SCENE,{method:'POST',body:JSON.stringify({scene:SCENE,cash:CASH,holds:HOLDS,trades:TRADES,orders:ORDERS})});
}
function loadSave(){
  fetch('/replay/trade?scene='+SCENE).then(r=>r.json()).then(j=>{
    CASH=j.cash!=null?j.cash:1000000; HOLDS=j.holds||{}; TRADES=j.trades||[]; ORDERS=j.orders||[];
    renderStats(); drawAll();
  });
}"""
new = """function save(){
  try{ localStorage.setItem('replay_save_'+SCENE, JSON.stringify({scene:SCENE,cash:CASH,holds:HOLDS,trades:TRADES,orders:ORDERS})); }catch(e){}
}
function loadSave(){
  var j={};
  try{ j=JSON.parse(localStorage.getItem('replay_save_'+SCENE)||'{}'); }catch(e){}
  CASH=j.cash!=null?j.cash:1000000; HOLDS=j.holds||{}; TRADES=j.trades||[]; ORDERS=j.orders||[];
  renderOrders(); renderStats(); drawAll();
}"""
assert old in s, 'save块'; s = s.replace(old, new)
s = s.replace('<title>行业轮动 Replay</title>', '<title>行业轮动 Replay (离线版)</title>')

# 写最新静态版(含条件单) — 同步到E盘replay/index_static.html
open('/mnt/e/stockSurface/replay/index_static.html', 'w').write(s)
print('index_static.html 已更新(含划线条件单)', len(s))

# 组包
with zipfile.ZipFile(WIN_ZIP) as wz, zipfile.ZipFile(OUT, 'w', zipfile.ZIP_STORED) as z:
    names = wz.namelist()
    z.writestr('index.html', s)
    z.write('/tmp/启动.command', '启动.command')
    z.write('/tmp/serve_mac.py', 'serve_mac.py')
    z.write('/tmp/README_Mac.md', 'README.md')
    n = 0
    for nm in names:
        if nm.startswith(('ind/', 'stock/')) or nm in ('cross.json','indmap.json','tier.json','universe.json'):
            z.writestr(nm, wz.read(nm))
            n += 1
    print(f'数据文件 {n}个 {os.path.getsize(OUT)/1e6:.0f}MB {time.time()-t0:.0f}s')

# 验证
with zipfile.ZipFile(OUT) as z:
    nl = z.namelist()
    assert 'index.html' in nl and '启动.command' in nl and 'serve_mac.py' in nl
    assert 'stock/600519.SH.json.gz' in nl and 'ind/881101.json' in nl
    html = z.read('index.html').decode()
    assert 'enterLine' in html and 'ORDERS' in html, '条件单不在包里!'
    import gzip as G, json as J
    j = J.loads(G.decompress(z.read('stock/600519.SH.json.gz')))
    rows = {str(r[0]): r for r in j['rows']}
    assert abs(rows['20240619'][4] - 1392.266) < 0.01, 'qfq数值!'
    assert len(j['rows']) == 2858
    print('验证OK: 条件单页面+qfq茅台2858根+启动器齐备, 条目', len(nl))
print('DONE', OUT)
