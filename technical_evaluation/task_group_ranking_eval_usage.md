# task_group_ranking_eval.py 快速说明

只保留两件事：

- 怎么换模型
- 怎么切换 baseline / 非 baseline

## 固定数据集

脚本默认数据集目录就是：

/Users/yukunyang/Documents/GitHub/EvalAgent/technical_evaluation/dataset/dataset_grouped_by_task

会递归读取该目录下所有子文件夹的 JSON。当前代码按子文件夹分组，每组做二选一排序（预期每组 2 个 JSON）。

## 两种 ranking 模式

- criteria2
  - 走你的后端 evaluate + rank 逻辑。
- baseline
  - 直接把同组两个 JSON 的关键信息给 LLM 做排序，不走后端 evaluate_experiment。
  - 但 baseline 也会使用 criteria2 作为排序标准（与 criteria2 模式一致）。

## criteria2 来源（两种模式都一样）

- 优先使用 --criteria2-text（全组统一覆盖）
- 不传时，读取每个组内 JSON 的 criteria2 / criteria_2
- 如果同组出现多个不同 criteria2：该组跳过（multiple_criteria2_in_group）
- 如果组内没有 criteria2：该组跳过（missing_criteria2）

通过 --run-modes 控制：

- 只跑后端逻辑：--run-modes criteria2
- 只跑 baseline：--run-modes baseline
- 两种都跑：--run-modes criteria2 baseline

## 运行命令（仓库根目录）

单模型，后端逻辑（非 baseline）：

python technical_evaluation/task_group_ranking_eval.py llm-rank --judge-model gpt-5 --run-modes criteria2

单模型，baseline：

python technical_evaluation/task_group_ranking_eval.py llm-rank --judge-model gpt-5 --run-modes baseline

多模型，后端逻辑（非 baseline）：

python technical_evaluation/task_group_ranking_eval.py llm-rank --judge-models gpt-5 deepseek-chat --run-modes criteria2

多模型，baseline：

python technical_evaluation/task_group_ranking_eval.py llm-rank --judge-models gpt-5 deepseek-chat --run-modes baseline

多模型，同时跑两种模式：

python technical_evaluation/task_group_ranking_eval.py llm-rank --judge-models gpt-5 deepseek-chat --run-modes criteria2 baseline

## 模型参数规则

- --judge-model：单个模型
- --judge-models：多个模型（空格或逗号分隔）
- 两者都不传：默认跑 gpt-5 和 deepseek-chat

## 输出目录

默认输出目录：

technical_evaluation/results

多模型或多模式时，会自动分子目录保存结果。
