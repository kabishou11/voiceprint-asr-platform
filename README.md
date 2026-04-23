# voiceprint-asr-platform

<p align="center">
  <img src="docs/logo.svg" alt="智能语音平台 Logo" width="96" />
</p>

<h1 align="center">智能语音平台</h1>

<p align="center">
  多人转写 · 说话人分离 · 声纹核验
</p>

面向会议记录、客服质检与身份核验场景的智能语音平台，主链路为：

- `FunASR`：高精度 ASR
- `3D-Speaker + FSMN-VAD`：说话人分离、声纹验证与识别
- `pyannote`：预留增强链路，当前默认关闭

当前前端稳定版采用：

- `Claude` 风格的浅色极简工作台
- `pretext` 驱动的标题与长文本排版增强
- 工作台、任务复核台、声纹回写、模型状态页统一的产品语言

当前项目已经收紧为：

- 所有模型都必须放在仓库根目录 `models/`
- 高精度任务强制要求 `CUDA GPU`
- 没有可用 `CUDA` 时，ASR / 多人分离 / 声纹任务会直接拒绝执行
- 样本跑数、benchmark、可读稿统一写入 `storage/experiments/`

## 一页复现

下面这条路径是当前仓库在另一台 Windows + NVIDIA 机器上的推荐复现方式。  
目标是只看这一页就能拉起。

### 1. 系统前提

已验证组合：

- Windows 10/11
- Python `3.13.x`
- Node.js `20+`
- `uv`
- NVIDIA 驱动正常，`torch.cuda.is_available() == True`

建议额外安装：

- `ffmpeg`
  作用：稳定解码 `.mp3/.m4a/.mp4`

如果你只是想跑最小高精度链路，`ffmpeg` 不是硬性前提，但没有它时，压缩音频解码能力会变差。

### 2. 克隆项目并创建环境

```powershell
git clone <your-repo-url>
cd voiceprint-asr-platform
uv sync --extra asr-funasr --extra speaker-3ds
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. 安装 CUDA 版 PyTorch

这个项目当前本地已验证可用的安装命令是：

```powershell
python -m pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
```

如果你已经安装过 CPU 版 `torch`，建议强制重装：

```powershell
python -m pip install --force-reinstall torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
```

### 4. 验证 GPU 运行时

```powershell
python -c "import torch; print('torch=', torch.__version__); print('cuda_runtime=', torch.version.cuda); print('cuda_available=', torch.cuda.is_available()); print('device_count=', torch.cuda.device_count()); print('device_name=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no-cuda')"
```

期望至少满足：

- `torch= 2.6.0+cu124`
- `cuda_available= True`
- 能打印出你的显卡名

如果这里不通过，后面的高精度任务都不会进入真实推理。

### 5. 安装前端依赖

```powershell
cd apps/web
npm install
cd ..\..
```

### 6. 准备环境变量

```powershell
Copy-Item .env.example .env
```

默认配置已经指向本地模型目录：

- `models/Fun-ASR-Nano-2512`
- `models/FSMN-VAD`
- `models/3D-Speaker/campplus`
- `models/pyannote/speaker-diarization-community-1`

当前默认：

- `ENABLE_PYANNOTE=false`
- `ENABLE_3D_SPEAKER_ADAPTIVE_CLUSTERING=false`

因为 `pyannote` 官方离线包需要 Hugging Face gated 权限，未补齐完整权重前不要打开。
`3D-Speaker` 的自适应聚类当前仍属于实验能力，只有在你明确做实验对比时才建议打开；当前默认主链路仍以已验证更稳的基线参数为主。

### 7. 准备本地模型目录

所有模型都必须放在仓库根目录 `models/` 下。

当前代码默认读取：

```text
models/
  Fun-ASR-Nano-2512/
  FSMN-VAD/
  3D-Speaker/
    campplus/
  pyannote/
    speaker-diarization-community-1/
```

当前本地真实状态：

- `models/Fun-ASR-Nano-2512`：已接入，可用于真实 ASR
- `models/FSMN-VAD`：已接入，可用于真实 VAD
- `models/3D-Speaker/campplus`：已接入，可用于真实 diarization / voiceprint
- `models/pyannote/speaker-diarization-community-1`：默认仍不完整，不参与主链路

更多说明见：

- [models/README.md](F:/1work/音频识别/voiceprint-asr-platform/models/README.md)

### 8. 启动服务

开三个终端。

终端 1，启动 API：

```powershell
.\.venv\Scripts\Activate.ps1
uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --reload
```

终端 2，启动 Worker：

```powershell
.\.venv\Scripts\Activate.ps1
uv run python -m apps.worker.app.main
```

终端 3，启动前端：

```powershell
cd apps/web
npm run dev
```

### 9. 最小验证

先跑后端健康与模型状态测试：

```powershell
uv run pytest tests/integration/test_health.py -q
```

再跑前端测试：

```powershell
cd apps/web
npm run test
```

如果你只想验证当前稳定版前端主链路，推荐最小检查：

```powershell
cd apps/web
pnpm test -- --run src/components/AppLayout.test.tsx src/pages/transcription/TranscriptionWorkbenchPage.test.tsx src/pages/jobs/JobDetailPage.test.tsx src/pages/voiceprints/VoiceprintLibraryPage.test.tsx src/pages/system/ModelRegistryPage.test.tsx
cmd /c .\node_modules\.bin\tsc.cmd -b
```

如果你只想快速验证多人链路，可以直接用样本脚本：

```powershell
.\.venv\Scripts\python.exe scripts\run_multi_speaker_sample.py storage\experiments\standard_recording_1\standard_recording_1_15min.wav storage\experiments\standard_recording_1\standard_recording_1_15min_multispeaker_verify.json --output-text storage\experiments\standard_recording_1\standard_recording_1_15min_multispeaker_verify.txt --title "标准录音 1（前15分钟）"
```

## 项目目录

- `apps/api`：API 服务
- `apps/worker`：任务执行与模型推理
- `apps/web`：前端工作台
- `packages/python/model_adapters`：模型适配层
- `packages/python/domain`：统一 schema 与领域模型
- `models`：本地模型目录
- `storage/uploads`：上传音频资产
- `storage/experiments`：样本跑数、benchmark、可读稿
- `tests`：单测与集成测试

## 当前稳定版前端

当前稳定版前端不是传统后台，而是一套围绕“上传任务 -> 复核结果 -> 回写身份”的极简工作台。

### 页面主链路

- `工作台`
  - 以“立即开始任务”为视觉中心
  - 支持高级参数、最近任务、模型状态提示
- `任务详情`
  - 以 speaker 过滤、时间线、分段阅读流为核心
  - 支持导出、快速重跑、跳转声纹库继续处理
- `声纹库`
  - 既能独立做验证/识别/注册，也能承接任务上下文做 speaker 回写
- `模型状态`
  - 强调真实可用性，不再只是模型清单
  - 明确区分本地 GPU 已就绪能力与受限能力

### 前端排版与视觉

- 整体风格参考 `Claude` 网页版：浅色、留白、弱边框、低噪声
- 品牌视觉来自项目自己的蓝青声波语言，不直接堆大图
- `@chenglou/pretext` 已实际接入：
  - 首页主标题
  - 任务详情长文本与摘要区
  - 重点说明文案的稳定换行与阅读布局

## 当前真实运行约束

### GPU 约束

系统现在不是“尽量用 GPU”，而是“高精度任务必须走 GPU”：

- `FunASR`：无 `CUDA` 直接拒绝
- `3D-Speaker diarization`：无 `CUDA` 直接拒绝
- `3D-Speaker voiceprint`：无 `CUDA` 直接拒绝

### 模型约束

运行时不接受默认远端模型名，必须是本地路径。

### pyannote 状态

`pyannote` 当前不是主链路依赖。原因不是代码没接，而是：

- 官方离线权重是 gated repo
- 本地没有完整授权包时，不会进入真实推理

所以当前默认主链路是：

- `FunASR + 3D-Speaker + FSMN-VAD`

## 真实业务接口

### 上传音频

```http
POST /api/v1/assets/upload
Content-Type: multipart/form-data
```

表单字段：

- `file`

支持：

- `.wav`
- `.mp3`
- `.m4a`
- `.flac`

### 发起转写

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

### 声纹注册

```http
POST /api/v1/voiceprints/profiles/{profile_id}/enroll
Content-Type: application/json
```

```json
{
  "asset_name": "02c83e122ad746b4.wav"
}
```

### 声纹验证

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

### 声纹识别

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

## 样本产物目录约定

样本转写、benchmark、可读稿统一输出到：

- `storage/experiments/<sample_name>/`

例如：

- `storage/experiments/standard_recording_1/standard_recording_1_funasr.json`
- `storage/experiments/standard_recording_1/standard_recording_1_multispeaker_v11.json`
- `storage/experiments/standard_recording_1/standard_recording_1_multispeaker_readable_v11.txt`

根目录只保留工程文件，不再放样本产物。

## 常见问题

### 1. 机器有显卡，但任务还是报 CUDA 不可用

先跑：

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

如果这里是 CPU 版 `torch` 或 `False`，项目一定不会进入高精度推理。

### 2. `.mp3/.m4a` 无法解码

优先安装 `ffmpeg`。  
如果环境里没有可用解码后端，先把音频转成 `16k wav` 再跑。

### 3. `pyannote` 为什么默认不可用

因为本地没有完整的 gated 离线权重。  
这不是代码开关问题，而是模型授权和权重文件问题。

## 当前主链路总结

当前已经稳定可复现的高精度主链路是：

- `FunASR`：GPU ASR
- `FSMN-VAD`：本地 VAD
- `3D-Speaker CAM++`：GPU diarization / voiceprint
- `exclusive alignment`：无重叠对齐时间轴
- `storage/experiments`：统一样本产物目录

当前稳定版产品链路则是：

1. 工作台上传音频并发起任务
2. 任务详情按 speaker 复核时间线与文本
3. 从任务详情跳到声纹库做验证、识别或注册
4. 把 speaker 身份回写回任务详情
5. 在模型状态页确认当前模型与 GPU 路径真实可用

如果你在另一台电脑上严格按本 README 执行，核心目标应该是：

1. `torch.cuda.is_available() == True`
2. `uv run pytest tests/integration/test_health.py -q` 通过
3. 能成功跑出 `storage/experiments/...` 下的多人转写结果
4. 前端 5 个关键页面测试通过，并能跑起极简工作台界面
