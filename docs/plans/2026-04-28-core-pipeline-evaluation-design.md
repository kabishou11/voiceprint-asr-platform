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
- `cjk_split_boundary_count`：疑似中文词被 speaker 边界切开的次数，用于发现“加工逻 / 辑的时候”这类可读性断裂。
- `cjk_split_boundary_ratio`：疑似中文断词边界占相邻段边界的比例，用于跨不同时长样本比较。
- `leading_punctuation_count`：以前导标点开头的段落数，用于发现对齐边界落在标点后的问题。
- `leading_punctuation_ratio`：前导标点段占全部段落的比例，用于跨不同时长样本比较。

### 声纹识别

- `matched_speaker_count`：成功匹配 speaker 数。
- `unmatched_speaker_count`：未匹配 speaker 数。
- `low_confidence_count`：低于阈值候选数。
- `top_candidate_scores`：每个 speaker 的 top 候选分数。

### 会议纪要

- `decision_coverage`：纪要决策可在原文中找到证据的比例。
- `action_item_coverage`：行动项可回链比例。
- `risk_coverage`：风险项可回链比例。
- `evidence_rows`：每条决策、行动项、风险对应的证据明细，包含是否命中、证据分数、命中的转写片段、弱证据原因和缺失 token，用于定位会议纪要漏召回或幻觉项。

## 错误处理

- 输入缺失时给出明确 CLI 错误。
- 解析失败时输出可读错误，不生成半成品报告。
- 没有参考文本时跳过 CER，只保留诊断指标。
- 没有声纹 metadata 或会议纪要时，对应指标返回 `available=false`。

## 测试策略

- 单元测试覆盖文本归一化、CER、热词命中率。
- 单元测试覆盖 readable txt 解析。
- 单元测试覆盖 speaker 诊断、会议纪要覆盖率和纪要证据明细。
- 脚本测试使用小样本 JSON，不运行真实模型。

## 后续演进

- 第二阶段接入真实 DER/JER 标注格式。已落地：`evaluate_core_pipeline.py --reference-speakers` 支持 RTTM、TranscriptResult JSON 与 readable txt，并输出轻量 DER/JER 近似指标。
- 第三阶段加入阈值扫描，输出声纹识别 ROC/EER 近似报告。已落地：`--voiceprint-labels` 支持 `{speaker: profile_id}` JSON，并输出阈值扫描点、近似 EER、Top1/TopK 命中率、缺失正确候选 speaker 明细。
- 第四阶段把报告接入前端任务详情页，形成可视化质检面板。已落地第一版：`GET /api/v1/transcriptions/{job_id}/evaluation` 基于当前任务结果生成轻量评测摘要，任务详情页展示 speaker、声纹与纪要覆盖诊断。
- 第五阶段形成真实样本集评测闭环。已落地第一版：`evaluate_core_pipeline_dataset.py` 读取样本集 manifest，批量生成样本明细与聚合基线报告；`compare_core_pipeline_baselines.py` 支持多个 baseline JSON 横向比较，并输出相对首个基线的变化值。下一步补齐 15min/长会议样本的参考文本、RTTM、声纹标签和人工纪要基准，即可横向比较 DER、EER、ASR 与纪要覆盖率。
- 第六阶段固化真实参考稿窗口。已落地第一版：`export_reference_slice.py` 可以把完整参考稿按音频时长比例导出固定窗口切片，供样本集 manifest 作为 `reference_text` 使用，避免每次评测依赖外部桌面文件。已补充质量门控：`time_ratio` 切片默认标记为 `draft_time_ratio`，只输出诊断，不进入正式 ASR 聚合；人工复核或时间戳对齐后需显式改为 `confirmed`。
- 第七阶段降低人工标注启动成本。已落地第一版：`generate_evaluation_annotation_templates.py` 可从当前转写结果生成 RTTM、声纹标签、人工纪要和复核清单草稿；这些草稿必须人工修正后才可作为 manifest 的参考标注。
- 第八阶段提升会议纪要评测可解释性。已落地第一版：`minutes_coverage_diagnostics` 在保留原有覆盖率字段的同时，新增逐条 `evidence_rows`、弱证据和缺证据统计；会议纪要服务层 `evidence` 同步返回证据分、命中 token、缺失 token 和原因，让长会议 map-reduce 纪要优化可以直接追踪到“哪条结论没有 transcript 支撑”。
- 第九阶段减少多人转写可读性断裂。已落地第一版：speaker 对齐层在无法按句子/标点切分、必须退回时间比例切片时，会检测中文词被 diarization 边界切开的情况，并把边界左移一字，避免出现“加工逻 / 辑的时候”这类断词片段。评测侧同步新增中文断词边界、前导标点段的数量与比例统计，让可读性问题可以进入 baseline 横向比较。
- 第十阶段保留内嵌插话 speaker。已落地第一版：exclusive speaker timeline 在长 speaker 段内出现短插话段时，会把长段拆成前段、插话段和尾段，避免嵌套 speaker 被中点裁边逻辑吞掉，后续 alignment 和声纹 probe 都能看到该 speaker。
- 第十一阶段补齐显式声纹候选名单。已落地第一版：多人转写任务只传 `voiceprint_profile_ids` 时不再被 `voiceprint_scope_mode=none` 短路，worker 会按显式候选名单执行 speaker 级声纹识别，并在 metadata 中保留实际候选范围。
- 第十二阶段增强长会议 LLM 纪要归并可靠性。已落地第一版：多分块纪要 reduce 后，会从 chunk 合并草稿中回填 reduce 遗漏且可在原始 transcript segments 中命中证据的决策、行动项和风险，避免模型归并时丢失后半段已有证据的关键事项。
- 第十三阶段保护真实短插话。已落地第一版：alignment 的 A-B-A 短碎片平滑只吸收 filler 或无句末标点的短残片，不再吞掉“不同意。”这类短但完整的跨 speaker 插话，避免多人会议中的关键反对意见被合并到前后 speaker。
- 第十四阶段补齐声纹库识别候选范围。已落地第一版：声纹库页面在分组上下文执行“声纹识别”时，会把当前可见分组档案 ID 作为 `profile_ids` 透传到 `/voiceprints/identify`，API 同步与异步 worker 链路再传到底层 adapter，避免 UI 已限定分组但实际全库识别。
- 第十五阶段把多时间线纳入评测。已落地第一版：核心评测报告新增 `timeline_diagnostics`，会并排计算 metadata 中 `regular`、`exclusive`、`display` 与最终 `segments` 的 speaker 诊断、DER/JER、中文断词和前导标点指标，并给出推荐 timeline；worker 同步读取 adapter 的 `get_last_outputs()`，避免 pyannote 的 regular/exclusive 元数据被折叠成同一份。
- 第十六阶段把多时间线诊断纳入样本集基线。已落地第一版：样本集聚合报告会统计推荐 timeline 分布、最佳 timeline 平均质量分，以及各 timeline source 的平均 DER/JER、短碎片率、中文断词率和前导标点率；baseline 对比同步加入最佳 timeline 分数 delta，让 speaker 对齐优化可以跨版本量化比较。
- 第十七阶段增强声纹阈值扫描可解释性。已落地第一版：`voiceprint_threshold_scan` 在统计缺失正确候选数量之外，会返回具体缺失 speaker 列表和完整 score rows；Markdown 报告同步展示阈值扫描缺失 speaker，方便区分阈值问题、候选范围问题和声纹模型打分问题。
- 第十八阶段修正无文本 timeline 的推荐偏差。已落地第一版：speaker 诊断新增文本覆盖率和可读性可用标记；在没有 reference speaker 标注时，缺少文本的 regular/exclusive/display 时间线不会因为“没有断词可检测”而被误选为最佳 timeline，样本集聚合表同步展示各 timeline 的文本覆盖率。
- 第十九阶段把最佳 timeline 文本覆盖纳入基线对比。已落地第一版：样本集聚合会记录被推荐 timeline 的平均文本覆盖率，baseline summary 与横向对比表同步展示该指标及 delta，避免后续只观察 Timeline 分数却忽略推荐结果是否保留了可读文本。
- 第二十阶段把部分文本覆盖纳入 timeline 质量分。已落地第一版：在没有 speaker reference 时，timeline 推荐分会按文本覆盖缺口增加惩罚，避免只有少量 segment 带文本的 display/regular 时间线与完整 final transcript 打平。
- 第二十一阶段修正声纹阈值扫描漏计缺失结果。已落地第一版：阈值扫描改为以 ground truth speaker 为评估主轴，若某个 speaker 完全没有 `voiceprint_matches` 结果，也会生成 `missing_result`/`missing_positive` score row 并按 false negative 计入 ROC/EER，避免多人转写声纹链路漏跑时被聚合指标吞掉。
