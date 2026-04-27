import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
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
import { PageSection } from '../../components/PageSection';
import { StatCard } from '../../components/StatCard';
import { StatusChip } from '../../components/StatusChip';

const RECENT_ACTIVE_JOB_STORAGE_KEY = 'voiceprint-active-job-ids';
type RuntimeState = 'ready' | 'loading' | 'loadable' | 'unavailable';

function runtimeLabel(label: string, state: RuntimeState) {
  if (state === 'ready') {
    return `${label} 已就绪`;
  }
  if (state === 'loading') {
    return `${label} 加载中`;
  }
  if (state === 'loadable') {
    return `${label} 可加载`;
  }
  return `${label} 不可用`;
}

function runtimeColor(state: RuntimeState): 'success' | 'warning' | 'info' | 'default' | 'error' {
  if (state === 'ready') {
    return 'success';
  }
  if (state === 'loading') {
    return 'warning';
  }
  if (state === 'loadable') {
    return 'info';
  }
  return 'default';
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
  const modelItems = modelsState.data?.items ?? [];
  const gpuReady = modelsState.data?.gpu?.cuda_available ?? false;

  const resolveRuntimeState = (key: string): RuntimeState => {
    const item = modelItems.find((candidate) => candidate.key === key);
    if (!item) {
      return 'unavailable';
    }
    if (item.status === 'loaded') {
      return 'ready';
    }
    if (item.status === 'loading') {
      return 'loading';
    }
    if (item.status === 'unloaded') {
      return gpuReady ? 'loadable' : 'unavailable';
    }
    return 'unavailable';
  };

  const diarizationOptions = useMemo(
    () => modelItems.filter((item) => item.task === 'diarization' && item.status !== 'load_failed'),
    [modelItems],
  );

  const asrState = resolveRuntimeState('funasr-nano');
  const diarizationState = resolveRuntimeState('3dspeaker-diarization');
  const voiceprintState = resolveRuntimeState('3dspeaker-embedding');
  const pyannoteState = resolveRuntimeState('pyannote-community-1');
  const asrLoadable = asrState !== 'unavailable';

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

  const recentJobs = useMemo(() => (jobsState.data?.items ?? []).slice(0, 6), [jobsState.data]);
  const activeJobs = useMemo(
    () => (jobsState.data?.items ?? []).filter((job) => job.status === 'running' || job.status === 'queued'),
    [jobsState.data],
  );

  const parsedHotwords = useMemo(
    () => hotwordsText.split(/[\n,，、]/).map((item) => item.trim()).filter(Boolean),
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
    const numSpeakers = parseInteger(numSpeakersText);
    const minSpeakers = parseInteger(minSpeakersText);
    const maxSpeakers = parseInteger(maxSpeakersText);

    if (!selectedFile && !uploadedAssetName.trim()) {
      setSubmitError('请先选择音频文件');
      return;
    }
    if (minSpeakers && maxSpeakers && minSpeakers > maxSpeakers) {
      setSubmitError('最少说话人数不能大于最多说话人数');
      return;
    }
    if (numSpeakers && minSpeakers && numSpeakers < minSpeakers) {
      setSubmitError('已知说话人数不能小于最少说话人数');
      return;
    }
    if (numSpeakers && maxSpeakers && numSpeakers > maxSpeakers) {
      setSubmitError('已知说话人数不能大于最多说话人数');
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
        num_speakers: numSpeakers,
        min_speakers: minSpeakers,
        max_speakers: maxSpeakers,
      });
      jobsState.setData((current) => ({
        items: [response.job, ...(current?.items ?? []).filter((job) => job.job_id !== response.job.job_id)],
      }));
      if (typeof window !== 'undefined') {
        const raw = window.localStorage.getItem(RECENT_ACTIVE_JOB_STORAGE_KEY);
        const stored = raw ? (JSON.parse(raw) as string[]) : [];
        window.localStorage.setItem(
          RECENT_ACTIVE_JOB_STORAGE_KEY,
          JSON.stringify([
            response.job.job_id,
            ...stored.filter((item) => item !== response.job.job_id),
          ].slice(0, 8)),
        );
      }
      navigate(`/jobs/${response.job.job_id}`);
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : '创建任务失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PageSection
      compact
      title="开始任务"
      description="上传音频、选择模式并快速进入结果审阅。"
      loading={modelsState.loading || jobsState.loading}
      error={modelsState.error ?? jobsState.error}
      actions={
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => navigate('/tasks')}>
            队列
          </Button>
          <Button variant="outlined" onClick={() => navigate('/system/models')}>
            模型
          </Button>
        </Stack>
      }
    >
      <Stack spacing={1.8}>
        <Grid container spacing={1.2}>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="运行中任务" value={activeJobs.length} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="ASR 状态" value={runtimeLabel('ASR', asrState).replace('ASR ', '')} color={runtimeColor(asrState) === 'success' ? 'success' : 'warning'} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="分离状态" value={runtimeLabel('分离', diarizationState).replace('分离 ', '')} color={runtimeColor(diarizationState) === 'success' ? 'success' : 'warning'} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="运行设备" value={gpuReady ? 'GPU' : 'CPU'} color={gpuReady ? 'success' : 'warning'} />
          </Grid>
        </Grid>

        <Grid container spacing={1.8}>
          <Grid size={{ xs: 12, xl: 8 }}>
            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip size="small" label={gpuReady ? 'GPU 已就绪' : 'CUDA 未就绪'} color={gpuReady ? 'success' : 'default'} />
                    <Chip size="small" label={runtimeLabel('ASR', asrState)} color={runtimeColor(asrState)} />
                    <Chip size="small" label={runtimeLabel('分离', diarizationState)} color={runtimeColor(diarizationState)} />
                    <Chip size="small" label={runtimeLabel('声纹', voiceprintState)} color={runtimeColor(voiceprintState)} />
                    <Chip size="small" label={pyannoteState === 'ready' ? 'pyannote 已就绪' : 'pyannote 未启用'} color={pyannoteState === 'ready' ? 'success' : 'default'} />
                  </Stack>

                  {activeJobs.length ? (
                    <Alert severity="info" sx={{ borderRadius: 3 }}>
                      后台仍有 {activeJobs.length} 个任务在运行。
                    </Alert>
                  ) : null}

                  {searchParams.get('asset') ? (
                    <Alert severity="info" sx={{ borderRadius: 3 }}>
                      <Stack spacing={0.5}>
                        <Typography fontWeight={700}>已带入历史任务参数</Typography>
                        <Typography variant="body2">当前将使用资产：{uploadedAssetName}</Typography>
                      </Stack>
                    </Alert>
                  ) : null}

                  <AudioUploadField
                    label="音频"
                    fileName={selectedFile?.name ?? (uploadedAssetName || null)}
                    helperText="支持 wav、m4a、mp3、flac。"
                    onChange={(file) => {
                      setSelectedFile(file);
                      if (file) {
                        setUploadedAssetName('');
                      }
                    }}
                  />

                  {uploadedAssetName && !selectedFile ? (
                    <Box
                      sx={{
                        px: 1.5,
                        py: 1.1,
                        borderRadius: 3,
                        bgcolor: alpha('#2f6fed', 0.05),
                        border: '1px solid',
                        borderColor: alpha('#2f6fed', 0.12),
                      }}
                    >
                      <Typography variant="body2" color="text.secondary">
                        当前将使用资产：{uploadedAssetName}
                      </Typography>
                    </Box>
                  ) : null}

                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                    <TextField select fullWidth label="语言" value={language} onChange={(event) => setLanguage(event.target.value)}>
                      <MenuItem value="zh-cn">中文</MenuItem>
                      <MenuItem value="en">英文</MenuItem>
                      <MenuItem value="ja">日文</MenuItem>
                      <MenuItem value="auto">自动检测</MenuItem>
                    </TextField>
                    <TextField
                      select
                      fullWidth
                      label="任务模式"
                      value={diarizationModel ? 'multi' : 'single'}
                      onChange={(event) => {
                        if (event.target.value === 'single') {
                          setDiarizationModel('');
                        } else if (diarizationOptions.length > 0) {
                          setDiarizationModel(diarizationOptions[0].key);
                        }
                      }}
                    >
                      <MenuItem value="single">单人转写</MenuItem>
                      <MenuItem value="multi">多人转写</MenuItem>
                    </TextField>
                  </Stack>

                  <Accordion disableGutters elevation={0} sx={{ bgcolor: 'transparent' }}>
                    <AccordionSummary expandIcon={<ExpandMoreRounded />}>
                      <Typography fontWeight={700}>高级设置</Typography>
                    </AccordionSummary>
                    <AccordionDetails sx={{ px: 0 }}>
                      <Stack spacing={1.5}>
                        <TextField
                          label="热词"
                          value={hotwordsText}
                          onChange={(event) => setHotwordsText(event.target.value)}
                          multiline
                          minRows={3}
                          placeholder="每行一个，或用逗号分隔"
                        />
                        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                          <TextField label="已知说话人数" value={numSpeakersText} onChange={(event) => setNumSpeakersText(event.target.value)} />
                          <TextField label="最少说话人数" value={minSpeakersText} onChange={(event) => setMinSpeakersText(event.target.value)} />
                          <TextField label="最多说话人数" value={maxSpeakersText} onChange={(event) => setMaxSpeakersText(event.target.value)} />
                        </Stack>
                        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
                          <FormControlLabel control={<Switch checked={vadEnabled} onChange={(event) => setVadEnabled(event.target.checked)} />} label="启用 VAD" />
                          <FormControlLabel control={<Switch checked={itnEnabled} onChange={(event) => setItnEnabled(event.target.checked)} />} label="启用 ITN" />
                        </Stack>
                      </Stack>
                    </AccordionDetails>
                  </Accordion>

                  {submitError ? <Alert severity="error">{submitError}</Alert> : null}

                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.25}>
                    <Button
                      variant="contained"
                      fullWidth
                      onClick={handleSubmit}
                      disabled={submitting || !asrLoadable || (!selectedFile && !uploadedAssetName.trim())}
                    >
                      {submitting ? '创建中' : '立即开始'}
                    </Button>
                    <Button variant="outlined" fullWidth onClick={() => navigate('/tasks')}>
                      查看任务队列
                    </Button>
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          <Grid size={{ xs: 12, xl: 4 }}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="h6">最近任务</Typography>
                    <Button size="small" onClick={() => navigate('/jobs')}>
                      全部任务
                    </Button>
                  </Stack>
                  <Divider />
                  {recentJobs.length ? (
                    <Stack spacing={1}>
                      {recentJobs.slice(0, 5).map((job) => (
                        <Box
                          key={job.job_id}
                          sx={{
                            px: 1.35,
                            py: 1,
                            borderRadius: 3,
                            bgcolor: alpha('#ffffff', 0.72),
                            border: '1px solid',
                            borderColor: alpha('#1c2431', 0.06),
                            cursor: 'pointer',
                          }}
                          onClick={() => navigate(`/jobs/${job.job_id}`)}
                        >
                          <Stack spacing={0.4}>
                            <Stack direction="row" justifyContent="space-between" spacing={1}>
                              <Typography fontWeight={700} noWrap sx={{ fontSize: '0.92rem' }}>{job.asset_name ?? job.job_id}</Typography>
                              <StatusChip status={job.status} />
                            </Stack>
                            <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.82rem' }}>
                              {jobTypeLabels[job.job_type]} · {formatDateTime(job.updated_at)}
                            </Typography>
                          </Stack>
                        </Box>
                      ))}
                    </Stack>
                  ) : (
                    <Alert severity="info">暂无最近任务。</Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Stack>
    </PageSection>
  );
}
