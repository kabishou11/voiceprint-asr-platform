# 说话人分离稳定性增强设计

日期：2026-04-23

## 目标

本轮只主攻多人链路中的说话人分离稳定性，不扩散到热词、全文纠错或新的模型接入。目标不是更换主模型，而是在当前 `FunASR + FSMN-VAD + 3D-Speaker(CAM++)` 主链路上，尽量复刻参考项目 `3D-Speaker` 的 diarization 稳定化能力，并把这些收益真实反映到任务结果和导出结果里。

## 当前问题

当前链路已经具备：

- `VAD -> chunk -> CAM++ embedding -> clustering`
- 局部 label 重分配
- 帧级单标签解码
- segment 级平滑

但仍存在三个典型问题：

1. 帧级 speaker 容易出现短时抖动，尤其是 `A-B-A` 型瞬时误切。
2. 底层结果比早期版本更稳，但最终任务页与可读稿未必同步体现这种收敛。
3. 参考 `3D-Speaker` 中更强的 `count / continuity / post_process` 思想还没有完全迁入。

## 设计

### 1. 模型层不变，主攻解码与后处理

主模型仍保持：

- ASR：`FunASR Nano`
- VAD：`FSMN-VAD`
- diarization embedding：`CAM++`

不引入新的主依赖，不让 `pyannote` 成为当前主路径的硬前提。

### 2. 帧级稳定化

在 `3D-Speaker` 帧级解码中继续补强两个能力：

- 标签投票增强：除 embedding center 相似度外，叠加当前 frame 被多少原始 chunk 标签覆盖。
- 近似 count 约束：当某个 frame 的次优 speaker 覆盖度不足时，将该 frame 视作单说话人帧，并提高切换门槛。

这样做的目的，是把参考实现中“同一帧最多允许几个 speaker 活跃”的思想，迁成当前单标签时间轴可用的稳定化规则。

### 3. run 级与 segment 级收口

现有局部重分配与 segment smoothing 保留，并继续承担：

- `A-B-A` 短 run 吞并
- 弱小 speaker 尾簇回并
- 小间隙同 speaker 合并

同时新增一层 `display timeline`，只影响展示和导出，不反向污染底层 raw/exclusive 时间轴。

### 4. 结果结构

`TranscriptMetadata.timelines` 保留并扩展为三层：

- `regular`：原始 diarization
- `exclusive`：文本对齐主时间轴
- `display`：服务任务页和导出的稳定展示时间轴

这样可以兼顾：

- 可追溯性
- 文本对齐质量
- 最终展示稳定性

## 验收标准

以 `storage/experiments/standard_recording_1/standard_recording_1_15min.wav` 为主样本：

- speaker 数不增加
- 原始对齐段数优先下降，至少不反弹
- 极短 speaker 残片减少
- 任务页能区分并显示 `display timeline`
- 对应单测补齐，覆盖 frame continuity、display timeline、metadata 回写

## 暂不处理

- `pyannote` gated 模型真实推理
- 多模型融合 ASR
- 声纹库新功能
- 长音频断点缓存
