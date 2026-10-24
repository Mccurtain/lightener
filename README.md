<div align="center">

# 荷丛（Lightener）
<img alt="许可证" src="https://img.shields.io/badge/License-MIT-263146?style=flat-square">

> 你是否还在为“这个东西该不该扔”耗费心神？
>
> 你是否在扔与不扔来回徘徊？
>
> 荷丛SKILL，把"扔还是留"从情绪化纠结变成确定性计算：多维度给物品量化打分，映射到明确的处置建议，并给出下一步动作。
>
> 结果不是"你自己看着办"，而是**一个建议 + 一条处置路径 + 一个可执行动作**。


</div>

## 立意
**为什么叫「荷丛 / Lightener」**

- **荷丛**：取荷花“出淤泥而不染”的洁净，荷丛的目的是维护个人身边空间整洁。荷丛，既为荷丛，也为指明何从。
- **Lightener**：取 *lighten* 的双关 —— 既为减负，也为明辨哪件真正有用。

**项目基于什么思想**
1. **断舍离** —— 项目最主要的参考思想，提供方法论骨架。
3. **行为经济学** —— 决定决策风格：
   - **禀赋效应**（Kahneman–Knetsch–Thaler）：一旦拥有就高估价值。
   - **沉没成本谬误**（Arkes & Blumer）：当初花的钱不该影响现在的决定。
   - **损失厌恶**（Kahneman & Tversky）：失去的痛约为得到的两倍。
4. **决策心理学** —— 推出 "封存观察" 的设计：
   - 用**预期性后悔**（Zeelenberg）、**后悔厌恶**（Loomes & Sugden）、**作为效应**（Kahneman & Tversky）推导出封存必须**单向移动、只给一次、期限写死**


## 什么时候用它

- "这个东西要不要扔？""留着还有用吗？"
- 断舍离、换季清理、搬家取舍、储物间清仓
- 一次要处理几十件，需要排出优先级
- 卡在"舍不得"上，需要有人把理由拆开给你看

> **边界**：只管生活物品的取舍，不替代法律、医疗、财务等专业判断；涉及证件、处方药、危险废弃物时请遵循当地法规与专业渠道。


## 快速上手

> 以下命令均在技能目录（`lightener/`）下执行。

### 对话（推荐）

直接说物品和它的情况，技能负责把事实翻译成分数：

> 一个旧手机的包装盒，手机已经卖掉了，盒子一直在抽屉里。

需要补充信息时它只会问**事实**（上次什么时候用、还能不能用、从哪来的、放哪儿），不会让你给"价值""必要性"打分。

### 命令行

准备 `items.json`（分数**必须嵌在 `scores` 里**，写在顶层会报错）：

```json
{
  "items": [
    {
      "name": "旧登山杖",
      "category": "hobby",
      "scores": {"usage": 1, "future": 2, "condition": 4, "replace": 3, "sentiment": 2, "space": 3},
      "evidence": {"usage": "去年夏天用过一次"},
      "flags": []
    }
  ]
}
```

运行：

```bash
python scripts/assess_item.py --input items.json --out report.md --html report.html
```

输出文本 / Markdown / HTML 三种报告，含总分、结论、处置路径、下一步动作、影响最大的维度，命中禀赋效应 / 沉没成本 / 损失厌恶时还会打出心理偏差提示。

也可以交互录入：

```bash
python scripts/assess_item.py --interactive
```

## 常用命令

| 场景 | 命令 |
|---|---|
| 单件 / 批量评估 | `python scripts/assess_item.py --input items.json --out report.md` |
| 交互录入 | `python scripts/assess_item.py --interactive` |
| 换取舍偏好 | `--preset minimalist \| sentimental \| space`（默认 `balanced`） |
| 自定义权重 | `--weights sentiment=0.05,usage=0.35`（未指定的维度沿用方案值） |
| 批量定容量 | `--capacity "book:10,clothing:20,cable:3"`（7·5·1，组内超出限额即处理） |
| 关闭同类冗余 | `--no-redundancy` |
| 封存档案 | `--log archive.json` 写入 / `--review archive.json` 列出到期需复评 |
| 价格换算替代难度 | `--price 200 --economy tight` |
| 查询可选项 | `--list-presets` / `--list-categories` / `--list-economy` |

物品 JSON 支持的字段：`name`（必填）、`scores`、`category`、`evidence`、`flags`（`safety` / `expired` / `irreparable` / `document`）、`owner`、`economy`、`swings`、`wtp`、`depends_on`、`host_gone`。

> 输入写错不会甩 traceback：脚本会把问题指到第几行第几列，并给出正确写法。
> 拿不准就看 `references/faq.md`（20 条 FAQ + 反模式清单）。

## 完整示例：从一句话到结论

**用户原话**：

> 一个旧手机的包装盒，手机已经卖掉了，盒子一直在抽屉里，没地方放。

**抽维度**：`phone_box` 品类基线 `0 1 4 1 1 4`（使用 / 未来 / 功能 / 替代 / 情感 / 空间），主件已不在 → 使用频率与未来需求按 0 计，标 `host_gone`。

**`items.json`**：

```json
{
  "items": [
    {
      "name": "旧手机包装盒",
      "category": "phone_box",
      "host_gone": true,
      "scores": {"usage": 0, "future": 0, "condition": 4, "replace": 1, "sentiment": 1, "space": 4},
      "evidence": {"usage": "手机已转卖，盒子半年没动过", "space": "抽屉一格"}
    }
  ]
}
```

**命令**：

```bash
python scripts/assess_item.py --input items.json --out report.md --html report.html
```

**报告节选**：

```text
物品：旧手机包装盒    权重方案：balanced    品类：手机 / 数码包装盒
总分：18.5 / 100  [██████░░░░░░░░░░░░░░░░░░░░░░░░]
标尺：0 丢弃 ─ 25 流转 ─ 40 暂存 ─ 55 降级 ─ 70 保留 ─ 100
结论：建议丢弃    处置：丢弃 / 回收
下一步：先问亲友或挂免费赠送，无人要再回收——完好的东西让它去被需要的地方
· 主件已不在：配件失去服务对象，使用频率与未来需求按 0 计
· 闲置物品：功能状态与替代难度按半折计入——主轴是现在的你，不是物品还能用、值多少钱
```

**回复用户时给**：总分、结论、处置路径、下一步动作，以及影响最大的 1–2 个维度（这里是"使用频率 0 + 主件已不在"）。

## 出错时长什么样

```text
$ python scripts/assess_item.py --input items.json
错误：items.json 不是合法 JSON：第 3 行第 44 列 Expecting property name enclosed in double quotes。
常见原因：用了中文引号「」“”、字段末尾多了逗号、或把注释写进了 JSON
```

```text
$ python scripts/assess_item.py --input items.json
错误：「旧登山杖」的分数写在了顶层（usage）。分数必须放进 scores 字段：
{"name":"旧登山杖","scores":{"usage":3}}
```

```text
! 旧手机：flags 里的 expiredd 不是已知标记，已忽略（可选：safety、expired、irreparable、document）
```

## 六维与结论

六个维度统一 **0–5 分，分数越高越倾向保留**：

| 维度 | key | 默认权重 | 5 分含义 |
|------|-----|----------|----------|
| 使用频率 | `usage` | 0.25 | 每周多次或每天都在用 |
| 未来需求 | `future` | 0.20 | 近期已排上日程，确定会用 |
| 功能状态 | `condition` | 0.15 | 全新或接近全新，功能完好 |
| 替代难度 | `replace` | 0.15 | 无法再获得（绝版、唯一、定制） |
| 情感价值 | `sentiment` | 0.15 | 与重要的人或时刻绑定，无可替代 |
| 空间友好度 | `space` | 0.10 | 收纳后几乎不占空间 |

加权汇总后的分档：

| 总分 | 结论 | 处置路径 |
|------|------|----------|
| ≥ 70 | 保留 | 继续使用 |
| 55–69 | 保留（观察） | 降级存放 |
| 40–54 | 暂存观察 | 封存，3–6 个月到期未取用即处理 |
| 25–39 | 建议流转 | 转赠 / 转卖 / 捐赠 |
| < 25 | 建议丢弃 | 丢弃 / 回收 |

另有 14 条硬规则优先于总分（安全隐患立即处理、证件合同强制保留、"总有一天"按不会用计、情感 ≥ 4 不判丢等），由脚本自动执行，详见 `SKILL.md`。

## 目录结构

```
lightener/
├── SKILL.md                 # 技能主体：六维速查表、品类基线、硬规则、操作流程
├── README.md                # 本文件
├── LICENSE                  # MIT
├── CONTRIBUTING.md          # 贡献流程：PR 一律提到 pending 分支
├── scripts/
│   ├── assess_item.py       # 主脚本：打分、硬规则、分档、报告渲染
│   ├── evaluate.py          # 通用加权汇总引擎（被主脚本复用）
│   ├── build_form.py        # 维护者：导出 assets/rules.json 并同步表单
│   ├── calibrate.py         # 维护者：30 条样例回归门禁
│   └── calibration_samples.json
├── references/              # 按需加载的深度文档
│   ├── advanced.md          # 批量清理 / 经济档位 / 封存档案 / 完整命令 / 维护者专区
│   ├── item-rubric.md       # 六维完整分档定义与边界争议
│   ├── category-priors.md   # 从一句话里抽维度
│   ├── evaluation-workflow.md # 答案→分数映射、JSON schema、摇摆话术
│   ├── faq.md               # 20 条 FAQ + 反模式清单（用户追问 / 报错看不懂时看）
│   └── calibration.md       # 标定样例与回归门禁
├── assets/
│   ├── assessment-form.html # 网页版评估表单
│   ├── report-template.md   # 结论输出模板
│   └── rules.json           # 生成物，不手写
└── .github/                 # CI、PR / Issue 模板
```

日常使用只需 `assess_item.py`；`references/` 里的内容由技能按需加载，不必预先通读。

## 贡献

PR 一律提到 `pending` 分支（不要提 `main`），由维护者审核后 squash 合并。完整流程、本地校验命令、标定样例格式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

提 PR 前请跑通：

```bash
python scripts/build_form.py --check   
python scripts/calibrate.py           
python -m compileall scripts
```

标定细节见 `references/calibration.md`，进阶用法与打包见 `references/advanced.md`。

## 许可

MIT，见 `LICENSE`。

## 声明
本SKILL仅提供决策辅助，不替代法律、医疗、财务等专业判断；涉及证件、处方药、危险废弃物时，请遵循当地法规与专业渠道。

---
如有问题或建议，欢迎提交 Issue 或 PR。