# 行业轮动 Replay — Mac 版使用说明

## 启动
1. 整个文件夹拷到 Mac 任意位置（如 `~/replay/`）
2. 双击 **启动.command**
   - 首次若提示"无法打开，因为来自身份不明的开发者"：
     右键点 启动.command → 打开 → 再点"打开"（只需一次）
   - 若提示没有执行权限：打开"终端"，执行 `chmod +x ~/replay/启动.command`（换成你的路径）
3. 浏览器自动打开页面（Safari / Chrome 均可）
4. 用完：关掉终端窗口即可（或 Ctrl+C）

## 兼容性
- 适用 macOS 10.13+（含无法升级的老系统，如 Big Sur）
- 零依赖：只用系统自带的 python3
- K 线数据为前复权（qfq），快照截至 2026-10-12，静态不含日更

## 说明
- 仅监听 127.0.0.1，其他设备无法访问
- 交易记录/条件单保存在浏览器 localStorage（同一浏览器永久保留，清缓存会丢）
- 想要新数据：回主 Windows/WSL 机器重新打包拷过来

## 文件清单
- 启动.command / serve_mac.py   启动器
- index.html                     页面（静态版）
- universe/indmap/cross/tier.json
- ind/                           90 个行业指数K线
- stock/                         5,809 只个股前复权K线(gz)
