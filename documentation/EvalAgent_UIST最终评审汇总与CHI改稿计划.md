# EvalAgent：UIST 最终评审汇总与 CHI 改稿计划

> 论文：*EvalAgent: Interactive Comparative Evaluation of Computer-Using GUI Agents*  
> 整理日期：2026-07-22  
> 文档目的：将 UIST first-round review、rebuttal、post-rebuttal review 和 PC meeting decision 转化为 CHI 2027 可执行改稿方案。

## 1. 核心结论

这不是一次“研究方向错误”的拒稿，而是一次“证据尚未覆盖主张范围”的拒稿。

UIST reviewers 和 PC 认可了以下方面：

- 研究问题重要且及时：只评估 GUI agent 的最终成功率，无法说明 agent 为什么做出某个中间决策，也无法发现 value-action gap。
- 系统设计完整：value-conditioned comparative simulation、structural trace visualization 和 evidence-grounded Agentic Judge 形成了连贯的评估工作流。
- 理论依据合理：Evaluability Hypothesis、Structural Alignment Theory 和 process supervision 能够解释比较视图和过程审计的价值。
- 技术评估与用户研究均显示出潜力，特别是 evidence extraction、behavioral divergence discovery 和 criteria evolution。

最终拒稿的主因是：**论文对一般 GUI-agent evaluation 提出了较广泛的主张，但目前 33 个 cases、12 人用户研究和有限任务场景不足以支撑这些主张。**

CHI 版本最重要的工作不是增加更多包装，而是：

1. 收敛 target user、deployment setting 和 contribution scope；
2. 扩大并透明化 empirical validation；
3. 把 rebuttal 中的关键澄清变成主文中的方法、数据、结果和限制；
4. 清楚区分 EvalAgent 与 observability、error attribution、LLM comparison、objective specification、co-planning 和 bidirectional alignment 文献。

## 2. UIST 最终评审汇总

### 2.1 评分与最终决策

| 角色 | 最终倾向 | 主要认可 | 主要保留意见 |
|---|---|---|---|
| 1AC / Meta-review | 3.0 Borderline | 问题及时，系统整合周全 | 验证规模与泛化、适用假设、相关工作定位 |
| R1 / 2AC | 2.5 Weak Reject | 动机强、写作清楚 | N=12；任务范围不清；Phase 3 证据不足 |
| R2 | 4.0 Probably Accept | 技术评估和用户评估都有价值 | 数据集小且为内部数据；文献类别和差异需要更准确 |
| R3 | 3.0 Borderline | 理论基础与 ablation 有说服力 | 部署范式、persona 现实性、hash 阈值、相关文献遗漏 |

PC meeting 后的最终结论是拒稿。委员会认为：

- empirical validation 相对 contribution scope 仍然偏弱；
- 跨 GUI-agent tasks、domains 和 deployment settings 的 generalizability 没有充分证明；
- 与已有 agent evaluation / observability systems 的定位还需要精炼；
- rebuttal 回答了许多问题，但关键澄清没有充分体现在 submitted manuscript 中。

### 2.2 一致认可的贡献

1. **问题框架有价值。** Outcome-only evaluation 无法解释中间决策、隐藏风险和偏好冲突。
2. **工作流完整。** Comparative simulation、aligned trace visualization 和 Agentic Judge 不是彼此孤立的功能，而是一个完整的人机审计流程。
3. **过程审计具有潜力。** Reviewers 认可 phase-level review protocol、trace auditing 和 evidence linking。
4. **用户研究方向适合 HCI。** 研究不只测总体质量，而是分析用户如何发现差异、查找证据、形成和修订 evaluation criteria。
5. **技术结果有潜力。** 相对 direct-prompt baseline，pipeline 在 verdict accuracy 和 evidence extraction 上显示出较明显的提升。

### 2.3 最终仍未解决的核心问题

#### A. 证据规模与主张范围不匹配

当前主要证据为：

- 33 个 technical evaluation cases；
- 10 个 comparative ranking case pairs；
- 444 个 evidence-level instances；
- 12 名技术型参与者的用户研究。

这些证据可以支撑 proof-of-concept，但不足以覆盖“GUI agents generally”。PC 明确将这一点视为拒稿主因。

#### B. 任务多样性与可复现性不透明

Rebuttal 解释了：

- 9 个 tasks；
- 4 个 domains：e-commerce、travel、local services、rentals；
- 33 条 value-divergent traces；
- 每条 trace 都有 step-level annotation；
- 3 名研究成员标注，Fleiss' κ = 0.924。

但主文只写了“diverse tasks”，读者无法判断：

- 具体覆盖了哪些任务；
- 任务和 persona/criteria 是如何选择的；
- 每个 domain 有多少 cases；
- traces 的长度、成功/失败比例和复杂度如何；
- 是否存在 researcher degrees of freedom；
- 数据能否复现或公开。

#### C. Phase 3 开放探索没有形成独立证据

主文只把 Phase 3 写成一个 role-playing exploration task，没有清楚报告：

- 六个 replica websites 分别是什么；
- 参与者选择了哪些网站和任务；
- 他们创建了哪些 persona、preference 或 criteria；
- criteria 是否跨 domain 发生变化；
- 哪些发现只来自 Phase 3；
- 有哪些失败、反例或不支持 generalizability 的情况。

R1 在 post-rebuttal comment 中仍将这一点列为主要问题。

#### D. 适用场景与安全边界仍不清楚

Rebuttal 将 EvalAgent 定义为 pre-deployment sandbox，这有效缓解了并行执行多个 GUI agents 的风险疑问。但 R3 仍不认可“帮助终端用户比较 persona 并选择一个用于生产”的 framing。

更可信的现实场景是：

> Provider-side CUA developer 在 sandbox、replica website 或 mocked API 中，用不同 user preferences、policy constraints、prompt variants 或 model variants 对 agent 做 deployment 前 robustness testing。

#### E. Persona 作为实验变量过粗

实际 agent development 中更常见的是：

- system prompt 的小幅修改；
- policy 或 preference constraint；
- model/configuration variation；
- prompt template 或 tool policy variation。

完整 persona shift 并不是唯一或最常见的开发实践。CHI 版本应把 independent variable 从 persona 扩展为 **preference / policy / prompt configuration**。

#### F. Hashing 机制缺少可靠性验证

Rebuttal 说明系统使用 256-bit perceptual hash 和约 9% Hamming-distance tolerance，但仍缺少：

- 9% 阈值的选择依据；
- threshold sensitivity analysis；
- false merge 与 false split；
- 动态内容、价格/选项变化等 failure cases；
- 与 aHash、pHash、SSIM、DOM/state features 或 hybrid 方法的比较。

论文当前的“controlled environment guarantees hash stability”表述过强。Controlled environment 可以降低噪声，但不能直接保证状态合并的语义正确性。

#### G. 相关工作与 novelty boundary 不足

Reviewers 指出的相关工作包括：

- AgentLens；
- LLM Comparator；
- CLEAR / Agentic CLEAR；
- ErrorMap；
- MAST、TRAIL、Who&When；
- Just-In-Time Objectives；
- Cocoa；
- Shen et al. 的 bidirectional human-AI alignment。

不能把这些工作全部笼统称为 observability systems。需要按功能类别梳理，并说明 EvalAgent 与每类工作的关系。

#### H. 统计与指标解释仍需深化

Rebuttal 给出了 t-test、Cohen's d 和 95% CI，但主文仍主要报告均值。

另外，literal-substring grounding 只证明 evidence text 来自原始 trace，不等于：

- evidence 在语义上正确；
- evidence 对 criterion 完整；
- evidence 是用户真正需要的关键证据；
- evidence 不会导致 automation bias。

## 3. Rebuttal 的处理效果

| 议题 | Rebuttal 状态 | CHI 版本必须做什么 |
|---|---|---|
| Deployment / 多轨迹风险 | 部分解决 | 在摘要、引言、scenario 和 discussion 中统一写成离线或模拟的 deployment 前审计，并列出不适用任务 |
| 33 cases 来源 | 解释清楚但未进入正文 | 加入 dataset construction、task inventory、trace statistics、annotation protocol 和 reproducibility materials |
| Phase 3 多样性 | 未充分解决 | 单独报告六站点、自选任务、criteria/persona 类型和跨域发现 |
| 统计严谨性 | 方向正确 | 正文报告 effect size、CI、检验假设和 exploratory framing |
| Hash / DG 术语 | 基本澄清 | 实证验证阈值；DAG 改为 DG；避免未经支持的 causal claim |
| Related work | 承诺补充 | 逐类定位并进入主文，不能只在 rebuttal 中列文献 |

## 4. CHI 版本的建议定位

### 4.1 建议定位句

> EvalAgent is a pre-deployment auditing environment for GUI-agent developers to stress-test how prompt and preference configurations shape process-level behavior, compare aligned trajectories, and inspect criterion-specific evidence before real-world deployment.

### 4.2 目标用户

主要用户：

- provider-provided CUA 的开发者；
- QA / evaluation researchers；
- responsible-AI auditors；
- agent platform 或 model provider 的评估团队。

次要用户可以包括配置 personal agent 的高级终端用户，但不应再把普通终端用户作为唯一或最强的现实性论据。

### 4.3 主要使用流程

1. 在 sandbox / replica / mocked API 中定义任务；
2. 生成或手动配置 preference、policy、prompt 或 model variants；
3. 批量运行 agent trajectories；
4. 通过 aligned trajectory graph 定位 divergence；
5. 使用 criteria-driven Agentic Judge 查找证据；
6. 检查 value-action gap、configuration robustness 和 judge reliability；
7. 决定是否修改 prompt、policy、agent design 或 evaluation criteria；
8. 只把通过部署前审计的单一 configuration 用于生产。

### 4.4 适用与不适用边界

| 任务条件 | EvalAgent 是否适合 | 更合适的范式 |
|---|---|---|
| 可模拟、可回放，存在多种有效行为 | 非常适合 | Comparative offline auditing |
| 可逆、低风险，需要理解 preference sensitivity | 适合 | Comparison + evidence audit |
| 目标尚未定义清楚，需要人与 AI 共同规划 | 有限适合 | 先 objective elicitation / co-planning |
| 购买、发送、删除等不可逆或高风险动作 | 不应在真实环境中并行执行 | Mock/sandbox；生产中单轨迹 + approval gates / co-execution |

这部分应进入 Discussion，而不只是 Limitations。它可以将 R3 的质疑转化为一个设计空间：comparative auditing、objective specification 和 co-planning/co-execution 是互补范式，适用于不同任务阶段。

### 4.5 收敛后的贡献声明

建议将贡献收敛为以下四项：

1. **概念贡献：**提出 preference-conditioned process auditing 的设计空间，明确其适用条件，以及它与 objective specification、co-planning 的互补关系。
2. **系统贡献：**将 prompt/preference variation、aligned trajectory graph 和 criterion-grounded evidence audit 集成为 deployment 前工作流。
3. **实证贡献：**揭示结构化比较和 evidence surfacing 如何改变开发者发现行为差异、验证 judge 和演化 evaluation criteria 的过程。
4. **方法/数据贡献（补足后）：**发布透明的 value-divergent GUI-agent trace corpus、标注协议和 hash reliability benchmark。

不要再把“bidirectional human-AI alignment”本身作为主要原创概念。更稳妥的表述是：criteria evolution 是该既有理论框架在 GUI-agent auditing 场景中的一种实例化现象。

## 5. 必做改稿清单

### P0：不完成就不建议投稿

- [ ] 重写摘要、引言和 motivating scenario，统一为 provider-side developer 的 pre-deployment sandbox。
- [ ] 删除或改写在真实网页上并行执行多个不可逆任务的暗示。
- [ ] 将 9 tasks / 4 domains / 33 cases / 444 evidence instances 完整写入正文。
- [ ] 公开 task list、configuration matrix、trace length、success/failure distribution、criteria type、model/environment 和 inclusion/exclusion logic。
- [ ] 扩展 empirical coverage，加入外部或公开可复现的环境/任务。
- [ ] 如果不能直接使用 WebArena / BrowserGym 数据，给出清楚的 adaptation protocol 和 value-conditioned variants。
- [ ] 补做 hashing reliability study：ground truth、threshold sweep、false merge/false split 和 failure cases。
- [ ] 将 Phase 3 写成独立结果，报告六个 replica sites、participants、tasks、criteria/persona evolution 和跨域边界。
- [ ] 重构 related work，逐类对比 reviewers 指出的研究。
- [ ] 正确引用 Shen et al.，并重新表述 bidirectional alignment contribution。
- [ ] 将 DAG 全部改为 DG；除非补充正式因果模型，否则不要称为 Causal Trajectory View。

### P1：显著提高 CHI 竞争力

- [ ] 扩大并重构用户研究，以真实 CUA developers/evaluators 为主要样本。
- [ ] 根据功效分析确定样本量，不要直接用经验数字替代 power analysis。
- [ ] 增加 participant-selected 或 work-relevant open-ended tasks。
- [ ] 将 independent variable 从 persona 扩展为 preference/policy/prompt configuration。
- [ ] 报告 paired effect sizes、bootstrap/95% CI、检验假设和必要的 non-parametric sensitivity analysis。
- [ ] 控制 multiple comparisons，继续把小样本量化结果称为 exploratory。
- [ ] 加入 Agentic Judge pipeline ablation、stronger fair baselines、holdout split 和跨域不确定性分析。
- [ ] 区分 grounding、semantic correctness、coverage、precision 和 usefulness。
- [ ] 报告 graph size、trace length、运行成本/延迟和 judge 调用次数。
- [ ] 展示 graph density 很高时的 semantic zoom、clustering 或 progressive disclosure。

### P2：写作与呈现

- [ ] 高分辨率重画系统图，清楚显示 configuration → execution → alignment → criteria → evidence → decision。
- [ ] 增加 reasoning/evidence panel 的局部放大图和交互说明。
- [ ] 将 Causal Trajectory View 改为 Aligned Trajectory Graph/View。
- [ ] 改写“identical states”“guaranteed hash stability”“large-scale evidence set”等过强表述。
- [ ] 增加 reproducibility appendix / artifact：task templates、prompt variants、annotation manual、judge prompts、data schema、interface video 和匿名代码。

## 6. 建议新增实验包

### 6.1 技术评估

#### Experiment A：Corpus scale and diversity

需要报告：

- task domains 和 task types；
- information seeking、comparison、form filling、transaction-like、long-horizon 等任务分布；
- 每类 cases 数量；
- trajectory length、branch count、state count 和 failure type；
- preference / policy / prompt variations；
- agent/model configurations；
- inclusion/exclusion criteria。

不要再只使用“diverse”描述数据。

#### Experiment B：External validity

在公开 benchmark environment 或可复现 replica 上构造 preference-conditioned task variants，并说明：

- 原 benchmark 的哪些部分被保留；
- 哪些 preference/value conditions 是新增的；
- 为什么这些修改仍然可复现；
- EvalAgent 在 held-out tasks 或 held-out domain 上是否有效。

#### Experiment C：Judge robustness

按 task/domain/configuration 分层报告：

- verdict accuracy；
- ranking performance；
- evidence grounding；
- evidence precision/recall；
- semantic correctness；
- evidence usefulness。

建议加入 bootstrap CI、held-out task 和 leave-one-domain-out evaluation。

#### Experiment D：Baseline fairness and ablation

Direct prompt 之外至少比较：

- phase segmentation only；
- evidence retrieval only；
- full pipeline；
- structured prompting baseline；
- 不同 judge model；
- 不同 context-selection strategy。

#### Experiment E：Hash reliability

建立人工标注的 screenshot-pair ground truth，报告：

- threshold sweep；
- precision/recall 或 false merge/false split；
- 关键状态差异的典型 failure cases；
- 动态 UI、广告、价格和选项变化的影响；
- aHash、pHash、SSIM、DOM/state features 和 hybrid approach 的比较。

### 6.2 人本评估

#### 研究对象

优先招募真实 agent developers/evaluators。如果保留终端用户，需要分层报告两类用户的任务、需求和结果，不能混为一谈。

#### 研究任务

同时保留两种任务：

1. Controlled comparison：用于测量结构化图和 evidence highlighting 的组件效应；
2. Ecological exploration：参与者选择自己熟悉或工作相关的 agent task，用于测量生态有效性。

#### Study design

- 如果样本量允许，采用完整的 within-subject counterbalancing；
- 如果不允许，应缩小研究问题，避免每个 ablation 只有 6 人却支撑广泛结论；
- 明确 primary outcomes，例如 divergence-detection accuracy/time、evidence-verification accuracy、criteria specificity/coverage；
- NASA-TLX 作为辅助指标，而不是唯一主要结果。

#### Criteria evolution analysis

建立可复核的 coding scheme，并报告：

- coding procedure；
- coder training；
- inter-rater agreement；
- criteria 的 granularity 和 dimensionality 如何变化；
- 没有发生演化的案例；
- 参与者形成错误 criteria 或过度依赖 judge 的反例。

### 6.3 最小可行版本与理想版本

| 版本 | 新增工作 | 可以支撑的主张 |
|---|---|---|
| 最小可行 | 透明化现有 corpus；补 hash validation；写全 Phase 3；重定位与补文献；完整统计 | 一个经过初步验证的 pre-deployment audit workflow；主张必须收敛 |
| 理想版本 | 扩展公开/外部任务、开发者样本、开放任务、跨域 holdout 和 scalability evaluation | 对 GUI-agent developer auditing 的效用与可迁移性提供更强 CHI 证据 |

## 7. 逐章节重写蓝图

### Title

突出 auditing、pre-deployment 和 preference-conditioned behavior，弱化笼统的 evaluation。

候选标题：

> EvalAgent: Comparative Auditing of Preference-Conditioned GUI Agent Behaviors

### Abstract

建议结构：

1. 定义 provider-side deployment risk；
2. 说明 outcome benchmark 和 raw trace inspection 的缺口；
3. 明确 EvalAgent 是 sandbox；
4. 概述三项核心能力；
5. 量化技术数据规模和用户研究对象；
6. 只写证据支持的结论，不泛化到所有 GUI agents。

### Introduction

建议叙事顺序：

1. Outcome-only evaluation 的局限；
2. Developer 在部署前需要理解 agent behavior；
3. 不同 preference/prompt configuration 可能导致 process-level divergence；
4. 现有工具缺少将 controlled variation、aligned trace comparison 和 evidence audit 集成的工作流；
5. EvalAgent 的 scope、target user 和安全边界；
6. 收敛后的 contributions。

第一页就应回答：谁使用、何时使用、为什么需要 comparison、为什么这不是 co-planning 的替代品。

### Related Work

分为六类：

1. Outcome-based GUI-agent benchmarks；
2. Agent observability and visual analytics；
3. Error attribution and diagnosis；
4. LLM-as-a-judge and evaluation interfaces；
5. Objective elicitation, co-planning and co-execution；
6. Human-AI alignment and criteria evolution。

每类都要写“EvalAgent 继承了什么、与它有什么不同”，不要只做文献罗列。

### Design Goals

- DG1：从 persona experimentation 改为 preference/prompt configuration testing；
- DG2：aligned structural comparison；
- DG3：evidence-grounded scalable auditing。

### System

需要新增或澄清：

- sandbox architecture；
- irreversible action isolation；
- prompt/configuration matrix；
- graph construction；
- hash threshold 和 failure handling；
- judge provenance；
- confidence 的含义；
- cost 和 latency。

### Technical Evaluation

先写 corpus construction 和 data split，再写 research questions、baselines、metrics 和 statistics。必须解释清楚：

- 33 cases 的单位；
- 10 ranking pairs 的构造；
- 444 evidence instances 的来源；
- train/development/holdout 是否分开；
- uncertainty 和跨 domain 表现。

### User Study

将 controlled study 和 ecological exploration 分开：

- 每个阶段明确 task/site、condition、data 和 analysis method；
- 每个 RQ 对应独立结果；
- Phase 3 不能只出现在 procedure 中；
- 报告 automation bias、judge disagreement 和 failure cases。

### Discussion

把 comparative auditing、objective specification 和 co-planning/co-execution 放进同一个 design space。重点讨论：

- developer decision-making；
- preference robustness；
- criteria evolution；
- automation bias；
- calibrated trust；
- deployment gates；
- 不可逆任务的边界。

### Limitations

明确写出：

- 小样本与技术型参与者；
- 内部任务与外部效度；
- hash errors；
- judge model dependence；
- thought-trace validity；
- criteria quality dependence；
- 运行成本；
- 与真实 developer workflow 的差距。

不要用 future work 替代当前验证。

## 8. 相关工作定位表

| 类别 | Reviewers 指出的代表工作 | EvalAgent 应如何区分 |
|---|---|---|
| Agent visual analytics / observability | AgentLens | 强调 GUI execution states 的跨-run structural alignment 与可交互 evidence audit |
| LLM comparison / evaluation | LLM Comparator、CLEAR、Agentic CLEAR | 强调多步 GUI traces，而不是单轮 output；承认 comparison UI 和 judge workflow 的继承关系 |
| Error attribution / diagnosis | ErrorMap、MAST、TRAIL、Who&When | EvalAgent 关注 preference/value misalignment，不仅是 failure taxonomy；比较 attribution granularity |
| Objective specification | Just-In-Time Objectives | 解释何时应先明确目标，何时 post-hoc comparison 能暴露未预见 trade-off |
| Co-planning / co-execution | Cocoa | 高风险真实任务需要前置协作；EvalAgent 主要用于可模拟的 deployment 前审计 |
| Human-AI alignment | Shen et al. 的 bidirectional alignment | 将 criteria evolution 视为既有概念在 agent evaluation 中的实例化，而非重新命名为原创概念 |

建议 novelty sentence：

> Prior systems support agent observability, output comparison, or error attribution; EvalAgent investigates how developers can experimentally vary preference configurations, structurally align resulting GUI trajectories, and audit criterion-specific evidence within one pre-deployment workflow.

## 9. Claim-Evidence 对齐检查

| 拟保留主张 | 所需最低证据 | 当前状态 |
|---|---|---|
| 结构对齐帮助发现 divergence | Controlled comparison 中的准确率/时间 + 定性机制 | 部分具备；需要清楚的 primary measure 与统计 |
| Evidence surfacing 降低审计负担 | 检索/验证表现 + workload + automation-bias observations | 部分具备；需报告 uncertainty 和错误后果 |
| Judge evidence 更贴近人类 | 独立标注、held-out test、semantic correctness/coverage | 444 instances 有潜力；指标定义需加强 |
| 适用于多类 GUI tasks | 跨域 task inventory、公开环境和 domain holdout | 不足，是 PC 主要拒稿理由 |
| 支持 criteria evolution | Coding scheme、前后变化、反例和可靠性 | 有定性案例；缺系统分析 |
| 适合现实部署决策 | 真实 developer workflow 或 field-relevant task | 不足；应收敛为 pre-deployment developer auditing |

## 10. CHI 2027 当前提交约束

截至 2026-07-22，CHI 2027 官方 Papers 页面说明：

- 鼓励 5,000–8,000 words；
- 超过 12,000 words 且无充分理由会 desk reject；
- review 阶段使用 single-column、anonymous 稿件；
- 主 PDF 必须 self-contained，不能依赖 appendix/supplement 才能理解核心贡献；
- Full paper deadline 为 2026-09-10 AoE；
- CHI 2027 保留 revise-and-resubmit 阶段；
- 评审强调 originality、significance、validity、research quality 和 presentation clarity。

本稿当前最需要提升的是 **validity、external validity 和 claim-scope calibration**。

官方来源：<https://chi2027.acm.org/authors/papers/>。提交前需再次核对更新。

## 11. 六周执行计划

| 周 | 核心目标 | 主要产出 | 完成标准 |
|---|---|---|---|
| 1 | 锁定定位与 claims | 新标题、摘要、贡献和 scope table | 所有作者同意 target user 和不适用边界 |
| 2 | 整理/扩展 corpus | Task inventory、data schema、公开环境 adaptation | 每个 case 可追溯、可复现 |
| 3 | 补技术验证 | Hash study、judge ablations、CI/holdout | 关键机制都有 failure analysis |
| 4 | 补人本证据 | Phase 3 重分析；必要时追加 developer study | 每个 RQ 有独立结果段 |
| 5 | 重写全文与图 | Single-column 完整稿、高清图、related work | 主文 self-contained；claims 与证据一一对应 |
| 6 | 内部审稿与复现 | Mock reviews、artifact、匿名与 accessibility 检查 | 能正面回答 UIST 每个未决问题 |

## 12. 投稿前 Go / No-Go 检查

- [ ] 主文是否在第一页明确写出 pre-deployment sandbox、主要用户和不可逆任务边界？
- [ ] 是否列全 9 tasks / 4 domains / 33 cases 的来源与分布？
- [ ] 是否提供足够的匿名化可复现材料？
- [ ] 是否出现至少一种外部或公开可复现任务来源？
- [ ] 如果没有扩展外部任务，是否将 generalizability claim 收敛到现有覆盖范围？
- [ ] Phase 3 是否有独立的 participants × sites × tasks × criteria 结果？
- [ ] Hash 的 9% 阈值是否有验证、敏感性分析和 failure cases？
- [ ] 所有统计结果是否包含 effect size、CI 和检验假设？
- [ ] 是否避免把 exploratory 结果写成 definitive claims？
- [ ] 是否正确引用并区分 AgentLens、comparison/evaluation tools、error attribution、co-planning 和 bidirectional alignment？
- [ ] 每条 contribution claim 是否都能指向至少一项明确方法和一项匹配结果？
- [ ] 视频和 figures 是否体现 developer auditing，而不是终端用户真实购买后的 post-hoc 选择？
- [ ] 是否完成 anonymous、single-column、accessibility、self-contained 和 word-count 检查？

## 附录 A：材料与数字核对

- 技术评估：33 unique cases。
- Comparative ranking：10 case pairs。
- Evidence-level metrics：444 instances。
- 技术标注：3 名研究团队成员；Fleiss' κ = 0.924。
- Rebuttal 补充：9 tasks，覆盖 e-commerce、travel、local services、rentals 四个领域；每条 trace 做 step-level annotation。
- 用户研究：N=12；60–90 分钟。
- Study conditions：所有参与者体验 Full System；6 人比较 No Image Hashing；另 6 人比较 No Evidence Highlight。
- Rebuttal 统计：Mental Demand 显著降低，t=-2.29、d=-0.66、95% CI [-3.10, -0.06]、p<.05；其他 NASA-TLX 维度为非显著趋势。
- 最终决策：PC 认可问题与系统整合，但因验证规模、泛化和定位不足而拒稿。

## 附录 B：本报告使用的材料

1. UIST 2026 submitted manuscript PDF；
2. PCS first-round、post-rebuttal、post-PC reviews 和 decision；
3. 作者 rebuttal；
4. CHI 2027 官方 Papers 页面（仅用于当前提交约束）。

本报告将 reviewer comments 与作者 rebuttal 中的事实分开处理。凡 rebuttal 已承诺但主文尚未呈现的内容，均标记为“需要进入正文”，不视为已经完成修改。
