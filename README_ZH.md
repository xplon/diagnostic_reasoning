# Diagnostic Reasoning

面向医生审核场景的检验单诊疗推理项目骨架。

项目目标是把结构化检验单、病人时间线、医生 gold 评价和可审计推理过程组织起来，让系统能够回答两个问题：

- 给定检验单和已知上下文，AI baseline 会提出哪些医生审核候选动作？
- 给定医生的真实评价，系统能否重建“医生为什么这么说”的中间推理过程？

当前第一阶段重点实现 CBC/血常规推理，同时保留非 CBC 检验单的扩展边界。CBC 是第一批可推理 domain，不是项目最终边界。

## 核心原则

- 检验单是病人时间线中的事件，不是孤立图片。
- 医生 gold answer 只作为病例级监督信号，不能泛化成患者端处方指令。
- 对外部 Codex/AI 工具默认暴露不含 gold 的上下文接口，只有复盘、评测、标注和 owner-supervised 学习才使用 gold。
- 私有数据、原始图片、真实聊天记录、真实病例输出和 API key 不进入公开仓库。

## 快速开始

```bash
uv sync --extra dev
uv run pytest
```

也可以直接用当前 Python 环境运行：

```bash
python -m pytest
```

## 常用 CLI

运行一个 synthetic case：

```bash
uv run diagnostic-reasoning run-case ^
  --data-dir fixtures\synthetic_dataset ^
  --case-id case_synth_002
```

给外部 Codex/AI 工具生成上下文：

```bash
uv run diagnostic-reasoning context ^
  --data-dir fixtures\synthetic_dataset ^
  --case-id case_synth_002 ^
  --format markdown
```

重建医生结论的中间推理：

```bash
uv run diagnostic-reasoning reconstruct-case ^
  --data-dir fixtures\synthetic_dataset ^
  --case-id case_synth_002
```

评估 baseline：

```bash
uv run diagnostic-reasoning eval ^
  --data-dir fixtures\synthetic_dataset
```

## 私有数据导入

真实病例数据只应保存在仓库外或被 `.gitignore` 覆盖的私有目录。导入 reviewed 数据集的命令示例：

```bash
uv run diagnostic-reasoning promote-staging ^
  --staging-dir ..\data_private\lab_ingest_staging ^
  --output-dir ..\data_private\diagnostic_reasoning\reviewed_v0 ^
  --mark-verified
```

## API

安装 API 依赖并启动：

```bash
uv sync --extra api
uv run uvicorn diagnostic_reasoning.server:app --reload
```

主要接口：

- `GET /health`
- `GET /api/v1/cases`
- `GET /api/v1/cases/{case_id}`
- `GET /api/v1/run-case/{case_id}`
- `GET /api/v1/reconstruct/{case_id}`
- `GET /api/v1/reconstruct`
- `GET /api/v1/codex/context/{case_id}?format=markdown`

## 医生结论推理重建

`run-case` 是从检验单出发生成 AI baseline 候选动作。

`reconstruct-case` 是另一条链路：给定医生原话和 gold action，反推出支撑医生判断的事实、趋势、排除理由和安全缺口。这个输出会标记 `uses_doctor_gold=true`，只适合训练、复盘、规则候选和病例记忆，不适合当作 hidden evaluation 的模型预测。

当前实现先覆盖 CBC Phase 1 的可审计结构化重建，同时保留非 CBC/生化病例并标记为 `preserved_out_of_phase1`。医生原话里的药名、针剂和剂量只作为该病例证据保存，不会自动变成可泛化处方规则。

## 真实 LLM 评审

项目提供真实 API 调用脚本，但不会读取命令行里的 key，也不会把 key 写入文件：

```powershell
$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_MODEL = "gpt-5.5"
python scripts\live_llm_project_review.py --include-pytest
```

输出保存在 `outputs/`，该目录已被 `.gitignore` 忽略。

## 仓库边界

可以提交：

- `src/`
- `tests/`
- `fixtures/` 中的 synthetic 数据
- `docs/` 中不含真实患者信息的公开项目文档
- `scripts/`
- `pyproject.toml`
- `.gitignore`
- `AGENTS.md`

不要提交：

- `data_private/`
- 原始图片、微信聊天记录、真实病例 Markdown
- 真实病例重建 JSON
- `.env`、API key、本地缓存和输出
