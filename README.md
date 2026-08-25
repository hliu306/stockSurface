# stockSurface — A股市场可视化套件

10 个纯手写（零框架依赖）的市场可视化页面 + 一条全自动数据管道。覆盖 2015 年至今全历史，每个交易日收盘后增量更新。

![no-deps](https://img.shields.io/badge/前端-零依赖手写Canvas%2FSVG-blue) ![data](https://img.shields.io/badge/数据-tushare%20%2B%20akshare-green) ![update](https://img.shields.io/badge/更新-每交易日自动增量-orange)

## 页面一览

| 页面 | 内容 | 数据源 |
|---|---|---|
| [index](index.html) 3D波浪 | 三维空间里全市场个股的"时间的河流"（three.js） | data.json |
| [streamgraph](streamgraph.html) 资金流向 | 行业资金流向堆叠流图 | data.json |
| [sankey](sankey.html) 桑基迁移 | 资金在行业板块间的迁移桑基图 | data.json |
| [dashboard](dashboard.html) 仪表盘 | 市场全景仪表盘（均值/中位数/波动/涨跌家数/成交额） | data.json |
| [calendar](calendar.html) 日历热力 | 日收益率日历热力图 | data.json |
| [state](state.html) 温度计 | 市场温度计（多指标复合状态） | data.json |
| [phase](phase.html) 相空间 | 市场相空间轨迹 | data.json |
| [marketstates](marketstates.html) 市场状态 | 基于 Münnix et al. (2012) 的市场状态聚类 | market_states.json |
| [marketscore](marketscore.html) 市场评分 | 市场评分 + 板块评分 + 周期阶段 | market_score.json |
| [liquidity](liquidity.html) 流动性 | 场内外流动性（两融/北向/SHIBOR/国债/M2/社融） | liquidity.json |

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

## 每日更新

```bash
python update_all.py    # 增量拉取最新交易日 → 重建 4 个 JSON
```

建议挂 cron（收盘后运行，如 16:10）：

```cron
10 16 * * 1-5  cd /path/to/stockSurface && python update_all.py >> update.log 2>&1
```

## 数据管道

```
tushare pro.daily ──┐
                    ├─→ cache_td_v2.parquet ─┬→ data.json          (市场/行业/十分位)
akshare 宏观/资金 ──┤                        ├→ market_score.json  (评分/周期)
                    │                        └→ market_states.json (Münnix 状态聚类)
                    └──→ cache_liquidity/ ──→ liquidity.json       (场内外流动性)
```

| 脚本 | 作用 |
|---|---|
| `bootstrap.py` | 新机器一键自举（股票行业映射→交易日历→全历史→全部 JSON） |
| `update_all.py` | 每日增量更新（检测缺失交易日 → 增量拉取 → 重建 JSON） |
| `rebuild_td_v2.py` | 全历史日线重建（按交易日拉取，幂等） |
| `compute_liquidity.py` / `_v2.py` | 场内外流动性（v1 基础版 / v2 扩展 M2、社融、中美利差） |
| `compute_market_score.py` | 市场评分、板块评分、周期阶段 |
| `compute_market_states.py` | Münnix 相关矩阵市场状态聚类 |
| `serve_nocache.py` | 本地静态服务（no-cache headers） |

## 说明

- 日线单位约定：tushare `amount` 为千元，管道内统一 ×1000 转元。
- 所有数据缓存在本地 parquet，删除缓存后重跑 `bootstrap.py` 即可重建。
- 仅供研究学习，不构成投资建议。

## License

MIT
