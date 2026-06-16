# -*- coding: utf-8 -*-
"""
===========================================
研析 → DSA 分析引擎适配器
===========================================
调用 daily_stock_analysis 的 AI 分析管线，
生成带买卖点位、止损目标、检查清单的决策报告。

使用方式:
    from dsa_adapter import dsa_analyze_stock, dsa_daily_report

    # 单股AI深度分析
    result = dsa_analyze_stock("BABA")  # 返回 AnalysisResult

    # 多股每日决策仪表盘
    report = dsa_daily_report(["BABA","FUTU","MU"])  # 返回格式化文本
"""

import os
import sys
import logging
from typing import Optional, List, Dict, Any

# 确保DSA项目在路径中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DSA 组件懒加载
_config = None
_pipeline = None
_notifier = None


def _ensure_dsa():
    """确保DSA环境已加载"""
    global _config, _pipeline, _notifier

    if _pipeline is not None:
        return

    try:
        from src.config import get_config
        _config = get_config()

        from src.notification import NotificationService
        _notifier = NotificationService(_config)

        from src.core.pipeline import StockAnalysisPipeline
        _pipeline = StockAnalysisPipeline(
            config=_config,
            max_workers=1,
            query_id="dsa_adapter",
            query_source="研析助手",
        )
        logger.info("DSA 分析引擎加载成功")
    except Exception as e:
        logger.error(f"DSA 加载失败: {e}")
        raise


def dsa_analyze_stock(code: str) -> Optional[Dict[str, Any]]:
    """
    使用DSA AI引擎深度分析单只股票（含买卖点位）

    返回:
        {
            "code": "BABA",
            "name": "阿里巴巴",
            "sentiment_score": 65,
            "operation_advice": "观望",
            "trend_prediction": "看多",
            "core_conclusion": "...",
            "position_advice": "...",
            "sniper_points": { "buy": "$110", "stop": "$105", "target": "$125" },
            "risk_alerts": [...],
            "checklist": [...],
        }
    """
    try:
        _ensure_dsa()

        from src.services.analyzer_service import analyze_stock
        config = _config
        config._report_type = "full"

        result = analyze_stock(
            stock_code=code,
            config=config,
            full_report=True,
            notifier=_notifier,
        )

        if result is None:
            return None

        # dashboard 包含 LLM 生成的完整决策数据
        dashboard = getattr(result, 'dashboard', None) or {}
        if isinstance(dashboard, dict):
            intelligence = dashboard.get('intelligence', {}) or {}
            battle_plan = dashboard.get('battle_plan', {}) or {}
            core_conc = dashboard.get('core_conclusion', {}) or {}
        else:
            intelligence, battle_plan, core_conc = {}, {}, {}

        if isinstance(core_conc, dict):
            one_sentence = core_conc.get('one_sentence', '') or ''
            pos_advice = core_conc.get('position_advice', '') or ''
        else:
            one_sentence = str(core_conc) if core_conc else ''
            pos_advice = ''

        sniper = {}
        if isinstance(battle_plan, dict):
            sp = battle_plan.get('sniper_points', None)
            if isinstance(sp, dict):
                sniper = sp

        risk_items = []
        if isinstance(intelligence, dict):
            r = intelligence.get('risk_alerts', None) or intelligence.get('risks', None) or []
            if isinstance(r, list):
                risk_items = r
            elif isinstance(r, str):
                risk_items = [r]

        checklist_items = []
        if isinstance(battle_plan, dict):
            cl = battle_plan.get('checklist', None) or battle_plan.get('check_list', None) or []
            if isinstance(cl, list):
                checklist_items = cl
            elif isinstance(cl, str):
                checklist_items = [cl]

        return {
            "code": getattr(result, 'code', code),
            "name": getattr(result, 'name', ''),
            "sentiment_score": getattr(result, 'sentiment_score', 0),
            "operation_advice": getattr(result, 'operation_advice', ''),
            "trend_prediction": getattr(result, 'trend_prediction', ''),
            "core_conclusion": one_sentence,
            "position_advice": pos_advice,
            "sniper_points": sniper,
            "risk_alerts": risk_items,
            "checklist": checklist_items,
            "risk_warning": getattr(result, 'risk_warning', ''),
        }
    except Exception as e:
        logger.error(f"DSA分析失败 {code}: {e}")
        return None


def dsa_daily_report(codes: List[str]) -> str:
    """
    多股票AI决策仪表盘（含买卖点位 + 检查清单）
    通过DSA管线生成完整报告
    """
    try:
        results = []
        for code in codes:
            r = dsa_analyze_stock(code)
            if r:
                results.append(r)

        if not results:
            return "⚠️ 所有股票分析均失败"

        results.sort(key=lambda x: x['sentiment_score'], reverse=True)

        lines = ["📊 研析 AI决策仪表盘", f"分析标的: {', '.join(codes)}", ""]

        for r in results:
            score = r['sentiment_score']
            advice = r['operation_advice']

            if '买入' in advice or '买' in advice:
                emoji = "🟢🟢" if score >= 70 else "🟢"
            elif '卖出' in advice or '卖' in advice:
                emoji = "🔴🔴" if score <= 30 else "🔴"
            else:
                emoji = "🟡"

            lines.append(f"{emoji} {r['code']} {r.get('name','')} | {advice} | 评分{score}")

            if r.get('core_conclusion'):
                lines.append(f"  📌 {r['core_conclusion']}")

            sniper = r.get('sniper_points', {})
            if sniper and isinstance(sniper, dict):
                buy = sniper.get('买入') or sniper.get('buy', '')
                stop = sniper.get('止损') or sniper.get('stop', '')
                target = sniper.get('目标') or sniper.get('target', '')
                if buy or stop or target:
                    lines.append(f"  💰 狙击: 买入{buy} | 止损{stop} | 目标{target}")

            alerts = r.get('risk_alerts', [])
            if alerts:
                for a in alerts[:2]:
                    lines.append(f"  ⚠️ {a}" if isinstance(a, str) else "")

            checklist = r.get('checklist', [])
            if checklist:
                for c in checklist[:3]:
                    lines.append(f"  {'✅' if '✅' in str(c) or '✔' in str(c) else '▪'} {c}" if isinstance(c, str) else "")

            lines.append("")

        lines.append("---\n🤖 研析数据引擎 | DSA AI分析")
        return "\n".join(lines)

    except Exception as e:
        return f"⚠️ 生成报告失败: {e}"


def _safe_attr(obj, attr, default=None):
    """安全获取嵌套属性"""
    if obj is None:
        return default
    val = getattr(obj, attr, None)
    if val is None:
        return default
    if hasattr(val, 'to_dict'):
        return val.to_dict()
    if hasattr(val, '_asdict'):
        return val._asdict()
    if isinstance(val, dict):
        return val
    return default


def _safe_list(obj, attr):
    """安全获取列表属性"""
    if obj is None:
        return []
    val = getattr(obj, attr, [])
    if val is None:
        return []
    return list(val) if hasattr(val, '__iter__') else []


if __name__ == "__main__":
    # 快速测试
    codes = sys.argv[1:] if len(sys.argv) > 1 else ['BABA', 'FUTU']
    print(dsa_daily_report(codes))
