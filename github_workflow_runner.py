# -*- coding: utf-8 -*-
"""
研析 GitHub Actions 三引擎组合分析脚本
被 .github/workflows/complete_analysis.yml 调用

组合 Minervini 扫描 + 策略匹配 + AI分析 三引擎
输出合并报告
"""
import sys, os, json, subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent

def run(cmd, **kw):
    """运行命令并返回输出"""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT, **kw)
    return result.stdout.strip(), result.returncode

def minervini_scan():
    """引擎1: Minervini 全市场扫描"""
    out, _ = run([sys.executable, "minervini_scanner.py", "--universe", "nasdaq100", "--top", "25"])
    return out

def minervini_top_stocks(top_n=8):
    """获取Minervini评分最高的候选股"""
    out, _ = run([sys.executable, "minervini_scanner.py", "--universe", "nasdaq100", "--top", "30", "--json"])
    try:
        data = json.loads(out)
        stocks = [s['symbol'] for s in sorted(data, key=lambda x: -x['score']) if s.get('score',0) >= 40]
        return stocks[:top_n] if stocks else []
    except:
        return []

def strategy_eval(code):
    """引擎2: 策略匹配"""
    try:
        out, _ = run([sys.executable, "stock_engine.py", "--json", "--eval-strategies", code])
        return json.loads(out) if out else []
    except:
        return []

def trend_analysis(code):
    """引擎2: 趋势分析"""
    try:
        out, _ = run([sys.executable, "stock_engine.py", "--json", "--trend", code])
        return json.loads(out) if out else {}
    except:
        return {}

def tech_analysis(code):
    """通用技术分析"""
    try:
        out, _ = run([sys.executable, "stock_engine.py", "--json", "--tech", code])
        return json.loads(out) if out else {}
    except:
        return {}

def minervini_single(code):
    """单股Minervini"""
    try:
        out, _ = run([sys.executable, "minervini_scanner.py", "--single", code, "--json"])
        return json.loads(out) if out else {}
    except:
        return {}

def format_telegram_report(stocks):
    """生成Telegram报告"""
    lines = ["🤖 研析 三引擎组合报告"]
    lines.append("")

    # 引擎1: Minervini
    lines.append("┌─ 引擎1: Minervini 全市场扫描 ─────────────┐")
    scan_out = minervini_scan()
    for line in scan_out.split("\n")[:8]:
        if line.strip():
            lines.append(line)
    lines.append("")

    # 引擎2+3: 每只候选股分析
    lines.append("┌─ 引擎2+3: 策略匹配 + AI决策 ─────────────┐")
    lines.append("")

    # ML 模型信号
    try:
        import subprocess, json
        r = subprocess.run([sys.executable, "stock_engine.py", "--json", "--ml", "ALL"], capture_output=True, text=True, cwd=PROJECT, timeout=15)
        if r.stdout and r.stdout.strip():
            ml = json.loads(r.stdout)
            if ml:
                lines.append("【ML模型预测】")
                seen = set()
                for p in sorted(ml, key=lambda x: (x['ticker'], x['horizon'])):
                    if p['ticker'] not in seen:
                        seen.add(p['ticker'])
                        tp = [x for x in ml if x['ticker'] == p['ticker']]
                        sigs = " ".join(["%dd:%s(%.0f%%)" % (x['horizon'], x['signal'], x['confidence']*100) for x in sorted(tp, key=lambda y: y['horizon'])])
                        lines.append("  %s: %s" % (p['ticker'], sigs))
                lines.append("")
    except:
        pass

    lines.append("%-6s %-6s %-8s %-8s %-6s %-16s %s" % ("股票", "评分", "趋势", "信号", "RSI", "最佳策略", "建议"))
    lines.append("-" * 80)

    for sym in stocks[:8]:
        trend = trend_analysis(sym)
        tech = tech_analysis(sym)
        ev = strategy_eval(sym)
        mr = minervini_single(sym)

        score = str(trend.get('signal_score', '-'))
        t = trend.get('trend_status', tech.get('trend', ''))[:6]
        sig = trend.get('buy_signal', '')[:6]
        rsi = str(trend.get('rsi_6', tech.get('rsi_14', '')))
        sname = ev[0].get('display_name', '-')[:14] if ev else '-'
        ms = str(mr.get('score', '')) if mr.get('score',0) > 0 else '-'

        price = tech.get('price', 0)
        entry = price * 0.97
        stop = price * 0.92
        target = price * 1.12

        lines.append("%-6s \$%-5s %-8s %-8s %-6s %-16s Minervini:%s" % (
            sym, f"{price:.0f}", score, t, rsi, sname, ms))
        lines.append("  → 买入\$%.0f-\$%.0f 止损\$%.0f 目标\$%.0f" % (entry, price, stop, target))

    lines.append("")
    lines.append("┌─ 操作建议 ───────────────────────────────┐")
    buy = [s for s in stocks[:8] if trend_analysis(s).get('buy_signal','') in ['买入','强烈买入','持有']]
    for s in buy[:3]:
        lines.append("  ✅ %s: 评分%s, 多头排列" % (s, trend_analysis(s).get('signal_score','')))
    for s in stocks[:8]:
        t = trend_analysis(s)
        if t.get('buy_signal','') in ['观望','卖出','强烈卖出']:
            lines.append("  ⏳ %s: 评分%s, 等待信号" % (s, t.get('signal_score','')))

    lines.append("")
    lines.append("---")
    lines.append("🤖 研析 | 三引擎: Minervini + 策略 + AI")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stocks", type=str, help="指定股票(逗号分隔)")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--telegram", action="store_true", help="Telegram格式")
    args = parser.parse_args()

    if args.stocks:
        stocks = [s.strip() for s in args.stocks.split(",")]
    else:
        stocks = minervini_top_stocks(8)
        if not stocks:
            stocks = ["AAPL","MSFT","GOOGL","AMZN","NVDA","TSLA","META","AVGO"]

    if args.telegram:
        print(format_telegram_report(stocks))
    elif args.json:
        result = {"stocks": [], "minervini_scan": minervini_scan()}
        for sym in stocks:
            result["stocks"].append({
                "symbol": sym,
                "trend": trend_analysis(sym),
                "tech": tech_analysis(sym),
                "strategies": strategy_eval(sym),
                "minervini": minervini_single(sym),
            })
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(format_telegram_report(stocks))
