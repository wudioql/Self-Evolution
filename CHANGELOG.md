# CHANGELOG · 变更记录

全部显著变更按日期倒序记录于此，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；日期一律用绝对日期（`AGENTS.md` §6）。

本文件记「**改了什么**」；审计核对范围、验证边界与待修登记记 [`AUDIT.md`](AUDIT.md)（2026-09-07 前名「维护审计.md」），记「**核对过什么、边界在哪**」。2026-09-07 前的条目自原 README §6 与原维护审计 §6 迁入，文字基本保留原貌；旧记录保留历史意义，与 2026-09-06 审计不符的旧结论不能作为「已解决」的证据。

## [2026-09-07]

### 隐私 · 脱敏范围收缩（本人确认）

- 2026-09-07 本人确认：用户名「何念生」（非真实姓名）、晶圆尺寸（6 吋）、出生年份（2001）、毕业院校（华东理工大学）不在敏感范围。
- 公开文件还原：`01-个人档案.md` §1 基本信息表与 §2 职业轨迹表、`README.md` §2、`02-方向分析.md` §1；`01` 顶部脱敏声明重写为「仅雇主与厂区所在地脱敏」。
- `01-个人档案.local.md` 映射表 8 条 → 4 条（保留雇主 / 厂区所在地 / 当前厂区）；`AGENTS.md` §9 禁区补敏感范围边界说明。隐私检测词表随映射表同步收缩。
- 验收：`check-docs.py` 15/15、回归 51/51、`sync-plan.py --check` 全绿；进度与打卡状态未变。

### 排期 · 设备线知识学习显性化（本人确认）

- 诊断：设备线 16 条任务全部为记录型且集中在周六；`半导体设备成长手册` §2.2 七大知识块与排期零对接；日常闭环从不推送「学什么 / 怎么学」。
- `progress/plan90.json`：新增 4 条设备知识点任务，全部落在既有周六 2.5h 设备块（零新增时间块）：`2-11` 真空技术（09-19）、`3-7` 气体与化学输送（09-26）、`6-6` 热工与温控 PID + 热电偶选型（10-17）、`9-6` RF 阻抗匹配与反射功率（11-07）；顺序按手册星级（真空先）。`dailyPlan` 四个周六加入对应动作；任务总数 92 → 96；只读视图已同步。
- `manuals/半导体设备成长手册.md`：新增 §2.7「七大知识块怎么用（学法）」——四步法、≤60 分钟 / 块、必须挂靠机台或故障、工作日微剂量规则；§7 对接表补 5 行。
- `00-速查表.md` §1 增加工作日微剂量行；`AGENTS.md` §8.1 贴士表设备线扩为 3 行（周六学习处方 / 故障根因对应知识块 / 墨墨后微剂量）。
- `01-个人档案.md` §8 登记决策项 11。
- 验收：回归 51/51、`check-docs.py`、`sync-plan.py --check`、`check-tools.py` 全绿；勾选与打卡状态未变。

### 功能 · 预设每日对话工作流与 `today` 只读扩展（本人授权）

- `AGENTS.md` §8.1「预设工作流：每日闭环（问 → 报 → 勾 → 预告）」：WF1 问任务（一条 `today` 命令覆盖日期 / 状态 / 当周剩余 / 里程碑 / 明日预告，附回复结构与贴士表）、WF2 报进展与打卡（note / done / checkin 判定，写完回预告与后续节点）、WF3 夜班豁免、WF4 故障口述；并给出读取优先级（token 纪律）。节号插在 §8 内部，后续章节不重排。
- `scripts/project_data.py` `day_info` 增加只读派生字段：`weekTitle / weekDone / weekTotal / weekRemaining`（当周剩余）、`tomorrow / tomorrowDate`（次日 `dailyPlan` 首个未完成动作）、`nextMilestones`（复检点与未完成交付物中最近 2 个）。
- `scripts/progress.py` `today` 文本输出补充「当周剩余 / 下一里程碑 / 明日」三行（夜班降档时不出后两行），`--json` 同步带出；全部由既有数据推导，未引入数据字段。
- `scripts/test_progress.py` 补 2 例回归：派生字段取值正确、查询前后文件零变化、勾选后当周上下文随之收缩、Day 0 不出现周次行。
- 验收：回归 51/51 通过；`python3 scripts/check-docs.py`、`python3 scripts/sync-plan.py --check`、`python3 scripts/check-tools.py` 全绿。排期、学习任务状态与两个 JSON 正本未变（未勾选、未打卡）。

### 文档 · 目录结构标准化（本人授权）

- 新建本文件：原 `README.md` §6「变更记录」与原 `维护审计.md` §6「审计后变更记录」全部迁入并去重，此后变更只记在这里；README §6 改为指针。
- `维护审计.md` 更名 **`AUDIT.md`** 并收窄职责（审计结果 / 验证边界 / 完整文件清单 / 待修登记）；`AGENTS.md`、`README.md`、`00-速查表.md`、`manuals/AI与工具手册.md`、私有档案说明与 `scripts/check-docs.py` 注释中的引用同步更新；`AGENTS.md` §6 修改规范改为「改后在 [`CHANGELOG.md`](CHANGELOG.md) 补一条」。
- 按奥卡姆剃刀**不新增** ARCHITECTURE / CONTRIBUTING / API / DATABASE / DEPLOYMENT / DEVELOPMENT / TROUBLESHOOTING 模板文件：单人学习仓库，上述职责已由 `AGENTS.md` / `README.md` / `AUDIT.md` / `manuals/` 覆盖，空壳文件只会扩大维护面。

### 修复 · check-docs.py Windows 必崩（本人授权）

- 原 AUDIT.md 登记：`glob.glob('manuals/*.md')` 在 Windows 返回反斜杠路径，与 `docs` 字典正斜杠键不匹配 → `KeyError`，本地每次运行必崩且不输出任何检查结果（CI 为 Linux 不触发，故未被发现）。修复时发现实为**两处漏修其一**：`manuals` 处已有 `as_posix()` 补丁，`tools/*.html` 的 `htmls` 字典漏改——Windows 上 `Path(f).read_text()` 直接 `FileNotFoundError`（仍必崩），且公开壳隐私检查会因键分隔符不符静默漏检。
- 修复：`htmls` 键统一 `as_posix()` 归一化、经 `Path(ROOT)` 重定位读取（正斜杠在 Windows / Linux 的 pathlib 均可解析）；同类修正 `project_data.sync_views` 的 `stale` 输出为正斜杠。排查 `check-tools.py`（用 `path.name`）、`browser-smoke.py`（`.as_uri()`）、`sync-plan.py`、`file-store.js`（浏览器端字符串键）无同类问题。
- 验收：Windows 分隔符负例 `test_b7_windows_backslash_glob_results_still_check_manuals_and_shell` 修复前 FAIL（L136 `FileNotFoundError`）→ 修复后 PASS；`test_docs` 8/8、`test_progress` 41/41、体检 15/15、`sync-plan --check` 已同步（Linux 沙箱验证；真实 Windows 未实测，负例以注入反斜杠 glob 等价覆盖）。

### 修复 · 测试在 Windows 的编码崩溃（本人授权）

- `scripts/test_docs.py` / `scripts/test_progress.py` 共 20 处裸 `read_text()` / `write_text(...)` 补 `encoding='utf-8'`：Windows 默认区域编码（cp936）读写 UTF-8 中文正本（`plan90.json` 为 `ensure_ascii=False` 原生中文）会乱码或抛 `UnicodeDecodeError`，本地跑回归必挂。
- Windows 兼容排查结论（生产代码无需再改）：`project_data.atomic_write` 锁文件 fd 即开即关（规避 Windows 不能删除已打开文件）、临时文件 `newline='\n'` + `os.replace` 均兼容；`check-tools.py` 以 `path.name` 作键、`browser-smoke.py` 用 `as_uri()` / `chromium.launch()`、Node 侧 `path.join` + utf8 读取；CI（ubuntu-latest）不受影响；`python3` 别名差异 AI 手册 §4.6 已有说明（可换 `python` / `py -3`）。
- 盘点补充：本地未上传 `music-log/01-lemon/stems/`（10 个 MSST 分轨音频）与根目录历史存档 `Self-Evolution.zip.txt`，`.gitignore`（`music-log/**/stems/`、`*.zip.txt`）已覆盖、不会误入库；`AUDIT.md` §5 盘点段同步。

## [2026-09-06]

当日多项变更；审计核对细节与验证边界见 [AUDIT.md](AUDIT.md) §1–§4。

- **审计修复（本人授权）**：修 `music-log/README.md` 断链（`03-burao/` → `03-buhaore/`，拼音笔误），4 项回归与体检 §8 转绿；Lemon 原曲音频与歌词移入 `music-log/01-lemon/original/`（符合 music-log 约定、git 忽略范围内），并清除歌词首行被下载来源夹带的外部追踪脚本（向 `kdev365.com` 发 Image 请求的 pixel，非本人内容，`[ti:]` 标题行连带破坏后已按原值恢复）；`.gitignore` 合并 `*.local.*` 子集规则、新增全局 `*.lrc`；文件数 47 → 49。进度 0/92 与故障 0 条未变，两个 JSON 正本未改。
- **修复 B1–B8（本人授权）**：修复生成标记校验、异常导入整包停止、首次建库竞态、Python / 网页字段对齐、旧格式备注保留、发布逾期暂停 IPA、隐藏目录体检、固定时钟浏览器回归共 8 项代码问题，全部纳入回归并补负例与跨语言对照；进度 revision 2 与故障 revision 0 未变。细节见 [AUDIT.md](AUDIT.md) §3–§4。
- **neat-freak 常规同步**：删除交付 ZIP，逐文件对齐规则 / 档案 / 五份手册 / 执行模板与文件记录；更正曲谱 / IPA / 编程目标 / 带人经历 / 工具采购 / 目录安装旧说法，校正 3 项任务文案后由 JSON 同步视图；学习状态与日期保留，实现缺口单列 AUDIT.md。
- **文件驱动的日常执行**：Day 0 = 09/06、Day 1 = 09/07，14 周于 12/13 收尾；92 个稳定任务 ID + 99 天每日建议进入 JSON（排期与状态唯一来源），自动生成进度总览与 HTML 快照；故障库用本地 JSON / Markdown / HTML，示例不计成果；新增 agent 查询 / 勾选 / 备注 / 打卡 / 豁免 / 迁移命令、冲突检测与回归测试，修复旧保存递归 / 旧同步解析失败 / 目录断链。学习任务未自动勾选。
- **准备开源**：新增 `.gitignore`、`music-log/` 三首歌骨架、`check-docs.py`（AGENTS 规范 → 11 项自动检查）、`docs-check.yml`（push / PR 体检）；引入 vendored 第三方 skill `neat-freak`（`.agents/skills/`，含 upstream 溯源与跨平台兼容表）；`AGENTS.md` §8 断链自检改调脚本、§9 新增「禁止提交未脱敏内容」。
- **脱敏 + 开源就绪**：5 个文件泛化处理（真实姓名 / 雇主 / 厂区所在地 / 晶圆尺寸，具体字段见本地 `01-个人档案.local.md`），`01` 顶部加脱敏声明；加 `LICENSE`（CC BY-NC-SA 4.0 官方全文）；README 新增 §0 对外说明。
- **泛化范围扩大**：毕业院校 → 国内双一流理工院校、出生年份 → 仅保留年龄（25 岁）。映射表扩至 8 条真值，检测词表同步扩大。
- **本地真值不外泄**：新增 `01-个人档案.local.md`（占位符→真值映射表，gitignored）。`AGENTS.md` §11 规定 agent 读档案时按映射还原真值、但不得写进任何产出物；`scripts/check-docs.py` 新增「隐私」检查——**反用该映射表作为泄露检测词表**扫描公开文件（隐藏目录覆盖缺口见 AUDIT.md）。skill 存于 `.agents/skills/`；原记录的 Claude 符号链接在本工作目录实际不存在，已纠正安装说明。
- **全量合规审计**：修正 2 处真违规（`00` §10 缺 `→` 指向；音乐手册「Transcribe! 值得买」违反 §9 禁买，已改为「90 天内不买，先用自带变速」）；把「先唱出根音」技巧从执行层收回手册（§6.1）；收紧 `03` §1 轨道 4 的论证篇幅。并在 `AGENTS.md` §2 补两条边界说明：**「可勾选」在 `03` 由进度表 HTML 承担、不在 03 里重复做复选框**；**「不解释为什么」允许每节几行、完整论证一律归 02**。
- **论证归位**：把「合唱为何不训练多声部听辨」的完整论证（含本人原话 + 训练到 / 没训练到的边界对照表）写入 `02-方向分析.md` §1.2——按 AGENTS §2，**基础层-决策的职责就是「论证」**；`manuals/音乐学习手册.md` §2.1 相应精简为「结论 + 练法」并指向 02，避免与 §6.1 单一真相源冲突。
- ⭐ **补充关键背景并修正诊断**：本人大学期间为**校合唱团男低声部成员，后任声部长**（带声部练、抠音准）；五线谱可固定调视唱。据此修正三处判断：①「唱歌」从负债改为「音准没问题，短板是气息与活人感」；②「多声部听觉缺失」成立且经本人确认——合唱一个声部最多 1–2 个音且有谱子，**不训练「从混音里分离同时响的 ≥3 个音」**，故不存在「有基础」，需从零练（但可训练）；③ 职业线补上**带人 / 教学经验**（「专家→主管」的门票）。Praat 的用法随之从「查音准」改为**「量活人感 + 查气息跑偏」**；新增**男低声部需先移调**的提醒。

## [2026-09-05]

- **执行单一真相源**：把 `03` §3/§4、`04` 的方法内容全部迁进 `manuals/`（Praat 操作、好听元素清单、扒带 6 步工作流、卡点速查表、工具清单、ACE-Step 显存应对），执行层只留「哪一周 · 做什么 · 算不算完」+ 一行指向手册。规则写入 `AGENTS.md` §6.1。
- **全面复查**：统一 H1 命名（`NN · 标题` / `手册 · 主题`）；层级口径修正为六层；修正旧文件名残留与章节引用错误；补「主线 A/B/C ↔ 轨道 1/2/3/4」口径映射。
- **新增 `00-速查表.md`**：只放硬事实与高频流程（不写解释），作为随身/贴墙层，每节标注详查入口。
- **重组为五层结构**：新增 `manuals/`（5 份参考手册，统一模板）、新增 `AGENTS.md`；README 改为纯人类入口，agent 内容迁出。
- **首次整理目录**：主文档加数字前缀、工具移入 `tools/`；新增 README 与 `01-个人档案.md`。
- **补 IPA / 音韵学内容**：进度表加入 12 条 IPA 任务（新增「音韵」轨道）。
- **创建整套体系**：诊断分析 → 14 周计划 → 扒带作业单 → 故障模式库 → 90 天进度表。
