# voiceprint-asr-platform

面向会议记录、客服质检与身份核验场景的智能语音平台，覆盖：
- 语音转写
- 多说话人分离与带说话人标签的转写
- 声纹注册、验证与识别

## 技术栈

- Python 3.13
- uv
- FastAPI
- React + TypeScript + MUI
- FunASR
- 3D-Speaker
- pyannote-audio（实验性）

## 目录

- `apps/api`：API 服务
- `apps/worker`：任务执行与模型推理
- `apps/web`：前端工作台
- `packages/python/model_adapters`：模型适配层
- `packages/python/domain`：领域模型与统一 schema
- `infra/compose`：本地联调基础设施
- `migrations`：数据库迁移骨架
- `tests`：集成与冒烟测试
- `models`：本地模型目录（如 FunASR）

## 本地开发

### 1. 安装依赖

```bash
uv sync
cd apps/web && npm install
```

如需真实 FunASR 推理，额外安装：

```bash
uv sync --extra asr-funasr
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

## 默认流程说明

### 说话人分离 / 多人转写

当前首页已经把多人转写作为默认主路径：
- 上传真实音频后，默认直接按“多人转写 / 说话人分离”流程创建任务
- 说话人模式下拉仍然保留，但“标准转写”变为可选项
- 这意味着大多数会议类场景无需额外配置即可获得带说话人标签的结果

### 声纹注册

声纹注册保留为按需启用的可选能力：
- 当你只需要转写和说话人分离时，不需要先做声纹注册
- 当你需要把某个身份写入声纹库时，再到声纹页使用“注册基准音频”功能
- 当前 MVP 语义：每个档案只保留 1 份注册基准音频，重复注册会覆盖旧样本

## 真实上传流程

当前系统已经支持“先上传音频，再发起业务处理”的真实用户流程。

### 上传音频资产

上传接口：

```http
POST /api/v1/assets/upload
Content-Type: multipart/form-data
```

表单字段：
- `file`：音频文件

支持格式：
- `.wav`
- `.m4a`
- `.mp3`
- `.flac`

成功返回：

```json
{
  "asset_name": "c797e67c8531b7cf.wav",
  "original_filename": "声纹-女1.wav",
  "size": 636940
}
```

上传后的文件会保存到：
- `storage/uploads/<asset_name>`

### 上传后转写

前端首页已采用两步式流程：
1. 先上传音频
2. 再调用转写接口

转写接口仍然接收 `asset_name`：

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

当 `diarization_model` 有值时，会走多人转写流程；当前前端默认就会这样提交。

### 上传后声纹注册

声纹注册同样采用两步式流程：
1. 先上传注册音频
2. 再对某个档案执行 enroll

注册接口：

```http
POST /api/v1/voiceprints/profiles/{profile_id}/enroll
Content-Type: application/json
```

```json
{
  "asset_name": "02c83e122ad746b4.wav"
}
```

成功返回：

```json
{
  "profile": {
    "profile_id": "profile-3",
    "display_name": "上传注册用户2",
    "model_key": "3dspeaker-embedding",
    "sample_count": 1
  },
  "enrollment": {
    "profile_id": "profile-3",
    "asset_name": "02c83e122ad746b4.wav",
    "status": "enrolled",
    "mode": "replace"
  }
}
```

当前 MVP 语义：
- 每个档案只保留 1 份注册基准音频
- 重复注册视为覆盖旧样本
- `sample_count` 会保持为 `1`

### 上传后声纹验证

验证接口：

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

识别接口：

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

### 前端页面现状

前端当前已经支持：
- 首页上传真实音频并发起转写（默认多人转写 / 说话人分离）
- 声纹页新建档案
- 声纹页按需上传注册音频并完成注册
- 声纹页上传待比对音频并完成验证 / 识别

## 测试音频样本

当前仓库已直接使用 `tests/` 下的样本文件作为本地冒烟素材；当 `storage/uploads/` 中不存在同名文件时，服务与 worker 会自动回退到 `tests/` 目录查找。

推荐样本：
- `tests/罗大佑 - 光阴的故事(片头曲).wav`：ASR 单人转写
- `tests/丹山路.m4a`：ASR / 多说话人转写联调
- `tests/声纹-女1.wav`：声纹注册底库样本
- `tests/5分钟.wav`：声纹验证 / 识别 probe 样本

## 当前进展

已完成：
- API、Worker、Web 工程骨架
- 模型注册中心与适配器协议
- 转写、任务、声纹接口骨架
- 产品化前端工作台首版
- 最小前端/后端测试骨架
- API / Worker / Web Dockerfile
- Compose 联调配置
- 本地 FunASR 模型目录接入
- 测试音频样本回退链路
- 真实上传音频接口
- 上传后转写流程
- 上传后声纹注册 / 验证 / 识别流程
- 默认多人转写与说话人分离流程
- 声纹注册按需启用入口

后续将继续接入更完整的持久化、数据库迁移与 CI。
