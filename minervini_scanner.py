# -*- coding: utf-8 -*-
"""
===========================================
Minervini 美股趋势扫描器
===========================================
基于 Mark Minervini 的 SEPA 趋势模板
自动扫描美股筛选 Stage 2 上升趋势股

8项严格条件:
1. RS Rating > 70（相对强度）
2. 股价 > MA50 > MA150 > MA200（均线多头排列）
3. MA200 至少向上1个月
4. MA50 在 MA150 和 MA200 上方
5. 股价距52周低点 ≥ 30%
6. 股价在52周高点25%以内
7. Stage 2 上升趋势（Weinstein）
8. VCP 形态（加分项）

使用:
    cd /f/stock && .venv/Scripts/python minervini_scanner.py
    cd /f/stock && .venv/Scripts/python minervini_scanner.py --top 20
    cd /f/stock && .venv/Scripts/python minervini_scanner.py --universe nasdaq100
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import yfinance as yf

# ── 美股市场代码库 ──
UNIVERSES = {
    "sp500":    "SPY",   # S&P 500 → 通过 SPY 成分股
    "nasdaq100": "QQQ",  # Nasdaq 100 → 通过 QQQ 成分股
    "dow30":    "DIA",   # 道琼斯30
}

# ── 技术指标计算 ──

def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI 计算"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _calc_vcp_score(high: pd.Series, low: pd.Series, close: pd.Series, vol: pd.Series) -> float:
    """
    VCP (波动收缩模式) 检测
    检查最近20-30个交易日是否出现连续缩量+振幅收窄
    返回 0-100 的分数
    """
    if len(close) < 30:
        return 0

    recent = 25
    # 振幅收缩
    ranges = (high.tail(recent) - low.tail(recent)) / close.tail(recent) * 100
    range_ratio = ranges.tail(10).mean() / ranges.head(15).mean() if ranges.head(15).mean() > 0 else 1

    # 成交量收缩
    vol_ma5 = vol.tail(recent).rolling(5).mean()
    vol_ratio = vol_ma5.tail(10).mean() / vol_ma5.head(10).mean() if vol_ma5.head(10).mean() > 0 else 1

    # 收缩幅度越大得分越高
    score = 0
    if range_ratio < 0.6:
        score += 40
    elif range_ratio < 0.8:
        score += 20

    if vol_ratio < 0.7:
        score += 40
    elif vol_ratio < 0.9:
        score += 20

    # 收缩后缩量企稳加分
    if range_ratio < 0.7 and vol_ratio < 0.8:
        score += 20

    return min(score, 100)


def scan_stock(symbol: str, spy_data: pd.DataFrame = None) -> Optional[Dict]:
    """
    对单只股票执行 Minervini 8项条件扫描

    返回:
        {
            "symbol": "AAPL",
            "score": 85,            # 综合评分 0-100
            "passed": 6,            # 通过项数
            "total": 7,             # 总项数（不含VCP加分）
            "rs_rating": 85,
            "stage": "Stage 2",
            "price": 180.5,
            "ma_alignment": True,
            "vcp_score": 45,
            "distance_52w_high": -5.2,  # 距52周高%
            "details": { ... }      # 每项检查详情
        }
    """
    try:
        # 获取2年股价数据
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y")
        if hist is None or len(hist) < 252:
            return None

        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        vol = hist['Volume']

        if len(close) < 20:
            return None

        price = float(close.iloc[-1])

        # 计算均线
        ma50 = close.rolling(50).mean()
        ma150 = close.rolling(150).mean()
        ma200 = close.rolling(200).mean()

        # 计算RS相对强度
        rs_rating = 50
        if spy_data is not None and len(spy_data) == len(hist):
            spy_close = spy_data['Close']
            # 相对强度 = 个股收益 - 大盘收益
            stock_ret = close.pct_change()
            spy_ret = spy_close.pct_change()
            relative_strength = (stock_ret - spy_ret).rolling(63).mean().iloc[-1]  # 约3个月
            # 转换为0-99的rating
            rs_rating = min(99, max(1, int((relative_strength + 0.5) * 100)))

        # 检查条件
        checks = {}
        passed = 0
        total = 7  # 前7项

        # 条件1: RS Rating > 70
        c1 = rs_rating >= 70
        checks["rs_rating"] = {"passed": c1, "value": rs_rating, "threshold": "≥ 70"}
        if c1: passed += 1

        # 条件2: 股价 > MA50 > MA150 > MA200（均线多头排列）
        if not pd.isna(ma50.iloc[-1]) and not pd.isna(ma150.iloc[-1]) and not pd.isna(ma200.iloc[-1]):
            c2 = (price > ma50.iloc[-1] > ma150.iloc[-1] > ma200.iloc[-1])
            checks["ma_alignment"] = {
                "passed": c2,
                "value": f"${price:.2f} > MA50=${ma50.iloc[-1]:.2f} > MA150=${ma150.iloc[-1]:.2f} > MA200=${ma200.iloc[-1]:.2f}",
            }
        else:
            c2 = False
            checks["ma_alignment"] = {"passed": False, "value": "数据不足"}
        if c2: passed += 1

        # 条件3: MA200 至少向上1个月（过去20天MA200呈上升趋势）
        if not pd.isna(ma200.iloc[-1]) and not pd.isna(ma200.iloc[-20]):
            c3 = ma200.iloc[-1] > ma200.iloc[-20]
            checks["ma200_trend"] = {
                "passed": c3,
                "value": f"MA200={ma200.iloc[-1]:.2f} (20天前={ma200.iloc[-20]:.2f})",
            }
        else:
            c3 = False
            checks["ma200_trend"] = {"passed": False, "value": "数据不足"}
        if c3: passed += 1

        # 条件4: MA50 > MA150 且 MA50 > MA200
        if not pd.isna(ma50.iloc[-1]) and not pd.isna(ma150.iloc[-1]) and not pd.isna(ma200.iloc[-1]):
            c4 = ma50.iloc[-1] > ma150.iloc[-1] and ma50.iloc[-1] > ma200.iloc[-1]
            checks["ma50_above"] = {
                "passed": c4,
                "value": f"MA50={ma50.iloc[-1]:.2f} > MA150={ma150.iloc[-1]:.2f} > MA200={ma200.iloc[-1]:.2f}",
            }
        else:
            c4 = False
            checks["ma50_above"] = {"passed": False, "value": "数据不足"}
        if c4: passed += 1

        # 条件5: 股价距52周低点 ≥ 30%
        low_52w = low.tail(252).min()
        dist_from_low = (price / low_52w - 1) * 100 if low_52w > 0 else 0
        c5 = dist_from_low >= 30
        checks["dist_from_52w_low"] = {
            "passed": c5,
            "value": f"{dist_from_low:.1f}% (52周低=${low_52w:.2f})",
            "threshold": "≥ 30%",
        }
        if c5: passed += 1

        # 条件6: 股价在52周高点25%以内
        high_52w = high.tail(252).max()
        dist_from_high = (high_52w / price - 1) * 100
        c6 = dist_from_high <= 25
        checks["dist_from_52w_high"] = {
            "passed": c6,
            "value": f"{dist_from_high:.1f}% (52周高=${high_52w:.2f})",
            "threshold": "≤ 25%",
        }
        if c6: passed += 1

        # 条件7: Stage 2 (均线多头 + 价格在50周均线上方)
        ma50w = close.rolling(250).mean()
        if not pd.isna(ma50w.iloc[-1]) and len(close) > 250:
            stage2 = price > ma50w.iloc[-1] and c2  # 价格在年线上 + 均线多头
            checks["stage_2"] = {
                "passed": stage2,
                "value": f"价格=${price:.2f} {'>' if price > ma50w.iloc[-1] else '<'} 年线=${ma50w.iloc[-1]:.2f}",
            }
        else:
            stage2 = c2
            checks["stage_2"] = {"passed": stage2, "value": c2}
        if stage2: passed += 1

        # 条件8 (加分项): VCP 形态
        vcp_score = _calc_vcp_score(high, low, close, vol)
        checks["vcp"] = {
            "passed": vcp_score >= 40,
            "value": f"VCP评分={vcp_score:.0f}/100",
        }

        # 综合评分
        base_score = (passed / total) * 70  # 基础分70
        vcp_bonus = min(vcp_score * 0.3, 30) if c2 else 0  # VCP加分30，但需要均线多头
        total_score = min(100, int(base_score + vcp_bonus))

        return {
            "symbol": symbol,
            "score": total_score,
            "passed": passed,
            "total": total,
            "rs_rating": rs_rating,
            "stage": "Stage 2" if stage2 else "Not Stage 2",
            "price": round(price, 2),
            "ma_alignment": bool(c2),
            "vcp_score": int(vcp_score),
            "distance_52w_high": round(float(dist_from_high), 1),
            "distance_52w_low": round(float(dist_from_low), 1),
            "sector": getattr(ticker, 'info', {}).get('sector', 'N/A') if hasattr(ticker, 'info') else 'N/A',
            "industry": getattr(ticker, 'info', {}).get('industry', 'N/A') if hasattr(ticker, 'info') else 'N/A',
            "details": checks,
        }
    except Exception as e:
        return None


def get_universe_tickers(universe: str = "sp500") -> List[str]:
    """获取股票池代码列表"""
    try:
        etf_map = {"sp500": "SPY", "nasdaq100": "QQQ", "dow30": "DIA"}
        etf = etf_map.get(universe, "SPY")
        etf_ticker = yf.Ticker(etf)
        info = etf_ticker.info
        holdings = info.get('holdings', []) if isinstance(info, dict) else []

        # 如果ETF的holdings不可用，使用各市场的知名股票列表
        fallback = {
            "sp500": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","BRK.B","JPM","V","JNJ",
                      "WMT","PG","MA","UNH","HD","DIS","PYPL","ADBE","NFLX","CRM",
                      "VZ","INTC","KO","PEP","XOM","MRK","BAC","T","PFE","ABT",
                      "CSCO","ORCL","ABBV","ACN","MCD","QCOM","TXN","NEE","HON","BA",
                      "SBUX","IBM","CAT","GE","C","WFC","GS","MMM","AXP","MS",
                      "LMT","RTX","SPGI","BLK","LOW","CVX","AMGN","MDT","TMO","DHR",
                      "LIN","PLD","AMAT","MU","F","GM","AAL","DAL","UAL","LUV"],
            "nasdaq100": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA","ADBE","NFLX","PYPL",
                          "INTC","CSCO","QCOM","TXN","AMAT","MU","ASML","AMD","ISRG","GILD",
                          "REGN","VRTX","MRNA","BIIB","CELG","ILMN","MDLZ","COST","PEP","SBUX",
                          "MAR","BKNG","CMCSA","CHTR","TMUS","ROST","LULU","WBA","JD","BABA",
                          "PDD","MELI","ZM","DOCU","CRWD","PANW","FTNT","OKTA","WDAY","ADSK"],
            "dow30": ["AAPL","MSFT","JPM","V","JNJ","WMT","PG","MA","UNH","HD",
                      "DIS","VZ","INTC","KO","PEP","XOM","MRK","MCD","CSCO","CAT",
                      "IBM","BA","CVX","AXP","MMM","GS","TRV","WBA","DOW","HON"],
        }
        return fallback.get(universe, fallback["sp500"])
    except:
        return []


def format_results(results: List[Dict], top_n: int = 10) -> str:
    """格式化扫描结果"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [f"📊 Minervini 美股趋势扫描", f"生成时间: {now} JST", f""]

    passing = [r for r in results if r and r['passed'] >= 6]
    borderline = [r for r in results if r and 4 <= r['passed'] <= 5]

    lines.append(f"扫描结果: 通过 {len(passing)} 只 | 临界 {len(borderline)} 只 | 共 {len(results)} 只")
    lines.append("")

    if passing:
        passing.sort(key=lambda r: r['score'], reverse=True)
        lines.append("🌟 通过全部条件 (Pass ≥ 6):")
        lines.append("")
        for r in passing[:top_n]:
            lines.append(f"  {r['symbol']:<8} 评分{r['score']:<4} RS={r['rs_rating']:<3} 通过{r['passed']}/{r['total']}")
            lines.append(f"          价格=${r['price']:<8} 距52周高={r['distance_52w_high']:+.1f}%")
            lines.append(f"          Stage: {r['stage']}  |  VCP评分: {r['vcp_score']}")
            if r.get('sector') and r['sector'] != 'N/A':
                lines.append(f"          {r['sector']} / {r.get('industry','')}")
            lines.append("")

    if borderline and len(passing) < top_n:
        borderline.sort(key=lambda r: r['score'], reverse=True)
        remaining = top_n - len(passing)
        lines.append(f"⚡ 接近达标 (Pass 4-5):")
        lines.append("")
        for r in borderline[:min(remaining, 5)]:
            lines.append(f"  {r['symbol']:<8} 评分{r['score']:<4} RS={r['rs_rating']:<3} 通过{r['passed']}/{r['total']}")
            lines.append(f"          价格=${r['price']:<8} | 距52周高={r['distance_52w_high']:+.1f}%")
            lines.append("")

    lines.append("---")
    lines.append("条件: ①RS>70 ②MA多头 ③MA200↑ ④MA50领先 ⑤距低≥30% ⑥距高≤25% ⑦Stage2 ⑧VCP(加分)")
    return "\n".join(lines)


# ══════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minervini 美股趋势扫描器")
    parser.add_argument("--universe", choices=["sp500", "nasdaq100", "dow30"], default="nasdaq100",
                        help="股票池（默认nasdaq100）")
    parser.add_argument("--top", type=int, default=15, help="显示前N只")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--single", type=str, help="扫描单只股票")
    args = parser.parse_args()

    if args.single:
        # 获取SPY作为基准
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="2y")
        result = scan_stock(args.single.upper(), spy_hist)
        if result:
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"无法扫描 {args.single}")
    else:
        print(f"获取 {args.universe} 股票池...")
        symbols = get_universe_tickers(args.universe)
        print(f"共 {len(symbols)} 只股票，开始扫描...")
        print()

        # 预获取SPY基准数据
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="2y")

        results = []
        for i, sym in enumerate(symbols):
            if (i+1) % 10 == 0:
                print(f"  进度: {i+1}/{len(symbols)}...")
            r = scan_stock(sym, spy_hist)
            if r:
                results.append(r)

        results = [r for r in results if r is not None]

        if args.json:
            results.sort(key=lambda r: r['score'], reverse=True)
            print(json.dumps(results[:args.top], ensure_ascii=False, indent=2, default=str))
        else:
            print(format_results(results, top_n=args.top))
