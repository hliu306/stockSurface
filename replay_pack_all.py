#!/usr/bin/env python3.12
"""统一重打 Windows/iPad 包: 数据取自已验证的 mac 包(qfq+最新页面含条件单), 启动器用用户修复版(git replay_win/)"""
import zipfile, os, time

MAC_ZIP = '/mnt/e/stockSurface/replay_mac.zip'
WIN_OUT = '/mnt/e/stockSurface/replay_windows.zip'   # 覆盖旧版(桌面版同步换新)
PAD_OUT = '/mnt/e/stockSurface/replay_ipad.zip'
GIT = os.path.expanduser('~/projects/stockSurface')
t0 = time.time()

page = open('/mnt/e/stockSurface/replay/index_static.html').read()
assert 'enterLine' in page and 'ORDERS' in page, '页面缺条件单'

DATA_DIRS = ('ind/', 'stock/')
DATA_FILES = ('cross.json', 'indmap.json', 'tier.json', 'universe.json')

with zipfile.ZipFile(MAC_ZIP) as mz:
    names = mz.namelist()
    data_names = [n for n in names if n.startswith(DATA_DIRS) or n in DATA_FILES]
    assert 'stock/600519.SH.json.gz' in data_names and 'ind/881101.json' in data_names

    # ---- Windows: 用户修复版启动器 + 最新页面 + 数据 ----
    with zipfile.ZipFile(WIN_OUT, 'w', zipfile.ZIP_STORED) as z:
        z.writestr('index.html', page)
        z.write(GIT + '/replay_win/启动.bat', '启动.bat')
        z.write(GIT + '/replay_win/serve.ps1', 'serve.ps1')
        z.write(GIT + '/replay_win/README.md', 'README_Windows.md')
        for n in data_names:
            z.writestr(n, mz.read(n))
    print('WIN %.0fMB' % (os.path.getsize(WIN_OUT)/1e6))

    # ---- iPad: 纯静态(无启动器) + 数据 ----
    readme_pad = """# 行情 Replay — iPad 离线包

数据: 前复权(qfq), 快照 2026-10-12, 5,809只个股+90行业. 页面含划线条件单.
要求: iPadOS 16.4+ (Safari 需支持 DecompressionStream).

## 部署(任选一种本地服务器App)
A. Koder / Web Files(Normal) 等"本地网站"App:
   1. 把本zip的全部内容解压到App的站点目录(如 Koder 的 Sites/replay/)
   2. 启动App的本地服务(默认端口见App, Koder=8080)
   3. Safari 打开 http://127.0.0.1:8080/
B. Shortcuts+iCloud 不可行(需http服务), 推荐A.

## 说明
- 交易/条件单存 Safari localStorage(同一iPad同一Safari保留; 清网站数据会丢)
- 无触屏专属优化: 缩放/拖拽需外接键盘鼠标; 点按/播放/按钮可用
- 想要新数据: 回主机器重新打包
"""
    with zipfile.ZipFile(PAD_OUT, 'w', zipfile.ZIP_STORED) as z:
        z.writestr('index.html', page)
        z.writestr('README_iPad.md', readme_pad)
        for n in data_names:
            z.writestr(n, mz.read(n))
    print('PAD %.0fMB' % (os.path.getsize(PAD_OUT)/1e6))

# 验证两个新包
import gzip as G, json as J
for path, extra in [(WIN_OUT, ['启动.bat','serve.ps1','README_Windows.md']),
                    (PAD_OUT, ['README_iPad.md'])]:
    with zipfile.ZipFile(path) as z:
        nl = z.namelist()
        for e in ['index.html'] + extra:
            assert e in nl, (path, e)
        html = z.read('index.html').decode()
        assert 'enterLine' in html, path+' 页面缺条件单'
        j = J.loads(G.decompress(z.read('stock/600519.SH.json.gz')))
        rows = {str(r[0]): r for r in j['rows']}
        assert abs(rows['20240619'][4] - 1392.266) < 0.01 and len(j['rows']) == 2858, path+' qfq!'
        print(path.split('/')[-1], '验证OK', len(nl), '条目')
print('DONE %.0fs' % (time.time()-t0))
