# AI Judge 功能框架文档

## 1. 概述
AI Judge 是一个多粒度、动态评估系统，旨在根据不同的评估标准（Criteria），智能选择最合适的分析维度来评估 Agent 的执行表现。

整个流程从 **Agent 运行结果** 开始，经过 **任务分解** 与 **粒度分析**，进入 **三个不同层级（Level）的处理逻辑**，最终生成 **评估结果**。

## 2. 整体流程

1.  **输入**: 读取 Agent 的历史运行日志（History Logs）。
2.  **预处理 (Pre-processing)**:
    *   **任务分解 (Task Decomposition)**: 将线性的步骤流分解为语义化的子任务簇（Clusters）。
    *   **粒度分析 (Granularity Analysis)**: 针对每一个评估标准（Criterion），决定采用哪种粒度（Step, Phase, Global）进行评估。
3.  **分层处理 (Multi-Level Processing)**: 根据确定的粒度，将原始数据聚合为特定的上下文格式。
4.  **评估 (Evaluation)**: LLM Judge 基于聚合后的上下文进行判定。
5.  **输出**: 生成包含判定结果、理由及原始证据引用的评估报告。

---

## 3. 详细处理逻辑与数据格式

### 3.1 输入数据：Agent 运行结果 (Agent Execution Results)
*   **来源**: `history_logs/*.json`
*   **核心数据结构**: 步骤列表 (`List[Step]`)。
*   **单步数据格式 (Example)**:
    ```json
    {
      "step": 1,
      "thinking": "思考过程...",
      "memory": "当前记忆状态...",
      "action": "click(Element ID)",
      "next_goal": "下一步的目标...",
      "evaluation_previous_goal": "上一目标完成情况..."
    }
    ```

---

### 3.2 三种不同 Level 的处理逻辑

AI Judge 根据评估标准的特性，将处理逻辑分为三个层级。每个层级负责不同的聚合方式和上下文构建。

#### Level 1: 步骤级 (STEP_LEVEL)
*   **适用场景**: 关注微观操作的正确性、每一步的推理逻辑、是否存在幻觉（Hallucination）或操作失误。
*   **处理逻辑**:
    1.  **不进行聚合**，将每一步视为独立单元。
    2.  **编码 (Encoding)**: 使用 `StepAggregatorService` 将每一步的详细信息压缩为一行简洁的编码（Thinking -> Action -> Outcome）。
    3.  **映射 (Mapping)**: 建立编码文本与原始步骤索引的直接映射。
*   **涉及的数据格式 (AggregatedSteps)**:
    ```json
    {
      "granularity": "step_level",
      "aggregated_content": "Step 1: [Search item] -> [Click Search] -> [Results verification]\nStep 2: ...",
      "step_mapping": {
        "Step 1": [1],
        "Step 2": [2]
      },
      "summary_metadata": {}
    }
    ```
*   **LLM 上下文**: 提供具体每一步的精细细节，通常用于逐个检查。

#### Level 2: 阶段/子任务级 (PHASE_LEVEL)
*   **适用场景**: 关注子任务的完成度、探索过程的合理性、一系列动作的逻辑连贯性。
*   **处理逻辑**:
    1.  **基于聚类 (Clustering)**: 利用预处理阶段生成的 `TaskDecomposition` 结果，将步骤分组为 "Phase" 或 "Cluster"。
    2.  **摘要 (Summarization)**: 对每个簇（Cluster）生成 2-3 句话的摘要，描述该阶段的主要目标和完成情况。
    3.  **映射 (Mapping)**: 建立阶段摘要与该阶段包含的所有步骤索引列表的映射。
*   **涉及的数据格式 (AggregatedSteps)**:
    ```json
    {
      "granularity": "phase_level",
      "aggregated_content": "Phase A (Steps 1-3): User navigated to Amazon and searched for milk.\nPhase B (Steps 4-6): User compared prices and selected the cheapest option.",
      "step_mapping": {
        "Phase A": [1, 2, 3],
        "Phase B": [4, 5, 6]
      },
      "summary_metadata": {
        "cluster_summaries": { "cluster_1": "Summary text..." }
      }
    }
    ```
*   **LLM 上下文**: 提供中层视野，隐藏单步的繁琐细节，突出阶段性成果。

#### Level 3: 全局摘要级 (GLOBAL_SUMMARY)
*   **适用场景**: 关注整体策略（Strategy）、最终任务是否成功、效率评估、Persona 一致性。
*   **处理逻辑**:
    1.  **全量聚合 (Full Aggregation)**: 综合所有步骤和阶段信息。
    2.  **叙事生成 (Narrative Generation)**: 生成一段高层级的叙事性总结，描述 Agent 的整体解题思路、遇到的重大转折和最终结果。
    3.  **映射 (Mapping)**: 映射指向所有步骤（或不强调具体步骤）。
*   **涉及的数据格式 (AggregatedSteps)**:
    ```json
    {
      "granularity": "global_summary",
      "aggregated_content": "The agent adopted a cost-saving strategy by verify prices across multiple pages before making a decision. It successfully purchased the item but took a longer path than necessary.",
      "step_mapping": {
        "global_trace": [1, 2, 3, 4, 5, 6, ...]
      },
      "summary_metadata": {
        "execution_outcome": "Success",
        "strategy_description": "..."
      }
    }
    ```
*   **LLM 上下文**: 提供上帝视角，忽略具体操作细节，专注于宏观评价。

---

### 3.3 评估结果 (Evaluation Results)

无论采用哪种 Level 的处理逻辑，最终都会输出统一格式的评估结果。

*   **数据实体**: `EvaluationResult`
*   **数据格式**:
    ```json
    {
      "criterion_name": "Cost Efficiency",
      "verdict": "PASS",  // 或 FAIL, UNSURE
      "reasoning": "The agent consistently sorted by price low-to-high...",
      "confidence_score": 0.95,
      "used_granularity": "global_summary",
      "evidence": {
        // 可选：引用具体的 AggregatedContent 片段或原始步骤 ID
      }
    }
    ```

## 4. 关键服务类对应
*   **TaskDecomposerService**: 负责生成 Phase Level 所需的 Clusters。
*   **StepAggregatorService**: 核心转换器，实现了上述三种 Level 的 `_aggregate_*` 逻辑。
*   **JudgeEvaluatorService**: 协调者，调用上述服务并与 LLM 交互进行最终判定。
*   **GranularityAnalyzerService**: 决策者，决定使用哪个 Level。
