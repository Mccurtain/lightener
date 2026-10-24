<div align="center">

# Lightener
**English** | [简体中文](README.md)

<img alt="License" src="https://img.shields.io/badge/License-MIT-263146?style=flat-square">

> Still agonizing over "should I keep this or throw it away"?
>
> Still oscillating between tossing it and keeping it?
>
> Lightener turns keep-or-toss from an emotional debate into a deterministic calculation: score an item on six dimensions, map the weighted total to a concrete verdict, and give you the next action to take.
>
> The output is never "you decide" — it is **one recommendation + one disposal path + one executable next step**.


</div>

## What it does

- Six dimensions (`usage` / `future` / `condition` / `replace` / `sentiment` / `space`), each 0–5, weighted into a 0–100 score
- Five verdict tiers, from *Keep* down to *Discard*, each with a disposal path and a next step you can finish this week
- 14 hard rules that outrank the score (safety hazards, expired goods, irreplaceable documents, "someday" never comes, sentiment ≥ 4 is never discarded…)
- Behavioural-economics calibration: names endowment effect, sunk cost and loss aversion when they show up, and answers each with one counter-question
- Regret management: a single one-way exit to *seal & review* with a fixed date — insurance against future regret, sold once, never renewed
- Batch mode with capacity limits (7·5·1), duplicate pruning, economy calibration, and a seal/review archive

## Why the name

- **荷丛 (Hécóng)**: from the lotus that rises clean out of muddy water. The skill exists to keep the space around you clean — the name is both the lotus cluster and a pointer to *what to follow*.
- **Lightener**: a pun on *lighten* — both "reduce the load" and "see clearly which item actually earns its place".

## What it builds on

1. **断捨離 (danshari)** — the primary reference, providing the methodological skeleton.
2. **Behavioural economics** — sets the decision style:
   - **Endowment effect** (Kahneman–Knetsch–Thaler): once owned, value is overestimated.
   - **Sunk cost fallacy** (Arkes & Blumer): what it cost back then must not shape today's decision.
   - **Loss aversion** (Kahneman & Tversky): the pain of losing is roughly twice the pleasure of gaining.
3. **Decision psychology** — where *seal & review* comes from:
   - **Anticipated regret** (Zeelenberg), **regret aversion** (Loomes & Sugden) and the **action effect** (Kahneman & Tversky) together imply that sealing must move **one way only, be offered once, and carry a hard deadline**

The philosophy behind it comes from Erich Fromm's *To Have or To Be?*: decluttering is not about tidiness — it moves your self-definition from "what I own" back to "what I do".

## When to use it

- "Should I throw this away?" / "Is this still worth keeping?"
- Decluttering, seasonal cleanouts, moving, clearing out storage
- Dozens of items at once that need a processing order
- Stuck on "I just can't let it go" and needing the reasons unpacked

> **Scope**: household belongings only. It does not replace legal, medical or financial advice. For documents, prescription drugs or hazardous waste, follow local regulations and professional channels.

## Quick start

> All commands below are run from inside the skill directory (`lightener/`).

### Conversation (recommended)

Describe the item and its situation; the skill translates facts into scores:

> It's the box my old phone came in. I sold the phone, and the box has been sitting in the drawer ever since.

When information is missing it asks only for **facts** (when you last used it, whether it still works, where it came from, where it sits) — never for a self-rated score of "value" or "necessity".

### CLI

Prepare `items.json` (scores **must** live inside `scores` — putting them at the top level is an error):

```json
{
  "items": [
    {
      "name": "Old trekking poles",
      "category": "hobby",
      "scores": {"usage": 1, "future": 2, "condition": 4, "replace": 3, "sentiment": 2, "space": 3},
      "evidence": {"usage": "used once last summer"},
      "flags": []
    }
  ]
}
```

Run:

```bash
python scripts/assess_item.py --input items.json --out report.md --html report.html
```

Output comes as text / Markdown / HTML, with the total, verdict, disposal path, next step and the dimensions that mattered most; when endowment effect, sunk cost or loss aversion is detected, a behavioural-bias note is printed too.

Interactive entry is available as well:

```bash
python scripts/assess_item.py --interactive
```

## Common commands

| Task | Command |
|---|---|
| Assess single item or batch | `python scripts/assess_item.py --input items.json --out report.md` |
| Interactive entry | `python scripts/assess_item.py --interactive` |
| Switch preference profile | `--preset minimalist \| sentimental \| space` (default `balanced`) |
| Custom weights | `--weights sentiment=0.05,usage=0.35` (unspecified dimensions keep the profile value) |
| Batch capacity | `--capacity "book:10,clothing:20,cable:3"` (7·5·1; over-limit items get processed) |
| Disable duplicate pruning | `--no-redundancy` |
| Seal archive | `--log archive.json` to write / `--review archive.json` to list items due for review |
| Price → replaceability | `--price 200 --economy tight` |
| List options | `--list-presets` / `--list-categories` / `--list-economy` |

Item fields: `name` (required), `scores`, `category`, `evidence`, `flags` (`safety` / `expired` / `irreparable` / `document`), `owner`, `economy`, `swings`, `wtp`, `depends_on`, `host_gone`.

> Bad input never dumps a traceback: the script points at the exact line and column and shows the correct shape.
> When in doubt, see `references/faq.md` (20 FAQs + an anti-pattern list).

## Worked example: from one sentence to a verdict

**What the user said**:

> It's the box my old phone came in. I sold the phone, and the box has been sitting in the drawer ever since — there's no room for it.

**Extracting the dimensions**: the `phone_box` priors are `0 1 4 1 1 4` (usage / future / condition / replace / sentiment / space); the host item is gone, so usage and future drop to 0 and the item is flagged `host_gone`.

**`items.json`**:

```json
{
  "items": [
    {
      "name": "Old phone box",
      "category": "phone_box",
      "host_gone": true,
      "scores": {"usage": 0, "future": 0, "condition": 4, "replace": 1, "sentiment": 1, "space": 4},
      "evidence": {"usage": "phone was sold, box untouched for six months", "space": "one drawer slot"}
    }
  ]
}
```

**Command**:

```bash
python scripts/assess_item.py --input items.json --out report.md --html report.html
```

**Report excerpt** (real output — report text is currently Chinese):

```text
总分：18.5 / 100  [██████░░░░░░░░░░░░░░░░░░░░░░░░]
标尺：0 丢弃 ─ 25 流转 ─ 40 暂存 ─ 55 降级 ─ 70 保留 ─ 100
结论：建议丢弃    处置：丢弃 / 回收
下一步：先问亲友或挂免费赠送，无人要再回收——完好的东西让它去被需要的地方
· 主件已不在：配件失去服务对象，使用频率与未来需求按 0 计
· 闲置物品：功能状态与替代难度按半折计入——主轴是现在的你，不是物品还能用、值多少钱
```

**What to tell the user**: the total, the verdict, the disposal path and the next step, plus the 1–2 dimensions that drove it (here: usage 0 and the host item already gone).

## What errors look like

```text
$ python scripts/assess_item.py --input items.json
错误：items.json 不是合法 JSON：第 3 行第 44 列 Expecting property name enclosed in double quotes。
常见原因：用了中文引号「」“”、字段末尾多了逗号、或把注释写进了 JSON
```

```text
$ python scripts/assess_item.py --input items.json
错误：「Old trekking poles」的分数写在了顶层（usage）。分数必须放进 scores 字段：
{"name":"Old trekking poles","scores":{"usage":3}}
```

```text
! Old phone：flags 里的 expiredd 不是已知标记，已忽略（可选：safety、expired、irreparable、document）
```

> CLI messages are currently Chinese. The shape is what matters: line/column for JSON errors, the correct shape for schema errors, and a warning (never silent failure) for unrecognised values.

## The six dimensions

All dimensions are **0–5, higher means keep**:

| Dimension | Key | Default weight | 5 means |
|---|---|---|---|
| Usage frequency | `usage` | 0.25 | used several times a week or daily |
| Future need | `future` | 0.20 | already scheduled, definitely needed |
| Condition | `condition` | 0.15 | as-new and fully functional |
| Replaceability | `replace` | 0.15 | unobtainable (discontinued, unique, custom) |
| Sentiment | `sentiment` | 0.15 | tied to an important person or moment |
| Space friendliness | `space` | 0.10 | almost no space once stored |

Verdict tiers after weighting:

| Score | Verdict | Disposal path |
|---|---|---|
| ≥ 70 | Keep | keep using it |
| 55–69 | Keep (watch) | downgrade storage |
| 40–54 | Hold for review | seal, dispose after 3–6 months untouched |
| 25–39 | Pass it on | gift / resell / donate |
| < 25 | Discard | discard / recycle |

14 hard rules outrank the total score (safety hazards handled immediately, documents force-kept, "someday" counts as never, sentiment ≥ 4 is never discarded…) and are applied automatically by the script — see `SKILL.md`.

## Repo layout

```
lightener/
├── SKILL.md                 # skill body: rubric, category priors, hard rules, workflow
├── README.md                # Chinese documentation (authoritative)
├── README_EN.md             # this file
├── LICENSE                  # MIT
├── CONTRIBUTING.md          # contributing: all PRs go to the `pending` branch
├── scripts/
│   ├── assess_item.py       # main script: scoring, hard rules, tiers, report rendering
│   ├── evaluate.py          # weighted-summary engine (reused by the main script)
│   ├── build_form.py        # maintainer: export assets/rules.json and sync the form
│   ├── calibrate.py         # maintainer: 30-sample regression gate
│   └── calibration_samples.json
├── references/              # deep docs, loaded on demand
│   ├── advanced.md          # batch mode / economy tiers / seal archive / full commands / maintainer section
│   ├── item-rubric.md       # full 0–5 definitions and edge cases
│   ├── category-priors.md   # inferring dimensions from a single sentence
│   ├── evaluation-workflow.md # answer→score mapping, JSON schema, anti-oscillation scripts
│   ├── faq.md               # 20 FAQs + anti-pattern list (user follow-ups / confusing errors)
│   └── calibration.md       # calibration samples and regression gate
├── assets/
│   ├── assessment-form.html # web assessment form
│   ├── report-template.md   # verdict output template
│   └── rules.json           # generated, do not edit by hand
└── .github/                 # CI, PR / Issue templates
```

Daily use only needs `assess_item.py`; the `references/` docs are loaded on demand — no need to read them up front.

**The authoritative documentation is in Chinese** (`SKILL.md` and `references/`). This file is a summary — it deliberately omits rule details so the two cannot drift apart.

## Contributing

All PRs target the `pending` branch (not `main`); the maintainer squash-merges after review. Full process, local checks and calibration-sample format: see [CONTRIBUTING.md](CONTRIBUTING.md).

Before opening a PR, run:

```bash
python scripts/build_form.py --check   
python scripts/calibrate.py           
python -m compileall scripts
```

Calibration details: `references/calibration.md`; advanced usage and packaging: `references/advanced.md`.

## License

MIT — see `LICENSE`.

## Disclaimer

Decision support only. It does not replace legal, medical or financial judgement; for documents, prescription drugs or hazardous waste, follow local regulations and professional channels.

---
Questions and suggestions are welcome as Issues or PRs.
