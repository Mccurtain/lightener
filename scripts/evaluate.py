#!/usr/bin/env python3
"""
荷丛 Lightener - 通用加权汇总引擎

Usage:
    evaluate.py --template
    evaluate.py --input scores.json [--out report.md] [--score-only]
    evaluate.py --input scores.json --fail-under 80 --thresholds '{"good":80}'

Exit codes:
    0 - 评判完成
    1 - 低于 --fail-under 门槛
    2 - 输入或参数错误
"""

import argparse
import json
import sys
from pathlib import Path

DEFAULT_THRESHOLDS = {"excellent": 90, "good": 80, "pass": 60}
VALID_CONFIDENCE = ("high", "medium", "low")

TEMPLATE = {
    "target": "评判对象名称",
    "scale": 5,
    "dimensions": [
        {
            "name": "维度名",
            "weight": 0.3,
            "score": 4,
            "evidence": "支撑该分数的具体事实",
            "comment": "补充说明（可选）",
            "confidence": "high",
        }
    ],
}


def grade(total, thresholds):
    if total >= thresholds["excellent"]:
        return "优秀", "采纳"
    if total >= thresholds["good"]:
        return "良好", "采纳或小修后采纳"
    if total >= thresholds["pass"]:
        return "合格", "修改后采纳"
    return "不合格", "否决或重做"


def normalize_weights(dimensions, warnings):
    raw = []
    for d in dimensions:
        w = d.get("weight")
        if w is None:
            raw.append(None)
        else:
            if not isinstance(w, (int, float)) or w < 0:
                raise ValueError(f"维度 {d.get('name')} 的权重必须为非负数")
            raw.append(float(w))

    if any(w is None for w in raw):
        if not all(w is None for w in raw):
            warnings.append("部分维度缺少权重，已全部按等权处理")
        equal = 1.0 / len(raw)
        return [equal] * len(raw)

    total = sum(raw)
    if total <= 0:
        raise ValueError("权重总和必须大于 0")
    if abs(total - 1.0) > 1e-6:
        warnings.append(f"权重总和为 {total:g}，已归一化到 1")
    return [w / total for w in raw]


def evaluate(data, thresholds):
    if not isinstance(data, dict):
        raise ValueError("输入必须是 JSON 对象")

    target = data.get("target") or "未命名对象"
    scale = data.get("scale", 5)
    if not isinstance(scale, (int, float)) or scale <= 0:
        raise ValueError("scale 必须为正数")

    dimensions = data.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("dimensions 必须是非空数组")

    warnings = []
    weights = normalize_weights(dimensions, warnings)

    rows = []
    for d, w in zip(dimensions, weights):
        name = d.get("name") or "未命名维度"
        score = d.get("score")
        if not isinstance(score, (int, float)):
            raise ValueError(f"维度 {name} 缺少 score")
        if score < 0 or score > scale:
            raise ValueError(f"维度 {name} 的分数 {score} 超出范围 0~{scale}")

        confidence = d.get("confidence", "medium")
        if confidence not in VALID_CONFIDENCE:
            warnings.append(f"维度 {name} 的 confidence 非法，已按 medium 处理")
            confidence = "medium"

        evidence = (d.get("evidence") or "").strip()
        if not evidence:
            warnings.append(f"维度 {name} 缺少证据")

        norm = score / scale
        rows.append(
            {
                "name": name,
                "weight": w,
                "weight_raw": d.get("weight"),
                "score": score,
                "norm": norm,
                "contribution": w * norm,
                "evidence": evidence,
                "comment": (d.get("comment") or "").strip(),
                "confidence": confidence,
            }
        )

    total = 100 * sum(r["contribution"] for r in rows)
    verdict, suggestion = grade(total, thresholds)

    low_count = sum(1 for r in rows if not r["evidence"] or r["confidence"] == "low")
    if low_count >= 3:
        overall_confidence = "low"
    elif low_count >= 1:
        overall_confidence = "medium"
    else:
        overall_confidence = "high"

    return {
        "target": target,
        "scale": scale,
        "rows": rows,
        "total": total,
        "verdict": verdict,
        "suggestion": suggestion,
        "warnings": warnings,
        "confidence": overall_confidence,
    }


def render_report(result, thresholds):
    lines = []
    lines.append(f"# 评判报告：{result['target']}")
    lines.append("")
    lines.append(f"- 加权总分：**{result['total']:.1f} / 100**")
    lines.append(f"- 定级：**{result['verdict']}**")
    lines.append(f"- 建议：{result['suggestion']}")
    lines.append(f"- 整体置信度：{result['confidence']}")
    lines.append(
        "- 定级门槛：优秀 ≥ {} / 良好 ≥ {} / 合格 ≥ {}".format(
            thresholds["excellent"], thresholds["good"], thresholds["pass"]
        )
    )
    lines.append("")
    lines.append("## 逐维度评分")
    lines.append("")
    lines.append("| 维度 | 权重 | 得分 | 加权贡献 | 置信度 | 证据 |")
    lines.append("|------|------|------|----------|--------|------|")
    for r in result["rows"]:
        lines.append(
            "| {} | {:.2f} | {} / {} | {:.3f} | {} | {} |".format(
                r["name"],
                r["weight"],
                r["score"],
                result["scale"],
                r["contribution"],
                r["confidence"],
                r["evidence"] or "**证据不足**",
            )
        )
    lines.append("")
    lines.append("## 补充说明")
    lines.append("")
    comments = [r for r in result["rows"] if r["comment"]]
    if comments:
        for r in comments:
            lines.append(f"- **{r['name']}**：{r['comment']}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 主要优点 / 关键问题 / 改进建议")
    lines.append("")
    lines.append("- 主要优点：TODO")
    lines.append("- 关键问题：TODO")
    lines.append("- 改进建议：TODO")
    if result["warnings"]:
        lines.append("")
        lines.append("## 校验提示")
        lines.append("")
        for w in result["warnings"]:
            lines.append(f"- {w}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="荷丛 Lightener - 通用加权汇总")
    parser.add_argument("--input", help="评分 JSON 文件路径")
    parser.add_argument("--out", help="报告输出路径（Markdown）")
    parser.add_argument("--template", action="store_true", help="打印输入模板")
    parser.add_argument("--score-only", action="store_true", help="仅打印加权总分")
    parser.add_argument("--fail-under", type=float, help="低于该总分时以退出码 1 结束")
    parser.add_argument("--thresholds", help="定级门槛 JSON，如 '{\"good\":80}'")
    args = parser.parse_args()

    if args.template:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return 0

    if not args.input:
        parser.error("需要 --input 或 --template")
        return 2

    thresholds = dict(DEFAULT_THRESHOLDS)
    if args.thresholds:
        try:
            custom = json.loads(args.thresholds)
        except json.JSONDecodeError as e:
            print(f"错误：--thresholds 不是合法 JSON（{e}）", file=sys.stderr)
            return 2
        if not isinstance(custom, dict):
            print("错误：--thresholds 必须是 JSON 对象", file=sys.stderr)
            return 2
        thresholds.update({k: float(v) for k, v in custom.items() if k in thresholds})

    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        print(f"错误：找不到输入文件 {args.input}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"错误：{args.input} 不是合法 JSON（{e}）", file=sys.stderr)
        return 2

    try:
        result = evaluate(data, thresholds)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    if args.score_only:
        print(f"{result['total']:.2f}")
    else:
        report = render_report(result, thresholds)
        if args.out:
            Path(args.out).write_text(report, encoding="utf-8")
            print(f"报告已写入 {args.out}  总分 {result['total']:.1f}  定级 {result['verdict']}")
        else:
            print(report)

    for w in result["warnings"]:
        print(f"警告：{w}", file=sys.stderr)

    if args.fail_under is not None and result["total"] < args.fail_under:
        print(
            f"失败：总分 {result['total']:.1f} 低于门槛 {args.fail_under:g}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
