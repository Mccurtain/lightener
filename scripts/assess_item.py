#!/usr/bin/env python3
"""
荷丛 Lightener 物品去留决策系统 —— 量化评估一件物品该丢弃还是保留。

用法:
    python assess_item.py --interactive
    python assess_item.py --input items.json [--preset balanced] [--weights '{"usage":0.35}']
    python assess_item.py --input items.json --out report.md --html report.html --json result.json
    python assess_item.py --list-presets

退出码:
    0 评估完成
    2 输入或参数错误
"""

from __future__ import annotations

import argparse
import calendar
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate as engine  # noqa: E402  通用加权汇总引擎

SCALE = 5

# 硬规则阈值（集中定义，便于标定调整）
HR_USAGE_LOW = 1          # 使用频率低
HR_FUTURE_LOW = 2         # 未来需求低
HR_FUTURE_WISH = 2        # "万一用得上"所在档
HR_SENTIMENT_NONE = 0     # 看到就烦
HR_SENTIMENT_PROTECT = 3  # 达到此分不做丢弃结论
HR_SENTIMENT_HIGH = 5     # 无可替代的纪念
HR_REPLACE_CHEAP = 1      # 随手可得
HR_CONDITION_GOOD = 4     # 完好
IDLE_WEIGHT_SCALE = 0.5   # 闲置物品：功能状态与替代难度的贡献折半
IDLE_SENTIMENT_MAX = 3    # 情感不超过此分才适用闲置折半
REDUNDANT_REPLACE_MAX = 2 # 同类冗余：容易再获得的阈值
SWING_SEAL_TIER = 2      # 摇摆后的落点：暂存观察 / 封存（只向这个方向移动一次）
SWING_LOCK_AT = 2        # 摇摆达到几次后锁定（后悔保险不续保）
SWING_LOCK_MONTHS = 3    # 锁定后统一的复评月数
# 附属件联动（狄德罗效应的反面）：主件失去意义时，只服务于它的配件价值随之清零
DEP_HOST_TIER = 3        # 主件结论达到此档（建议流转）即视为"主件没了"
DEP_FLOOR_TIER = 3       # 附属件的结论下限：不低于建议流转
DEP_SENTIMENT_KEEP = 4   # 情感达到此分的附属件可封存，不强制流转

# 行为经济学三件套：命中时在报告里点名心理偏差，把"舍不得"从情绪变成可解释的机制。
# when 是结构化条件（dim=某个维度 / idx=结论档位 / evidence=依据文本匹配），
# 由 build_form.py 导出给网页表单，两边共用同一份定义，不各写一套。
BIAS_HINTS = [
    {
        "key": "endowment",
        "name": "禀赋效应",
        "when": [
            {"kind": "dim", "dim": "replace", "op": ">=", "val": 3},
            {"kind": "dim", "dim": "usage", "op": "<=", "val": 1},
        ],
        "text": "「值钱 / 难得」却一直没在用——一旦拥有就会高估价值"
                "（Kahneman-Knetsch-Thaler 的马克杯实验：卖价远高于买价）。"
                "替代难度只问「现在还能不能弄到」，不问「它值多少钱」。"
                "更深一层：在占有型导向里，物品被当成自我的一部分，放手才像割掉自己一块"
                "（弗洛姆《占有还是存在》）。",
    },
    {
        "key": "sunk_cost",
        "name": "沉没成本",
        "when": [
            {"kind": "evidence", "pattern": "花了|花掉|买成|买的|当年|当初|原价|专柜|海淘|打折|挺贵|很贵"},
        ],
        "text": "提到的花销已经付出且收不回（Arkes & Blumer, 1985）。"
                "决策只看从今往后的得失：当初花了多少，不该影响现在要不要留。",
    },
    {
        "key": "loss_aversion",
        "name": "损失厌恶",
        "when": [
            {"kind": "idx", "op": ">=", "val": 3},
            {"kind": "dim", "dim": "condition", "op": ">=", "val": 3},
        ],
        "text": "东西还完好却要放手，反弹是正常的：失去的痛感约为等量得到的两倍"
                "（Kahneman & Tversky 前景理论）。这不是你犹豫不决，是大脑的默认机制——"
                "所以结论不改，只给一个出口：封存观察，到期再看。",
    },
]

_CMP = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def bias_hints(scores, idx, evidence):
    """按结构化条件挑出命中的心理偏差提示。"""
    blob = " ".join(str(v) for v in (evidence or {}).values() if v)
    hits = []
    for hint in BIAS_HINTS:
        hit = True
        for cond in hint["when"]:
            if cond["kind"] == "dim":
                hit = hit and _CMP[cond["op"]](scores.get(cond["dim"], 0), cond["val"])
            elif cond["kind"] == "idx":
                hit = hit and _CMP[cond["op"]](idx, cond["val"])
            elif cond["kind"] == "evidence":
                hit = hit and bool(re.search(cond["pattern"], blob))
        if hit:
            hits.append({"key": hint["key"], "name": hint["name"], "text": hint["text"]})
    return hits

DIMENSIONS = [
    {
        "key": "usage",
        "name": "使用频率",
        "question": "上一次真正用到它，是什么时候？",
        "options": [
            (5, "最近一两周还在用"),
            (4, "最近几个月用过"),
            (3, "大概一年前"),
            (2, "去年或更早，一年里偶尔用"),
            (1, "想不起来上次是什么时候"),
            (0, "买来就没怎么用过 / 从没用过"),
        ],
    },
    {
        "key": "future",
        "name": "未来需求",
        "question": "接下来一年，有没有具体哪件事会用到它？",
        "options": [
            (5, "已经定好了，肯定会用"),
            (4, "有固定的时候（换季、过年、每年一次）"),
            (3, "能想到具体场景，但不确定"),
            (2, "说不准，就是觉得万一用得上"),
            (1, "想不出什么事"),
            (0, "情况变了，肯定用不上了"),
        ],
    },
    {
        "key": "condition",
        "name": "功能状态",
        "question": "现在还能用吗？",
        "options": [
            (5, "能，跟新的差不多"),
            (4, "能用，有正常使用痕迹"),
            (3, "能用，但得修一下或换配件"),
            (2, "得大修才行"),
            (1, "勉强能用，快不行了"),
            (0, "用不了了：坏了 / 过期 / 变质"),
        ],
    },
    {
        "key": "replace",
        "name": "替代难度",
        "question": "如果现在需要，还能再弄到一个吗？",
        "options": [
            (5, "弄不到了：绝版、独一无二、别人手工做的"),
            (4, "能，但很贵，或者得费劲找"),
            (3, "得专门跑一趟或下单等几天"),
            (2, "网上随手就能买，也不贵"),
            (1, "随处都有，很便宜"),
            (0, "家里还有好几个"),
        ],
    },
    {
        "key": "sentiment",
        "name": "情感价值",
        "question": "它是从哪来的？",
        "options": [
            (5, "重要的人给的或留下的"),
            (4, "某次特别的经历带回来的"),
            (3, "自己买的，用了很久有点感情"),
            (2, "有点喜欢，没什么特别来历"),
            (1, "随手买的 / 别人给的，无感"),
            (0, "看到就烦，或连着不愉快的事"),
        ],
    },
    {
        "key": "space",
        "name": "空间友好度",
        "question": "它现在放在哪儿，占多大地方？",
        "options": [
            (5, "随手就能拿到，几乎不占地方"),
            (4, "收在一个小格子里"),
            (3, "占一格层板或一个抽屉"),
            (2, "占半个柜子"),
            (1, "算大件，占一整柜"),
            (0, "专门腾了地方：一个角落 / 一间房"),
        ],
    },
]

DIM_KEYS = [d["key"] for d in DIMENSIONS]
DIM_NAMES = {d["key"]: d["name"] for d in DIMENSIONS}

PRESETS = {
    "balanced": {
        "usage": 0.25, "future": 0.20, "condition": 0.15,
        "replace": 0.15, "sentiment": 0.15, "space": 0.10,
    },
    "minimalist": {
        "usage": 0.35, "future": 0.25, "condition": 0.10,
        "replace": 0.10, "sentiment": 0.10, "space": 0.10,
    },
    "sentimental": {
        "usage": 0.20, "future": 0.15, "condition": 0.15,
        "replace": 0.10, "sentiment": 0.30, "space": 0.10,
    },
    "space": {
        "usage": 0.25, "future": 0.20, "condition": 0.10,
        "replace": 0.10, "sentiment": 0.05, "space": 0.30,
    },
}

PRESET_LABELS = {
    "balanced": "均衡（默认）",
    "minimalist": "极简主义",
    "sentimental": "念旧宽容",
    "space": "空间优先",
}

# (下限, 结论, 处置路径, 下一步动作)
TIERS = [
    (70, "保留", "继续使用", "放回原位，保持随时可取"),
    (55, "保留（观察）", "降级存放", "移出黄金位，6 个月后复评"),
    (40, "暂存观察", "封存", "装箱标记日期，3-6 个月到期未取用即处理"),
    (25, "建议流转", "转赠 / 转卖 / 捐赠", "一周内挂二手或问亲友，无人接手则回收"),
    (0, "建议丢弃", "丢弃 / 回收", "按当地规则分类投放或预约回收"),
]

FLAGS = [
    ("safety", "安全/卫生/法律风险（违禁、霉变、鼓包电池等）"),
    ("expired", "已过期或变质（食品、药品、化妆品）"),
    ("irreparable", "损坏且不可修复"),
    ("document", "不可替代凭证（证件、合同、产权、保修凭证）"),
]

FLAG_LABELS = dict(FLAGS)

TIER_MARKS = "0 丢弃 ─ 25 流转 ─ 40 暂存 ─ 55 降级 ─ 70 保留 ─ 100"

# 品类基线：从物品品类一次性推断多个维度，只把真正不确定的维度留给用户
# scores 为推断值（用户给了分数时以用户为准），ask 为必须追问的维度，flags 为品类自带的硬规则标记
CATEGORY_PRIORS = {
    "phone_box": {
        "label": "手机 / 数码包装盒",
        "scores": {"usage": 0, "future": 1, "condition": 4, "replace": 1, "sentiment": 1, "space": 4},
        "ask": ["future", "sentiment"],
        "hint": "留着通常只为保修、退换或转卖；没有这些用途就不必留",
        "dependent": True,
    },
    "cable": {
        "label": "线材 / 充电线 / 小配件",
        "scores": {"usage": 1, "future": 2, "condition": 3, "replace": 1, "sentiment": 1, "space": 5},
        "ask": ["usage", "condition"],
        "hint": "最容易囤积的品类：只留当前设备正在用的，其余处理",
        "dependent": True,
    },
    "clothing": {
        "label": "一年以上没穿的衣服",
        "scores": {"usage": 1, "future": 2, "condition": 4, "replace": 2, "sentiment": 2, "space": 3},
        "ask": ["sentiment", "condition"],
        "hint": "合身与否和情感是主要变量，其余维度可沿用基线",
    },
    "book": {
        "label": "未读 / 已读完的书",
        "scores": {"usage": 1, "future": 2, "condition": 4, "replace": 2, "sentiment": 2, "space": 3},
        "ask": ["sentiment", "future"],
        "hint": "可转赠或数字化；成套书、签名本另按情感价值加分",
        "digitize": True,
    },
    "manual": {
        "label": "说明书 / 保修卡 / 票据",
        "scores": {"usage": 0, "future": 1, "condition": 4, "replace": 1, "sentiment": 1, "space": 5},
        "ask": ["future"],
        "hint": "多数可拍照存档；跟着物件走更有用，单独留存意义不大",
        "digitize": True,
        "dependent": True,
    },
    "packaging": {
        "label": "包装袋 / 纸箱 / 礼品袋",
        "scores": {"usage": 2, "future": 3, "condition": 4, "replace": 0, "sentiment": 1, "space": 4},
        "ask": ["usage"],
        "hint": "留少量常用尺寸备用即可，其余压扁回收",
    },
    "kitchenware": {
        "label": "厨具 / 餐具",
        "scores": {"usage": 3, "future": 4, "condition": 4, "replace": 2, "sentiment": 1, "space": 2},
        "ask": ["usage"],
        "hint": "功能重复的是处理重点，同用途留一件最好用的",
    },
    "appliance": {
        "label": "小家电",
        "scores": {"usage": 2, "future": 3, "condition": 4, "replace": 2, "sentiment": 1, "space": 2},
        "ask": ["usage", "condition"],
        "hint": "一年没通电、又没有季节用途的，多半不再需要",
    },
    "hobby": {
        "label": "兴趣装备（运动 / 乐器 / 摄影）",
        "scores": {"usage": 1, "future": 2, "condition": 4, "replace": 3, "sentiment": 2, "space": 2},
        "ask": ["usage", "future"],
        "hint": "关键看这个兴趣还在不在；装备通常还有残值，可转卖",
    },
    "gift": {
        "label": "别人送的摆件 / 礼品",
        "scores": {"usage": 0, "future": 1, "condition": 4, "replace": 3, "sentiment": 3, "space": 3},
        "ask": ["sentiment"],
        "hint": "情感价值几乎是唯一变量：留下真心喜欢的，其余转赠",
    },
    "kids": {
        "label": "孩子的成长纪念物",
        "scores": {"usage": 0, "future": 1, "condition": 3, "replace": 5, "sentiment": 4, "space": 3},
        "ask": ["sentiment"],
        "hint": "拍照或扫描后精简实体，留少量最有代表性的",
        "digitize": True,
    },
    "keepsake": {
        "label": "亲人的遗物",
        "scores": {"usage": 0, "future": 1, "condition": 3, "replace": 5, "sentiment": 5, "space": 3},
        "ask": [],
        "hint": "情感价值按 5 处理，结论不会是丢弃；建议封存或纪念化",
    },
    "device": {
        "label": "旧手机 / 旧电脑",
        "scores": {"usage": 0, "future": 1, "condition": 3, "replace": 3, "sentiment": 1, "space": 4},
        "ask": ["condition", "future"],
        "hint": "先确认数据已备份并清除，再决定转卖或回收",
    },
    "furniture": {
        "label": "家具 / 大件",
        "scores": {"usage": 3, "future": 3, "condition": 4, "replace": 3, "sentiment": 1, "space": 0},
        "ask": ["condition", "usage"],
        "hint": "空间占用权重最高，处理大件对居住体验改善最明显",
    },
    "document": {
        "label": "证件 / 合同 / 产权文件",
        "scores": {"usage": 1, "future": 4, "condition": 4, "replace": 5, "sentiment": 1, "space": 5},
        "flags": ["document"],
        "ask": [],
        "hint": "不可替代凭证，硬规则强制保留",
    },
    "expired": {
        "label": "过期食品 / 药品 / 化妆品",
        "scores": {"usage": 0, "future": 0, "condition": 0, "replace": 1, "sentiment": 0, "space": 5},
        "flags": ["expired"],
        "ask": [],
        "hint": "硬规则立即处理，不参与评分",
    },
}


# ---------- 权重 ----------

def parse_weights(raw):
    """支持两种写法：JSON 对象 或 key=value,key=value（后者免引号，跨 shell 更稳）。"""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"--weights 不是合法 JSON（{e}）")
        if not isinstance(parsed, dict):
            raise ValueError("--weights 必须是 JSON 对象")
        return parsed

    out = {}
    for part in raw.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        pair = re.split(r"[=:]", part, maxsplit=1)
        if len(pair) != 2:
            raise ValueError(f"--weights 片段 {part!r} 格式应为 维度=权重")
        key, value = pair[0].strip(), pair[1].strip()
        try:
            out[key] = float(value)
        except ValueError:
            raise ValueError(f"--weights 中 {key} 的权重不是数字")
    return out


ECONOMY_LEVELS = {
    "tight": {
        "label": "预算敏感",
        "anchors": [(200, 4), (50, 3), (0, 2)],
        "flow": "优先自己用掉或转卖换钱，别急着送人",
        "preset": "space",
        "hint": "价格阈值下调：两百块已属不小支出，替代难度偏高，结论更倾向保留",
    },
    "normal": {
        "label": "常规",
        "anchors": [(1000, 4), (200, 3), (0, 2)],
        "flow": "先问亲友，无人要再挂二手，仍无人接手则回收",
        "preset": "balanced",
        "hint": "按常规价格敏感度判定：千元以上才算难再获得",
    },
    "comfortable": {
        "label": "预算宽裕",
        "anchors": [(5000, 4), (1000, 3), (0, 2)],
        "flow": "直接送人或捐赠，不必为小钱花时间挂二手",
        "preset": "balanced",
        "hint": "价格阈值上移：多数物品都容易再买到，替代难度偏低；处置以省时间为主",
    },
}


def price_to_replace(price, economy="normal"):
    """把"重新买一个要多少钱"翻译成替代难度分，阈值随经济档位缩放。"""
    if economy not in ECONOMY_LEVELS:
        raise ValueError(f"未知经济档位 {economy}，可选 {', '.join(ECONOMY_LEVELS)}")
    if price < 0:
        raise ValueError("价格不能为负")
    for threshold, score in ECONOMY_LEVELS[economy]["anchors"]:
        if price >= threshold:
            return score
    return 1


def resolve_weights(preset, override_raw, warnings):
    if preset not in PRESETS:
        raise ValueError(f"未知权重方案：{preset}，可选 {', '.join(PRESETS)}")
    weights = dict(PRESETS[preset])

    if override_raw:
        override = parse_weights(override_raw)
        for key, value in override.items():
            if key not in DIM_KEYS:
                raise ValueError(f"未知维度 {key}，可选 {', '.join(DIM_KEYS)}")
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"维度 {key} 的权重必须为非负数")
            weights[key] = float(value)

    total = sum(weights.values())
    if total <= 0:
        raise ValueError("权重总和必须大于 0")
    if abs(total - 1.0) > 1e-6:
        warnings.append(f"权重总和为 {total:g}，已归一化到 1")
    return {k: v / total for k, v in weights.items()}


# ---------- 判定 ----------

def tier_index(total):
    for i, (low, *_rest) in enumerate(TIERS):
        if total >= low:
            return i
    return len(TIERS) - 1


def apply_hard_rules(scores, flags, idx):
    """返回 (index, verdict_override, action_override, next_step_override, reasons)。"""
    reasons = []

    if "safety" in flags:
        return 4, "立即处理", "按当地规定投放或专业回收", "本周内单独分拣处理，不与生活垃圾混放", [
            "存在安全/卫生/法律风险，强制处理，不参与评分"
        ]
    if "expired" in flags:
        return 4, "立即处理", "丢弃或按品类回收", "清理出有效期已过的全部同批物品", [
            "已过期或变质，强制处理"
        ]
    if "document" in flags:
        return 0, "强制保留", "归档固定位置并做备份", "放入证件盒，扫描件存云端", [
            "不可替代凭证，强制保留"
        ]
    if scores.get("condition", SCALE) == 0 or "irreparable" in flags:
        if scores.get("sentiment", 0) >= 4:
            return 3, "纪念化处理", "拍照或留存部件后处理本体", "先拍照/剪留一小块，再处理本体", [
                "已不可修复；情感价值较高，先做纪念化留存"
            ]
        return 4, "建议丢弃", "不可修复件优先回收", "查询可回收渠道，无法回收再丢弃", [
            "功能状态为 0 或标记不可修复，直接建议处理"
        ]

    if (
        scores.get("replace", 1) <= 1
        and idx == 3
        and scores.get("sentiment", 0) <= 2
    ):
        idx = 4
        reasons.append("随手可得、没有转卖或转赠价值，直接回收处理，不必挂二手")
    if scores.get("usage", 0) == SCALE and scores.get("future", 1) >= 4 and idx > 0:
        idx = 0
        reasons.append("每天都在用且未来确定需要，结论上调为保留")
    if scores.get("sentiment", 0) == SCALE and idx >= 4:
        idx = 2
        reasons.append("情感价值为 5，不输出丢弃，结论上调为封存观察")
    # 舍不是扔：还能用、送得出去的东西不进垃圾桶
    if (
        idx == 4
        and scores.get("condition", 0) >= 3
        and scores.get("replace", 0) >= 2
    ):
        idx = 3
        reasons.append("还能用且送得出去（功能 ≥3、替代 ≥2），不做丢弃结论，先流转")
    # 误丢不可逆：有感情的物品不做丢弃结论，至少先流转
    if scores.get("sentiment", 0) >= HR_SENTIMENT_PROTECT and idx == 4:
        idx = 3
        reasons.append(
            f"情感价值 ≥ {HR_SENTIMENT_PROTECT}（丢了会可惜），丢弃不可逆，改为先流转"
        )
    # 情感较高：既不丢弃也不转赠，封存观察
    if scores.get("sentiment", 0) >= 4 and idx > 2:
        idx = 2
        reasons.append("情感价值 ≥ 4：不丢弃也不转赠，改为封存观察")
    # 未来需求明确：不能因为现在没用就处理掉
    if scores.get("future", 0) >= 4 and idx > 2:
        idx = 2
        reasons.append("未来需求明确（≥4）：不能因为现在没用就处理，改为封存观察")
    # 断舍离：看到就烦的东西不该继续留在生活里
    if scores.get("sentiment", 1) == 0 and idx < 3:
        idx = 3
        reasons.append("情感价值为 0（看到就烦或负面记忆），结论不低于建议流转")
    # 断舍离：主轴是"现在的我"，不是"物品还能不能用"
    if scores.get("usage", SCALE) <= 1 and scores.get("future", SCALE) <= 2 and idx < 2:
        idx = 2
        reasons.append("对现在的你已无用途（使用频率 ≤1 且未来需求 ≤2），结论不得高于暂存观察")
    return idx, None, None, None, reasons


ITEM_KEYS = {
    "name", "category", "scores", "evidence", "flags", "notes", "owner", "economy", "swings",
    "depends_on", "host_gone", "wtp",
}


def validate_item(item):
    """防止分数被写在顶层而静默回退——这类错误必须报错，不能悄悄算出错结论。"""
    if not isinstance(item, dict):
        raise ValueError("每个物品必须是 JSON 对象")
    name = item.get("name") or "未命名物品"

    misplaced = [k for k in item if k in DIM_KEYS]
    if misplaced:
        example = ", ".join(f'"{k}":3' for k in misplaced[:3])
        raise ValueError(
            f"「{name}」的分数写在了顶层（{'、'.join(misplaced)}）。"
            f'分数必须放进 scores 字段：{{"name":"{name}","scores":{{{example}}}}}'
        )

    return [k for k in item if k not in ITEM_KEYS]


def assess(
    item,
    weights,
    preset_label,
    default_category=None,
    default_economy="normal",
    host_disposed=False,
    host_name="",
):
    unknown = validate_item(item)
    name = item.get("name") or "未命名物品"
    raw_scores = item.get("scores") or {}

    economy_key = item.get("economy") or default_economy or "normal"
    if economy_key not in ECONOMY_LEVELS:
        raise ValueError(f"未知经济档位 {economy_key}，可选 {', '.join(ECONOMY_LEVELS)}")
    econ = ECONOMY_LEVELS[economy_key]

    category_key = item.get("category") or default_category
    prior = CATEGORY_PRIORS.get(category_key, {}) if category_key else {}
    if category_key and not prior:
        raise ValueError(f"未知品类 {category_key}，可选 {', '.join(CATEGORY_PRIORS)}")
    prior_scores = prior.get("scores", {})

    scores = {}
    sources = {}
    for key in DIM_KEYS:
        value = raw_scores.get(key)
        if value is not None:
            sources[key] = "user"
        elif key in prior_scores:
            value = prior_scores[key]
            sources[key] = "inferred"
        else:
            value = 0
            sources[key] = "default"
        if not isinstance(value, (int, float)) or value < 0 or value > SCALE:
            raise ValueError(f"{name}：维度 {key} 的分数必须是 0-{SCALE}")
        scores[key] = value

    evidence = item.get("evidence") or {}
    flags = [f for f in (item.get("flags") or []) if f in FLAG_LABELS]
    for f in prior.get("flags", []):
        if f not in flags:
            flags.append(f)

    # 断舍离：时间轴是"现在"，「万一 / 总有一天会用」按 1 分计
    danshari = []

    # WTP 检验：今天愿意掏多少钱再买一个——愿意付的钱才是真实估价（对冲禀赋效应）
    wtp = item.get("wtp")
    if wtp is not None:
        try:
            wtp_price = float(wtp)
        except (TypeError, ValueError):
            raise ValueError(f"{name}：wtp（今天愿意再买的价格）必须是数字")
        scores["replace"] = (
            1 if wtp_price <= 0 else price_to_replace(wtp_price, economy_key)
        )
        sources["replace"] = "wtp"
        if not (evidence.get("replace") or "").strip():
            evidence = {
                **evidence,
                "replace": "一分钱也不愿意花" if wtp_price <= 0 else f"今天最多愿意花 {wtp_price:g} 元再买一个",
            }
        danshari.append(
            f"WTP 检验：今天{'一分钱也不愿意花' if wtp_price <= 0 else f'最多愿意花 {wtp_price:g} 元'}"
            f"再买一个 → 替代难度记 {scores['replace']} 分"
            "（愿意付的钱才是真实估价，无关当初花多少、也无关能卖多少）"
        )
    if (
        scores.get("usage", SCALE) <= 1
        and scores.get("future", SCALE) == 2
        and scores.get("sentiment", 0) <= 2
    ):
        scores["future"] = 1
        sources["future"] = "adjusted"
        danshari.append("「万一以后用得上」按 1 分计：总有一天永远不会来")

    # 附属件：主件已失去意义 → 服务对象没了，使用频率与未来需求清零
    host_desc = f"主件「{host_name}」已判处理" if host_name else "主件已不在"
    if host_disposed:
        for key in ("usage", "future"):
            if scores.get(key, 0) != 0:
                scores[key] = 0
                sources[key] = "adjusted"
        danshari.append(
            f"{host_desc}：配件失去服务对象，使用频率与未来需求按 0 计"
        )

    # 闲置折半：对现在的你已无用途时，功能状态与替代难度不再撑起保留分
    idle = (
        scores.get("usage", SCALE) <= HR_USAGE_LOW
        and scores.get("future", SCALE) <= HR_FUTURE_LOW
        and scores.get("sentiment", 0) <= IDLE_SENTIMENT_MAX
    )
    if idle:
        danshari.append(
            "闲置物品：功能状态与替代难度按半折计入——主轴是现在的你，不是物品还能用、值多少钱"
        )

    payload = {
        "target": name,
        "scale": SCALE,
        "dimensions": [
            {
                "name": DIM_NAMES[key],
                "weight": weights[key],
                "score": scores[key],
                "evidence": (evidence.get(key) or "").strip(),
            }
            for key in DIM_KEYS
        ],
    }
    base = engine.evaluate(payload, {"excellent": 70, "good": 55, "pass": 40})
    warnings = [w for w in base["warnings"] if "缺少证据" not in w]

    for key in DIM_KEYS:
        if sources[key] == "default":
            warnings.append(
                f"{name}：维度 {DIM_NAMES[key]} 未取得信息，按默认 {scores[key]} 处理，结论不可靠"
            )
        elif sources[key] == "inferred":
            warnings.append(
                f"{name}：维度 {DIM_NAMES[key]} 由品类基线推断为 {scores[key]}，确认后可修正"
            )
        elif not (evidence.get(key) or "").strip() and sources[key] != "wtp":
            warnings.append(f"{name}：维度 {DIM_NAMES[key]} 缺少证据")

    if unknown:
        warnings.append(f"{name}：字段 {'、'.join(unknown)} 未被识别，已忽略（分数要放在 scores 里）")
    if not raw_scores and not prior:
        warnings.append(
            f"{name}：既没有 scores 也没有 category，六维全部按默认 0 处理，结论不可靠——"
            "请补 scores 或指定品类"
        )
    if prior.get("dependent") and not (item.get("depends_on") or item.get("host_gone")):
        warnings.append(
            f"{name}：{prior.get('label', '这一品类')}通常是附属件——建议用 depends_on 指定主件，"
            "主件被处理时它会一并清零"
        )

    total = base["total"]
    if idle:
        total = 100 * sum(
            row["contribution"] * (IDLE_WEIGHT_SCALE if key in ("condition", "replace") else 1)
            for key, row in zip(DIM_KEYS, base["rows"])
        )

    idx, v_ov, a_ov, n_ov, reasons = apply_hard_rules(scores, flags, tier_index(total))
    # 后悔管理：摇摆阶梯。第 1 次摇摆只向"封存"移动（不回到保留），第 2 次起锁定
    # 强制结论（安全 / 过期 / 凭证）没有犹豫空间，不接受摇摆，也不必提示心理偏差
    swings = 0 if v_ov else int(item.get("swings") or 0)
    locked_swing = swings >= SWING_LOCK_AT
    if swings >= 1 and idx > SWING_SEAL_TIER:
        idx = SWING_SEAL_TIER
        if not locked_swing:
            reasons.append(
                "第 1 次摇摆：结论不回到「保留」，改为封存观察——"
                "给犹豫一个带期限的出口，不是妥协"
            )
    # 附属件的结论下限：主件都处理了，配件不该单独留下（情感够高时改为封存）
    if (
        host_disposed
        and not v_ov
        and idx < DEP_FLOOR_TIER
        and scores.get("sentiment", 0) < DEP_SENTIMENT_KEEP
    ):
        idx = DEP_FLOOR_TIER
        reasons.append(
            f"{host_desc}：配件不该单独留下，结论不低于建议流转"
            "——狄德罗效应的反面，主件走了，配套不该留下"
        )
    biases = [] if v_ov else bias_hints(scores, idx, evidence)
    verdict, action, next_step = TIERS[idx][1], TIERS[idx][2], TIERS[idx][3]
    if v_ov:
        verdict, action, next_step = v_ov, a_ov, n_ov
    elif idx == 3:
        next_step = econ["flow"]
    elif idx == 4 and scores.get("condition", 0) >= HR_CONDITION_GOOD and scores.get("sentiment", 0) <= 2:
        # 断舍离：完好的东西不该直接扔，让它去需要它的人手里
        next_step = "先问亲友或挂免费赠送，无人要再回收——完好的东西让它去被需要的地方"
    if not v_ov and idx >= 3 and prior.get("digitize"):
        next_step = "先拍照或扫描存档，再" + next_step

    months = REVIEW_MONTHS.get(idx)
    if locked_swing:
        months = months or SWING_LOCK_MONTHS
        next_step = (
            f"结论已锁定：装箱、写明封存日期与复评日期（{months} 个月后）——"
            "到期未取用即按原结论处理，不再重新权衡"
        )
        reasons.append(
            f"摇摆已达 {swings} 次：结论锁定，只重复执行封存动作，不再重算"
            "（后悔保险只买一次，不续保）"
        )
    reasons = danshari + reasons

    owner = (item.get("owner") or "self").strip()
    needs_consent = bool(owner) and owner not in ("self", "自己", "本人", "我")
    if needs_consent:
        reasons.append(f"归属他人（{owner}）：处置前需与对方协商，本结论仅供参考，不直接执行")

    rows = []
    for key, row in zip(DIM_KEYS, base["rows"]):
        rows.append(
            {
                "key": key,
                "name": DIM_NAMES[key],
                "weight": row["weight"],
                "score": row["score"],
                "points": row["contribution"]
                * 100
                * (IDLE_WEIGHT_SCALE if idle and key in ("condition", "replace") else 1),
                "evidence": row["evidence"],
                "source": sources[key],
            }
        )

    return {
        "name": name,
        "total": total,
        "verdict": verdict,
        "action": action,
        "next_step": next_step,
        "tier_index": idx,
        "rows": rows,
        "scores": scores,
        "flags": flags,
        "reasons": reasons,
        "biases": biases,
        "warnings": warnings,
        "notes": (item.get("notes") or "").strip(),
        "preset": preset_label,
        "category": category_key or "",
        "category_label": prior.get("label", ""),
        "category_hint": prior.get("hint", ""),
        "ask": list(prior.get("ask", [])),
        "economy": economy_key,
        "economy_label": econ["label"],
        "economy_hint": econ["hint"],
        "economy_preset": econ["preset"],
        "swings": swings,
        "locked_swing": locked_swing,
        "depends_on": (item.get("depends_on") or "").strip(),
        "host_gone": bool(item.get("host_gone")),
        "host_disposed": bool(host_disposed),
        "review_months": months,
        "review_date": add_months(date.today(), months).isoformat() if months else "",
        "over_capacity": False,
        "capacity_rank": None,
        "capacity_limit": None,
        "redundant": False,
        "owner": owner,
        "needs_consent": needs_consent,
        "locked": bool(v_ov),
    }


# ---------- 文本可视化 ----------

def bar(value, scale, width=10):
    filled = int(round(value / scale * width))
    return "█" * filled + "░" * (width - filled)


def pad(text, width=12):
    """按终端显示宽度补空格（中文按两个字符宽计）。"""
    used = sum(2 if ord(ch) > 127 else 1 for ch in text)
    return text + " " * max(0, width - used)


def render_text(results):
    out = []
    for r in results:
        out.append("=" * 58)
        out.append(f"物品：{r['name']}    权重方案：{r['preset']}")
        if r["category_label"]:
            out.append(f"品类：{r['category_label']}")
        out.append(f"经济档位：{r['economy_label']}")
        out.append(f"总分：{r['total']:.1f} / 100  [{bar(r['total'], 100, 30)}]")
        out.append(f"标尺：{TIER_MARKS}")
        out.append(f"结论：{r['verdict']}    处置：{r['action']}")
        out.append("-" * 58)
        for row in r["rows"]:
            tags = []
            if row["source"] == "inferred":
                tags.append("推断")
            elif row["source"] == "default":
                tags.append("默认")
            if not row["evidence"]:
                tags.append("待补依据")
            mark = f"  ({'、'.join(tags)})" if tags else ""
            out.append(
                f"{pad(row['name'])}{bar(row['score'], SCALE)} {row['score']}/{SCALE}"
                f"  权重 {row['weight']:.2f}  贡献 {row['points']:5.1f}{mark}"
            )
        if r["flags"]:
            out.append("-" * 58)
            out.append("标记：" + "、".join(FLAG_LABELS[f] for f in r["flags"]))
        out.append("-" * 58)
        out.append(f"下一步：{r['next_step']}")
        for reason in r["reasons"]:
            out.append(f"· {reason}")
        for bias in r.get("biases", []):
            out.append(f"心理偏差【{bias['name']}】{bias['text']}")
        if r["category_hint"]:
            out.append(f"品类提示：{r['category_hint']}")
        out.append(f"经济校准：{r['economy_hint']}")
        if r["over_capacity"]:
            out.append(
                f"容量：排第 {r['capacity_rank']} 位，超出上限 {r['capacity_limit']} 件 → 按处理路径执行"
            )
        if r["redundant"]:
            out.append("同类冗余：同用途只留一件，这件优先处理")
        if r["needs_consent"]:
            out.append(f"归属：{r['owner']} —— 处置前需与对方协商，结论仅供参考")
        if r.get("swings"):
            out.append(
                f"摇摆：{r['swings']} 次"
                + ("（已锁定，只执行不复盘）" if r["locked_swing"] else "（已给出口：封存观察）")
            )
        if r.get("review_date"):
            out.append(
                f"封存：{date.today().isoformat()} → 复评 {r['review_date']}"
                "（到期未取用即按原结论处理，不再重新权衡）"
            )
        if r["ask"]:
            out.append("建议确认：" + "、".join(DIM_NAMES[k] for k in r["ask"]))
        for w in r["warnings"]:
            out.append(f"! {w}")
        if r["notes"]:
            out.append(f"备注：{r['notes']}")
    out.append("=" * 58)

    if len(results) > 1:
        out.append("")
        out.append("处理优先级（分数越低越优先处理）：")
        for i, r in enumerate(sorted(results, key=lambda x: x["total"]), 1):
            mark = "  （超出容量）" if r["over_capacity"] else ""
            out.append(f"  {i}. {r['name']}  {r['total']:.1f}  → {r['verdict']} / {r['action']}{mark}")
    return "\n".join(out)


def render_markdown(results, preset_label):
    lines = ["# 物品去留决策报告", "", f"- 权重方案：{preset_label}", f"- 评估数量：{len(results)}", ""]
    if len(results) > 1:
        lines += ["## 处理优先级", "", "| # | 物品 | 总分 | 结论 | 处置路径 |", "|---|------|------|------|----------|"]
        for i, r in enumerate(sorted(results, key=lambda x: x["total"]), 1):
            lines.append(f"| {i} | {r['name']} | {r['total']:.1f} | {r['verdict']} | {r['action']} |")
        lines.append("")

    for r in results:
        lines += [f"## {r['name']}", ""]
        lines += [
            f"- 总分：**{r['total']:.1f} / 100**",
            f"- 结论：**{r['verdict']}**",
            f"- 处置路径：{r['action']}",
            f"- 下一步：{r['next_step']}",
        ]
        if r["category_label"]:
            lines.append(f"- 品类基线：{r['category_label']}")
        lines.append(f"- 经济档位：{r['economy_label']}（{r['economy_hint']}）")
        if r["over_capacity"]:
            lines.append(
                f"- 容量：排第 {r['capacity_rank']} 位，超出上限 {r['capacity_limit']} 件 → 按处理路径执行"
            )
        if r["redundant"]:
            lines.append("- 同类冗余：同用途只留一件，这件优先处理")
        if r["needs_consent"]:
            lines.append(f"- 归属他人：{r['owner']} —— 处置前需与对方协商，结论仅供参考")
        if r.get("swings"):
            lines.append(
                f"- 摇摆次数：{r['swings']}"
                + ("（已锁定，只执行不复盘）" if r["locked_swing"] else "（已给出口：封存观察）")
            )
        if r.get("review_date"):
            lines.append(
                f"- 封存 → 复评：{date.today().isoformat()} → {r['review_date']}"
                "（到期未取用即按原结论处理，不再重新权衡）"
            )
        lines += [
            "",
            "| 维度 | 权重 | 得分 | 贡献分 | 来源 | 依据 |",
            "|------|------|------|--------|------|------|",
        ]
        for row in r["rows"]:
            source = {
                "user": "用户",
                "inferred": "品类推断",
                "default": "默认",
                "adjusted": "断舍离校准",
                "wtp": "WTP 检验",
            }[row["source"]]
            lines.append(
                f"| {row['name']} | {row['weight']:.2f} | {row['score']}/{SCALE} "
                f"| {row['points']:.1f} | {source} | {row['evidence'] or '待补充'} |"
            )
        if r["category_hint"]:
            lines += ["", f"**品类提示**：{r['category_hint']}"]
        if r["ask"]:
            lines += ["", "**建议确认**：" + "、".join(DIM_NAMES[k] for k in r["ask"])]
        if r["flags"]:
            lines += ["", "**标记**：" + "、".join(FLAG_LABELS[f] for f in r["flags"])]
        if r["reasons"]:
            lines += ["", "**判定依据**："]
            lines += [f"- {x}" for x in r["reasons"]]
        if r.get("biases"):
            lines += ["", "**心理偏差提示**："]
            lines += [f"- **{b['name']}**：{b['text']}" for b in r["biases"]]
        if r["notes"]:
            lines += ["", f"**备注**：{r['notes']}"]
        if r["warnings"]:
            lines += ["", "> " + "；".join(r["warnings"])]
        lines.append("")
    return "\n".join(lines)


def render_html(results, preset_label):
    esc = html.escape
    cards = []
    colors = ["#16a34a", "#65a30d", "#ca8a04", "#ea580c", "#dc2626"]
    for r in results:
        color = colors[r["tier_index"]]
        rows = "\n".join(
            f"""<tr>
<td class="dim">{esc(row['name'])}</td>
<td>{row['weight']:.2f}</td>
<td>{row['score']}/{SCALE}</td>
<td class="barcell"><div class="bar"><span style="width:{row['score'] / SCALE * 100:.0f}%"></span></div></td>
<td>{row['points']:.1f}</td>
<td class="ev">{esc(row['evidence']) or '<em>待补充</em>'}</td>
</tr>"""
            for row in r["rows"]
        )
        flags = (
            f'<p class="flags">标记：{esc("、".join(FLAG_LABELS[f] for f in r["flags"]))}</p>'
            if r["flags"] else ""
        )
        reasons = (
            "<ul class='reasons'>" + "".join(f"<li>{esc(x)}</li>" for x in r["reasons"]) + "</ul>"
            if r["reasons"] else ""
        )
        bias = (
            "<ul class='bias'>"
            + "".join(
                f"<li><b>{esc(b['name'])}</b>：{esc(b['text'])}</li>" for b in r.get("biases", [])
            )
            + "</ul>"
            if r.get("biases") else ""
        )
        notes = f"<p class='notes'>备注：{esc(r['notes'])}</p>" if r["notes"] else ""
        warns = (
            "<ul class='warn'>" + "".join(f"<li>{esc(w)}</li>" for w in r["warnings"]) + "</ul>"
            if r["warnings"] else ""
        )
        econ = f"<p class='notes'><b>经济档位</b>：{esc(r['economy_label'])}　{esc(r['economy_hint'])}</p>"
        cap = (
            f"<p class='flagsline'>容量：排第 {r['capacity_rank']} 位，超出上限 {r['capacity_limit']} 件 → 按处理路径执行</p>"
            if r["over_capacity"] else ""
        )
        extra = ""
        if r["redundant"]:
            extra += "<p class='flagsline'>同类冗余：同用途只留一件，这件优先处理</p>"
        if r["needs_consent"]:
            extra += f"<p class='flagsline'>归属他人：{esc(r['owner'])} —— 处置前需与对方协商，结论仅供参考</p>"
        if r.get("swings"):
            extra += (
                f"<p class='flagsline'>摇摆 {r['swings']} 次"
                + ("（已锁定，只执行不复盘）" if r["locked_swing"] else "（已给出口：封存观察）")
                + "</p>"
            )
        if r.get("review_date"):
            extra += (
                f"<p class='flagsline'>封存 {date.today().isoformat()} → 复评 {r['review_date']}"
                "：到期未取用即按原结论处理，不再重新权衡</p>"
            )
        hint = (
            f"<p class='notes'><b>品类基线</b>：{esc(r['category_label'])}　{esc(r['category_hint'])}</p>"
            if r["category_label"] else ""
        )
        ask = (
            f"<p class='ask'>建议确认：" + esc("、".join(DIM_NAMES[k] for k in r["ask"])) + "</p>"
            if r["ask"] else ""
        )
        cards.append(f"""
<section class="card">
  <header>
    <h2>{esc(r['name'])}</h2>
    <span class="badge" style="background:{color}">{esc(r['verdict'])}</span>
  </header>
  <div class="score">
    <div class="gauge"><span style="width:{r['total']:.1f}%;background:{color}"></span></div>
    <div class="total"><b>{r['total']:.1f}</b> / 100</div>
  </div>
  <p class="scale">{esc(TIER_MARKS)}</p>
  <p class="action"><b>处置路径</b>：{esc(r['action'])}<br><b>下一步</b>：{esc(r['next_step'])}</p>
  {flags}{hint}{econ}{cap}{extra}
  <table>
    <thead><tr><th>维度</th><th>权重</th><th>得分</th><th></th><th>贡献分</th><th>证据</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {reasons}{bias}{ask}{warns}{notes}
</section>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>物品去留决策报告</title>
<style>
body{{font-family:"Microsoft YaHei",system-ui,sans-serif;background:#f5f5f4;color:#1c1917;margin:0;padding:32px}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#78716c;margin-bottom:24px}}
.card{{background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
header{{display:flex;align-items:center;justify-content:space-between}}
h2{{font-size:18px;margin:0}} .badge{{color:#fff;padding:4px 12px;border-radius:999px;font-size:13px}}
.gauge{{flex:1;height:14px;background:#e7e5e4;border-radius:999px;overflow:hidden}}
.gauge span{{display:block;height:100%}}
.score{{display:flex;align-items:center;gap:12px;margin:14px 0 4px}}
.total{{font-size:14px;min-width:80px;text-align:right}}
.scale{{color:#a8a29e;font-size:12px;margin:0 0 10px}}
.action{{background:#fafaf9;border-left:3px solid #d6d3d1;padding:10px 12px;font-size:14px}}
table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px}}
th,td{{padding:6px 8px;border-bottom:1px solid #f0efee;text-align:left}}
.barcell{{width:120px}} .bar{{background:#e7e5e4;height:8px;border-radius:4px;overflow:hidden}}
.bar span{{display:block;height:100%;background:#0d9488}}
.ev{{color:#57534e}} .reasons{{color:#b45309;font-size:13px}}
.warn{{color:#b45309;font-size:12px;margin:8px 0 0;padding-left:18px}}
.bias{{background:#f5f3ff;border-left:3px solid #7c3aed;color:#5b21b6;font-size:12px;
margin:10px 0 0;padding:8px 12px 8px 28px;border-radius:0 6px 6px 0}}
.flags{{color:#b91c1c;font-size:13px}} .notes{{color:#57534e;font-size:13px}}
</style></head><body>
<h1>物品去留决策报告</h1>
<p class="sub">权重方案：{esc(preset_label)} · 共 {len(results)} 件</p>
{''.join(cards)}
</body></html>"""


# ---------- 分组容量与同类冗余 ----------

def parse_capacity(spec):
    """支持 3（全局上限）或 clothing:10,book:20（按品类分别设限）。"""
    spec = spec.strip().replace("，", ",")
    if spec.isdigit():
        return {"*": int(spec)}
    limits = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        pair = re.split(r"[:：]", part, maxsplit=1)
        if len(pair) != 2:
            raise ValueError(f"容量片段 {part!r} 应为 品类:件数，或纯数字表示全局上限")
        try:
            limits[pair[0].strip() or "*"] = int(pair[1])
        except ValueError:
            raise ValueError(f"容量 {pair[1]!r} 不是整数")
    return limits


def restyle(result, idx, reason):
    """重设结论档位（用于同类冗余等后置调整）。"""
    result["tier_index"] = idx
    result["verdict"], result["action"], result["next_step"] = TIERS[idx][1], TIERS[idx][2], TIERS[idx][3]
    if idx == 3:
        result["next_step"] = ECONOMY_LEVELS[result["economy"]]["flow"]
    result["reasons"] = result["reasons"] + [reason]


def apply_dependency(items, results, weights, preset_label, default_category, default_economy):
    """附属件联动：主件被判处理时，只服务于它的配件价值随之清零（狄德罗效应的反面）。"""
    index = {r["name"]: r for r in results}
    for position, item in enumerate(items):
        host_name = (item.get("depends_on") or "").strip()
        gone = bool(item.get("host_gone"))
        if not host_name and not gone:
            continue
        host = index.get(host_name)
        disposed = gone or (host is not None and host["tier_index"] >= DEP_HOST_TIER)
        if host is None and not gone:
            results[position]["warnings"].append(
                f"{results[position]['name']}：主件「{host_name}」不在本批，未联动——"
                '若主件已不在，请加 "host_gone": true'
            )
        if not disposed:
            continue
        results[position] = assess(
            item,
            weights,
            preset_label,
            default_category,
            default_economy,
            True,
            host_name,
        )


def assess_all(items, weights, preset_label, default_category=None, default_economy="normal"):
    """评估一批物品：先逐件打分，再做附属件联动，最后交给分组规则。"""
    results = [
        assess(item, weights, preset_label, default_category, default_economy) for item in items
    ]
    apply_dependency(items, results, weights, preset_label, default_category, default_economy)
    return results


def apply_groups(results, limits):
    """按品类分组：标记超出容量的件，并把同类冗余件拉到流转档（同用途只留一件）。"""
    groups = {}
    for r in results:
        groups.setdefault(r["category"] or "*", []).append(r)

    for key, group in groups.items():
        ordered = sorted(group, key=lambda x: x["total"], reverse=True)
        limit = limits.get(key)
        if limit is None and key != "*":
            limit = limits.get("*")
        for rank, r in enumerate(ordered, 1):
            r["capacity_rank"] = rank
            if limit is not None:
                r["capacity_limit"] = limit
                r["over_capacity"] = rank > limit
                if r["over_capacity"]:
                    r["review_months"] = 1
                    r["review_date"] = add_months(date.today(), 1).isoformat()
            if r["locked"] or r["locked_swing"] or r["needs_consent"]:
                continue
            redundant = (
                rank >= 2
                and r["scores"].get("usage", SCALE) <= HR_USAGE_LOW + 1
                and r["scores"].get("replace", SCALE) <= REDUNDANT_REPLACE_MAX
                and r["scores"].get("sentiment", 0) <= HR_SENTIMENT_PROTECT
            )
            if redundant and (limit is None or rank > limit):
                r["redundant"] = True
                if r["tier_index"] < 3:
                    restyle(
                        r,
                        3,
                        f"同类第 {rank} 件且容易再获得：同用途只留一件，这件优先处理",
                    )


# ---------- 封存档案（闭环） ----------

REVIEW_MONTHS = {1: 6, 2: 3}  # 结论档位 → 复评月数


def add_months(day, months):
    year = day.year + (day.month - 1 + months) // 12
    month = (day.month - 1 + months) % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def append_log(path, results):
    today = date.today()
    log_path = Path(path)
    entries = []
    if log_path.exists():
        try:
            entries = json.loads(log_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            entries = []
    added = 0
    for r in results:
        months = r.get("review_months") or REVIEW_MONTHS.get(r["tier_index"])
        if not months:
            continue
        entries.append(
            {
                "name": r["name"],
                "category": r["category"],
                "total": round(r["total"], 1),
                "verdict": r["verdict"],
                "action": r["action"],
                "seal_date": today.isoformat(),
                "review_date": r.get("review_date") or add_months(today, months).isoformat(),
                "review_months": months,
                "swings": r.get("swings", 0),
                "locked": bool(r.get("locked_swing")),
            }
        )
        added += 1
    log_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return added, len(entries)


def review_log(path):
    log_path = Path(path)
    if not log_path.exists():
        print(f"档案不存在：{path}")
        return 0
    entries = json.loads(log_path.read_text(encoding="utf-8-sig"))
    today = date.today().isoformat()
    due = [e for e in entries if e["review_date"] <= today]
    pending = [e for e in entries if e["review_date"] > today]
    print(f"封存档案：{path}   共 {len(entries)} 条，到期 {len(due)} 条")
    if due:
        print("\n需复评（到期未取用即按原结论处理——这是新事实，不是重新权衡）：")
        for e in due:
            over = (date.fromisoformat(today) - date.fromisoformat(e["review_date"])).days
            tag = "（已锁定）" if e.get("locked") else ""
            print(
                f"  - {e['name']}  {e['total']} 分  {e['verdict']} / {e['action']}{tag}"
                f"  封存于 {e['seal_date']}，应复评 {e['review_date']}（逾期 {over} 天）"
            )
        print("\n  执行动作：打开箱子看一眼 → 取用过就重新评分；没取用过，直接按上面的结论处理。")
    if pending:
        print("\n未到期：")
        for e in pending:
            print(f"  - {e['name']}  复评日期 {e['review_date']}  {e['verdict']}")
        print("\n  未到期的不提前处理，也不提前讨论——期限是这份保险生效的条件。")
    return len(due)


# ---------- 输入 ----------

def load_items(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ValueError(f"找不到输入文件 {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} 不是合法 JSON（{e}）")

    if isinstance(data, dict) and "items" in data:
        items = data["items"]
    elif isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        raise ValueError("输入必须是对象、数组或包含 items 的对象")
    if not items:
        raise ValueError("输入中没有任何物品")
    return items


def interactive_collect():
    print("荷丛物品去留决策 —— 交互录入（物品名留空即结束）")
    items = []
    while True:
        name = input("\n物品名称：").strip()
        if not name:
            break
        scores = {}
        for d in DIMENSIONS:
            print(f"\n【{d['name']}】{d['question']}")
            for value, label in d["options"]:
                print(f"  {value}. {label}")
            while True:
                raw = input(f"选择 0-{SCALE}：").strip()
                if raw.isdigit() and 0 <= int(raw) <= SCALE:
                    scores[d["key"]] = int(raw)
                    break
                print(f"  请输入 0-{SCALE} 的数字")
        print("\n特殊情况（可多选，直接回车跳过）：")
        for i, (_key, desc) in enumerate(FLAGS, 1):
            print(f"  {i}. {desc}")
        raw = input("序号（如 13）：").strip()
        flags = [
            FLAGS[int(ch) - 1][0]
            for ch in raw
            if ch.isdigit() and 1 <= int(ch) <= len(FLAGS)
        ]
        items.append({"name": name, "scores": scores, "flags": flags})
    if not items:
        raise ValueError("未录入任何物品")
    return items


def main():
    parser = argparse.ArgumentParser(description="荷丛 Lightener 物品去留决策系统")
    parser.add_argument("--input", help="物品 JSON 文件")
    parser.add_argument("--interactive", action="store_true", help="交互问答录入")
    parser.add_argument("--preset", default="balanced", help="权重方案")
    parser.add_argument("--weights", help="自定义权重 JSON，如 '{\"usage\":0.35}'")
    parser.add_argument("--out", help="Markdown 报告输出路径")
    parser.add_argument("--html", dest="html_out", help="HTML 报告输出路径")
    parser.add_argument("--json", dest="json_out", help="结构化结果输出路径")
    parser.add_argument("--category", help="品类基线 key，未提供分数的维度按该品类推断")
    parser.add_argument("--economy", help="经济档位：tight / normal / comfortable，默认 normal")
    parser.add_argument("--capacity", help="容量上限（7·5·1）：3 表示全局；clothing:10,book:20 按品类分别设限")
    parser.add_argument("--no-redundancy", action="store_true", help="关闭同类冗余判定（同用途只留一件）")
    parser.add_argument("--log", dest="log_file", help="把需复评的物品写入封存档案（JSON）")
    parser.add_argument("--review", dest="review_file", help="读取封存档案，列出到期需复评的物品")
    parser.add_argument("--price", type=float, help="重新买一个要多少钱，配合 --economy 换算替代难度分")
    parser.add_argument("--list-presets", action="store_true", help="列出权重方案")
    parser.add_argument("--list-categories", action="store_true", help="列出品类基线")
    parser.add_argument("--list-economy", action="store_true", help="列出经济档位与价格锚点")
    args = parser.parse_args()

    if args.price is not None:
        economy = args.economy or "normal"
        try:
            score = price_to_replace(args.price, economy)
        except ValueError as e:
            print(f"错误：{e}", file=sys.stderr)
            return 2
        level = ECONOMY_LEVELS[economy]
        thresholds = " / ".join(
            f"≥{t} 元 → {s} 分" for t, s in level["anchors"]
        )
        print(f"重新买一个约 {args.price:g} 元，经济档位「{level['label']}」→ 替代难度建议 {score} 分")
        print(f"该档位价格锚点：{thresholds}；低于最低锚点记 1 分")
        verdict = {
            5: "弄不到（绝版 / 唯一），构成强保留理由",
            4: "难再获得，构成保留理由",
            3: "得专门跑一趟或中等花费，弱保留理由",
            2: "随手能买到，不构成保留理由",
            1: "随处都有，不构成保留理由",
            0: "家里还有好几个，不构成保留理由",
        }[score]
        print(f"WTP 判定：{verdict}")
        print("用法：这一问的答案是数字才作数——说不出数字、答「看情况」，按不会买处理。")
        return 0

    if args.list_economy:
        for key, level in ECONOMY_LEVELS.items():
            thresholds = "  ".join(f"≥{t}→{s}分" for t, s in level["anchors"])
            print(f"{key:<12} {level['label']:<6} 价格锚点 {thresholds}")
            print(f"{'':<12} 推荐权重 {level['preset']}　处置偏好：{level['flow']}")
        return 0

    if args.list_presets:
        for key, weights in PRESETS.items():
            detail = "  ".join(f"{DIM_NAMES[k]}{v:g}" for k, v in weights.items())
            print(f"{key:<12} {PRESET_LABELS[key]:<10} {detail}")
        return 0

    if args.list_categories:
        for key, prior in CATEGORY_PRIORS.items():
            scores = "  ".join(f"{DIM_NAMES[k]}{v}" for k, v in prior["scores"].items())
            ask = "、".join(DIM_NAMES[k] for k in prior.get("ask", [])) or "无需追问"
            print(f"{key:<12} {prior['label']:<16} {scores}\n{'':<12} 需确认：{ask}")
        return 0

    if args.review_file:
        review_log(args.review_file)
        return 0

    if not args.input and not args.interactive:
        parser.error("需要 --input、--interactive、--list-presets 或 --list-categories")
        return 2

    limits = {}
    if args.capacity:
        try:
            limits = parse_capacity(args.capacity)
        except ValueError as e:
            print(f"错误：{e}", file=sys.stderr)
            return 2
        if any(v < 1 for v in limits.values()):
            print("错误：容量上限必须是正整数", file=sys.stderr)
            return 2

    warnings = []
    try:
        weights = resolve_weights(args.preset, args.weights, warnings)
        items = interactive_collect() if args.interactive else load_items(args.input)
        results = assess_all(items, weights, args.preset, args.category, args.economy or "normal")
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    if not args.no_redundancy or limits:
        apply_groups(results, limits)

    if len(results) >= 5 and not limits:
        warnings.append(
            f"批量评估 {len(results)} 件却没有设定容量上限：帕金森定律——物品会膨胀到填满可用空间。"
            "建议用 --capacity 先定容器再选物品，否则清完的位置会被剩下的东西重新填满"
        )

    report = render_text(results)
    print(report)

    if args.out:
        Path(args.out).write_text(render_markdown(results, args.preset), encoding="utf-8")
        print(f"\nMarkdown 报告已写入 {args.out}")
    if args.html_out:
        Path(args.html_out).write_text(render_html(results, args.preset), encoding="utf-8")
        print(f"HTML 报告已写入 {args.html_out}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结构化结果已写入 {args.json_out}")

    if args.log_file:
        added, total_entries = append_log(args.log_file, results)
        print(f"封存档案已更新 {args.log_file}：新增 {added} 条，共 {total_entries} 条")

    for w in warnings:
        print(f"提示：{w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
