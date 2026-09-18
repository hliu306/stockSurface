# stockSurface — A股 + 期货市场可视化套件

纯手写（零框架依赖）的市场可视化页面 + 全自动数据管道。股票侧覆盖 2015 年至今全历史；期货侧 65 品种 / 7 产业链。每个交易日收盘后增量更新。

![no-deps](https://img.shields.io/badge/前端-零依赖手写Canvas%2FSVG-blue) ![data](https://img.shields.io/badge/数据-tushare%20%2B%20akshare%20%2B%20新浪期货-green) ![update](https://img.shields.io/badge/更新-每交易日自动增量-orange)

## 页面一览

### 股票侧（tushare + 同花顺）

| 页面 | 内容 | 数据源 |
|---|---|---|
| [stockheat](stockheat.html) 个股热力 | 全市场 5533 只个股按行业聚类的热力图 + 行业/板块评分分层（用户主力页） | cache_td_v2 + THS |
| [marketscore_ths](marketscore_ths.html) 市场评分 | 市场评分 + 板块评分 + 周期阶段（同花顺口径） | market_score_ths_full.json |
| [index](index.html) 3D波浪 | 三维空间里全市场个股的"时间的河流"（three.js） | data.json |
| [streamgraph](streamgraph.html) 资金流向 | 行业资金流向堆叠流图 | data.json |
| [sankey](sankey.html) 桑基迁移 | 资金在行业板块间的迁移桑基图 | data.json |
| [dashboard](dashboard.html) 仪表盘 | 市场全景仪表盘（均值/中位数/波动/涨跌家数/成交额） | data.json |
| [calendar](calendar.html) 日历热力 | 日收益率日历热力图 | data.json |
| [state](state.html) 温度计 | 市场温度计（多指标复合状态） | data.json |
| [phase](phase.html) 相空间 | 市场相空间轨迹 | data.json |
| [marketstates](marketstates.html) 市场状态 | 基于 Münnix et al. (2012) 的市场状态聚类 | market_states.json |
| [marketscore](marketscore.html) 市场评分 | 市场评分 + 板块评分 + 周期阶段（tushare 口径） | market_score.json |
| [liquidity](liquidity.html) 流动性 | 场内外流动性（两融/北向/SHIBOR/国债/M2/社融） | liquidity.json |

### 期货侧（新浪财经，免 token）

| 页面 | 内容 | 数据源 |
|---|---|---|
| [futpan](futpan.html) 期货全局 | **L1** 产业链拓扑热图（节点=品种，块高=持仓，可切 1/5/20/60 日）｜**L2** 期限结构墙（全合约曲线+年化展期收益）｜**L3** 品种状态流形（20日动量 × 展期收益，正方形坐标框满铺+5日位移箭头）｜全品种下钻放大面板（两年 K 线可缩放/期限放大/十指标卡） | futpan/futpan.json |

所有页面均为原生 HTML + Canvas/SVG（仅 index.html 使用本地 three.js），**无 CDN、无构建步骤**，克隆即可用。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备 tushare token (需 pro.daily 权限, 积分>=120)
export TUSHARE_TOKEN=你的token

# 3. 一键自举 (首次约 2-4 小时, 拉取 2015 至今全历史, 全程幂等可断点续跑)
python bootstrap.py

# 4. 启动本地服务
python serve_nocache.py
# 浏览器打开 http://localhost:8765/index.html
```

期货页无需 tushare 权限：`python futpan/futpan_build.py` 直接可用（新浪源免 token，首次运行约 3 分钟探测全合约）。

## 每日更新

```bash
python update_all.py          # 股票侧: 增量拉取最新交易日 → 重建 JSON
python ths_daily_update.py    # 同花顺侧: 缓存增量 → 热力/评分/分层重生成
python futpan/futpan_build.py # 期货侧: 65 品种全合约重拉 → futpan.json
```

建议挂 cron（收盘后运行）：

```cron
40 16 * * 1-5  cd /path/to/stockSurface && python futpan/futpan_build.py >> futpan/log 2>&1
```

## 数据管道

```
tushare pro.daily ──┐
                    ├─→ cache_td_v2.parquet ─┬→ data.json          (市场/行业/十分位)
akshare 宏观/资金 ──┤                        ├→ market_score.json  (评分/周期)
                    │                        └→ market_states.json (Münnix 状态聚类)
                    └──→ cache_liquidity/ ──→ liquidity.json       (场内外流动性)

同花顺接口 ──→ cache_ths增量 ──→ stock_heat*.json / market_score_ths_full.json / stock_heat_tier.json

新浪 hq.sinajs.cn ──→ nf_ 合约实时 ──→ futpan.json  (期货产业链/期限结构/状态流形/477日历史)
```

| 脚本 | 作用 |
|---|---|
| `bootstrap.py` | 新机器一键自举（股票行业映射→交易日历→全历史→全部 JSON） |
| `update_all.py` | 每日增量更新（检测缺失交易日 → 增量拉取 → 重建 JSON） |
| `rebuild_td_v2.py` | 全历史日线重建（按交易日拉取，幂等） |
| `compute_stock_heat.py` | 个股热力图 JSON 生成（90 行业分文件） |
| `ths_daily_update.py` | 同花顺链日更（热力/评分/分层/索引） |
| `union_fetch.py` | 同花顺 100 只上限突破（field/order 并集拉取） |
| `compute_liquidity.py` / `_v2.py` | 场内外流动性（v1 基础版 / v2 扩展 M2、社融、中美利差） |
| `compute_market_score.py` | 市场评分、板块评分、周期阶段 |
| `compute_market_states.py` | Münnix 相关矩阵市场状态聚类 |
| `futpan/futpan_build.py` | 期货全局页数据管线（65 品种全合约，akshare+新浪源） |
| `futpan/futpan_daily.sh` | 期货页日更包装（成功静默/失败报警） |
| `serve_nocache.py` | 本地静态服务（no-cache headers，仅绑定 127.0.0.1） |

## 说明

- 日线单位约定：tushare `amount` 为千元，管道内统一 ×1000 转元。
- 期货展期收益口径：到期升序、主力→下一活跃月（持仓>1万手流动性过滤），防止近交割流动性陷阱产生假展期收益。
- 期货链上下游位置为手工标注的静态分层（原料→成品），非数据学习所得。
- 所有数据缓存在本地 parquet，删除缓存后重跑 `bootstrap.py` 即可重建。
- 仅供研究学习，不构成投资建议。

## License

MIT
