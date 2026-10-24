# 贡献指南

感谢愿意给荷丛（Lightener）做贡献。本仓库用一条固定的协作链路：

```
你的功能分支 ──PR──> pending ──审核 + squash 合并──> main
```


1. **所有 PR 的目标分支都是 `pending`，不是 `main`。** 
2. **提 PR 前必须本地跑通文末的校验。**

## 没有写权限：fork 流程

```bash
# 1. 在 GitHub 上点 Fork
# 2. 克隆你的 fork，从它的 main 切分支
git clone https://github.com/<你的账号>/lightener.git
cd lightener
git switch -c feat/xxx

# 3. 改完后本地校验（见下）
# 4. 推送并发 PR —— base 分支选 pending，不是 main
git push -u origin feat/xxx
gh pr create --base pending --repo Mccurtain/lightener
```

## 有写权限

同样走 PR，只是不用 fork：

```bash
git switch -c feat/xxx
git push -u origin feat/xxx
gh pr create --base pending
```

不要直接往 `main` 或 `pending` 推提交。

## 提 PR 前必须过的校验

```bash
python scripts/build_form.py --check   # 网页表单与规则数据是否同步，不同步返回 1
python scripts/calibrate.py            # 30 条人工样例回归，必须全部相符
python -m compileall scripts           # 语法编译
```

改了规则、阈值、品类基线时，顺序是：先 `python scripts/build_form.py` 重新生成，再 `python scripts/calibrate.py`。

## 提交信息

`类型: 简述`，类型取 `feat` / `fix` / `docs` / `refactor` / `chore`。改规则时请在正文说明**改了哪一条、为什么、期望结论变成什么**。

## 改规则的特别注意

- `SKILL.md` 的品类基线速查表数值必须与 `scripts/assess_item.py` 的 `CATEGORY_PRIORS` 保持一致，改一处就要改另一处。
- 分档阈值（70 / 55 / 40 / 25）与六维权重的改动请在 PR 描述里给出理由。
- 标定样例的期望值如果随规则变化，同步更新 `scripts/calibration_samples.json` 的 `expect` / `why`。

## 维护者怎么合并

```bash
# 收 PR：本地复核后批准
gh pr list --base pending
gh pr checkout <编号>
python scripts/build_form.py --check && python scripts/calibrate.py
gh pr review <编号> --approve
gh pr merge <编号> --squash --delete-branch

# 攒一批后，把 pending 合进 main
git fetch origin
gh pr create --base main --head pending --title "chore: merge pending into main" \
  --body "$(git log --oneline origin/main..origin/pending)"
gh pr merge <该PR编号> --squash          # 不要加 --delete-branch，会删掉 pending
git push --force-with-lease origin origin/main:pending   # 把 pending 重置到 main
```

最后一步不能省：squash 合并后 `pending` 仍指向旧提交，不重置会让后续 PR 带着重复历史。

## 反馈问题

开 issue 时请给出：物品或品类、输入 JSON / 命令、实际输出、你期望的结论与理由、用的权重方案。`scripts/calibrate.py` 能跑通但结论不合理，属于规则问题，欢迎直接提 PR。

## 行为准则

- 评审只认新事实：不接受"还是舍不得""挺值钱的"这类主观理由作为改判依据——这也是本 skill 对自己的要求。
- 对事不对人，改规则的分歧用标定样例和数据说话。
