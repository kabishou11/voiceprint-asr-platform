# 多人转写主链路与精度增强设计

日期：2026-04-21

## 背景

当前仓库已经接入了 FunASR、3D-Speaker 与 pyannote 的基础骨架，但多人转写、说话人分离与声纹识别链路仍存在明显精度瓶颈：

- ASR 分段与 speaker 对齐协议存在错误短路
- 3D-Speaker 声纹 embedding 仍为简化统计特征，不是真实 speaker embedding
- pyannote 仍为占位实现
- API、worker、前端对多人转写主路径的建模不统一
- 音频预处理与评测闭环尚未形成

本轮目标不是继续堆接口，而是把多人转写主链路做成“真实可用、高精度优先、具备回退能力”的产品级路径。

## 目标

### 主目标

- 以多人转写为主，显著提升会议、访谈、客服录音等场景下的分离与转写准确率
- 让声纹注册、验证、识别成为多人转写结果的后处理能力，而不是独立孤岛
- 前端围绕“上传 -> 转写 -> 复核 -> 声纹处理”形成连续工作流

### 非目标

- 本轮不做数据库持久化重构
- 本轮不做在线训练/微调平台
- 本轮不做复杂权限、多租户、审计能力

## 设计原则

- 主链路必须是真实模型推理，不允许占位结果混入默认流程
- 所有运行时模型必须从仓库根目录 `models/` 读取
- 高精度优先，同时保留缺依赖时的明确回退路径
- 多人转写的 orchestration 只保留一套，不允许 API 与 worker 分别实现
- 前端优先服务主链路，不做分散式能力展示
- 每项改造都必须可测量，至少能通过固定样本比较前后结果

## 总体架构

### 新主链路

1. 上传音频
2. 统一音频预处理
3. FunASR 执行全文转写
4. 3D-Speaker 或 pyannote 执行 diarization
5. 对齐层做时间轴重切分与 speaker 贴标
6. speaker 级后处理与结果聚合
7. 从 speaker 结果直接触发声纹识别、验证或入库

### 模型分层

#### 主链路

- ASR：FunASR
- Speaker embedding / voiceprint：3D-Speaker
- 默认 diarization：3D-Speaker

#### 增强链路

- 复杂会议、多人交叠、高噪声场景可启用 pyannote
- pyannote 可用于独立 diarization，也可用于边界修正与复杂场景回退

#### 回退链路

- 无 GPU、无 pyannote 依赖、无 HuggingFace token 时，回退到轻量 3D-Speaker 路径
- 回退必须是真实推理，不能继续使用固定返回值或伪 speaker 结果

## 后端改造

### 1. 统一多人转写编排

将多人转写主流程统一收敛到 worker pipeline：

- API 负责参数接收、校验与任务创建
- worker 负责 orchestrate：预处理、ASR、diarization、alignment、postprocess
- API 层不再自行做 `_merge_segments`

### 2. 音频预处理

预处理模块必须真正完成：

- 解码输入音频
- 重采样到 16kHz
- 转单声道
- 规范波形 dtype
- 输出稳定的临时标准化音频引用

必要时预留：

- 简单响度归一
- 长音频切片
- 静音裁剪开关

### 3. ASR 对齐协议修正

FunASR 适配层需遵循以下规则：

- 若 ASR 原始结果没有 speaker，则 segment.speaker 必须为 `None`
- 句级、词级时间戳优先保留
- 不允许默认填充 `SPEAKER_00` 造成 diarization 短路

### 4. Diarization 升级

#### 3D-Speaker 路线

对齐 3D-Speaker 官方流程：

- VAD 产生语音段
- 子段切分
- 真 speaker embedding 提取
- 聚类
- 后处理生成稳定 speaker 段

禁止使用：

- `i % 2` 轮换 speaker 的演示 fallback
- 伪 embedding 占位后处理

#### pyannote 路线

pyannote 适配器改为真实 pipeline：

- `Pipeline.from_pretrained(...)`
- 支持 `num_speakers/min_speakers/max_speakers`
- 在依赖缺失或 token 不可用时显式返回不可用，而非固定段落

### 5. Alignment 与 postprocess

alignment 从“按段挑一个 speaker”升级为“时间轴重切分”：

- 按 transcript 段与 diarization 段的重叠关系二次切分
- 对短段、孤立段、超短换人段做平滑
- 优先保留时间边界，再做 speaker 归属
- 允许引入 `merge_short_segments` 进入主流程

### 6. 声纹链路升级

声纹适配器改为真实 speaker embedding 流程：

- 真实 CAM++ 或兼容 3D-Speaker speaker embedding
- verify/identify 不允许 probe 自比 fallback
- identify 在库为空时返回空候选，不构造伪样本

后续预留能力：

- 多样本注册与聚合 embedding
- 阈值校准
- score normalization

## 前端改造

### 1. 工作台首页

改成单一主路径页面：

- 上传音频作为主视觉区域
- 默认选择多人转写
- 高级设置暴露语言、热词、VAD、ITN、说话人数约束、分离模型
- 右侧展示进行中任务与场景预设

### 2. 任务详情页

改为多人转写复核工作区：

- 音频播放器与时间跳转
- 分段结果列表
- speaker 聚合侧栏
- 参数回显、语言、置信度展示
- 从 speaker 分组直接发起识别、验证、入库

### 3. 声纹库页

保留身份库管理，同时支持：

- 接收来自任务详情的 speaker 上下文
- 调整阈值与 top-k
- 将识别候选直接绑定到 speaker 标签

## 测试与评测

### 最小自动化验证

- API 参数下传测试
- ASR 未带 speaker 时不再默认填 `SPEAKER_00`
- pyannote 依赖缺失时返回正确 availability
- voiceprint verify/identify 不再走 probe 自比

### 评测指标

- 多人转写：DER / JER / 带 speaker 的文本复核结果
- 声纹验证：EER / 阈值一致性
- 声纹识别：Top1 / TopK

## 分阶段落地

### 第一阶段

- 写入设计文档
- 统一 worker 主链路
- 修正 API 参数下传
- 真实预处理落地
- 修正 ASR 对齐协议
- 去掉声纹伪 embedding 与自比逻辑
- 替换 pyannote 占位实现

### 第二阶段

- 多人转写复核页
- 首页高级设置与场景预设
- speaker 到声纹库的直接工作流

### 第三阶段

- 多样本声纹注册
- 更完整评测集
- 模型切换策略与结果导出

## 风险

- pyannote 依赖与 HuggingFace token 增加运行门槛
- 真实模型推理会放大本地环境差异
- 缺少标准数据集时，前期评估需要依赖固定样本与回归测试

## 验收标准

- 默认多人转写路径不再返回占位 diarization
- speaker 对齐不再因默认 `SPEAKER_00` 被短路
- voiceprint verify/identify 不再出现 probe 自比或伪候选
- 前端可从任务结果直接操作 speaker 级声纹能力
- 至少存在一组固定样本可比较改造前后的结果
