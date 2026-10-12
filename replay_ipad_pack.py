#!/usr/bin/env python3.12
"""iPad离线包组装: index_static.html→index.html + 数据文件, 打zip
产物: /mnt/e/stockSurface/replay_ipad.zip (约250MB)
内含: index.html, cross/indmap/tier/universe.json, ind/(90), stock/(5809 gz), saves空目录
"""
import zipfile, os, time
RP = '/mnt/e/stockSurface/replay'
OUT = '/mnt/e/stockSurface/replay_ipad.zip'
t0 = time.time()
src_html = open(f'{RP}/index_static.html').read()
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_STORED) as z:   # gz/json已压缩, STORED最快
    z.writestr('index.html', src_html)
    for f in ['cross.json', 'indmap.json', 'tier.json', 'universe.json']:
        z.write(f'{RP}/{f}', f)
    n = 0
    for d in ['ind', 'stock']:
        for fn in sorted(os.listdir(f'{RP}/{d}')):
            z.write(f'{RP}/{d}/{fn}', f'{d}/{fn}')
            n += 1
print(f'zip完成 {n}个数据文件 {os.path.getsize(OUT)/1e6:.0f}MB {time.time()-t0:.0f}s', flush=True)

# 验证: 解压抽查看+列目录
with zipfile.ZipFile(OUT) as z:
    names = z.namelist()
    print('条目数', len(names))
    assert 'index.html' in names
    assert f'ind/881101.json' in names and f'stock/600519.SH.json.gz' in names
    print('600519 gz大小', z.getinfo('stock/600519.SH.json.gz').file_size)
print('验证OK', OUT)
