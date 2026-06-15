# -*- coding: utf-8 -*-
"""
===========================================
研析 数据引擎 - A/H/美股智能分析核心
===========================================
Phase 2: 集成 StockTrendAnalyzer + 15种策略分析 + 每日报告

使用方式:
    import sys; sys.path.insert(0, 'F:/stock')
    from stock_engine import (
        get_quote, get_kline, get_technical_analysis, get_enhanced_report,
        get_trend_analysis, get_strategy_list, get_strategy_analysis,
        get_daily_report,
    )

依赖: uv pip install -r requirements.txt (已安装)
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ──────────────────────────────────────────────
# 全局懒加载
# ──────────────────────────────────────────────
_manager = None
_analyzer = None
_skill_catalog = None

def _get_manager():
    global _manager
    if _manager is not None:
        return _manager
    try:
        from data_provider.base import DataFetcherManager
        from data_provider.yfinance_fetcher import YfinanceFetcher
        _manager = DataFetcherManager([YfinanceFetcher()])
    except ImportError:
        _manager = _YfinanceFallback()
    return _manager


class _YfinanceFallback:
    import yfinance as _yf

    def get_realtime_quote(self, code):
        try:
            tk = self._yf.Ticker(code)
            info = tk.info if hasattr(tk, 'info') else {}
            hist = tk.history(period='5d')
            if hist is None or len(hist) == 0:
                return None
            price = float(info.get('currentPrice') or info.get('regularMarketPrice') or hist['Close'].iloc[-1])
            class _Q: pass
            q = _Q()
            q.code = code
            q.name = info.get('shortName') or info.get('longName') or code
            q.price = price
            q.change_pct = float(hist['Close'].pct_change().iloc[-1] * 100) if len(hist) > 1 else 0
            q.change_amount = float(hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) if len(hist) > 1 else 0
            q.open_price = float(hist['Open'].iloc[-1]) if 'Open' in hist else price
            q.high = float(hist['High'].iloc[-1]) if 'High' in hist else price
            q.low = float(hist['Low'].iloc[-1]) if 'Low' in hist else price
            q.pre_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else price
            q.volume = int(hist['Volume'].iloc[-1]) if 'Volume' in hist else 0
            q.amplitude = float((q.high - q.low) / q.price * 100)
            q.total_mv = float(info.get('marketCap', 0) or 0)
            return q
        except Exception:
            return None

    def get_daily_data(self, code, days=60):
        try:
            tk = self._yf.Ticker(code)
            df = tk.history(period='6mo')
            if df is None or len(df) == 0:
                return None, 'yfinance'
            df = df.tail(days).copy()
            df.index.name = 'date'
            df = df.reset_index()
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            if 'close' in df.columns:
                df['pct_chg'] = df['close'].pct_change() * 100
            return df, 'yfinance_fallback'
        except Exception:
            return None, 'yfinance_fallback'

def _get_trend_analyzer():
    global _analyzer
    if _analyzer is not None:
        return _analyzer
    from src.stock_analyzer import StockTrendAnalyzer
    _analyzer = StockTrendAnalyzer()
    return _analyzer

def _get_skill_catalog():
    """加载15种策略目录"""
    global _skill_catalog
    if _skill_catalog is not None:
        return _skill_catalog
    try:
        from src.agent.skills.defaults import _load_builtin_skill_catalog
        raw = _load_builtin_skill_catalog()
        catalog = []
        for skill in raw:
            catalog.append({
                "name": getattr(skill, 'name', ''),
                "display_name": getattr(skill, 'display_name', ''),
                "description": getattr(skill, 'description', ''),
                "category": getattr(skill, 'category', ''),
                "aliases": getattr(skill, 'aliases', []),
                "priority": getattr(skill, 'default_priority', 100),
            })
        _skill_catalog = sorted(catalog, key=lambda s: s['priority'])
    except Exception:
        _skill_catalog = []
    return _skill_catalog


# ══════════════════════════════════════════════
# Phase 1 接口（保持兼容）
# ══════════════════════════════════════════════

def get_quote(code: str) -> Optional[Dict[str, Any]]:
    """获取实时行情"""
    try:
        mgr = _get_manager()
        q = mgr.get_realtime_quote(code)
        if q is None:
            return None
        return {
            "code": getattr(q, 'code', code),
            "name": getattr(q, 'name', ''),
            "price": round(float(getattr(q, 'price', 0)), 2),
            "change_pct": round(float(getattr(q, 'change_pct', 0)), 2),
            "change_amount": round(float(getattr(q, 'change_amount', 0)), 2),
            "open": round(float(getattr(q, 'open_price', 0)), 2),
            "high": round(float(getattr(q, 'high', 0)), 2),
            "low": round(float(getattr(q, 'low', 0)), 2),
            "pre_close": round(float(getattr(q, 'pre_close', 0)), 2),
            "volume": int(getattr(q, 'volume', 0)),
            "amplitude": round(float(getattr(q, 'amplitude', 0)), 2),
            "total_mv": float(getattr(q, 'total_mv', 0)),
            "source": "yfinance",
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }
    except Exception as e:
        return {"error": str(e), "code": code}


def get_kline(code: str, days: int = 60) -> Optional[pd.DataFrame]:
    """获取日K线"""
    try:
        mgr = _get_manager()
        result = mgr.get_daily_data(code, days=days)
        if result is None:
            return None
        df = result[0] if isinstance(result, tuple) else result
        if df is None or len(df) == 0:
            return None
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception:
        return None


def get_technical_analysis(code: str, days: int = 60) -> Optional[Dict[str, Any]]:
    """获取技术分析（Phase 1兼容）"""
    try:
        df = get_kline(code, days=days)
        if df is None or len(df) < 5:
            return None
        close = df['close'].astype(float)
        mas, above_count = {}, 0
        for n in [5, 10, 20, 60]:
            if len(df) >= n:
                v = round(float(close.rolling(n).mean().iloc[-1]), 2)
                mas[f'ma{n}'] = v
                if close.iloc[-1] > v:
                    above_count += 1
        if above_count == 0:
            ma_sig, trend, strength = "全部空头排列", "下跌趋势", "弱势"
        elif above_count >= 3:
            ma_sig, trend, strength = "多头排列", "上涨趋势", "强势"
        elif above_count == 1:
            ma_sig, trend, strength = "仅MA5上方", "偏弱震荡", "偏弱"
        else:
            ma_sig, trend, strength = "均线纠缠", "震荡整理", "中性"
        ret = close.pct_change()
        vol = df['volume'].astype(float)
        lr = df.iloc[-1]
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = round(float((100 - 100 / (1 + rs)).iloc[-1]), 1) if not pd.isna((100 - 100 / (1 + rs)).iloc[-1]) else None
        ema12, ema26 = close.ewm(span=12).mean(), close.ewm(span=26).mean()
        macd_line = (ema12 - ema26).iloc[-1]
        macd_sig = (ema12 - ema26).ewm(span=9).mean().iloc[-1]
        return {
            "code": code, "date": str(lr['date']), "price": round(float(close.iloc[-1]), 2),
            "open": round(float(lr['open']), 2), "high": round(float(lr['high']), 2),
            "low": round(float(lr['low']), 2), "volume": int(float(lr['volume'])),
            "ma": mas, "ma_signal": ma_sig, "trend": trend, "strength": strength,
            "returns": {
                "daily": round(float(ret.iloc[-1] * 100), 2),
                "5d": round(float(ret.tail(5).sum() * 100), 2),
                "20d": round(float(ret.tail(min(20, len(ret))).sum() * 100), 2),
                "60d": round(float(ret.tail(min(60, len(ret))).sum() * 100), 2),
            },
            "volatility": {
                "amplitude_pct": round(float((lr['high']-lr['low'])/lr['close']*100), 2),
                "vol_ratio": round(float(lr['volume']/vol.tail(5).mean()), 2),
            },
            "support_resistance": {
                "support_60d": round(float(close.tail(60).min()), 2),
                "resistance_60d": round(float(close.tail(60).max()), 2),
                "position_pct": round(float((close.iloc[-1]-close.tail(60).min())/(close.tail(60).max()-close.tail(60).min())*100), 1),
            },
            "rsi_14": rsi,
            "macd": {
                "macd": round(float(macd_line), 2), "signal": round(float(macd_sig), 2),
                "histogram": round(float(macd_line - macd_sig), 2),
                "signal_type": "多头" if macd_line > macd_sig else "空头",
            },
        }
    except Exception as e:
        return {"error": str(e), "code": code}


def get_enhanced_report(code: str) -> str:
    """文本报告"""
    tech = get_technical_analysis(code)
    if tech is None or "error" in tech:
        return f"[{code}] 无法获取技术分析数据"
    q = get_quote(code)
    lines = [f"【{code}】技术分析报告"]
    lines.append(f"最新价: ${tech['price']} | {tech['date']}")
    if q:
        lines.append(f"日内: O={q['open']} H={q['high']} L={q['low']} C={q['price']}")
        lines.append(f"涨跌: {q['change_pct']:+.2f}%")
    lines.append(f"")
    lines.append(f"【均线】{tech['ma_signal']}")
    for k, v in tech['ma'].items():
        pos = "上" if tech['price'] > v else "下"
        lines.append(f"  {k.upper()}=${v} (股价在{pos})")
    lines.append(f"")
    lines.append(f"【趋势】{tech['trend']} | {tech['strength']}")
    lines.append(f"  RSI(14): {tech.get('rsi_14', 'N/A')}")
    lines.append(f"  MACD: {tech['macd']['signal_type']} (MACD={tech['macd']['macd']}, Signal={tech['macd']['signal']})")
    lines.append(f"")
    lines.append(f"【涨跌幅】")
    r = tech['returns']
    lines.append(f"  当日: {r['daily']:+.2f}% | 5日: {r['5d']:+.2f}% | 20日: {r['20d']:+.2f}% | 60日: {r['60d']:+.2f}%")
    lines.append(f"  量比: {tech['volatility']['vol_ratio']}x | 振幅: {tech['volatility']['amplitude_pct']}%")
    sr = tech['support_resistance']
    lines.append(f"  60日区间: ${sr['support_60d']} ~ ${sr['resistance_60d']} (当前位置{sr['position_pct']}%分位)")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# Phase 2 新增: 趋势分析引擎集成
# ══════════════════════════════════════════════

def get_trend_analysis(code: str, days: int = 120) -> Optional[Dict[str, Any]]:
    """
    基于 StockTrendAnalyzer 的深度趋势分析

    返回更丰富的趋势状态、MACD/RSI专业判断、买卖信号

    参数:
        code: 股票代码
        days: 分析天数（建议120天，至少20天）

    返回:
        包含 trend_status, buy_signal, signal_score, signal_reasons, risk_factors 等
    """
    try:
        df = get_kline(code, days=days)
        if df is None or len(df) < 20:
            return None

        analyzer = _get_trend_analyzer()
        result = analyzer.analyze(df, code)
        return result.to_dict()
    except Exception as e:
        return {"error": str(e), "code": code}


def get_trend_report(code: str) -> str:
    """趋势分析的文本报告"""
    tr = get_trend_analysis(code)
    if tr is None or "error" in tr:
        return f"[{code}] 无法完成趋势分析"

    lines = [f"【{code}】趋势交易分析"]
    lines.append(f"价格: ${tr['current_price']} | 趋势: {tr['trend_status']}")
    lines.append(f"排列: {tr['ma_alignment']}")
    lines.append(f"")
    lines.append(f"【均线】")
    lines.append(f"  MA5={tr.get('ma5',0):.2f} 乖离={tr.get('bias_ma5',0):+.2f}%")
    lines.append(f"  MA10={tr.get('ma10',0):.2f} 乖离={tr.get('bias_ma10',0):+.2f}%")
    lines.append(f"  MA20={tr.get('ma20',0):.2f} 乖离={tr.get('bias_ma20',0):+.2f}%")
    lines.append(f"  MA60={tr.get('ma60',0):.2f}")
    lines.append(f"")
    lines.append(f"【量能】{tr.get('volume_status','')}")
    lines.append(f"  量比(5日): {tr.get('volume_ratio_5d',0):.2f}x")
    lines.append(f"  {tr.get('volume_trend','')}")
    lines.append(f"")
    lines.append(f"【MACD】{tr.get('macd_status','')}")
    lines.append(f"  DIF={tr.get('macd_dif',0):.2f} DEA={tr.get('macd_dea',0):.2f}")
    lines.append(f"  BAR={tr.get('macd_bar',0):.2f} | {tr.get('macd_signal','')}")
    lines.append(f"")
    lines.append(f"【RSI】{tr.get('rsi_status','')}")
    lines.append(f"  RSI6={tr.get('rsi_6',0):.1f} RSI12={tr.get('rsi_12',0):.1f} RSI24={tr.get('rsi_24',0):.1f}")
    lines.append(f"  {tr.get('rsi_signal','')}")
    lines.append(f"")
    lines.append(f"【信号】{tr.get('buy_signal','')} | 评分: {tr.get('signal_score',0)}/100")
    for reason in tr.get('signal_reasons', []):
        lines.append(f"  + {reason}")
    lines.append(f"")
    if tr.get('risk_factors'):
        lines.append(f"【风险点】")
        for risk in tr['risk_factors']:
            lines.append(f"  ! {risk}")
    lines.append(f"")
    lines.append(f"【支撑确认】MA5支撑={tr.get('support_ma5','')} MA10支撑={tr.get('support_ma10','')}")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# Phase 2 新增: 策略分析
# ══════════════════════════════════════════════

def get_strategy_list() -> List[Dict[str, Any]]:
    """
    获取所有可用策略列表

    返回:
        [{ "name": "ma_golden_cross", "display_name": "均线金叉", "description": "...", "category": "trend", ... }]
    """
    return _get_skill_catalog()


def format_strategy_list() -> str:
    """格式化的策略列表"""
    catalog = _get_skill_catalog()
    lines = ["【研析 15种分析策略】", ""]
    categories = {}
    for s in catalog:
        cat = s.get('category', '其他')
        categories.setdefault(cat, []).append(s)

    cat_names = {'trend': '趋势类', 'pattern': '形态类', 'reversal': '反转类', 'framework': '框架类'}
    for cat_key in ['trend', 'pattern', 'reversal', 'framework']:
        skills = categories.get(cat_key, [])
        if not skills:
            continue
        lines.append(f"── {cat_names.get(cat_key, cat_key)} ──")
        for s in skills:
            lines.append(f"  {s['display_name']}({s['name']}): {s.get('description', '')[:60]}")
        lines.append("")

    return "\n".join(lines)


def get_strategy_analysis(code: str, strategy_name: str) -> Dict[str, Any]:
    """
    使用指定策略分析股票

    参数:
        code: 股票代码
        strategy_name: 策略名称，如 "ma_golden_cross", "shrink_pullback", "dragon_head" 等

    返回:
        策略分析 + 趋势数据 + 针对该策略的判断
    """
    tech = get_technical_analysis(code)
    trend = get_trend_analysis(code)
    quote = get_quote(code)

    # 验证策略是否存在
    catalog = _get_skill_catalog()
    matched = [s for s in catalog if s['name'] == strategy_name]
    strategy_info = matched[0] if matched else None

    return {
        "code": code,
        "strategy": strategy_name,
        "strategy_display": strategy_info['display_name'] if strategy_info else strategy_name,
        "strategy_description": strategy_info.get('description', '') if strategy_info else '',
        "price": tech['price'] if tech else None,
        "trend": trend,
        "technical": tech,
        "quote": quote,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ══════════════════════════════════════════════
# Phase 2 新增: 每日报告
# ══════════════════════════════════════════════

def get_daily_report(codes: List[str]) -> str:
    """
    生成多股票每日分析报告（供定时推送用）

    参数:
        codes: 股票代码列表，如 ["BABA", "FUTU", "MU"]

    返回:
        格式化的综合报告文本
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 研析 每日决策仪表盘", f"生成时间: {now} JST", f"分析标的: {', '.join(codes)}"]
    lines.append("")

    results = []
    for code in codes:
        try:
            tr = get_trend_analysis(code)
            tech = get_technical_analysis(code)
            q = get_quote(code)

            if tr and "error" not in tr:
                signal = tr.get('buy_signal', 'N/A')
                score = tr.get('signal_score', 0)
                trend_st = tr.get('trend_status', '')
                results.append((code, signal, score, trend_st, tr, tech, q))
            elif tech and "error" not in tech:
                trend_st = tech.get('trend', '')
                results.append((code, '技术参考', 50, trend_st, None, tech, q))
        except Exception:
            continue

    if not results:
        return "⚠️ 所有标的均无法获取数据"

    # 按评分排序
    results.sort(key=lambda r: r[2], reverse=True)
    buy_count = sum(1 for r in results if '买入' in r[1] or '强烈' in r[1])
    sell_count = sum(1 for r in results if '卖出' in r[1])

    lines.append(f"信号汇总: 🟢买入:{buy_count} 🟡观望:{len(results)-buy_count-sell_count} 🔴卖出:{sell_count}")
    lines.append("")

    for code, signal, score, trend_st, tr, tech, q in results:
        price = tech.get('price', 0) if tech else 0
        change = q.get('change_pct', 0) if q else 0

        # 信号表情
        if '强烈买入' in signal:
            emoji = "🟢🟢"
        elif '买入' in signal:
            emoji = "🟢"
        elif '持有' in signal:
            emoji = "🔵"
        elif '强烈卖出' in signal:
            emoji = "🔴🔴"
        elif '卖出' in signal:
            emoji = "🔴"
        else:
            emoji = "🟡"

        lines.append(f"{emoji} {code} | ${price} ({change:+.2f}%) | {signal} | 评分{score}")
        lines.append(f"   趋势: {trend_st}")

        if tr:
            reasons = tr.get('signal_reasons', [])
            if reasons:
                lines.append(f"   依据: {'; '.join(reasons[:3])}")
            risks = tr.get('risk_factors', [])
            if risks:
                lines.append(f"   风险: {'; '.join(risks[:2])}")

        if tech:
            r = tech.get('returns', {})
            lines.append(f"   收益: 5日{r.get('5d',0):+.2f}% 20日{r.get('20d',0):+.2f}%")
            sr = tech.get('support_resistance', {})
            lines.append(f"   区间: ${sr.get('support_60d',0)} ~ ${sr.get('resistance_60d',0)}")
            lines.append(f"   RSI: {tech.get('rsi_14','N/A')} | MACD: {tech.get('macd',{}).get('signal_type','')}")
        lines.append("")

    lines.append("---")
    lines.append("研析 数据引擎 | 基于 daily_stock_analysis + YFinance")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# Phase 3 新增: 策略执行引擎
# ══════════════════════════════════════════════

def _eval_bull_trend(tech: dict, trend: dict) -> dict:
    """评估多头趋势策略"""
    score, reasons, risks = 0, [], []
    ma = tech.get('ma', {})
    p = tech.get('price', 0)

    # 多头排列 MA5 > MA10 > MA20
    if ma.get('ma5', 0) > ma.get('ma10', 0) > ma.get('ma20', 0):
        score += 30
        reasons.append("均线多头排列(MA5>MA10>MA20)")
    else:
        risks.append("均线非多头排列")

    # 乖离率检查
    bias5 = (p - ma.get('ma5', p)) / ma.get('ma5', p) * 100 if ma.get('ma5', 0) else 0
    if -2 < bias5 < 5:
        score += 15
        reasons.append(f"乖离率适中({bias5:+.1f}%)")
    elif bias5 > 5:
        risks.append(f"乖离率过高({bias5:+.1f}%)，追高风险")

    # RSI中性偏强
    rsi = tech.get('rsi_14', 50)
    if 40 <= rsi <= 70:
        score += 10
        reasons.append(f"RSI中性偏强({rsi:.0f})")

    # MACD多头
    if tech.get('macd', {}).get('signal_type') == '多头':
        score += 10
        reasons.append("MACD多头")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_ma_golden_cross(tech: dict, trend: dict) -> dict:
    """评估均线金叉策略"""
    score, reasons, risks = 0, [], []
    kline = _kline_cache
    if kline is None or len(kline) < 10:
        return {"score": 0, "reasons": ["数据不足"], "risks": []}

    close = kline['close'].astype(float)
    ma5_s = close.rolling(5).mean()
    ma10_s = close.rolling(10).mean()
    vol = kline['volume'].astype(float)

    # 检查最近3日是否有金叉
    cross = False
    for i in range(-3, 0):
        if len(ma5_s) > abs(i+1) and len(ma10_s) > abs(i+1):
            if ma5_s.iloc[i] > ma10_s.iloc[i] and ma5_s.iloc[i-1] <= ma10_s.iloc[i-1]:
                cross = True
                break

    if cross:
        score += 25
        reasons.append("MA5上穿MA10(金叉)")
    else:
        risks.append("无金叉信号")

    # 量能确认
    vol_ratio = tech.get('volatility', {}).get('vol_ratio', 1)
    if vol_ratio > 1.2:
        score += 10
        reasons.append(f"量能确认(量比{vol_ratio:.1f}x)")

    # MACD金叉
    md = tech.get('macd', {})
    if md.get('signal_type') == '多头' and md.get('histogram', 0) > 0:
        score += 15
        reasons.append("MACD金叉配合")

    # RSI位置
    rsi = tech.get('rsi_14', 50)
    if 30 <= rsi <= 60:
        score += 5
    elif rsi > 70:
        risks.append("RSI过高，追高风险")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_volume_breakout(tech: dict, trend: dict) -> dict:
    """评估放量突破策略"""
    score, reasons, risks = 0, [], []
    sr = tech.get('support_resistance', {})
    p = tech.get('price', 0)
    vol_ratio = tech.get('volatility', {}).get('vol_ratio', 1)
    hi_60d = sr.get('resistance_60d', 0)

    # 接近60日高点
    if hi_60d > 0 and p >= hi_60d * 0.97:
        score += 20
        reasons.append("价格接近60日高点")
    elif hi_60d > 0 and p >= hi_60d * 0.9:
        score += 10
        reasons.append(f"距60日高{((hi_60d-p)/hi_60d*100):.0f}%，有空间")

    # 放量
    if vol_ratio > 1.8:
        score += 20
        reasons.append(f"放量突破(量比{vol_ratio:.1f}x)")
    elif vol_ratio > 1.3:
        score += 10
        reasons.append(f"温和放量(量比{vol_ratio:.1f}x)")
    else:
        risks.append("量能不足")

    # 突破均线
    ma = tech.get('ma', {})
    if p > ma.get('ma20', 0):
        score += 10
        reasons.append("站上MA20")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_shrink_pullback(tech: dict, trend: dict) -> dict:
    """评估缩量回踩策略"""
    score, reasons, risks = 0, [], []
    p = tech.get('price', 0)
    ma = tech.get('ma', {})
    vol_ratio = tech.get('volatility', {}).get('vol_ratio', 1)

    # 缩量
    if vol_ratio < 0.7:
        score += 20
        reasons.append(f"缩量回调(量比{vol_ratio:.1f}x)")
    elif vol_ratio < 1.0:
        score += 10
        reasons.append(f"量能萎缩(量比{vol_ratio:.1f}x)")

    # 回踩MA5/MA10
    bias5 = (p - ma.get('ma5', p)) / ma.get('ma5', p) * 100 if ma.get('ma5', 0) else 0
    bias10 = (p - ma.get('ma10', p)) / ma.get('ma10', p) * 100 if ma.get('ma10', 0) else 0

    if -1 < bias5 < 2:
        score += 25
        reasons.append(f"回踩MA5支撑(乖离{bias5:+.1f}%)")
    elif -2 < bias10 < 2:
        score += 15
        reasons.append(f"接近MA10支撑(乖离{bias10:+.1f}%)")
    else:
        risks.append(f"离均线较远(MA5乖离{bias5:+.1f}%)")

    # 趋势背景
    if ma.get('ma5', 0) > ma.get('ma20', 0):
        score += 10
        reasons.append("短中期均线多头")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_dragon_head(tech: dict, trend: dict) -> dict:
    """评估龙头策略"""
    score, reasons, risks = 0, [], []
    sr = tech.get('support_resistance', {})
    ret = tech.get('returns', {})
    p = tech.get('price', 0)

    # 价格在60日区间高位
    pos = sr.get('position_pct', 0)
    if pos > 80:
        score += 20
        reasons.append(f"处于60日区间高位({pos:.0f}%分位)")
    elif pos > 60:
        score += 10

    # 短期收益强劲
    if ret.get('5d', 0) > 5:
        score += 15
        reasons.append(f"近5日强势(+{ret['5d']:.1f}%)")
    elif ret.get('20d', 0) > 10:
        score += 10

    # 趋势确认
    ma = tech.get('ma', {})
    if ma.get('ma5', 0) > ma.get('ma10', 0) and ma.get('ma10', 0) > ma.get('ma20', 0):
        score += 15
        reasons.append("多头排列确认")
    else:
        risks.append("均线未多头排列")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_one_yang_three_yin(tech: dict, trend: dict) -> dict:
    """评估一阳三阴形态"""
    score, reasons, risks = 0, [], []
    kline = _kline_cache
    if kline is None or len(kline) < 5:
        return {"score": 0, "reasons": ["数据不足"], "risks": []}

    closes = kline['close'].astype(float).values
    opens = kline['open'].astype(float).values

    if len(closes) < 5:
        return {"score": 0, "reasons": ["数据不足"], "risks": []}

    # 检查最近5根K线: 大阳线后跟3根小阴线
    last5_c = closes[-5:]
    last5_o = opens[-5:]

    # 阳线: close > open; 阴线: close < open
    candle_types = ['up' if last5_c[i] > last5_o[i] else 'down' for i in range(5)]

    # 找一阳三阴模式: 1阳 + 3阴, 且阴线不破阳线低点
    for i in range(len(candle_types) - 3):
        if candle_types[i] == 'up':
            yang_low = last5_o[i] if last5_o[i] < last5_c[i] else last5_c[i]
            yang_high = last5_c[i] if last5_c[i] > last5_o[i] else last5_o[i]
            yang_body = abs(last5_c[i] - last5_o[i])

            # 阳线实体至少2%
            if yang_body / yang_low * 100 < 2:
                continue

            # 后面3根阴线且不破阳线低点
            pattern_ok = True
            for j in range(1, 4):
                if i + j >= len(candle_types):
                    pattern_ok = False
                    break
                if candle_types[i + j] != 'down':
                    pattern_ok = False
                    break
                # 阴线最低
                yin_low = last5_o[i+j] if last5_o[i+j] < last5_c[i+j] else last5_c[i+j]
                if yin_low < yang_low:
                    pattern_ok = False
                    break

            if pattern_ok:
                score += 30
                reasons.append("一阳三阴形态确认")

    if score == 0:
        risks.append("未识别出一阳三阴形态")
    else:
        score += 10
        reasons.append("缩量回踩不破阳线低点")

    # RSI中性
    rsi = tech.get('rsi_14', 50)
    if 30 <= rsi <= 60:
        score += 5

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_bottom_volume(tech: dict, trend: dict) -> dict:
    """评估底部放量策略"""
    score, reasons, risks = 0, [], []
    sr = tech.get('support_resistance', {})
    ret = tech.get('returns', {})
    vol_ratio = tech.get('volatility', {}).get('vol_ratio', 1)
    pos = sr.get('position_pct', 0)

    # 处于低位
    if pos < 20:
        score += 20
        reasons.append(f"处于60日区间低位({pos:.0f}%分位)")
    elif pos < 40:
        score += 10
        reasons.append(f"相对低位({pos:.0f}%分位)")

    # 近期有跌幅
    if ret.get('20d', 0) < -10:
        score += 10
        reasons.append(f"近期跌幅较大(-{abs(ret['20d']):.0f}%)")
    elif ret.get('60d', 0) < -15:
        score += 10
        reasons.append("中期跌幅较大")

    # 放量
    if vol_ratio > 1.5:
        score += 15
        reasons.append(f"底部放量(量比{vol_ratio:.1f}x)")

    # RSI超卖反弹
    rsi = tech.get('rsi_14', 50)
    if rsi < 30:
        score += 15
        reasons.append(f"RSI超卖反弹机会({rsi:.0f})")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_box_oscillation(tech: dict, trend: dict) -> dict:
    """评估箱体震荡策略"""
    score, reasons, risks = 0, [], []
    sr = tech.get('support_resistance', {})
    pos = sr.get('position_pct', 0)
    ret = tech.get('returns', {})

    # 在区间中部
    if 30 <= pos <= 70:
        score += 15
        reasons.append(f"在箱体中部({pos:.0f}%分位)")

    # 振幅收窄
    amp = tech.get('volatility', {}).get('amplitude_pct', 0)
    if amp < 3:
        score += 10
        reasons.append("振幅收窄")

    # 近期横盘
    if abs(ret.get('20d', 0)) < 5:
        score += 15
        reasons.append("近20日横盘整理")

    # 近箱底可买入
    if pos < 30:
        score += 10
        reasons.append("接近箱体下沿")
    # 近箱顶需谨慎
    elif pos > 70:
        risks.append("接近箱体上沿")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_chan_theory(tech: dict, trend: dict) -> dict:
    """缠论简化评估：顶底分型识别"""
    score, reasons, risks = 0, [], []
    kline = _kline_cache
    if kline is None or len(kline) < 10:
        return {"score": 0, "reasons": ["数据不足"], "risks": []}

    highs = kline['high'].astype(float).values
    lows = kline['low'].astype(float).values
    closes = kline['close'].astype(float).values

    # 简化: 找最近3根K线的顶底分型
    if len(highs) >= 3:
        h3 = highs[-5:]  # 最近5根高点
        l3 = lows[-5:]   # 最近5根低点
        c3 = closes[-5:]

        # 底分型: 中间低点 < 两边
        for i in range(1, len(h3)-1):
            if l3[i] < l3[i-1] and l3[i] < l3[i+1]:
                score += 20
                reasons.append("底分型确认")
                if c3[i] > highs[i-1] or (i+1 < len(c3) and c3[i+1] > highs[i-1]):
                    score += 15
                    reasons.append("底分型+突破确认")
                break

        # 顶分型: 中间高点 > 两边
        for i in range(1, len(h3)-1):
            if h3[i] > h3[i-1] and h3[i] > h3[i+1]:
                risks.append("出现顶分型信号")
                break

    if score == 0:
        score += 10
        reasons.append("无明确缠论信号")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_wave_theory(tech: dict, trend: dict) -> dict:
    """波浪理论简化评估"""
    score, reasons, risks = 0, [], []
    kline = _kline_cache
    if kline is None or len(kline) < 30:
        return {"score": 0, "reasons": ["数据不足"], "risks": []}

    closes = kline['close'].astype(float).values

    # 找最近的波峰波谷（简化：用过去60天的最高最低）
    recent_high = max(closes[-60:])
    recent_low = min(closes[-60:])
    current = closes[-1]
    mid = (recent_high + recent_low) / 2

    # 从低位反弹
    if current < mid and trend.get('trend_strength', 0) > 30:
        score += 15
        reasons.append("可能处于上升浪初期")

    # 接近前高
    if current >= recent_high * 0.95:
        risks.append("可能处于第5浪末端")

    # 深度回调后企稳
    ret_60d = tech.get('returns', {}).get('60d', 0)
    if ret_60d < -15 and trend.get('trend_strength', 0) > 0:
        score += 15
        reasons.append("深度回调后企稳，可能开始新的上升浪")

    if score == 0:
        score += 10
        reasons.append("无明确波浪信号")

    return {"score": score, "reasons": reasons, "risks": risks}


def _eval_emotion_cycle(tech: dict, trend: dict) -> dict:
    """情绪周期评估"""
    score, reasons, risks = 0, [], []
    rsi = tech.get('rsi_14', 50)
    ret_20d = tech.get('returns', {}).get('20d', 0)
    vol_ratio = tech.get('volatility', {}).get('vol_ratio', 1)

    # 恐慌区域(超卖)
    if rsi < 30:
        score += 25
        reasons.append(f"RSI超卖({rsi:.0f})，恐慌情绪，可能是买入机会")

    # 贪婪区域(超买)
    elif rsi > 70:
        risks.append(f"RSI超买({rsi:.0f})，市场过热")

    # 大跌后放量
    if ret_20d < -10 and vol_ratio > 1.5:
        score += 15
        reasons.append("恐慌性放量下跌，短期可能见底")

    # 缩量企稳
    if ret_20d < -5 and vol_ratio < 0.7:
        score += 15
        reasons.append("缩量企稳，卖压衰竭")

    return {"score": score, "reasons": reasons, "risks": risks}


_evaluators = {
    'bull_trend': _eval_bull_trend,
    'ma_golden_cross': _eval_ma_golden_cross,
    'volume_breakout': _eval_volume_breakout,
    'shrink_pullback': _eval_shrink_pullback,
    'dragon_head': _eval_dragon_head,
    'one_yang_three_yin': _eval_one_yang_three_yin,
    'bottom_volume': _eval_bottom_volume,
    'box_oscillation': _eval_box_oscillation,
    'emotion_cycle': _eval_emotion_cycle,
    'chan_theory': _eval_chan_theory,
    'wave_theory': _eval_wave_theory,
}

_kline_cache = None

def evaluate_strategy(code: str, strategy_name: str) -> Dict[str, Any]:
    """
    对指定股票运行策略评估，返回策略评分和依据

    参数:
        code: 股票代码
        strategy_name: 策略名称

    返回:
        {"strategy": ..., "applicable": bool, "score": 0-100,
         "reasons": [...], "risks": [...]}
    """
    global _kline_cache
    _kline_cache = get_kline(code, days=120)
    tech = get_technical_analysis(code)
    trend = get_trend_analysis(code)

    if tech is None:
        return {"strategy": strategy_name, "score": 0, "applicable": False,
                "reasons": ["无法获取技术数据"], "risks": ["数据不足"]}

    # 获取策略显示名
    catalog = _get_skill_catalog()
    matched = [s for s in catalog if s['name'] == strategy_name]
    display = matched[0]['display_name'] if matched else strategy_name

    # 执行评估
    evaluator = _evaluators.get(strategy_name)
    if evaluator is None:
        return {
            "strategy": strategy_name,
            "display_name": display,
            "score": 0,
            "applicable": False,
            "reasons": ["该策略需要基本面/新闻数据支持，暂无法自动评估"],
            "risks": [],
            "note": "需结合新闻/基本面分析",
        }

    result = evaluator(tech, trend)
    score = min(result['score'], 80)  # 封顶80，给综合分析留空间

    # 趋势评分加权
    if trend and "error" not in trend:
        trend_score = trend.get('signal_score', 50)
        score = int(score * 0.7 + trend_score * 0.3)

    applicable = score >= 40

    return {
        "strategy": strategy_name,
        "display_name": display,
        "score": score,
        "applicable": applicable,
        "reasons": result['reasons'],
        "risks": result['risks'],
    }


def find_matching_strategies(code: str, top_n: int = 5) -> List[Dict[str, Any]]:
    """
    为指定股票匹配最适用的策略

    参数:
        code: 股票代码
        top_n: 返回前N个最匹配的策略

    返回:
        按评分降序排列的策略评估列表
    """
    results = []
    for sname in _evaluators:
        try:
            ev = evaluate_strategy(code, sname)
            results.append(ev)
        except Exception:
            continue

    # 按评分排序
    results.sort(key=lambda r: r['score'], reverse=True)
    return results[:top_n]


def format_strategy_evaluation(code: str) -> str:
    """格式化策略匹配结果"""
    matches = find_matching_strategies(code)
    tech = get_technical_analysis(code)
    price = tech['price'] if tech else 0

    lines = [f"【{code}】策略匹配分析 (${price})", ""]
    lines.append(f"最适用的策略 TOP {len(matches)}:")
    lines.append("")

    for i, m in enumerate(matches, 1):
        tag = "🟢" if m['applicable'] else "⚪"
        lines.append(f"  {tag} #{i} {m['display_name']}({m['strategy']}) — 评分{m['score']}")
        for r in m['reasons']:
            lines.append(f"      + {r}")
        for r in m['risks']:
            lines.append(f"      ! {r}")
        lines.append("")

    return "\n".join(lines)


def compare_stocks(codes: List[str]) -> str:
    """
    多股票综合对比报告

    参数:
        codes: 股票代码列表

    返回:
        结构化的对比表格文本
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 研析 多股对比分析", f"生成时间: {now} JST"]
    lines.append("")

    data = []
    for code in codes:
        try:
            tech = get_technical_analysis(code)
            trend = get_trend_analysis(code)
            q = get_quote(code)
            strategies = find_matching_strategies(code, top_n=3)
            best_s = strategies[0] if strategies else None
            data.append((code, tech, trend, q, best_s))
        except Exception:
            continue

    if not data:
        return "⚠️ 无法获取数据"

    # 表头
    lines.append(f"{'代码':<8} {'价格':<10} {'趋势':<12} {'评分':<6} {'最佳策略':<16} {'信号':<8}")
    lines.append("-" * 65)

    for code, tech, trend, q, best_s in data:
        price = f"${tech['price']:.2f}" if tech else "N/A"
        trend_st = trend.get('trend_status', tech.get('trend', ''))[:8] if (trend or tech) else "N/A"
        score = f"{trend.get('signal_score', 50)}" if trend else "50"
        strategy = best_s['display_name'] if best_s else "-"
        signal = trend.get('buy_signal', tech.get('ma_signal', ''))[:6] if (trend or tech) else "-"

        lines.append(f"{code:<8} {price:<10} {trend_st:<12} {score:<6} {strategy:<16} {signal:<8}")

    lines.append("")
    lines.append("")
    # 详细策略匹配
    lines.append("【策略详情】")
    lines.append("")
    for code, tech, trend, q, best_s in data:
        p = f"${tech['price']:.2f}" if tech else "N/A"
        lines.append(f"── {code} ({p}) ──")
        strategies = find_matching_strategies(code, top_n=3)
        for s in strategies:
            tag = "🟢" if s['applicable'] else "⚪"
            lines.append(f"  {tag} {s['display_name']} (评分{s['score']})")
            for r in s['reasons'][:2]:
                lines.append(f"    + {r}")
        lines.append("")

    lines.append("---")
    lines.append("研析 数据引擎 Phase 3 | 策略执行引擎")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="研析数据引擎 Phase 3")
    parser.add_argument("--quote", type=str, help="获取实时行情")
    parser.add_argument("--tech", type=str, help="获取技术分析")
    parser.add_argument("--report", type=str, help="获取文本报告")
    parser.add_argument("--trend", type=str, help="获取深度趋势分析")
    parser.add_argument("--strategy", type=str, nargs=2, metavar=("CODE", "STRATEGY"), help="使用指定策略分析股票")
    parser.add_argument("--eval-strategies", type=str, metavar="CODE", help="评估股票的最佳策略")
    parser.add_argument("--daily", type=str, help="每日报告（逗号分隔代码）")
    parser.add_argument("--compare", type=str, help="多股对比（逗号分隔代码）")
    parser.add_argument("--list-strategies", action="store_true", help="列出所有策略")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")
    args = parser.parse_args()

    if args.list_strategies:
        print(format_strategy_list())
    elif args.quote:
        result = get_quote(args.quote)
        print(json.dumps(result, ensure_ascii=False, default=str) if args.json else json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.tech:
        result = get_technical_analysis(args.tech)
        print(json.dumps(result, ensure_ascii=False, default=str) if args.json else json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.trend:
        result = get_trend_analysis(args.trend)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, default=str))
        else:
            print(get_trend_report(args.trend))
    elif args.strategy:
        code, sname = args.strategy
        result = get_strategy_analysis(code, sname)
        print(json.dumps(result, ensure_ascii=False, default=str) if args.json else json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.eval_strategies:
        if args.json:
            result = find_matching_strategies(args.eval_strategies)
            print(json.dumps(result, ensure_ascii=False, default=str))
        else:
            print(format_strategy_evaluation(args.eval_strategies))
    elif args.compare:
        codes = [c.strip() for c in args.compare.split(",")]
        print(compare_stocks(codes))
    elif args.daily:
        codes = [c.strip() for c in args.daily.split(",")]
        print(get_daily_report(codes))
    elif args.report:
        print(get_enhanced_report(args.report))
    else:
        # 默认: 简单验证
        print(get_daily_report(['BABA', 'FUTU', 'MU', 'TSLA', '7203.T']))
