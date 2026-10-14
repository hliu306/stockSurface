# 行情 Replay — Mac 老系统版 (macOS 10.11 El Capitan)

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
