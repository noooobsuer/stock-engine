# 研析数据引擎 — 股票智能分析系统

基于 [daily_stock_analysis](https://github.com/noooobsuer/daily_stock_analysis) 的数据层封装的股票分析引擎，专注美股/日股/港股实时行情、技术分析和策略评估。

## 功能特点

| Phase | 能力 | 说明 |
|:---|:---|---:|
| **Phase 1** | 实时行情 + 技术分析 | 多市场行情、K线、均线、RSI、MACD、支撑阻力 |
| **Phase 2** | 深度趋势 + 15种策略 | StockTrendAnalyzer 深度趋势、策略目录、每日决策仪表盘 |
| **Phase 3** | 策略执行引擎 + 多股对比 | 策略自动匹配评分、多股横向对比、买入/止损点位分析 |

## 快速开始

```bash
# 1. 安装依赖
pip install yfinance pandas numpy

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 3. 使用
python stock_engine.py --quote BABA        # 实时行情
python stock_engine.py --tech FUTU         # 技术分析
python stock_engine.py --trend 7203.T      # 深度趋势分析
python stock_engine.py --daily BABA,FUTU   # 每日报告
python stock_engine.py --eval-strategies BABA  # 策略匹配
python stock_engine.py --compare BABA,FUTU,MU  # 多股对比
python stock_engine.py --list-strategies       # 列出15种策略

# 4. 定时推送
python cron_daily_report.py
```

## Python 接口

```python
from stock_engine import (
    get_quote, get_technical_analysis, get_enhanced_report,
    get_trend_analysis, get_trend_report,
    get_strategy_list, format_strategy_list,
    get_strategy_analysis, get_daily_report,
    evaluate_strategy, find_matching_strategies,
    format_strategy_evaluation, compare_stocks,
)

# 实时行情
quote = get_quote("BABA")
# → {"code":"BABA","price":112.82,"change_pct":-0.46,...}

# 深度趋势分析
trend = get_trend_analysis("FUTU")
# → {"trend_status":"空头排列","signal_score":44,"buy_signal":"观望",...}

# 策略自动匹配
matches = find_matching_strategies("BABA", top_n=3)
# → [{"strategy":"bottom_volume","score":42,"applicable":true,...}, ...]

# 每日决策仪表盘
report = get_daily_report(["BABA","FUTU","MU"])
```

## 支持市场

| 市场 | 代码格式 | 示例 |
|:---|:---|---:|
| 美股(NYSE/NASDAQ) | 直接代码 | BABA, AAPL, FUTU |
| 日股(TSE) | 代码+T | 7203.T, 9984.T |
| 港股(HKEX) | 代码.HK | 9988.HK, 0700.HK |
| ETF | 直接代码 | QQQ, SPY, DRAM |

## 15种分析策略

**趋势类**: bull_trend, ma_golden_cross, volume_breakout, shrink_pullback, dragon_head
**形态类**: one_yang_three_yin
**反转类**: bottom_volume
**框架类**: hot_theme, event_driven, box_oscillation, growth_quality, expectation_repricing,
        chan_theory, wave_theory, emotion_cycle

## 交易策略 — Minervini 趋势跟踪

内置完整的 **Mark Minervini SEPA 趋势跟踪策略**，自动扫描美股 Stage 2 上升趋势股。

### 策略原理

```
Minervini 8项条件:
① RS相对强度 > 70
② 股价 > MA50 > MA150 > MA200（均线多头）
③ MA200 持续上升 ≥ 1个月
④ MA50 在 MA150 和 MA200 上方
⑤ 股价距52周低点 ≥ 30%
⑥ 股价在52周高点25%以内
⑦ Stage 2 上升趋势
⑧ VCP 形态（加分项）
```

### 使用方法

```bash
# 全市场扫描（默认 Nasdaq 100）
python minervini_scanner.py

# 扫描 S&P 500
python minervini_scanner.py --universe sp500

# 单股诊断
python minervini_scanner.py --single AAPL --json

# 查看完整交易计划
python trading_plan.py
```

### GitHub Actions 自动扫描

仓库内置了 GitHub Actions 自动扫描工作流。

| 触发方式 | 频率 | 内容 |
|:---|:---:|:---|
| 定时（工作日） | 每天 21:00 JST | 持仓+候选池每日报告 |
| 定时（周日） | 每周 23:00 JST | Minervini 全市场扫描 |
| 手动触发 | 任意 | 支持单股深度分析 |

#### 配置步骤

1. **Fork 本仓库**
2. **创建 Telegram Bot**（如果没有）

   打开 [@BotFather](https://t.me/botfather) → 发送 `/newbot` → 获取 Token

   获取 Chat ID: 发消息给机器人后访问 `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`

3. **Settings → Secrets and variables → Actions → New repository secret**
   
   | Secret 名称 | 说明 | 必填 |
   |:---|:---|---:|
   | `STOCK_LIST` | 跟踪股票代码，如 `QQQ,SPY,CSCO` | 推荐 |
   | `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（从 @BotFather 获取） | ✅ |
   | `TELEGRAM_CHAT_ID` | 接收消息的 Telegram 聊天 ID | ✅ |

4. **Actions 标签 → 启用工作流**
5. **手动测试**: Actions → `研析自动扫描` → `Run workflow`

### 交易纪律

```
✅ 买入条件: Minervini候选 + 缩量回踩MA5/MA10 + MACD多头
❌ 卖出条件: 跌破止损 / MACD死叉 / 跌破MA20
⚠️ 绝对禁止: 追高 / 亏损加仓 / 无止损过夜
```

## 数据源

- **YFinance** — 美股/港股/日股实时行情、K线、基本面
- 可扩展至 Akshare( A股)、Tushare 等数据源

## 免责声明

本项目仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。
