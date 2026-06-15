# -*- coding: utf-8 -*-
"""
===========================================
研析 每日定时分析任务
===========================================
被 cron 调度调用，生成每日决策仪表盘

调用方式:
    cd /f/stock && .venv/Scripts/python cron_daily_report.py

环境变量:
    CRON_STOCKS: 分析股票列表（逗号分隔，默认从 .env 读取 STOCK_LIST）
"""

import os
import sys
import json
from datetime import datetime, timedelta, timezone

# 加入项目路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Tokyo timezone
JST = timezone(timedelta(hours=9))

from stock_engine import get_daily_report


def load_stock_list():
    """从 .env 或环境变量加载股票列表"""
    # 优先从环境变量读取
    env_stocks = os.environ.get("CRON_STOCKS")
    if env_stocks:
        return [s.strip() for s in env_stocks.split(",") if s.strip()]

    # 从 .env 文件读取
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("STOCK_LIST="):
                    stocks = line.split("=", 1)[1].strip()
                    return [s.strip() for s in stocks.split(",") if s.strip()]

    # 默认
    return ["FUTU", "QQQ", "SPY"]


def main():
    stocks = load_stock_list()
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

    print(f"📊 研析 每日定时分析")
    print(f"时间: {now_jst} JST")
    print(f"标的: {', '.join(stocks)}")
    print()

    report = get_daily_report(stocks)
    print(report)

    # 保存到日志
    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"daily_{datetime.now(JST).strftime('%Y%m%d')}.md")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已保存: {log_file}")


if __name__ == "__main__":
    main()
