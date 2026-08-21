# EvalAgent 现场配置与意义建构用户研究方案

**版本：** 4.0  
**日期：** 2026 年 7 月 29 日  
**目标样本量：** 12 人  
**研究形式：** 有主持人的远程用户研究  
**目标时长：** 约 50 分钟，最多不超过 55 分钟  
**研究环境：** EvalAgent 与 WebHarbor 安全复刻网站  
**核心循环：** 现场探索 → 配置两个 Agent → 等待运行并访谈 → 比较 trajectories → 修改配置 → 再次运行并修正心智模型

## 1. 设计调整的核心理由

参与者不需要在研究前编写任务、Agent 配置、evaluation criteria 或行为预测。研究前只收集知情同意、基本背景和参与资格。

所有与研究问题直接相关的活动都在正式研究中现场完成：

1. 参与者先探索 WebHarbor 网站；
2. 根据网站内容提出自己感兴趣的任务；
3. 现场配置两个具有对比意义的 Agent；
4. 在 BrowserUse 运行期间，通过访谈记录其初始标准、配置理由和行为预期；
5. 使用 EvalAgent 比较运行结果；
6. 根据比较形成新的解释并修改一个配置；
7. 再次运行修改后的配置，同时访谈其心智模型变化；
8. 如果运行及时完成，快速检查新的行为是否符合预期。

这样的设计减少了研究前填表负担，也能直接观察用户如何从网站探索进入 Agent 配置，而不是只分析研究人员提前准备好的 configurations。

## 2. 研究定位

本研究将 EvalAgent 定位为一个支持 GUI Agent 配置实验和比较式意义建构的部署前沙盒。

研究的重点不是：

- 参与者能否写出更多或更详细的 criteria；
- Agentic Judge 的 evidence 是否比人工查找更快；
- 某个单独界面组件是否显著降低 workload。

研究的重点是：

- 用户如何从开放网站和任务中确定值得测试的 Agent 差异；
- 用户如何把偏好、政策约束或行为优先级转化为 Agent 配置；
- 用户如何通过比较 trajectories 理解不同配置下的 Agent；
- 意外行为和矛盾如何改变用户的心智模型；
- 新的理解如何影响下一次配置。

Agentic Judge、criteria 和 evidence highlighting 仍然可以被参与者自由使用，但它们是意义建构资源，而不是强制任务或主要研究结果。

## 3. 研究问题

**RQ1 - 现场配置：** 用户在探索一个任务领域后，如何构造两个他们认为值得比较的 Agent 配置？

**RQ2 - 比较式意义建构：** 用户如何理解不同 Agent trajectories 之间的相似点、差异、trade-offs 和意外行为？

**RQ3 - 心智模型变化：** 比较不同 Agent 后，用户对“configuration 如何影响 behavior”的理解发生了什么变化？

**RQ4 - 重新配置：** 用户如何将新的理解转化为修改后的 Agent 配置，以及新的运行结果如何支持或挑战其解释？

## 4. 参与者

招募 12 名具有以下一项或多项经验的参与者：

- LLM Agent 或 GUI Agent 开发；
- prompt/configuration testing；
- AI evaluation 或 quality assurance；
- Agent debugging；
- HCI/AI research；
- responsible-AI auditing；
- 具有较强技术经验的 Agent 使用。

参与者必须年满 18 岁，能够使用英语完成研究，并同意屏幕和音频录制。

低任务完成率、形成错误解释、不使用 Judge、不创建 criteria 或最终不修改配置，都不构成排除条件。只有严重技术故障、缺少主要录制数据或未完成核心比较阶段时，才考虑排除或补招。

## 5. WebHarbor 选择与领域覆盖

### 5.1 不要求提前选择网站

参与者无需在研究前填写网站志愿或任务。正式研究开始后，系统向参与者展示三个当前配额未满的 WebHarbor 网站。

这三个网站应来自不同 broad domain families，并根据当前样本覆盖情况动态生成。参与者从中自由选择一个。

这一方法属于**配额约束下的现场自由选择**：

- 参与者仍然选择自己更感兴趣的网站；
- 研究人员不直接分配具体任务；
- Amazon 不会因为熟悉度而占据大多数样本；
- 不增加研究前表单负担。

### 5.2 N = 12 的覆盖要求

最终样本应满足：

- 至少覆盖 6 个不同 WebHarbor 网站；
- 至少覆盖 5 个 broad domain families；
- 任何单一网站，包括 Amazon，最多 2 人；
- 任何单一 broad domain family 最多 3 人。

研究日志应记录：

- 每名参与者看到的三个候选网站；
- 最终选择的网站；
- 选择理由；
- 该网站当时的配额状态。

论文只能报告实际覆盖的网站与领域，不能声称验证了全部 WebHarbor domains。

## 6. Agent 配置与运行控制

### 6.1 第一次配置

参与者在探索网站后提出一个安全、可逆的任务，并现场配置两个 Agent：

- **Agent A：** 第一种 preference、policy constraint 或 behavioral priority；
- **Agent B：** 与 A 具有实质对比意义的第二种配置。

两个 Agent 使用相同的：

- base model；
- task；
- WebHarbor initial state；
- BrowserUse version；
- tools；
- maximum steps；
- timeout；
- safety constraints。

唯一的实验变化是参与者定义的配置文本。

为了控制时间，初始阶段不额外生成 neutral run。两个具有明确对比的 runs 已足以支持 joint comparison。若未来技术条件允许，可以将 neutral run 作为补充，但不应影响主要流程。

### 6.2 任务安全边界

任务可以包括：

- 搜索；
- 比较；
- 信息综合；
- 推荐；
- 填写但不提交的模拟过程。

任务不得完成：

- 真实或模拟购买确认；
- 预订或支付；
- 课程注册；
- 下载；
- 消息发送；
- 账户修改；
- 输入真实凭据或敏感信息；
- 其他不可逆或有现实后果的操作。

### 6.3 BrowserUse 运行时间控制

Agent A 和 Agent B 并行运行，目标运行窗口为 10 分钟。

在正式数据收集前，通过 pilot 确认：

- 大多数任务能在 10 分钟内产生足够比较的 trajectories；
- maximum steps 和 timeout 对所有参与者一致；
- 两个 agents 可以并行执行；
- 运行期间不会向参与者展示不断更新的 partial trajectory，以免影响初始预期访谈。

如果运行达到预设 timeout 但任务未完成，保留 incomplete trajectory。任务失败、循环或提前退出属于有效 Agent 行为，不应仅因为结果不理想而重新运行。

只有启动失败、网站无法访问、日志损坏或没有形成可检查 steps 等技术错误，才允许按预注册规则重新运行。

## 7. 研究流程

### 总体时间安排

| 阶段 | 内容 | 时间 |
|---|---|---:|
| 0 | 欢迎、同意与简短说明 | 2 分钟 |
| 1 | 现场探索 WebHarbor 并确定任务 | 5 分钟 |
| 2 | 配置 Agent A 和 Agent B | 5 分钟 |
| 3 | 两个 Agents 并行运行，同时进行初始访谈 | 10 分钟 |
| 4 | 使用 EvalAgent 比较两个 trajectories | 15 分钟 |
| 5 | 修改配置并启动新的 run | 3 分钟 |
| 6 | 新 run 执行，同时进行 mental-model interview | 7 分钟 |
| 7 | 快速检查新 run，或进入延迟跟进 | 3 分钟 |
| **总计** |  | **约 50 分钟** |

若 revised run 在第 7 阶段仍未完成，session 最多可延长至 55 分钟；仍未完成时，在 48 小时内安排一次 5 分钟的标准化异步跟进。

### 阶段 0：欢迎、同意与研究说明，2 分钟

主持人说明：

> 我们研究的是人们如何配置、比较和理解 Agent，而不是考察你能否找到唯一正确答案。Agent 可能失败或出现意外行为，EvalAgent 的 Judge 也可能出错。请按照最能帮助你理解这些 Agent 的方式使用系统。

主持人提醒参与者：

- WebHarbor 是安全复刻环境；
- 不要输入真实敏感信息；
- 可以随时停止参与；
- 研究对象是系统和意义建构过程，不是参与者能力。

### 阶段 1：现场探索 WebHarbor，5 分钟

系统向参与者展示三个配额未满、来自不同领域类别的网站。参与者选择一个网站并自由探索。

主持人只使用中性提示：

- 这个网站上什么任务对你比较有意义或有趣？
- 哪类任务可能存在不止一种合理策略？
- 你想让 Agent 帮你完成什么？
- 任务应该在哪里停止，避免产生真实后果？

阶段结束时记录：

- 选择的网站；
- 参与者自拟任务；
- 明确停止条件；
- 选择任务的原因。

研究人员可以对任务进行最小程度的安全或可执行性修改，但不得替参与者添加 preference 或 configuration。

### 阶段 2：现场配置两个 Agent，5 分钟

参与者为同一任务创建 Agent A 和 Agent B。

配置界面仅要求填写：

1. Agent A 应优先考虑什么？
2. Agent B 应优先考虑什么？

必要时主持人可以解释 configuration 的形式：

> 请描述当多个选项都满足任务要求时，Agent 应优先考虑什么。配置不能允许 Agent 忽略任务中的明确要求。

主持人不得建议具体价值维度。只有参与者无法理解操作时，才可提供与当前任务无关的示例，如“速度与全面性”。

阶段结束时保存：

- Agent A 配置文本；
- Agent B 配置文本；
- 最终任务文本；
- 配置创建和修改日志。

### 阶段 3：Agents 运行与初始访谈，10 分钟

Agent A 和 Agent B 开始并行运行。运行期间不让参与者检查 partial trajectories，以保护 initial mental model 数据。

主持人进行半结构化访谈：

#### 关于任务

- 为什么选择这个网站和任务？
- 这个任务中什么样的 Agent 行为算是好的？
- 什么样的行为会让你觉得 Agent 有问题？

#### 关于配置

- 为什么这样配置 Agent A？
- 为什么这样配置 Agent B？
- 这两个配置之间最重要的 contrast 是什么？
- 有没有任何 requirement 是两个 Agent 都必须遵守的？

#### 关于 criteria

不要直接要求参与者编写正式 criteria。使用开放问题：

- 当你稍后比较两个 Agent 时，你会关注哪些方面？
- 什么观察会让你认为某个配置表现更好？
- 有没有不能只看最终结果、必须检查过程的内容？

研究人员随后可以将这些口头回答编码为参与者的 initial evaluation concerns。

#### 关于行为预期

- 你预期两个 Agent 在哪些步骤会相同？
- 你预期它们在哪里会出现差异？
- 你预计结果不同、过程不同，还是两者都会不同？
- 哪个 Agent 更可能符合你的预期？为什么？
- 对这些预期的信心是多少？1-7 分。

如果访谈提前结束，可以继续讨论参与者过去配置或评估 Agent 的经验，但不得提前展示运行结果。

### 阶段 4：比较 trajectories，15 分钟

运行结束后，参与者使用完整 EvalAgent 自由比较 Agent A 和 Agent B。

参与者可以使用：

- aligned trajectory graph；
- trajectory filtering；
- step-level reasoning/action/observation；
- summary outcomes；
- Agentic Judge；
- criteria 和 evidence highlighting。

但不要求参与者：

- 至少创建多少 criteria；
- 至少调用多少次 Judge；
- 必须找到某个特定 divergence；
- 必须选择唯一最佳 Agent。

开场提示：

> 请像你真实测试两个 Agent 配置时那样进行比较。请告诉我你注意到了什么、什么与你的预期一致或矛盾，以及你如何解释这些行为。

中性追问包括：

- 你现在比较的是什么？
- 这个差异是 meaningful 还是 incidental？
- 两个 Agent 是 strategy 不同、outcome 不同，还是两者都不同？
- 你认为这个行为与 configuration 有什么关系？
- 哪个观察最让你意外？
- 有没有证据挑战了你最初的解释？
- 你还有什么无法判断？

主持人不得指向特定 node、evidence、criterion 或 Judge verdict。

在该阶段记录：

- 查看过的 nodes 和 trajectories；
- trajectory switching；
- Judge 与 criteria 使用；
- 口头表达的 similarities、differences 和 surprises；
- configuration-behavior explanations；
- confidence changes；
- 未解决的不确定性。

### 阶段 5：修改配置并启动新 run，3 分钟

比较结束后询问：

> 如果你现在可以再运行一个 Agent，你会修改哪个配置？你希望验证或改变什么行为？

参与者：

- 修改 Agent A 或 Agent B；或者
- 创建一个新的 Agent C。

第二次运行必须保持同一网站、同一任务和同一 base model。它不是一个新的无关任务，而是对参与者刚刚形成的 configuration-behavior hypothesis 的检验。

记录：

- revised configuration；
- 触发修改的具体观察；
- 预期发生的行为变化；
- 什么结果会支持该解释；
- 什么结果会挑战该解释。

随后立即启动 revised run。

### 阶段 6：新 run 执行与心智模型访谈，7 分钟

新 run 在后台执行时，进行 mental-model interview：

- 比较前，你如何理解 Agent A 和 B？
- 现在你的理解发生了什么变化？
- 哪个 surprise 最影响你的解释？
- 你认为 configuration 对 behavior 的影响是什么？
- 哪些差异可能只是随机性、页面状态或 Agent 本身能力造成的？
- 为什么选择现在这个 revised configuration？
- 你预计 revised Agent 会怎么行动？
- 什么结果会证明你当前的解释不完整或错误？
- 比较两个 trajectories 与单独看一个 trajectory 有什么不同？
- 哪个系统资源最帮助你理解 Agent？哪个可能误导你？

这部分是研究 mental-model revision 的主要访谈，不应再次变成 criteria refinement interview。

### 阶段 7：快速检查 revised run，3 分钟

如果新 run 已完成，让参与者快速检查最重要的结果和 trajectory：

- 行为是否按预期改变？
- 哪个观察支持或挑战了你的解释？
- 你会保留、继续修改还是放弃该配置？
- 你现在的 confidence 是多少？1-7 分。

将结果编码为：

- 支持；
- 部分支持；
- 挑战；
- 未解决；
- 技术上不可用。

如果新 run 未完成，研究 session 最多延长至 55 分钟。仍未完成时，在 48 小时内安排一次 5 分钟标准化跟进，只完成上述四个问题。

## 8. 数据收集

### 8.1 主要数据

1. 网站候选集合与最终选择。
2. 参与者自拟任务和停止条件。
3. Agent A、Agent B 和 revised Agent 的配置文本。
4. 初始口头 criteria/evaluation concerns。
5. 初始行为预期和 confidence。
6. 三条 trajectories 及其运行状态。
7. 屏幕、音频和 think-aloud。
8. 完整交互日志。
9. similarities、differences、surprises 和 uncertainties。
10. configuration-behavior explanations。
11. mental-model revisions。
12. revised run 是否符合预测。

### 8.2 次要数据

- Agentic Judge 使用情况；
- criteria 创建和修改；
- evidence source verification；
- perceived mental effort；
- preferred configuration。

这些是辅助解释数据，不是主要 outcome。

## 9. 分析方案

### 9.1 主要分析单位

主要分析单位是 sensemaking episode：

> 触发因素 → 观察 → 解释 → 心智模型变化 → 配置行动 → revised run 结果。

### 9.2 编码维度

- **Trigger：** graph、divergence、raw trace、outcome、Judge 或跨 trajectory 比较。
- **Observation：** similarity、difference、failure、trade-off、surprise 或 uncertainty。
- **Interpretive move：** 描述、比较、解释、质疑、验证或修正。
- **Mental-model change：** 确认、扩展、纠正、替换或未解决。
- **Configuration action：** 保留、澄清、加强、减弱、增加条件、增加 guardrail 或创建新配置。
- **Test result：** 支持、部分支持、挑战、未解决或技术不可用。

两名研究人员使用共享 codebook 独立编码全部 sensemaking episodes，报告一致性并通过讨论解决分歧。

### 9.3 主要结果主题

结果应围绕以下结构组织：

1. 用户如何从网站探索中构造值得比较的 Agent contrasts。
2. 用户如何在 trajectory comparison 中发现 alignable similarities 和 differences。
3. surprises 和 contradictions 如何改变用户的 mental model。
4. 用户如何把新的理解转化为 revised configuration。
5. revised run 如何支持、挑战或未能解决用户的解释。
6. 不同 WebHarbor domains 中重复出现的模式和边界。

### 9.4 描述性指标

可以报告：

- 识别出的 meaningful differences 数量；
- initial expectations 被确认、挑战或未解决的数量；
- mental-model revisions 的数量和类型；
- revised configurations 的类型；
- revised run 是否符合预测；
- confidence 前后变化；
- 不同界面资源触发 sensemaking episode 的次数。

由于 N = 12，这些量化数据只作为探索性描述，不做 domain 之间的统计显著性比较。

### 9.5 反例与失败案例

必须报告：

- 两个配置产生的行为几乎没有差异；
- 参与者把随机性误认为 configuration effect；
- participant explanation 缺少 trace 支持；
- Judge 误导或造成过度依赖；
- 比较增加而不是减少不确定性；
- revised configuration 未产生预期变化；
- BrowserUse timeout 或 incomplete trajectory；
- 参与者最终决定不修改任何配置。

## 10. 研究主张边界

如果数据支持，本研究可以说明：

- 用户如何现场构造 GUI Agent 配置；
- comparative trajectories 如何支持 Agent behavior sensemaking；
- 用户的配置与行为心智模型如何发生变化；
- 新的理解如何影响下一次配置和小规模 hypothesis testing；
- 这些过程在哪些已观察领域中重复出现或失效。

本研究不能声称：

- 单次 revised run 证明 configuration 导致了某种 behavior；
- EvalAgent 已在所有 WebHarbor domains 中得到验证；
- N = 12 足以进行 domain-level statistical comparison；
- criteria 或 Judge evidence 是意义建构的唯一来源；
- 所有 participants 都能通过比较得到更正确的理解。

## 11. 论文中的建议定位

建议将原研究和新增研究明确分开：

> 原 controlled component study 提供 structural alignment 和 evidence highlighting 如何支持比较与检查的探索性证据。新增的 in-session developer sensemaking study 则考察完整过程：用户如何现场探索任务、配置 Agent、比较 trajectories、修正心智模型，并测试后续配置。

新增研究的结果章节建议使用：

1. From Open-Ended Task Exploration to Agent Configuration
2. Making Sense of Alignable Similarities and Differences
3. Surprises, Contradictions, and Mental-Model Revision
4. From Interpretation to Reconfiguration
5. Testing and Challenging Configuration-Behavior Hypotheses
6. Cross-Domain Patterns and Boundaries

criteria evolution 可以在参与者自发使用 criteria 时作为次要发现出现，但不应成为新增研究的组织主线。
