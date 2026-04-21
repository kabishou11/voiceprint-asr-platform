import AddRounded from '@mui/icons-material/AddRounded';
import GraphicEqRounded from '@mui/icons-material/GraphicEqRounded';
import QueueMusicRounded from '@mui/icons-material/QueueMusicRounded';
import TimelineRounded from '@mui/icons-material/TimelineRounded';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { createTranscription, fetchJobs, fetchModels, uploadAudio } from '../../api/client';
import {
  formatDateTime,
  jobStatusLabels,
  jobTypeLabels,
  modelAvailabilityLabels,
  modelTaskLabels,
  providerLabels,
  type ModelInfo,
} from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { AudioUploadField } from '../../components/AudioUploadField';
import { PageSection } from '../../components/PageSection';
import { StatusChip } from '../../components/StatusChip';

const quickTemplates = [
  '罗大佑 - 光阴的故事(片头曲).wav',
  '丹山路.m4a',
  '5分钟.wav',
];

export function TranscriptionWorkbenchPage() {
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadedAssetName, setUploadedAssetName] = useState('');
  const [diarizationModel, setDiarizationModel] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const modelsState = useAsyncData(() => fetchModels(), []);
  const jobsState = useAsyncData(() => fetchJobs(), []);

  const diarizationOptions = useMemo(
    () => (modelsState.data?.items ?? []).filter((item) => item.task === 'diarization'),
    [modelsState.data],
  );

  const modelSummary = useMemo(() => {
    const items = modelsState.data?.items ?? [];
    return {
      ready: items.filter((item) => item.availability === 'available').length,
      optional: items.filter((item) => item.availability === 'optional').length,
      total: items.length,
    };
  }, [modelsState.data]);

  const recentJobs = useMemo(() => (jobsState.data?.items ?? []).slice(0, 3), [jobsState.data]);

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
      const response = await createTranscription(assetName, diarizationModel || undefined);
      navigate(`/jobs/${response.job.job_id}`);
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : '创建任务失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Stack spacing={3}>
      <PageSection
        title="智能语音工作台"
        description="上传真实音频文件，创建转写任务、跟踪处理进度，并集中查看模型与结果状态。"
        loading={modelsState.loading || jobsState.loading}
        error={modelsState.error ?? jobsState.error}
        actions={
          <Button variant="contained" startIcon={<AddRounded />} onClick={handleSubmit} disabled={submitting || (!selectedFile && !uploadedAssetName.trim())}>
            {submitting ? '正在创建' : '新建任务'}
          </Button>
        }
      >
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, xl: 8 }}>
            <Card
              sx={{
                minHeight: 280,
                background: 'linear-gradient(135deg, #0f172a 0%, #1d4ed8 48%, #0f766e 100%)',
                color: '#fff',
              }}
            >
              <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                <Grid container spacing={3} alignItems="stretch">
                  <Grid size={{ xs: 12, md: 7 }}>
                    <Stack spacing={2.5}>
                      <Chip label="语音任务中心" sx={{ alignSelf: 'flex-start', bgcolor: 'rgba(255,255,255,0.16)', color: '#fff' }} />
                      <Typography variant="h3">一站式完成转写、分离与声纹识别</Typography>
                      <Typography sx={{ color: 'rgba(255,255,255,0.82)', fontSize: 16, lineHeight: 1.75 }}>
                        面向会议纪要、客服质检和安全核验场景，上传真实音频并快速发起任务。
                      </Typography>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                        {quickTemplates.map((item) => (
                          <Chip
                            key={item}
                            label={item}
                            onClick={() => {
                              setUploadedAssetName(item);
                              setSelectedFile(null);
                            }}
                            sx={{ bgcolor: 'rgba(255,255,255,0.12)', color: '#fff' }}
                          />
                        ))}
                      </Stack>
                    </Stack>
                  </Grid>
                  <Grid size={{ xs: 12, md: 5 }}>
                    <Card sx={{ bgcolor: 'rgba(255,255,255,0.94)', color: 'text.primary' }}>
                      <CardContent>
                        <Stack spacing={2.25}>
                          <Typography variant="h6">快速发起任务</Typography>
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
                          <TextField
                            select
                            label="说话人模式"
                            value={diarizationModel}
                            onChange={(event) => setDiarizationModel(event.target.value)}
                          >
                            <MenuItem value="">标准转写</MenuItem>
                            {diarizationOptions.map((item) => (
                              <MenuItem key={item.key} value={item.key}>
                                {item.display_name}
                              </MenuItem>
                            ))}
                          </TextField>
                          {submitError ? <Alert severity="error">{submitError}</Alert> : null}
                          <Stack direction="row" spacing={1.5}>
                            <Button variant="contained" fullWidth onClick={handleSubmit} disabled={submitting || (!selectedFile && !uploadedAssetName.trim())}>
                              {submitting ? '创建中' : '立即开始'}
                            </Button>
                            <Button variant="outlined" fullWidth onClick={() => navigate('/jobs')}>
                              查看全部任务
                            </Button>
                          </Stack>
                        </Stack>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>
          <Grid size={{ xs: 12, xl: 4 }}>
            <Stack spacing={3}>
              <Grid container spacing={2}>
                {[
                  { label: '总任务数', value: String(jobsState.data?.items?.length ?? 0), icon: <QueueMusicRounded color="primary" /> },
                  { label: '就绪模型', value: `${modelSummary.ready}/${modelSummary.total || 0}`, icon: <GraphicEqRounded color="primary" /> },
                  { label: '按需模型', value: String(modelSummary.optional), icon: <TimelineRounded color="primary" /> },
                ].map((item) => (
                  <Grid key={item.label} size={{ xs: 12, sm: 4, xl: 12 }}>
                    <Card>
                      <CardContent>
                        <Stack direction="row" spacing={1.5} alignItems="center">
                          {item.icon}
                          <Box>
                            <Typography color="text.secondary" variant="body2">
                              {item.label}
                            </Typography>
                            <Typography variant="h5">{item.value}</Typography>
                          </Box>
                        </Stack>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Stack>
          </Grid>
        </Grid>

        <Grid container spacing={3}>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Card>
              <CardContent>
                <Stack spacing={2.5}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="h6">最近任务</Typography>
                    <Button size="small" onClick={() => navigate('/jobs')}>
                      查看全部
                    </Button>
                  </Stack>
                  <Stack spacing={2}>
                    {recentJobs.length ? (
                      recentJobs.map((job) => (
                        <Card key={job.job_id} variant="outlined" sx={{ borderRadius: 4 }}>
                          <CardContent>
                            <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
                              <Stack spacing={0.75}>
                                <Typography variant="subtitle1" fontWeight={700}>
                                  {job.asset_name ?? job.job_id}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                  {jobTypeLabels[job.job_type]} · 更新时间 {formatDateTime(job.updated_at)}
                                </Typography>
                              </Stack>
                              <Stack direction="row" spacing={1} alignItems="center">
                                <StatusChip status={job.status} />
                                <Button size="small" onClick={() => navigate(`/jobs/${job.job_id}`)}>
                                  查看
                                </Button>
                              </Stack>
                            </Stack>
                          </CardContent>
                        </Card>
                      ))
                    ) : (
                      <Alert severity="info">暂无任务记录。</Alert>
                    )}
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Card>
              <CardContent>
                <Stack spacing={2.5}>
                  <Typography variant="h6">模型状态</Typography>
                  {(modelsState.data?.items ?? []).map((item: ModelInfo) => (
                    <Stack key={item.key} direction="row" justifyContent="space-between" alignItems="center">
                      <Stack spacing={0.5}>
                        <Typography fontWeight={700}>{item.display_name}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {providerLabels[item.provider] ?? item.provider} · {modelTaskLabels[item.task]}
                        </Typography>
                      </Stack>
                      <Stack direction="row" spacing={1}>
                        {item.experimental ? <Chip size="small" color="warning" label="实验性" /> : null}
                        <Chip size="small" label={modelAvailabilityLabels[item.availability]} color={item.availability === 'available' ? 'success' : 'default'} />
                      </Stack>
                    </Stack>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </PageSection>
    </Stack>
  );
}
