# LLM as a Judge 处理逻辑详解（统一架构版）

> 当前代码已移除原三种 granularity 分支处理，统一为单一路径：
> **Criteria 解释维度 -> 维度驱动 phase 切分 -> phase 评估 -> 证据校验/修复 -> 汇总**。

## 1) 单一处理链路

1. 输入：`task + personas + criterion + all_steps`。
2. Criteria Interpretation：LLM 将 criterion 转成可观测评估维度（dimensions）。
3. Phase Segmentation：LLM 基于 dimensions 对全量 steps 切分 phase，并标记相关 phase。
4. Phase Evaluation：对相关 phase 并发评估，抽取结构化 evidence。
5. Evidence Grounding：校验 evidence `highlighted_text` 是否是原始 step 文本 substring。
6. Evidence Repair：若不满足 substring 约束，对该 step 触发 AI 重提取一次证据。
7. Result Merge：多 phase 结果合并成单 criterion verdict。
8. Overall Assessment：按 criterion 汇总输出 condition 结果；多 condition 再做横向 ranking。

## 2) 代码入口

- 主入口：`POST /judge/evaluate-experiment`
- 单 criterion 主流程：`JudgeEvaluatorService.evaluate_criterion_unified`
- 核心文件：
  - `app/services/judge_evaluator.py`
  - `app/services/evaluation_prompts.py`
  - `app/api/judge.py`

## 3) 统一 Prompt 集

仅保留以下 prompt：
1. `get_criterion_interpretation_prompt`
2. `get_phase_segmentation_prompt`
3. `get_unified_phase_evaluation_prompt`
4. `get_evidence_reextract_prompt`
5. `get_merge_results_prompt`
6. `get_overall_criterion_assessment_prompt`

## 4) 证据准确性策略

- 一次评估返回 evidence 后，先做 substring 严格校验；
- 若失败：在声明 step 上执行 `evidence_reextract_prompt`；
- 仅当重提取文本能在原 step 字段中精确命中，才保留；
- 最终输出 evidence 全部可在原始 steps 追溯。

## 5) 已删除的旧架构能力

- 旧三分支执行路径（step/phase/global 的独立处理代码）
- 旧的 granularity 分析、独立 step 聚合、旧分解调度链路
- API 旧调试接口：
  - `/judge/analyze-granularity`
  - `/judge/decompose-task`
  - `/judge/aggregate-steps`

## 6) 当前设计目标

- 架构唯一：避免双路径和分支漂移。
- 证据可信：先校验后修复。
- 扩展集中：后续改动只需修改统一链路和统一 prompt。