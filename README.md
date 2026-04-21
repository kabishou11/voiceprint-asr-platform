# voiceprint-asr-platform

<p align="center">
  <img src="docs/logo.svg" alt="智能语音平台 Logo" width="96" />
</p>

<h1 align="center">智能语音平台</h1>

<p align="center" style="color: #64748b; font-size: 15px; margin-top: -4px;">
  多人转写 · 说话人分离 · 声纹核验
</p>

---

面向会议记录、客服质检与身份核验场景的智能语音平台，一站式覆盖：

| 核心能力 | 说明 |
|---------|------|
| **语音识别** | 将音频转为文字，支持中文普通话及多语言 |
| **说话人分离** | 自动识别音频中的不同说话人，带说话人标签输出转写结果 |
| **声纹识别** | 1:1 验证与 1:N 识别，精准核验说话人身份 |

## 技术栈

- Python 3.13 / uv
- FastAPI（API 服务）
- React + TypeScript + MUI 7（前端工作台）
- FunASR（语音识别）
- 3D-Speaker（说话人分离 · 声纹）
- pyannote-audio（实验性 diarization）

## 目录

- `apps/api` — API 服务
- `apps/worker` — 任务执行与模型推理
- `apps/web` — 前端工作台
- `packages/python/model_adapters` — 模型适配层
- `packages/python/domain` — 领域模型与统一 schema
- `infra/compose` — 本地联调基础设施
- `migrations` — 数据库迁移骨架
- `tests` — 集成与冒烟测试
- `models` — 本地模型目录（如 FunASR）

## 本地开发

### 1. 安装依赖

```bash
uv sync
cd apps/web && npm install
```

如需真实 FunASR 推理，额外安装：

```bash
uv pip install --no-deps funasr==1.3.1
uv pip install torch torchaudio transformers modelscope
```

### 2. 准备本地模型

默认配置会优先读取仓库内的 `models/Fun-ASR-Nano-2512`：

```bash
git lfs clone https://www.modelscope.cn/FunAudioLLM/Fun-ASR-Nano-2512.git models/Fun-ASR-Nano-2512
```

也可以通过 `.env` 中的 `FUNASR_MODEL` 指向其他本地目录或远端模型名。

### 3. 启动 API

```bash
uv run uvicorn apps.api.app.main:app --reload
```

### 4. 启动 Worker

```bash
uv run python -m apps.worker.app.main
```

### 5. 启动前端

```bash
cd apps/web && npm run dev
```

### 6. 运行测试

后端：

```bash
uv run pytest tests/integration/test_health.py
```

前端：

```bash
cd apps/web && npm run test
```

### 7. 容器联调

```bash
cd infra/compose && docker compose up --build
```

## 核心功能说明

### 语音识别（ASR）

将音频文件转成文字，采用 FunASR 高精度模型，支持中文普通话实时转写。

上传音频后可直接发起单人转写任务，适合录音转写、字幕生成等场景。

### 说话人分离（Diarization）

自动识别音频中的不同说话人，为每段话标注说话人编号，适合会议录音多人记录。

首页已把说话人分离设为**默认主路径**，上传音频后无需额外配置即可获得带说话人标签的转写结果。

### 声纹识别（Voiceprint）

提供三大声纹能力：

- **声纹注册**：将目标说话人的音频样本注册为身份档案
- **1:1 验证**：给定一段音频和一个档案，判断是否为同一人（核验）
- **1:N 识别**：给定一段音频，在声纹库中找出最相似的候选人（识别）

> 声纹注册属于**按需启用**的可选能力。默认转写和说话人分离流程不依赖声纹库，无需预先注册即可使用。

## 真实上传流程

系统采用"先上传音频，再发起业务处理"的两步式流程。

### 上传音频资产

```http
POST /api/v1/assets/upload
Content-Type: multipart/form-data
```

表单字段：`file` — 音频文件

支持格式：`.wav` `.m4a` `.mp3` `.flac`

成功返回：

```json
{
  "asset_name": "c797e67c8531b7cf.wav",
  "original_filename": "声纹-女1.wav",
  "size": 636940
}
```

上传后的文件保存到：`storage/uploads/<asset_name>`

### 上传后转写（默认说话人分离）

```http
POST /api/v1/transcriptions
Content-Type: application/json
```

```json
{
  "asset_name": "c797e67c8531b7cf.wav",
  "diarization_model": "3dspeaker-diarization"
}
```

### 上传后声纹注册

```http
POST /api/v1/voiceprints/profiles/{profile_id}/enroll
Content-Type: application/json
```

```json
{
  "asset_name": "02c83e122ad746b4.wav"
}
```

### 上传后声纹验证

```http
POST /api/v1/voiceprints/verify
Content-Type: application/json
```

```json
{
  "profile_id": "sample-female-1",
  "probe_asset_name": "8ddb6cf41a63f222.wav",
  "threshold": 0.7
}
```

### 上传后声纹识别

```http
POST /api/v1/voiceprints/identify
Content-Type: application/json
```

```json
{
  "probe_asset_name": "047b1d8e67fc41c7.wav",
  "top_k": 3
}
```

## 测试音频样本

当 `storage/uploads/` 中不存在同名文件时，服务与 worker 会自动回退到 `tests/` 目录查找。

推荐样本：

| 文件 | 用途 |
|------|------|
| `tests/罗大佑 - 光阴的故事(片头曲).wav` | ASR 单人转写 |
| `tests/丹山路.m4a` | ASR / 多说话人转写联调 |
| `tests/声纹-女1.wav` | 声纹注册底库样本 |
| `tests/5分钟.wav` | 声纹验证 / 识别 probe 样本 |

## 当前进展

已完成：

- API、Worker、Web 工程骨架
- 模型注册中心与适配器协议
- 转写、任务、声纹接口完整链路
- 产品化前端工作台（品牌标识 · 任务统计 · 快速发起）
- 最小前端 / 后端测试骨架
- API / Worker / Web Dockerfile
- Compose 联调配置
- 本地 FunASR 模型目录接入
- 测试音频样本回退链路
- 真实上传音频接口与两步式业务流
- 默认说话人分离 + 声纹按需启用的产品路径
- 公共组件体系（BrandLogo · StatCard · AudioUploadField · PageSection）

后续将继续接入更完整的持久化、数据库迁移与 CI。
