# 进阶用法与维护者专区

> **这份文档不是判断单件物品时读的。** 单件判断看 `SKILL.md` 就够了。
> 只在以下情况打开：批量清理几十件、需要按经济档位校准价格、要维护封存档案、或者你要改规则 / 改阈值 / 打包。
>
> 用户追问、命令报错看不懂 → 看 `faq.md`（20 条 FAQ + 反模式清单），不要来这份里翻。

## 1. 批量评估：容量、冗余与优先级

一次清理一柜子时，逐件纠结没有意义——**先定容器，再选物品**。

### 为什么必须先定容器：帕金森定律的物品版

**帕金森定律**（C. Northcote Parkinson，1955 年《经济学人》）：*工作会自动膨胀，直到填满所有可用的时间*。物品版是同一个结构——**东西会自动膨胀，直到填满所有可用的空间**：多一个柜子就多一柜东西，房子换大了，车照样停不进车库。

可观察的事实：

- UCLA《Life at Home in the Twenty-First Century》观察 32 个洛杉矶中产家庭：**75% 的家庭车库停不进车**；母亲在处理物品时皮质醇（压力激素）明显升高。
- 2023 年 Self-Storage Almanac：超过 **11%** 的美国家庭在租储物间——把家里的空间"外包"出去，好让膨胀继续。

三条推论，也是 7·5·1 的真正理由：

1. **逐件取舍永远做不完**：容器还是满的时候，清掉一件，剩下的会自动铺开补位。所以顺序必须是**先定容量，再选物品**。
2. **别用收纳解决取舍问题**：买一个更大的柜子等于给膨胀扩容——空间变大，物品会用同样的速度把它填满。买收纳用品之前先做容量决策（它同时也是狄德罗效应的配套消费：新柜子 → 新收纳盒 → 新标签机）。
3. **清理完必须留下空位**：7 成 / 5 成 / 1 成留出的空不是浪费，是**膨胀余量**。把空间填到 100%，等于宣布下一轮清理立刻开始。

> 判断标准不是"柜子还塞得下吗"，而是"这个容器该放几成"。

### 分组容量（7·5·1 的落地）

```bash
python scripts/assess_item.py --input items.json --capacity "book:10,clothing:20,cable:3"
python scripts/assess_item.py --input items.json --capacity 3     # 全局上限
```

组内按总分排序，排名在限额之外的标为「超出容量 → 按处理路径执行」。批量评估 ≥5 件却没设容量时，脚本会提醒你这一点（帕金森定律）。

### 同类冗余（同用途只留一件）

同品类组内第 2 件及以后，若使用频率 ≤ 2、替代难度 ≤ 2（容易再获得）、情感 ≤ 3，直接拉到「建议流转」并标记同类冗余。第三把重复的削皮器、一箱旧数据线都属于这一类。

不想要这个行为时用 `--no-redundancy` 关闭。

### 批量时的其他行为

- **归属他人**（`owner`）：结论照算，但标注「处置前需与对方协商」，且不参与冗余自动调整——你没有替别人做决定的权力。
- **数字化处置**：`manual` / `book` / `kids` 品类在结论为处理类时，下一步自动加「先拍照或扫描存档，再……」。舍的是实体，不是记忆。
- **优先级**：批量报告按总分升序输出处理优先级（分数越低越优先）；体积大的优先，收益最明显。

## 2. 附属件：主件没了，配件不该留（狄德罗效应的反面）

**狄德罗效应**：狄德罗在 1769 年的短文《与旧睡袍别离之后的烦恼》里写过——得到一件新睡袍后，旧椅子、旧书桌、旧书架一件件都显得不配，最后整个书房全换了一遍。人类学家 Grant McCracken 在 1988 年把它命名为 Diderot Effect：一件新物品打破原有的"整体感"，引发一连串配套消费；这些物品之间构成**互补关系**，一件离开，另一件就失去意义。

规则：**一件只能服务于已经失去意义的主件的配件，其价值随主件一起清零。**

处理主件时把配件一并入册：贴膜神器、专用壳、原装线、说明书、包装盒。否则会出现最难清理的残留——**主件走了，配件还堆在抽屉里**：它们没有服务对象，又小到不占地方、不惹人注意，于是永久滞留。

```json
{"items": [
  {"name": "旧手机", "category": "device"},
  {"name": "贴膜神器", "scores": {"usage": 2, "future": 3, "condition": 4, "replace": 2, "sentiment": 1, "space": 5}, "depends_on": "旧手机"}
]}
```

- `depends_on`：主件名（同批里的 `name`），主件结论为处理类时自动联动清零。
- `host_gone`：`true` 表示主件已不在（已转卖 / 已坏 / 已送人），用于主件不在本批时——**单件判断也能用这一个字段**。

联动后：使用频率与未来需求按 0 计（服务对象没了），**结论不低于建议流转**；情感 ≥ 4 的配件改为封存观察——父亲留下的镜头不该跟着机身一起走。实测同一个贴膜神器：主件还在时 53 分暂存观察，主件处理掉后 22 分建议流转。

`phone_box` / `cable` / `manual` 三类已标记为附属品类，没填 `depends_on` 时报告会提示补主件。

## 3. 经济水平校准（三档）

**同一个物品，不同经济状况的人该得出不同结论。** 丢一个重新买要两百块的东西：预算紧的人会觉得肉疼（替代难度 4，倾向保留），宽裕的人觉得随手再买（替代难度 2，倾向处理）。不校准这一层，评判就是脱离用户处境的平均数。

| 档位 | key | 价格锚点（重新买一个的花费） | 处置偏好 | 推荐权重 |
|------|-----|--------------------------|----------|----------|
| 预算敏感 | `tight` | ≥200 元→4 分；≥50 元→3 分；其余 2 分 | 优先自己用掉或转卖换钱，别急着送人 | `space` |
| 常规 | `normal` | ≥1000 元→4 分；≥200 元→3 分；其余 2 分 | 先问亲友，无人要再挂二手，仍无人接手则回收 | `balanced` |
| 预算宽裕 | `comfortable` | ≥5000 元→4 分；≥1000 元→3 分；其余 2 分 | 直接送人或捐赠，不必为小钱花时间挂二手 | `balanced` |

价格只决定**替代难度**这一维；"弄不到了（绝版/唯一）"仍记 5 分，"家里还有好几个"仍记 0 分，不受档位影响。

### 怎么判断用户属于哪档

优先从**对话里已有的线索**推断，不要一上来就问收入：

| 线索 | 指向 |
|------|------|
| 租房 / 合租 / 老破小 / 提到房价房贷压力 | 偏 `tight`（同时用 `space` 权重） |
| 比价、等促销、常买二手、提到"这个挺贵的" | 偏 `tight` |
| 学生、刚工作、育儿中、退休金生活 | 偏 `tight` |
| 提到自有住房、装修、请收纳师、开车 | 偏 `normal`–`comfortable` |
| 说"才两百块""不值几个钱""直接买新的" | 偏 `comfortable` |

判断不出时**默认 `normal`**。确实需要确认时，问两个可观察的锚点（不问收入）：

1. 「你现在住的地方，东西好放吗？会不会觉得挤？」→ 空间紧张度
2. 「像两三百块的东西，对你来说是要犹豫一下的开销吗？」→ 价格敏感度

### 用法

```bash
python scripts/assess_item.py --input items.json --economy tight
python scripts/assess_item.py --price 200 --economy tight        # → 4 分
python scripts/assess_item.py --price 200 --economy comfortable  # → 2 分
```

JSON 里也可给单个物品加 `economy` 字段。

**配合 WTP 检验**：用户答出"今天愿意花 X 元再买一个"时，把 X 填进 `wtp` 字段，脚本按档位换算替代难度并在报告标注来源「WTP 检验」：

```json
{"name": "当年八千买的单反", "scores": {"usage": 2, "future": 3, "condition": 4, "replace": 4, "sentiment": 2, "space": 3}, "wtp": 100}
```

同一台相机，按"当年很贵"记替代难度 4 是 58 分保留（观察）；按"今天只愿花一百再买"记 2 则是 52 分暂存观察——**愿意付的钱才是真实估价**。金额的档位差异会改变结论（预算敏感档下这一百块记 3 分），这正是经济校准在起作用。

## 4. 封存档案（--log / --review）

**封存是后悔管理，档案就是这份保险的保单。** 说"3 个月后复评"而没有地方记，就等于没有复评——犹豫会原地复活。

```bash
python scripts/assess_item.py --input items.json --log seal.json
python scripts/assess_item.py --review seal.json
```

档案记录物品、分数、结论、封存日期与复评日期：「暂存观察」3 个月、「保留（观察）」6 个月、超出容量 1 个月。到期后打开箱子看一眼，比当场想一百遍准。

复评规则：到期未取用即按原结论处理——这是**新事实**，不是重新权衡。

## 5. 摇摆字段（swings）

对话里用户摇摆时，把次数写进物品的 `swings` 字段，脚本会自动执行摇摆阶梯：

- `"swings": 1` → 结论拉到**封存观察**（不回到保留），写明封存日期与复评日期
- `"swings": 2` 及以上 → **锁定**：分数照算但不再改结论，只输出执行动作，报告标注"已锁定，只执行不复盘"

强制结论（安全 / 过期 / 凭证）不接受摇摆。锁定项也不参与同类冗余自动调整。

## 6. 完整命令参数

```bash
python scripts/assess_item.py --interactive                      # 交互录入
python scripts/assess_item.py --input items.json                 # 批量评估
python scripts/assess_item.py --input items.json --out report.md --html report.html --json result.json
python scripts/assess_item.py --input items.json --preset space --weights sentiment=0.05,usage=0.35
python scripts/assess_item.py --input items.json --capacity "book:10" --no-redundancy
python scripts/assess_item.py --input items.json --log seal.json
python scripts/assess_item.py --review seal.json
python scripts/assess_item.py --price 200 --economy tight        # WTP 换算
python scripts/assess_item.py --list-presets | --list-categories | --list-economy
```

## 7. 维护者专区

你判断物品时永远不会碰这些，只有**改规则 / 改阈值 / 打包**时才需要：

- `scripts/build_form.py`：把 `assess_item.py` 里的规则导出为 `assets/rules.json` 并同步进 `assets/assessment-form.html`；`--check` 校验同步。**改动规则数据后必须运行。**
- `scripts/calibrate.py` + `scripts/calibration_samples.json`：30 条人工样例的回归门禁，并校验 SKILL.md 品类速查表一致性与 WTP 价格换算，不符返回退出码 1。**改动规则后必须运行。** 详见 `references/calibration.md`。
- `assets/assessment-form.html`：单文件交互式评估页，常量由 `build_form.py` 注入，不要手改。
- `assets/rules.json`：生成物，不手写。
- `scripts/evaluate.py`：通用加权汇总引擎，被主脚本复用。

改动规则后的标准流程：`python scripts/build_form.py` → `python scripts/calibrate.py` → 重新打包。
