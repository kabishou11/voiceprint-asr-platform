import AddRounded from '@mui/icons-material/AddRounded';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import CheckCircleOutlineRounded from '@mui/icons-material/CheckCircleOutlineRounded';
import ErrorOutlineRounded from '@mui/icons-material/ErrorOutlineRounded';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import FingerprintRounded from '@mui/icons-material/FingerprintRounded';
import HourglassEmptyRounded from '@mui/icons-material/HourglassEmptyRounded';
import MicExternalOnRounded from '@mui/icons-material/MicExternalOnRounded';
import QueueMusicRounded from '@mui/icons-material/QueueMusicRounded';
import RecordVoiceOverRounded from '@mui/icons-material/RecordVoiceOverRounded';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControlLabel,
  Grid,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { createTranscription, fetchJobs, fetchModels, uploadAudio } from '../../api/client';
import { formatDateTime, jobTypeLabels } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { AudioUploadField } from '../../components/AudioUploadField';
import { BrandLogo } from '../../components/BrandLogo';
import { PageSection } from '../../components/PageSection';
import { BalancedPretextText, MeasuredPretextBlock } from '../../components/PretextText';
import { StatCard } from '../../components/StatCard';
import { StatusChip } from '../../components/StatusChip';

const quickTemplates = [
  '罗大佑 - 光阴的故事(片头曲).wav',
  '丹山路.m4a',
  '5分钟.wav',
];

function TonePill({
  label,
  active = false,
}: {
  label: string;
  active?: boolean;
}) {
  return (
    <Chip
      label={label}
      size="small"
      sx={{
        bgcolor: active ? alpha('#2f6fed', 0.1) : alpha('#ffffff', 0.74),
        color: active ? 'primary.main' : 'text.secondary',
        border: '1px solid',
        borderColor: active ? alpha('#2f6fed', 0.18) : 'divider',
      }}
    />
  );
}

export function TranscriptionWorkbenchPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadedAssetName, setUploadedAssetName] = useState('');
  const [diarizationModel, setDiarizationModel] = useState('');
  const [language, setLanguage] = useState('zh-cn');
  const [hotwordsText, setHotwordsText] = useState('');
  const [vadEnabled, setVadEnabled] = useState(true);
  const [itnEnabled, setItnEnabled] = useState(true);
  const [numSpeakersText, setNumSpeakersText] = useState('');
  const [minSpeakersText, setMinSpeakersText] = useState('');
  const [maxSpeakersText, setMaxSpeakersText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const modelsState = useAsyncData(() => fetchModels(), []);
  const jobsState = useAsyncData(() => fetchJobs(), []);

  const diarizationOptions = useMemo(
    () =>
      (modelsState.data?.items ?? []).filter(
        (item) => item.task === 'diarization' && item.availability === 'available',
      ),
    [modelsState.data],
  );
  const availableModelKeys = useMemo(
    () =>
      new Set(
        (modelsState.data?.items ?? [])
          .filter((item) => item.availability === 'available')
          .map((item) => item.key),
      ),
    [modelsState.data],
  );
  const asrReady = availableModelKeys.has('funasr-nano');
  const threeDSpeakerReady = availableModelKeys.has('3dspeaker-diarization');
  const voiceprintReady = availableModelKeys.has('3dspeaker-embedding');
  const pyannoteReady = availableModelKeys.has('pyannote-community-1');

  useEffect(() => {
    if (!diarizationModel && diarizationOptions.length > 0) {
      setDiarizationModel(diarizationOptions[0].key);
    }
  }, [diarizationModel, diarizationOptions]);

  useEffect(() => {
    const asset = searchParams.get('asset') ?? '';
    const incomingLanguage = searchParams.get('language') ?? '';
    const mode = searchParams.get('mode') ?? '';

    if (asset) {
      setUploadedAssetName(asset);
      setSelectedFile(null);
    }
    if (incomingLanguage) {
      setLanguage(incomingLanguage);
    }
    if (mode === 'single') {
      setDiarizationModel('');
    }
    if (mode === 'multi' && diarizationOptions.length > 0) {
      setDiarizationModel(diarizationOptions[0].key);
    }
  }, [diarizationOptions, searchParams]);

  const jobSummary = useMemo(() => {
    const items = jobsState.data?.items ?? [];
    return {
      total: items.length,
      running: items.filter((j) => j.status === 'running' || j.status === 'queued').length,
      done: items.filter((j) => j.status === 'succeeded').length,
      failed: items.filter((j) => j.status === 'failed').length,
    };
  }, [jobsState.data]);

  const recentJobs = useMemo(() => (jobsState.data?.items ?? []).slice(0, 4), [jobsState.data]);

  const parsedHotwords = useMemo(
    () =>
      hotwordsText
        .split(/[\n,，、]/)
        .map((item) => item.trim())
        .filter(Boolean),
    [hotwordsText],
  );

  const parseInteger = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const parsed = Number.parseInt(trimmed, 10);
    return Number.isNaN(parsed) ? null : parsed;
  };

  const handleSubmit = async () => {
    if (!selectedFile && !uploadedAssetName.trim()) {
      setSubmitError('请先选择音频文件');
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      let assetName = uploadedAssetName.trim();
      if (selectedFile) {
        const uploaded = await uploadAudio(selectedFile);
        assetName = uploaded.asset_name;
        setUploadedAssetName(uploaded.asset_name);
      }
      const response = await createTranscription({
        asset_name: assetName,
        diarization_model: diarizationModel || null,
        hotwords: parsedHotwords.length ? parsedHotwords : null,
        language,
        vad_enabled: vadEnabled,
        itn: itnEnabled,
        num_speakers: parseInteger(numSpeakersText),
        min_speakers: parseInteger(minSpeakersText),
        max_speakers: parseInteger(maxSpeakersText),
      });
      navigate(`/jobs/${response.job.job_id}`);
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : '创建任务失败');
    } finally {
      setSubmitting(false);
    }
  };

  const capabilityCards = [
    {
      icon: <MicExternalOnRounded sx={{ fontSize: 24 }} />,
      label: '语音识别',
      desc: asrReady
        ? 'FunASR 本地高精度模型已就绪，当前会严格走 CUDA 推理。'
        : '当前 ASR 运行时未满足 CUDA 要求，高精度转写任务会直接被拒绝。',
      chip: asrReady ? 'CUDA 已就绪' : 'CUDA 未就绪',
      chipColor: asrReady ? ('primary' as const) : ('error' as const),
      actionLabel: '已内置',
      action: () => undefined,
    },
    {
      icon: <RecordVoiceOverRounded sx={{ fontSize: 24 }} />,
      label: '说话人分离',
      desc: threeDSpeakerReady
        ? '3D-Speaker + FSMN-VAD 已就绪，当前多人任务默认走本地说话人分离链路。'
        : '当前未检测到可用本地说话人分离模型，只能退回标准转写。',
      chip: threeDSpeakerReady ? '本地已就绪' : '需补模型',
      chipColor: threeDSpeakerReady ? ('success' as const) : ('error' as const),
      actionLabel: '已内置',
      action: () => undefined,
    },
    {
      icon: <FingerprintRounded sx={{ fontSize: 24 }} />,
      label: '声纹识别',
      desc: voiceprintReady
        ? 'CAM++ 本地模型已接入，支持 1:1 验证与 1:N 识别。'
        : '依赖 3D-Speaker 与 CUDA 运行时，未就绪时不会进入真实声纹推理。',
      chip: voiceprintReady ? '本地可用' : '不可用',
      chipColor: voiceprintReady ? ('warning' as const) : ('error' as const),
      actionLabel: '前往声纹库',
      action: () => navigate('/voiceprints'),
    },
  ];

  return (
    <Stack spacing={3.5}>
      <PageSection
        title="将音频直接送入高精度多人转写工作流"
        eyebrow="任务工作台"
        eyebrowColor="secondary"
        description="上传音频、配置热词与说话人数约束，然后直接进入本地 GPU 驱动的 FunASR + 3D-Speaker 主链路。结果页会优先展示更稳定的 display timeline 与 speaker 复核工作区。"
        loading={modelsState.loading || jobsState.loading}
        error={modelsState.error ?? jobsState.error}
        actions={
          <Button
            variant="contained"
            startIcon={<AddRounded />}
            onClick={handleSubmit}
            disabled={submitting || !asrReady || (!selectedFile && !uploadedAssetName.trim())}
          >
            {submitting ? '正在创建' : '新建任务'}
          </Button>
        }
      >
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, xl: 8.5 }}>
            <Card
              sx={{
                overflow: 'hidden',
                background:
                  'linear-gradient(180deg, rgba(255,252,247,0.96) 0%, rgba(250,246,240,0.94) 100%)',
              }}
            >
              <CardContent sx={{ p: { xs: 2.6, md: 3.2 } }}>
                <Stack spacing={3}>
                  <Stack
                    direction={{ xs: 'column', lg: 'row' }}
                    spacing={3}
                    justifyContent="space-between"
                  >
                      <Stack spacing={1.6} sx={{ maxWidth: 620 }}>
                        <Stack direction="row" spacing={1.2} alignItems="center">
                          <BrandLogo size={54} title="Voiceprint" subtitle="ASR Platform" />
                        </Stack>
                        <BalancedPretextText
                          text="Good afternoon, 直接开始你的多人语音工作流"
                          font='500 52px "Iowan Old Style"'
                          lineHeight={58}
                          targetLines={2}
                          minWidth={360}
                          maxWidth={620}
                          typographyProps={{
                            variant: 'h2',
                            sx: {
                              maxWidth: 620,
                              fontSize: { xs: '2.3rem', md: '3.25rem' },
                            },
                          }}
                        />
                        <MeasuredPretextBlock
                          text="当前首页不再强调仪表盘，而是优先把上传、参数和模型可用性集中到一处。你可以先发起任务，再去结果页做 speaker 复核与声纹处理。"
                          font='400 16px "PingFang SC"'
                          lineHeight={30}
                          typographyProps={{
                            color: 'text.secondary',
                            sx: {
                              maxWidth: 580,
                              fontSize: 16,
                              lineHeight: 1.9,
                            },
                          }}
                        />
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <TonePill label="Claude 风格工作台" active />
                        <TonePill label="本地 GPU 推理" active={asrReady} />
                        <TonePill label="多人转写优先" active={threeDSpeakerReady} />
                        <TonePill label="可接声纹核验" active={voiceprintReady} />
                      </Stack>
                    </Stack>
                    <Card
                      variant="outlined"
                      sx={{
                        minWidth: { xs: '100%', lg: 290 },
                        maxWidth: 340,
                        bgcolor: alpha('#ffffff', 0.68),
                        borderColor: alpha('#1c2431', 0.08),
                      }}
                    >
                      <CardContent>
                        <Stack spacing={1.4}>
                          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: '0.08em' }}>
                            模式摘要
                          </Typography>
                          <Typography variant="h6">默认直达多人转写与说话人分离</Typography>
                          <Typography variant="body2" color="text.secondary">
                            适合会议纪要、访谈、客服质检和声纹核验前处理。
                          </Typography>
                          <Divider />
                          <Stack spacing={1}>
                            <Typography variant="body2" color="text.secondary">
                              当前说话人模式
                            </Typography>
                            <Typography fontWeight={700}>
                              {diarizationModel ? '多人转写（已启用 diarization）' : '标准转写（可选）'}
                            </Typography>
                          </Stack>
                          <Stack spacing={1}>
                            <Typography variant="body2" color="text.secondary">
                              快速样例
                            </Typography>
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                              {quickTemplates.map((item) => (
                                <Chip
                                  key={item}
                                  label={item}
                                  onClick={() => {
                                    setUploadedAssetName(item);
                                    setSelectedFile(null);
                                  }}
                                  sx={{
                                    bgcolor: alpha('#ffffff', 0.8),
                                    border: '1px solid',
                                    borderColor: 'divider',
                                  }}
                                />
                              ))}
                            </Stack>
                          </Stack>
                        </Stack>
                      </CardContent>
                    </Card>
                  </Stack>

                  <Card
                    variant="outlined"
                    sx={{
                      borderRadius: 5,
                      bgcolor: alpha('#ffffff', 0.74),
                      borderColor: alpha('#1c2431', 0.07),
                    }}
                  >
                    <CardContent sx={{ p: { xs: 2, md: 2.5 } }}>
                      <Grid container spacing={2.25}>
                        <Grid size={{ xs: 12, lg: 8 }}>
                          <Stack spacing={2.1}>
                            <Typography variant="h5">快速发起任务</Typography>
                            <AudioUploadField
                              label="上传音频文件"
                              fileName={(selectedFile?.name ?? uploadedAssetName) || null}
                              helperText="支持 wav、m4a、mp3、flac；上传后会自动生成资产名并创建任务。"
                              disabled={submitting}
                              error={null}
                              onChange={(file) => {
                                setSelectedFile(file);
                                if (file) {
                                  setUploadedAssetName('');
                                }
                              }}
                            />
                            {uploadedAssetName ? (
                              <Typography variant="body2" color="text.secondary">
                                当前将使用资产：{uploadedAssetName}
                              </Typography>
                            ) : null}
                            {searchParams.get('asset') ? (
                              <Alert severity="info">
                                已从历史任务带入资产与基础参数，可直接重新发起转写。
                              </Alert>
                            ) : null}
                            {!asrReady ? (
                              <Alert severity="error">
                                当前运行时未满足高精度推理要求。系统现在强制要求本地模型、运行时依赖和 CUDA GPU 同时就绪；若只安装了 CPU 版 `torch`，转写与多人分离任务都会直接被拒绝。
                              </Alert>
                            ) : null}
                            {threeDSpeakerReady ? (
                              <Alert severity="success">
                                3D-Speaker 与本地 VAD 已就绪，当前多人转写会优先走真实本地说话人分离路径，且已完成最小 GPU 实跑。
                              </Alert>
                            ) : null}
                            {diarizationOptions.length === 0 ? (
                              <Alert severity="warning">
                                当前未检测到可用的本地说话人分离模型，现阶段只能稳定使用标准转写路径。请先补齐 `models/3D-Speaker/campplus` 与相关本地模型文件。
                              </Alert>
                            ) : null}
                            {threeDSpeakerReady && !pyannoteReady ? (
                              <Alert severity="info">
                                高级重叠说话增强仍未启用。`pyannote` 官方离线包尚未补齐，本地多人转写当前以 3D-Speaker 主链路为准。
                              </Alert>
                            ) : null}
                          </Stack>
                        </Grid>
                        <Grid size={{ xs: 12, lg: 4 }}>
                          <Stack spacing={1.7}>
                            <TextField
                              select
                              label="说话人模式"
                              value={diarizationModel}
                              onChange={(event) => setDiarizationModel(event.target.value)}
                              helperText="默认已启用说话人分离；如需仅文本转写，可切换为标准转写。"
                              disabled={!asrReady}
                            >
                              <MenuItem value="">标准转写（可选）</MenuItem>
                              {diarizationOptions.map((item) => (
                                <MenuItem key={item.key} value={item.key}>
                                  {item.display_name}
                                </MenuItem>
                              ))}
                            </TextField>
                            <Accordion
                              elevation={0}
                              disableGutters
                              sx={{
                                border: '1px solid',
                                borderColor: 'divider',
                                borderRadius: 4,
                                bgcolor: alpha('#ffffff', 0.7),
                              }}
                            >
                              <AccordionSummary expandIcon={<ExpandMoreRounded />}>
                                <Stack spacing={0.4}>
                                  <Typography fontWeight={700}>高级设置</Typography>
                                  <Typography variant="body2" color="text.secondary">
                                    语言、热词、VAD、ITN 和说话人数约束
                                  </Typography>
                                </Stack>
                              </AccordionSummary>
                              <AccordionDetails>
                                <Stack spacing={2}>
                                  <TextField
                                    select
                                    label="语言"
                                    value={language}
                                    onChange={(event) => setLanguage(event.target.value)}
                                  >
                                    <MenuItem value="zh-cn">中文普通话</MenuItem>
                                    <MenuItem value="en">英文</MenuItem>
                                    <MenuItem value="yue">粤语</MenuItem>
                                  </TextField>
                                  <TextField
                                    label="热词"
                                    value={hotwordsText}
                                    onChange={(event) => setHotwordsText(event.target.value)}
                                    helperText="用逗号、顿号或换行分隔，例如：项目名、人名、术语。"
                                    multiline
                                    minRows={2}
                                  />
                                  <Grid container spacing={1.25}>
                                    <Grid size={{ xs: 12, sm: 4 }}>
                                      <TextField
                                        label="已知说话人数"
                                        value={numSpeakersText}
                                        onChange={(event) => setNumSpeakersText(event.target.value)}
                                        placeholder="可选"
                                      />
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 4 }}>
                                      <TextField
                                        label="最少说话人数"
                                        value={minSpeakersText}
                                        onChange={(event) => setMinSpeakersText(event.target.value)}
                                        placeholder="可选"
                                      />
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 4 }}>
                                      <TextField
                                        label="最多说话人数"
                                        value={maxSpeakersText}
                                        onChange={(event) => setMaxSpeakersText(event.target.value)}
                                        placeholder="可选"
                                      />
                                    </Grid>
                                  </Grid>
                                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                                    <FormControlLabel
                                      control={
                                        <Switch
                                          checked={vadEnabled}
                                          onChange={(event) => setVadEnabled(event.target.checked)}
                                        />
                                      }
                                      label="启用 VAD"
                                    />
                                    <FormControlLabel
                                      control={
                                        <Switch
                                          checked={itnEnabled}
                                          onChange={(event) => setItnEnabled(event.target.checked)}
                                        />
                                      }
                                      label="启用 ITN"
                                    />
                                  </Stack>
                                </Stack>
                              </AccordionDetails>
                            </Accordion>
                            {submitError ? <Alert severity="error">{submitError}</Alert> : null}
                            <Stack direction="row" spacing={1.25}>
                              <Button
                                variant="contained"
                                fullWidth
                                onClick={handleSubmit}
                                disabled={
                                  submitting || !asrReady || (!selectedFile && !uploadedAssetName.trim())
                                }
                              >
                                {submitting ? '创建中' : '立即开始'}
                              </Button>
                              <Button variant="outlined" fullWidth onClick={() => navigate('/jobs')}>
                                查看全部任务
                              </Button>
                            </Stack>
                          </Stack>
                        </Grid>
                      </Grid>
                    </CardContent>
                  </Card>
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          <Grid size={{ xs: 12, xl: 3.5 }}>
            <Stack spacing={2.4}>
              <Grid container spacing={1.5}>
                <Grid size={{ xs: 6, md: 3, xl: 12 }}>
                  <StatCard
                    label="总任务数"
                    value={String(jobSummary.total)}
                    icon={<QueueMusicRounded fontSize="small" />}
                    color="primary"
                  />
                </Grid>
                <Grid size={{ xs: 6, md: 3, xl: 12 }}>
                  <StatCard
                    label="处理中"
                    value={String(jobSummary.running)}
                    icon={<HourglassEmptyRounded fontSize="small" />}
                    color="warning"
                  />
                </Grid>
                <Grid size={{ xs: 6, md: 3, xl: 12 }}>
                  <StatCard
                    label="已完成"
                    value={String(jobSummary.done)}
                    icon={<CheckCircleOutlineRounded fontSize="small" />}
                    color="success"
                  />
                </Grid>
                {jobSummary.failed > 0 ? (
                  <Grid size={{ xs: 6, md: 3, xl: 12 }}>
                    <StatCard
                      label="失败"
                      value={String(jobSummary.failed)}
                      icon={<ErrorOutlineRounded fontSize="small" />}
                      color="error"
                    />
                  </Grid>
                ) : null}
              </Grid>

              <Card>
                <CardContent>
                  <Stack spacing={1.8}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                      <Typography variant="h6">最近任务</Typography>
                      <Button size="small" onClick={() => navigate('/jobs')}>
                        查看全部
                      </Button>
                    </Stack>
                    <Stack spacing={1.2}>
                      {recentJobs.length ? (
                        recentJobs.map((job) => (
                          <Box
                            key={job.job_id}
                            sx={{
                              p: 1.5,
                              borderRadius: 4,
                              bgcolor: alpha('#ffffff', 0.74),
                              border: '1px solid',
                              borderColor: alpha('#1c2431', 0.06),
                            }}
                          >
                            <Stack spacing={1}>
                              <Stack direction="row" justifyContent="space-between" spacing={1}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                  {job.asset_name ?? job.job_id}
                                </Typography>
                                <StatusChip status={job.status} />
                              </Stack>
                              <Typography variant="body2" color="text.secondary">
                                {jobTypeLabels[job.job_type]} · {formatDateTime(job.updated_at)}
                              </Typography>
                              <Button
                                size="small"
                                sx={{ alignSelf: 'flex-start', px: 0 }}
                                onClick={() => navigate(`/jobs/${job.job_id}`)}
                              >
                                继续复核
                              </Button>
                            </Stack>
                          </Box>
                        ))
                      ) : (
                        <Alert severity="info">暂无任务记录。</Alert>
                      )}
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>
          </Grid>
        </Grid>

        <Grid container spacing={3}>
          <Grid size={{ xs: 12, lg: 5.5 }}>
            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h5">模型状态与能力边界</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ textWrap: 'pretty' }}>
                    当前首页只保留最影响任务发起的状态，不再堆大量说明卡片。高精度能力是否可用，会在这里以更安静的方式提示。
                  </Typography>
                  <Stack spacing={1.25}>
                    {capabilityCards.map((item) => (
                      <Box
                        key={item.label}
                        sx={{
                          p: 1.5,
                          borderRadius: 4,
                          bgcolor: alpha('#ffffff', 0.72),
                          border: '1px solid',
                          borderColor: alpha('#1c2431', 0.06),
                        }}
                      >
                        <Stack spacing={1.1}>
                          <Stack direction="row" spacing={1.3} alignItems="center">
                            <Box sx={{ color: 'primary.main', display: 'flex' }}>{item.icon}</Box>
                            <Typography fontWeight={700}>{item.label}</Typography>
                            <Chip size="small" label={item.chip} color={item.chipColor} />
                          </Stack>
                          <Typography variant="body2" color="text.secondary">
                            {item.desc}
                          </Typography>
                          {item.label === '语音识别' && parsedHotwords.length ? (
                            <Chip size="small" variant="outlined" label={`热词 ${parsedHotwords.length}`} />
                          ) : null}
                          <Button
                            size="small"
                            variant="text"
                            onClick={item.action}
                            sx={{ alignSelf: 'flex-start', px: 0 }}
                          >
                            {item.actionLabel}
                          </Button>
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
          <Grid size={{ xs: 12, lg: 6.5 }}>
            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="h5">工作流提示</Typography>
                  <Grid container spacing={1.5}>
                    {[
                      {
                        title: '先发起任务',
                        desc: '上传或复用历史资产，先确定语言、热词和说话人数约束。',
                      },
                      {
                        title: '再做复核',
                        desc: '任务详情页会优先显示 display timeline 与 speaker 聚焦视图。',
                      },
                      {
                        title: '最后做声纹处理',
                        desc: '从 speaker 卡片直接跳入声纹库，完成识别、验证或注册。',
                      },
                    ].map((item, index) => (
                      <Grid key={item.title} size={{ xs: 12, md: 4 }}>
                        <Box
                          sx={{
                            height: '100%',
                            p: 1.6,
                            borderRadius: 4,
                            bgcolor: alpha('#ffffff', 0.68),
                            border: '1px solid',
                            borderColor: alpha('#1c2431', 0.06),
                          }}
                        >
                          <Stack spacing={1}>
                            <Stack direction="row" spacing={1} alignItems="center">
                              <Chip
                                size="small"
                                label={`0${index + 1}`}
                                sx={{
                                  bgcolor: alpha('#2f6fed', 0.08),
                                  color: 'primary.main',
                                }}
                              />
                              <Typography fontWeight={700}>{item.title}</Typography>
                            </Stack>
                            <Typography variant="body2" color="text.secondary">
                              {item.desc}
                            </Typography>
                          </Stack>
                        </Box>
                      </Grid>
                    ))}
                  </Grid>
                  <Divider />
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <TonePill label="多人链路就绪" active={threeDSpeakerReady} />
                    <TonePill label="GPU 已就绪" active={asrReady} />
                    <TonePill label="pyannote 待补齐" active={false} />
                    <TonePill label="可直接查看结果" active />
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </PageSection>
    </Stack>
  );
}
