#!/usr/bin/env python3
"""
标定检查：用人工判断的样例验证系统的阈值与规则是否合理。

用法:
    python calibrate.py             # 列出每条样例的期望 / 实际 / 是否相符
    python calibrate.py --quiet     # 只输出不符的条目与统计
    python calibrate.py --preset sentimental   # 换权重方案跑一遍

退出码:
    0 全部相符
    1 存在不符（用于作为改规则的回归门禁）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assess_item as core  # noqa: E402

SAMPLES_PATH = Path(__file__).resolve().parent / "calibration_samples.json"
SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"


def check_skill_table():
    """SKILL.md 品类速查表的数值必须与脚本的 CATEGORY_PRIORS 一致（否则两处漂移）。"""
    lines = SKILL_MD.read_text(encoding="utf-8").splitlines()
    problems = []
    for key, prior in core.CATEGORY_PRIORS.items():
        row = next((ln for ln in lines if f"`{key}`" in ln and ln.strip().startswith("|")), None)
        if row is None:
            problems.append(f"SKILL.md 品类速查表缺少 {key}")
            continue
        numbers = [int(n) for n in re.findall(r"(?<![\d.])(\d)(?![\d.])", row)]
        if len(numbers) < 6:
            problems.append(f"SKILL.md 中 {key} 行读不到六维数值：{row}")
            continue
        want = [prior["scores"][k] for k in core.DIM_KEYS]
        if numbers[:6] != want:
            problems.append(f"{key}：SKILL.md 为 {numbers[:6]}，脚本为 {want}")
    return problems


def check_wtp():
    """WTP 检验的价格换算必须稳定：同一个金额在不同经济档位下落到不同分。"""
    cases = [(200, "tight", 4), (200, "normal", 3), (200, "comfortable", 2), (100, "normal", 2)]
    problems = []
    for price, econ, want in cases:
        got = core.price_to_replace(price, econ)
        if got != want:
            problems.append(f"--price {price} --economy {econ}：应为 {want} 分，实际 {got} 分")
    return problems


def run(preset="balanced", economy="normal"):
    samples = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))["samples"]
    weights = core.resolve_weights(preset, None, [])
    rows = []
    results = core.assess_all(samples, weights, preset, None, economy)
    for sample, result in zip(samples, results):
        # 期望可按权重方案 / 经济档位覆盖：这两者本就会改变结论（如空间优先对小件的宽容）
        expect = sample.get("expect_by_preset", {}).get(preset, sample["expect"])
        expect = sample.get("expect_by_economy", {}).get(economy, expect)
        rows.append(
            {
                "name": sample["name"],
                "expect": expect,
                "actual": result["verdict"],
                "total": result["total"],
                "ok": result["verdict"] == expect,
                "why": sample.get("why", ""),
                "reasons": result["reasons"],
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description="标定样例回归检查")
    parser.add_argument("--preset", default="balanced", help="权重方案")
    parser.add_argument("--economy", default="normal", help="经济档位")
    parser.add_argument("--quiet", action="store_true", help="只显示不符的条目")
    args = parser.parse_args()

    rows = run(args.preset, args.economy)
    passed = sum(1 for r in rows if r["ok"])

    if not args.quiet:
        for r in rows:
            flag = "OK  " if r["ok"] else "FAIL"
            print(
                f"{flag} {r['name']:<16} 期望 {r['expect']:<6} 实际 {r['actual']:<6} {r['total']:>5.1f} 分"
            )
        print()

    for r in rows:
        if not r["ok"]:
            print(f"不符：{r['name']}  期望 {r['expect']}，实际 {r['actual']}（{r['total']:.1f} 分）")
            print(f"      理由：{r['why']}")
            for reason in r["reasons"]:
                print(f"      - {reason}")

    print(f"\n{passed}/{len(rows)} 条相符（preset={args.preset}, economy={args.economy}）")

    doc_problems = check_skill_table()
    wtp_problems = check_wtp()
    for title, problems in (("文档一致性", doc_problems), ("WTP 换算", wtp_problems)):
        if problems:
            print(f"\n{title}检查未通过：")
            for p in problems:
                print(f"  - {p}")
    if not doc_problems:
        print("文档一致性检查通过（SKILL.md 品类速查表与脚本一致）")
    if not wtp_problems:
        print("WTP 换算检查通过（价格锚点随经济档位缩放正常）")

    return 0 if passed == len(rows) and not doc_problems and not wtp_problems else 1


if __name__ == "__main__":
    sys.exit(main())
