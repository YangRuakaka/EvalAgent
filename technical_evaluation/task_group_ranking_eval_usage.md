# task_group_ranking_eval.py 使用说明

这份文档只说明两件事：

- 怎么运行
- 参数怎么设置

## 1. 运行前提

- 在仓库根目录执行命令。
- 使用当前项目的 Python 环境。
- 如果运行 `llm-rank` 或 `full`，需要先配置好后端评审模型所需的环境变量；脚本会自动尝试读取以下位置的 `.env`：
  - `technical_evaluation/.env`
  - `backend/.env`
  - 仓库根目录 `.env`
- 如果只运行 `group` 或 `inter-agreement`，不依赖 LLM API。

推荐从仓库根目录执行：

```bash
python technical_evaluation/task_group_ranking_eval.py --help
```

如果不写子命令，脚本会自动默认使用 `full`。

例如下面两条命令等价：

```bash
python technical_evaluation/task_group_ranking_eval.py full
python technical_evaluation/task_group_ranking_eval.py
```

## 2. 命令结构

脚本支持 4 个子命令：

- `group`：按任务把数据集 JSON 分组，生成 manifest
- `llm-rank`：对每个任务组运行 LLM 排序
- `inter-agreement`：计算 LLM 排序和人工排序的一致性
- `full`：直接运行完整流程，包含分组和 LLM 排序；如果提供人工排序文件，还会继续计算一致性

通用调用格式：

```bash
python technical_evaluation/task_group_ranking_eval.py <command> [options]
```

查看某个子命令的参数：

```bash
python technical_evaluation/task_group_ranking_eval.py group --help
python technical_evaluation/task_group_ranking_eval.py llm-rank --help
python technical_evaluation/task_group_ranking_eval.py inter-agreement --help
python technical_evaluation/task_group_ranking_eval.py full --help
```

## 3. group：先把数据按任务分组

### 示例

最常用：

```bash
python technical_evaluation/task_group_ranking_eval.py group
```

指定数据目录和输出文件：

```bash
python technical_evaluation/task_group_ranking_eval.py group \
  --dataset-dir technical_evaluation/results/dataset_grouped_by_task_v2 \
  --json-pattern "**/*.json" \
  --output-file technical_evaluation/results/task_groups_latest.json
```

除了生成 manifest，还把文件拷贝到按任务分好的目录：

```bash
python technical_evaluation/task_group_ranking_eval.py group \
  --materialize-dir technical_evaluation/results/task_groups_materialized
```

### 参数

- `--dataset-dir`
  - 输入数据目录。
  - 默认值：`technical_evaluation/results/dataset_grouped_by_task_v2`
- `--json-pattern`
  - JSON 文件匹配规则。
  - 默认值：`**/*.json`
  - 常见写法：
    - `"**/*.json"`：递归扫描全部子目录
    - `"*.json"`：只扫描当前目录
- `--output-file`
  - 分组结果 manifest 输出路径。
  - 默认值：`technical_evaluation/results/task_groups_latest.json`
- `--materialize-dir`
  - 可选。
  - 如果传入这个参数，脚本会把同组文件复制到这个目录下，按任务组生成子目录。

## 4. llm-rank：对每个任务组做排序

### 示例

最常用：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank
```

指定单个 judge 模型：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank --judge-model deepseek-chat
```

一次跑多个 judge 模型：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank \
  --judge-models gpt-5 deepseek-chat
```

只跑某个任务子目录：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank \
  --dataset-dir technical_evaluation/results/dataset_grouped_by_task_v2/buy_shoes \
  --json-pattern "*.json"
```

手动覆盖 criteria2：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank \
  --criteria2-text "Prefer the option that best satisfies the user's value preference."
```

### 参数

- `--dataset-dir`
  - 输入数据目录。
  - 默认值：`technical_evaluation/results/dataset_grouped_by_task_v2`
- `--json-pattern`
  - JSON 匹配规则。
  - 默认值：`**/*.json`
- `--groups-file`
  - 可选。
  - 如果已经有分组 manifest，可以直接传入，不再现场重新分组。
- `--output-dir`
  - 输出目录。
  - 默认值：`technical_evaluation/results`
- `--criteria2-text`
  - 可选。
  - 作用：强制所有任务组都使用同一条 criteria2 断言。
  - 如果不传：脚本会从每个数据集 JSON 里读取 `criteria2` 或 `criteria_2`。
  - 如果同一个组里存在多条不同的非空 criteria2，且你没有显式传这个参数，该组会被跳过，原因是 `multiple_criteria2_in_group`。
- `--judge-model`
  - 可选。
  - 指定单个 judge 模型。
- `--judge-models`
  - 可选。
  - 指定多个 judge 模型。
  - 支持空格分隔，也支持逗号分隔。
  - 这个参数优先级高于 `--judge-model`。
  - 如果两个都不传，默认会跑两个模型：
    - `gpt-5`
    - `deepseek-chat`
- `--min-group-size`
  - 默认值：`2`
  - 只有组内样本数大于等于这个值才会进入排序评测。

### 输出结果

每次运行都会在输出目录下生成一个时间戳目录，例如：

```text
technical_evaluation/results/task_group_ranking_20260314_153000/
```

主要文件：

- `llm_group_ranking.json`
  - LLM 排序汇总结果
- `human_ranking_template.json`
  - 给人工标注/人工排序用的模板
- `raw/`
  - 每个任务组的原始 judge 返回结果
- `_normalized/`
  - 为后端 judge 生成的标准化中间文件

如果用了多个 judge 模型，输出会先按模型名分子目录，例如：

```text
technical_evaluation/results/gpt-5/task_group_ranking_时间戳/
technical_evaluation/results/deepseek-chat/task_group_ranking_时间戳/
```

## 5. inter-agreement：计算 LLM 和人工排序一致性

### 示例

```bash
python technical_evaluation/task_group_ranking_eval.py inter-agreement \
  --llm-ranking-file technical_evaluation/results/task_group_ranking_20260314_153000/llm_group_ranking.json \
  --human-ranking-file technical_evaluation/results/task_group_ranking_20260314_153000/human_ranking_template_filled.json \
  --output-file technical_evaluation/results/task_group_ranking_20260314_153000/inter_agreement.json
```

### 参数

- `--llm-ranking-file`
  - 必填。
  - `llm-rank` 生成的汇总文件，通常就是 `llm_group_ranking.json`。
- `--human-ranking-file`
  - 必填。
  - 人工完成排序后的 JSON 文件。
- `--output-file`
  - 可选。
  - 如果传入，会把一致性结果写到指定文件。
  - 如果不传，只在控制台打印摘要。

### 输出指标

脚本会统计：

- `spearman_mean`
- `kendall_tau_b_mean`
- `top1_agreement_rate`
- 每个任务组的对比明细

## 6. full：一条命令跑完整流程

### 示例

直接运行完整流程：

```bash
python technical_evaluation/task_group_ranking_eval.py full
```

指定多个 judge 模型：

```bash
python technical_evaluation/task_group_ranking_eval.py full \
  --judge-models gpt-5 deepseek-chat
```

完整流程并在最后计算人工一致性：

```bash
python technical_evaluation/task_group_ranking_eval.py full \
  --human-ranking-file technical_evaluation/results/human_ranking.json
```

### 参数

- `--dataset-dir`
  - 默认值：`technical_evaluation/results/dataset_grouped_by_task_v2`
- `--json-pattern`
  - 默认值：`**/*.json`
- `--output-dir`
  - 默认值：`technical_evaluation/results`
- `--criteria2-text`
  - 可选，含义同 `llm-rank`
- `--judge-model`
  - 可选，含义同 `llm-rank`
- `--judge-models`
  - 可选，含义同 `llm-rank`
- `--min-group-size`
  - 默认值：`2`
- `--human-ranking-file`
  - 可选。
  - 如果提供，脚本会在完成 LLM 排序后继续生成 `inter_agreement.json`。

## 7. 参数怎么选

### 只想先确认分组对不对

用 `group`：

```bash
python technical_evaluation/task_group_ranking_eval.py group
```

### 只想跑一个模型

用 `--judge-model`：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank --judge-model deepseek-chat
```

### 想同时比较多个 judge 模型

用 `--judge-models`：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank --judge-models gpt-5 deepseek-chat
```

### 只想重跑一个任务组

把 `--dataset-dir` 指到某个任务子目录，并把 `--json-pattern` 改成 `*.json`：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank \
  --dataset-dir technical_evaluation/results/dataset_grouped_by_task_v2/buy_shoes \
  --json-pattern "*.json"
```

### 数据里没有统一的 criteria2

显式传 `--criteria2-text`，避免某些组被跳过：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank \
  --criteria2-text "Prefer the option that best matches the target user value."
```

### 只保留样本数足够的组

调大 `--min-group-size`：

```bash
python technical_evaluation/task_group_ranking_eval.py llm-rank --min-group-size 3
```

## 8. 常见默认值汇总

- 默认子命令：`full`
- 默认数据目录：`technical_evaluation/results/dataset_grouped_by_task_v2`
- 默认 JSON 匹配：`**/*.json`
- 默认输出目录：`technical_evaluation/results`
- 默认最小组大小：`2`
- 默认 judge 模型集合：`gpt-5` 和 `deepseek-chat`

## 9. 最短可用命令

只生成分组：

```bash
python technical_evaluation/task_group_ranking_eval.py group
```

直接跑完整流程：

```bash
python technical_evaluation/task_group_ranking_eval.py full
```

或直接省略子命令：

```bash
python technical_evaluation/task_group_ranking_eval.py
```