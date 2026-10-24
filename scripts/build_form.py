#!/usr/bin/env python3
"""
把 assess_item.py 里的规则数据导出为 assets/rules.json，并同步进网页表单。

规则只此一份（assess_item.py），网页不再手写常量，避免两边改漏。

用法:
    python build_form.py           # 生成 rules.json 并同步表单
    python build_form.py --check   # 只检查是否同步，不同步返回 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assess_item as core  # noqa: E402

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
FORM = ASSETS / "assessment-form.html"
RULES_JSON = ASSETS / "rules.json"

COLORS = ["#16a34a", "#65a30d", "#ca8a04", "#ea580c", "#dc2626"]

PRICE_FN = """function priceToReplace(price, econ){
  const e = ECONOMY[econ] || ECONOMY.normal;
  for(const [t,s] of e.anchors){ if(price>=t) return s; }
  return 1;
}"""


def build_rules():
    return {
        "scale": core.SCALE,
        "dimensions": [
            {
                "key": d["key"],
                "name": d["name"],
                "q": d["question"],
                "opts": [label for _score, label in d["options"]],
            }
            for d in core.DIMENSIONS
        ],
        "presets": {
            key: {"label": core.PRESET_LABELS[key], "w": weights}
            for key, weights in core.PRESETS.items()
        },
        "tiers": [list(t) for t in core.TIERS],
        "colors": COLORS,
        "categories": {
            key: {
                "label": value["label"],
                "scores": value["scores"],
                "ask": value.get("ask", []),
                "hint": value.get("hint", ""),
                "flags": value.get("flags", []),
                "digitize": bool(value.get("digitize", False)),
                "dependent": bool(value.get("dependent", False)),
            }
            for key, value in core.CATEGORY_PRIORS.items()
        },
        "economy": {
            key: {
                "label": value["label"],
                "anchors": [list(a) for a in value["anchors"]],
                "flow": value["flow"],
                "preset": value["preset"],
                "hint": value["hint"],
            }
            for key, value in core.ECONOMY_LEVELS.items()
        },
        "flags": [list(f) for f in core.FLAGS],
        "bias": core.BIAS_HINTS,
        "marks": core.TIER_MARKS,
    }


def consts_block():
    """生成表单里的常量：全部从 RULES 读取，不再硬编码。"""
    return "\n".join(
        [
            "const DIMS = RULES.dimensions;",
            "const PRESETS = RULES.presets;",
            "const TIERS = RULES.tiers;",
            "const COLORS = RULES.colors;",
            "const CATEGORIES = RULES.categories;",
            "const ECONOMY = RULES.economy;",
            "const FLAGS = RULES.flags;",
            "const BIAS = RULES.bias;",
            "const MARKS = RULES.marks;",
            PRICE_FN,
        ]
    )


def replace_between(text, begin, end, payload):
    start = text.find(begin)
    stop = text.find(end)
    if start == -1 or stop == -1:
        raise SystemExit(f"在 {FORM} 中找不到标记 {begin} / {end}")
    return text[: start + len(begin)] + "\n" + payload + "\n" + text[stop:]


def main():
    parser = argparse.ArgumentParser(description="生成规则数据并同步网页表单")
    parser.add_argument("--check", action="store_true", help="只检查是否同步")
    args = parser.parse_args()

    rules = build_rules()
    payload = json.dumps(rules, ensure_ascii=False, indent=1)
    text = FORM.read_text(encoding="utf-8")
    updated = replace_between(text, "/* RULES:BEGIN */", "/* RULES:END */", payload)
    updated = replace_between(updated, "/* CONSTS:BEGIN */", "/* CONSTS:END */", consts_block())

    if args.check:
        if updated != text:
            print("网页表单与规则数据不同步，请运行：python scripts/build_form.py", file=sys.stderr)
            return 1
        print("网页表单已与规则数据同步")
        return 0

    RULES_JSON.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    FORM.write_text(updated, encoding="utf-8")
    print(f"已生成 {RULES_JSON}")
    print(f"已同步 {FORM}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
