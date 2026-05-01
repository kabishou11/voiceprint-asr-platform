# voiceprint-asr-platform

<p align="center">
  <img src="apps/web/public/logo.svg" alt="智能语音平台 Logo" width="96" />
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
后端 `/api/v1/health` 与 `/api/v1/models` 会返回 `audio_decoder`，用于确认当前是 `ffmpeg`、`torchaudio` 回退还是无可用解码后端。
`/api/v1/models` 还会返回 `worker_model_status`，用于区分 API 进程模型状态和 Celery Worker 进程实际可见的模型/CUDA 状态。
其中每个 Worker 模型项会区分 `availability`（模型文件/依赖/CUDA 是否满足）与
`runtime_status`（Worker 进程内是否已加载真实推理对象）。需要预热真实任务执行进程时，
调用 `POST /api/v1/models/{model_key}/warmup-worker`。

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
- `MINUTES_LLM_MODEL=MiniMax-M2.7`

因为 `pyannote` 官方离线包需要 Hugging Face gated 权限，未补齐完整权重前不要打开。
`3D-Speaker` 的自适应聚类当前仍属于实验能力，只有在你明确做实验对比时才建议打开；当前默认主链路仍以已验证更稳的基线参数为主。

会议纪要是独立功能页，不会混入原文转写页。它支持两种模式：

- 本地规则纪要：无需外部 key，用于兜底预览。
- AI 会议纪要：走 OpenAI-compatible Chat Completions 接口，默认模型 `MiniMax-M2.7`。

如需启用 AI 会议纪要，在 `.env` 中配置：

```env
MINUTES_LLM_API_KEY=你的_key
MINUTES_LLM_BASE_URL=https://api.minimax.chat/v1
MINUTES_LLM_MODEL=MiniMax-M2.7
MINUTES_LLM_REASONING_SPLIT=true
MINUTES_LLM_TIMEOUT_SECONDS=90
```

如果你的部署环境已经统一使用 OpenAI-compatible 变量，也可以改用 `OPENAI_API_KEY` 与 `OPENAI_BASE_URL`；
`MINUTES_LLM_*` 优先级更高，便于单独给会议纪要指定 MiniMax-M2.7 或其他兼容模型。
后端 `/api/v1/health` 会返回 `meeting_minutes_llm`，用于确认是否已配置 key、模型、base URL、reasoning split 与超时时间；该状态不会泄露 API Key。

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

检查核心模型完整性：

```powershell
uv run python scripts/check_models.py
```

报告会区分“必需模型”和“可选模型”。`FunASR Nano`、`FSMN-VAD`、`3D-Speaker CAM++`
决定主链路是否可用；`pyannote community-1` 只作为可选增强显示，不完整时不会阻断默认链路。

如需输出机器可读 JSON，或发布前计算关键文件哈希：

```powershell
uv run python scripts/check_models.py --json
uv run python scripts/check_models.py --json --sha256
```

交接或生产部署前建议再跑一次环境自检：

```powershell
uv run python scripts/deployment_preflight.py
uv run python scripts/deployment_preflight.py --json --strict
```

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
uv run python -m apps.worker.app.worker
```

Windows 本地开发会默认使用 `--pool=solo --concurrency=1`，避免 Celery/billiard
多进程池在 Windows 上报 `PermissionError: [WinError 5] 拒绝访问`。如果你手动用
`celery -A ... worker` 启动，也请带上：

```powershell
uv run celery -A apps.worker.app.celery_app worker --loglevel=info --pool=solo --concurrency=1
```

如果日志出现 `Cannot connect to redis://localhost:6379/0`，说明 Redis 没启动。
本地可先启动基础依赖：

```powershell
docker compose -f infra/compose/docker-compose.yml up -d redis
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

pytest 默认会把临时目录写入 `storage/pytest-tmp`。如果你在 Windows 上遇到 `.pytest_cache` 或系统临时目录权限警告，优先确认没有旧测试进程占用文件；通常不需要再手动传 `--basetemp`。

如果 `uv` 访问用户目录缓存时报 `AppData\Local\uv\cache ... 拒绝访问`，可以临时把缓存放到仓库内的忽略目录：

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
uv run pytest tests/unit -q
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

### 10. 生产部署交接要点

当前仓库的容器配置是“可交接的部署骨架”，不是已经完成 GPU 生产镜像的最终形态。正式部署前必须确认：

- API 与 Worker 镜像需要 `ffmpeg`、本地模型卷、持久化 `storage/` 卷。
- 高精度 ASR / diarization / voiceprint 需要 CUDA 版 `torch/torchaudio`，`uv.lock` 中的 PyPI `torch` 不能替代 CUDA wheel。
- `infra/compose/docker-compose.yml` 会把容器内 DSN 覆盖为 `postgres`、`redis`、`minio` 服务名；如果手动启动，`.env` 中可以继续使用 `localhost`。
- 当前业务数据真实落在 `storage/jobs.db`、`storage/uploads`、`storage/voiceprints`、`storage/minutes` 等本地目录；`POSTGRES_DSN` 与 `S3_*` 目前是部署预留配置，尚未承载主业务持久化。
- 前端 Dockerfile 当前运行 Vite dev server。生产环境建议 `npm run build` 后用 Nginx/Caddy 静态托管，并反向代理 `/api` 到 API 服务。
- Worker 必须启动 `python -m apps.worker.app.worker` 或等价 Celery worker；`apps.worker.app.main` 只用于打印能力，不会消费队列。
- 队列任务支持轻量取消：`POST /api/v1/jobs/{job_id}/cancel` 会把 `pending/queued/running` 标记为 `canceled`。该操作不会强杀已经进入模型推理的进程，但 Worker 在开始前和写回结果时会尊重取消状态，避免取消后又被覆盖为成功或失败。
- 创建转写任务默认必须走异步队列；如果 Redis/Worker 不可用，API 会快速返回错误，而不会在请求线程里同步跑大模型。仅本地调试小音频时可设置 `ALLOW_SYNC_TRANSCRIPTION_FALLBACK=1`。

生产验收推荐顺序：

```powershell
uv run python scripts/deployment_preflight.py --strict
uv run python scripts/check_models.py
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/models
```

确认 `health.execution_mode=async`、`audio_decoder.backend=ffmpeg`、`worker_model_status.online=true` 后，再预热 Worker 模型：

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/models/funasr-nano/warmup-worker
curl -X POST http://127.0.0.1:8000/api/v1/models/3dspeaker-diarization/warmup-worker
curl -X POST http://127.0.0.1:8000/api/v1/models/3dspeaker-embedding/warmup-worker
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
  - 支持高级参数、运行中任务、最近结果、模型状态提示
- `任务队列`
  - 用于持续查看后台异步任务
  - 刷新页面后仍可追踪排队中、处理中和已完成任务
- `任务详情`
  - 以 speaker 过滤、时间线、分段阅读流为核心
  - 支持导出、快速重跑、跳转声纹库继续处理
- `声纹库`
  - 既能独立做验证/识别/注册，也能承接任务上下文做 speaker 回写
- `模型状态`
  - 强调真实可用性，不再只是模型清单
  - 明确区分本地 GPU 已就绪能力与受限能力
- `模型管理`
  - 用于手动加载、卸载模型与查看显存占用
  - 让 GPU 运行时准备工作显式可见

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

## 核心流水线评测

可以用离线评测脚本直接检查现有转写产物，不需要重新跑模型：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_core_pipeline.py `
  storage\experiments\standard_recording_1\standard_recording_1_15min_multispeaker_readable_v20_hotwords.txt `
  --sample-name standard_recording_1_15min_eval
```

如果有参考稿、热词或会议纪要 JSON，可以追加：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_core_pipeline.py result.json `
  --reference-text reference.txt `
  --hotwords-file hotwords.txt `
  --minutes-json minutes.json
```

脚本会输出：

- `*_evaluation.json`：结构化指标，便于后续自动对比
- `*_evaluation.md`：可读报告，包含 ASR、Speaker、声纹和会议纪要诊断

当前第一版指标包括 CER、文本相似度、热词召回、speaker 短碎片率、换人频率、声纹低置信统计、声纹 Top1/TopK 命中率、近似 EER 和会议纪要证据覆盖率。会议纪要诊断不仅输出决策、行动项、风险的覆盖率，还会为每条纪要生成 `evidence_rows`，记录证据分数、命中的 transcript 片段、弱证据项和缺证据项；会议纪要接口自身的 `evidence` 也会返回 `evidence_score`、`reason`、命中 token 和缺失 token，避免长会议摘要只看总分而无法定位漏召回。

如果要把多个固定样本做成可横向比较的版本基线，先维护一个样本集 manifest。
示例 manifest 已指向本地 15 分钟参考稿切片；首次运行前，先用完整参考稿导出这个切片：

```powershell
.\.venv\Scripts\python.exe scripts\export_reference_slice.py `
  "G:\desktop\通用语音识别_标准录音 1.mp3.txt" `
  storage\experiments\standard_recording_1_15min_refbench\standard_recording_1_15min_reference_slice.txt `
  --audio storage\experiments\standard_recording_1\standard_recording_1_16k.wav `
  --max-seconds 900 `
  --metadata-json storage\experiments\standard_recording_1_15min_refbench\standard_recording_1_15min_reference_slice.json
```

manifest 每个样本支持：

- `transcript`：必填，TranscriptResult JSON 或 readable txt
- `reference_text`：参考稿，用于 CER / 文本相似度
- `reference_metadata`：可选，参考稿元数据 JSON；比例切片会自动标记为草稿
- `reference_quality`：可选，只有 `confirmed` / `gold` / `manual` / `aligned` 会进入正式 ASR 聚合
- `reference_speakers`：RTTM、TranscriptResult JSON 或 readable txt，用于轻量 DER / JER
- `hotwords_file`：热词 txt 或 `{hotwords: []}` JSON
- `voiceprint_labels`：`{speaker: profile_id}` JSON，用于阈值扫描与近似 EER
- `minutes_json`：人工纪要基准，用于决策、行动项、风险覆盖率

注意：`export_reference_slice.py` 生成的 `time_ratio` 参考稿只是启动标注用的草稿。它会保留 ASR 诊断值，但默认不进入样本集的正式 CER 聚合；人工复核或时间戳对齐后，再把 manifest 中的 `reference_quality` 改为 `confirmed`。

批量评测会输出：

- `*_baseline.json`：样本明细 + 聚合指标
- `*_baseline.md`：适合人工复核的基线报告

然后执行样本集评测：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_core_pipeline_dataset.py configs\evaluation\core_pipeline_dataset.example.json
```

剩余标注可以先从当前转写结果生成草稿模板，再人工复核：

```powershell
.\.venv\Scripts\python.exe scripts\generate_evaluation_annotation_templates.py `
  storage\experiments\standard_recording_1\standard_recording_1_15min_multispeaker_readable_v20_hotwords.txt `
  --sample-id standard_recording_1_15min `
  --output-dir storage\experiments\standard_recording_1_15min_refbench `
  --prefix standard_recording_1_15min
```

该命令会生成 RTTM、声纹标签 JSON、人工纪要 JSON 与复核清单。它们只是从模型结果转换来的草稿，必须人工校正后再写入 manifest 的 `reference_speakers` / `voiceprint_labels` / `minutes_json`。

有多个版本的 baseline 后，可以横向比较：

```powershell
.\.venv\Scripts\python.exe scripts\compare_core_pipeline_baselines.py `
  storage\experiments\core_pipeline_baseline_example\core_pipeline_baseline_example_baseline.json `
  storage\experiments\core_pipeline_baseline_example\core_pipeline_baseline_example_baseline.json
```

对比报告会列出每个 baseline 的核心指标，并给出相对首个 baseline 的变化值。除 CER、DER、声纹和纪要覆盖外，对比表也会展示中文断词边界数/比例、前导标点段数/比例，方便评估 speaker 对齐优化是否真实改善可读性，并避免不同长度样本只按绝对数量比较。

## 端到端 API Smoke

离线评测用于比较算法产物，API smoke 用于验证“真实用户路径”是否打通：上传音频、创建任务、轮询状态、读取转写详情，并可选生成会议纪要。
先分别启动 API 与 worker，然后运行：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_api_core_pipeline.py `
  --base-url http://127.0.0.1:8000 `
  --audio tests\fixtures\sample-meeting.wav `
  --minutes-mode local
```

如果音频已经上传过，可以复用后端返回的 `asset_name`：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_api_core_pipeline.py `
  --asset-name sample-meeting.wav `
  --num-speakers 3 `
  --hotword 分类分级 `
  --hotword 数据资产 `
  --hotwords-file hotwords.txt
```

脚本默认创建多人转写任务，报告会写入 `storage/experiments/<sample>/api_smoke_report_*.json`，其中包含每个接口的耗时、状态码、错误详情、任务 ID、最终任务状态、speaker 数量和会议纪要证据计数。最终任务不是 `succeeded` 时，脚本会返回非零退出码并保留失败报告，方便接入发布前验收。需要只验证单人转写时，追加 `--single-speaker`；需要验证 LLM 纪要时，追加 `--minutes-mode llm`。

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
也可以先调用 `/api/v1/health` 查看 `audio_decoder.warning`，确认当前压缩音频解码是否处于回退状态。

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
