#!/usr/bin/env python3.12
"""macOS 10.11 (El Capitan) legacy包: Python3.6.8 + Safari 11"""
import zipfile, os, time, gzip as G, json as J

MAC_ZIP = '/mnt/e/stockSurface/replay_mac.zip'
OUT = '/mnt/e/stockSurface/replay_mac_legacy.zip'
page = open('/mnt/e/stockSurface/replay/index_static.html').read()
assert 'enterLine' in page
# CSS兼容化确认
assert 'gap:' not in page, '还有残留gap'

t0 = time.time()
DATA_DIRS = ('ind/', 'stock/')
DATA_FILES = ('cross.json', 'indmap.json', 'tier.json', 'universe.json')
readme = """# 行情 Replay — Mac 老系统版 (macOS 10.11 El Capitan)

针对: 2017前的老Mac, 系统无法升级, 只能装 Python 3.6.8, Safari 11.

## 启动
1. 整个文件夹拷到 Mac 任意位置
2. 双击 启动.command
   - 首次被拦("身份不明的开发者"): 右键点它 → 打开 → 打开 (只此一次)
   - 若提示无执行权限: 终端执行 chmod +x <路径>/启动.command
3. 浏览器自动打开 (Safari 11 / Firefox / Chrome 均可)
4. 用完关闭终端窗口即可

## 前提: 需已装 Python 3.6.8
10.11.6 官方最后支持 python.org 的 3.6.8 安装包.
未装的话: 去 python.org/downloads/release/python-368/ 下载 macosx10.9 pkg 安装.
(装好后终端 python3 -V 应显示 3.6.8)

## 兼容性处理(与标准mac包差异)
- 启动器改用 Python 3.5+ 语法(无 f-string / 无 directory= 参数)
- 页面 CSS 去掉 flex gap (Safari 14.1 才支持) 改用 margin 布局
- gz 解压由启动器发 Content-Encoding 头, 浏览器原生解压 (不依赖 DecompressionStream)

## 说明
- 数据: 前复权(qfq), 快照 2026-10-12, 5,809只+90行业, 页面含划线条件单
- 交易/条件单存浏览器 localStorage; 清网站数据会丢
- 仅监听 127.0.0.1
"""
with zipfile.ZipFile(MAC_ZIP) as mz, zipfile.ZipFile(OUT, 'w', zipfile.ZIP_STORED) as z:
    names = mz.namelist()
    z.writestr('index.html', page)
    z.write('/tmp/serve_mac_legacy.py', 'serve_mac.py')          # 覆盖为legacy版
    z.write('/tmp/启动.command', '启动.command')
    z.writestr('README.md', readme)
    n = 0
    for nm in names:
        if nm.startswith(DATA_DIRS) or nm in DATA_FILES:
            z.writestr(nm, mz.read(nm)); n += 1
    print('数据文件', n, '个')

# 验证
with zipfile.ZipFile(OUT) as z:
    nl = z.namelist()
    assert 'serve_mac.py' in nl and '启动.command' in nl
    srv = z.read('serve_mac.py').decode()
    assert 'f\'' not in srv and 'f"' not in srv, 'serve含f-string!'
    assert 'super().__init__(*a, directory=' not in srv, '含directory kwarg!'
    html = z.read('index.html').decode()
    assert 'enterLine' in html and 'gap:' not in html
    j = J.loads(G.decompress(z.read('stock/600519.SH.json.gz')))
    rows = {str(r[0]): r for r in j['rows']}
    assert abs(rows['20240619'][4] - 1392.266) < 0.01 and len(j['rows']) == 2858
    print('验证OK:', len(nl), '条目, %.0fMB' % (os.path.getsize(OUT)/1e6))
print('DONE %.0fs' % (time.time()-t0))
