# 后端核心流水线评测与诊断层设计

日期：2026-04-28

## 背景

后端核心链路已经收敛为：音频预处理 -> ASR -> 说话人分离 -> speaker 对齐 -> 声纹识别 -> 会议纪要。下一阶段继续优化模型参数前，必须先建立可重复的评测与诊断层，避免只凭单个样本的主观观感判断效果。

仓库现有 `scripts/benchmark_funasr_against_reference.py` 与 `scripts/run_reference_hotword_window_benchmark.py`，已经能对 FunASR 与参考稿做轻量对比。本轮设计在此基础上扩展为统一核心流水线评测入口。

## 目标

- 用固定样本输出稳定的 JSON/Markdown 评测报告。
- 覆盖 ASR、多人转写、声纹识别、会议纪要四类核心能力。
- 为后续参数调优提供可比较的基线指标。
- 复用现有实验产物目录 `storage/experiments`，不引入新服务依赖。

## 非目标

- 不在本轮引入在线训练、模型微调或复杂数据集管理。
- 不要求一次性实现标准 DER/EER 全量学术评测。
- 不改变现有 API 返回结构。

## 推荐方案

采用“评测脚本 + 纯 Python 指标模块 + Markdown 报告”的轻量方案。

原因：

- 与当前仓库结构最匹配，能快速落地。
- 不依赖额外第三方评测库，Windows 本地更稳。
- 后续可以逐步替换或补充为更标准的 DER/EER/WER 评测。

## 数据流

1. 输入音频路径、参考文本路径、转写结果 JSON 或 readable txt。
2. 解析 `TranscriptResult` 或 readable 分段文本。
3. 计算文本指标：CER、归一化相似度、热词命中率。
4. 计算 speaker 诊断：speaker 数量、时长占比、短碎片率、换人频率、长段统计。
5. 计算声纹诊断：candidate 覆盖、matched 比例、低置信度 speaker。
6. 计算会议纪要诊断：行动项/决策/风险是否可回链到原始文本。
7. 输出 JSON 与 Markdown 报告。

## 指标设计

### ASR

- `cer`：中文字符级编辑距离错误率。
- `sequence_ratio`：归一化文本相似度，兼容现有 benchmark。
- `reference_length` / `hypothesis_length`：用于观察漏转或幻觉。
- `hotword_recall`：参考热词在识别结果中的命中比例。

### 多人转写

- `speaker_count`：识别出的 speaker 数。
- `speaker_duration_share`：每个 speaker 的时长占比。
- `short_fragment_ratio`：短碎片段占比。
- `speaker_turns_per_minute`：换人频率。
- `long_segment_count`：过长段数量，用于发现切分过粗。

### 声纹识别

- `matched_speaker_count`：成功匹配 speaker 数。
- `unmatched_speaker_count`：未匹配 speaker 数。
- `low_confidence_count`：低于阈值候选数。
- `top_candidate_scores`：每个 speaker 的 top 候选分数。

### 会议纪要

- `decision_coverage`：纪要决策可在原文中找到证据的比例。
- `action_item_coverage`：行动项可回链比例。
- `risk_coverage`：风险项可回链比例。

## 错误处理

- 输入缺失时给出明确 CLI 错误。
- 解析失败时输出可读错误，不生成半成品报告。
- 没有参考文本时跳过 CER，只保留诊断指标。
- 没有声纹 metadata 或会议纪要时，对应指标返回 `available=false`。

## 测试策略

- 单元测试覆盖文本归一化、CER、热词命中率。
- 单元测试覆盖 readable txt 解析。
- 单元测试覆盖 speaker 诊断与会议纪要覆盖率。
- 脚本测试使用小样本 JSON，不运行真实模型。

## 后续演进

- 第二阶段接入真实 DER/JER 标注格式。已落地：`evaluate_core_pipeline.py --reference-speakers` 支持 RTTM、TranscriptResult JSON 与 readable txt，并输出轻量 DER/JER 近似指标。
- 第三阶段加入阈值扫描，输出声纹识别 ROC/EER 近似报告。已落地：`--voiceprint-labels` 支持 `{speaker: profile_id}` JSON，并输出阈值扫描点、近似 EER、Top1/TopK 命中率、缺失正确候选 speaker 明细。
- 第四阶段把报告接入前端任务详情页，形成可视化质检面板。已落地第一版：`GET /api/v1/transcriptions/{job_id}/evaluation` 基于当前任务结果生成轻量评测摘要，任务详情页展示 speaker、声纹与纪要覆盖诊断。
- 第五阶段形成真实样本集评测闭环。已落地第一版：`evaluate_core_pipeline_dataset.py` 读取样本集 manifest，批量生成样本明细与聚合基线报告；`compare_core_pipeline_baselines.py` 支持多个 baseline JSON 横向比较，并输出相对首个基线的变化值。下一步补齐 15min/长会议样本的参考文本、RTTM、声纹标签和人工纪要基准，即可横向比较 DER、EER、ASR 与纪要覆盖率。
- 第六阶段固化真实参考稿窗口。已落地第一版：`export_reference_slice.py` 可以把完整参考稿按音频时长比例导出固定窗口切片，供样本集 manifest 作为 `reference_text` 使用，避免每次评测依赖外部桌面文件。已补充质量门控：`time_ratio` 切片默认标记为 `draft_time_ratio`，只输出诊断，不进入正式 ASR 聚合；人工复核或时间戳对齐后需显式改为 `confirmed`。
- 第七阶段降低人工标注启动成本。已落地第一版：`generate_evaluation_annotation_templates.py` 可从当前转写结果生成 RTTM、声纹标签、人工纪要和复核清单草稿；这些草稿必须人工修正后才可作为 manifest 的参考标注。
