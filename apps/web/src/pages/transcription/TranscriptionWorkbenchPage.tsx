import AddRounded from '@mui/icons-material/AddRounded';
import CheckCircleOutlineRounded from '@mui/icons-material/CheckCircleOutlineRounded';
import ErrorOutlineRounded from '@mui/icons-material/ErrorOutlineRounded';
import GraphicEqRounded from '@mui/icons-material/GraphicEqRounded';
import HourglassEmptyRounded from '@mui/icons-material/HourglassEmptyRounded';
import QueueMusicRounded from '@mui/icons-material/QueueMusicRounded';
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
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { createTranscription, fetchJobs, fetchModels, uploadAudio } from '../../api/client';
import {
  formatDateTime,
  jobStatusLabels,
  jobTypeLabels,
  modelTaskLabels,
  providerLabels,
  type ModelInfo,
} from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { BrandLogo } from '../../components/BrandLogo';
import { AudioUploadField } from '../../components/AudioUploadField';
import { PageSection } from '../../components/PageSection';
import { StatusChip } from '../../components/StatusChip';

const quickTemplates = [
  '罗大佑 - 光阴的故事(片头曲).wav',
  '丹山路.m4a',
  '5分钟.wav',
];

function JobStatCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: 'primary' | 'success' | 'error' | 'warning';
}) {
  return (
    <Card>
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Box
            sx={{
              width: 40,
              height: 40,
              borderRadius: 3,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              bgcolor: `${color}.main`,
              color: '#fff',
              opacity: 0.9,
            }}
          >
            {icon}
          </Box>
          <Box>
            <Typography color="text.secondary" variant="body2">
              {label}
            </Typography>
            <Typography variant="h5">{value}</Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}

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
    () =>
      (modelsState.data?.items ?? []).filter(
        (item) => item.task === 'diarization' && item.availability === 'available',
      ),
    [modelsState.data],
  );

  useEffect(() => {
    if (!diarizationModel && diarizationOptions.length > 0) {
      setDiarizationModel(diarizationOptions[0].key);
    }
  }, [diarizationModel, diarizationOptions]);

  const jobSummary = useMemo(() => {
    const items = jobsState.data?.items ?? [];
    return {
      total: items.length,
      running: items.filter((j) => j.status === 'running' || j.status === 'queued').length,
      done: items.filter((j) => j.status === 'succeeded').length,
      failed: items.filter((j) => j.status === 'failed').length,
    };
  }, [jobsState.data]);

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
        description="上传真实音频文件，默认按多人转写流程处理，任务状态随时可查。"
        loading={modelsState.loading || jobsState.loading}
        error={modelsState.error ?? jobsState.error}
        actions={
          <Button
            variant="contained"
            startIcon={<AddRounded />}
            onClick={handleSubmit}
            disabled={submitting || (!selectedFile && !uploadedAssetName.trim())}
          >
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
                      <BrandLogo size={52} withWordmark={false} light />
                      <Typography variant="h3">默认直达多人转写与说话人分离</Typography>
                      <Typography sx={{ color: 'rgba(255,255,255,0.82)', fontSize: 16, lineHeight: 1.75 }}>
                        面向会议纪要、客服质检和安全核验场景，上传真实音频后优先输出带说话人标签的转写结果。
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
                            helperText="默认已启用说话人分离；如需仅文本转写，可切换为标准转写。"
                          >
                            <MenuItem value="">标准转写（可选）</MenuItem>
                            {diarizationOptions.map((item) => (
                              <MenuItem key={item.key} value={item.key}>
                                {item.display_name}
                              </MenuItem>
                            ))}
                          </TextField>
                          {submitError ? <Alert severity="error">{submitError}</Alert> : null}
                          <Stack direction="row" spacing={1.5}>
                            <Button
                              variant="contained"
                              fullWidth
                              onClick={handleSubmit}
                              disabled={submitting || (!selectedFile && !uploadedAssetName.trim())}
                            >
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
                <Grid size={{ xs: 6, sm: 4, xl: 12 }}>
                  <JobStatCard
                    label="总任务数"
                    value={String(jobSummary.total)}
                    icon={<QueueMusicRounded fontSize="small" />}
                    color="primary"
                  />
                </Grid>
                <Grid size={{ xs: 6, sm: 4, xl: 12 }}>
                  <JobStatCard
                    label="处理中"
                    value={String(jobSummary.running)}
                    icon={<HourglassEmptyRounded fontSize="small" />}
                    color="warning"
                  />
                </Grid>
                <Grid size={{ xs: 6, sm: 4, xl: 12 }}>
                  <JobStatCard
                    label="已完成"
                    value={String(jobSummary.done)}
                    icon={<CheckCircleOutlineRounded fontSize="small" />}
                    color="success"
                  />
                </Grid>
                {jobSummary.failed > 0 ? (
                  <Grid size={{ xs: 6, sm: 4, xl: 12 }}>
                    <JobStatCard
                      label="失败"
                      value={String(jobSummary.failed)}
                      icon={<ErrorOutlineRounded fontSize="small" />}
                      color="error"
                    />
                  </Grid>
                ) : null}
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
                            <Stack
                              direction={{ xs: 'column', md: 'row' }}
                              justifyContent="space-between"
                              spacing={2}
                            >
                              <Stack spacing={0.75}>
                                <Typography variant="subtitle1" fontWeight={700}>
                                  {job.asset_name ?? job.job_id}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                  {jobTypeLabels[job.job_type]} · 更新时间{' '}
                                  {formatDateTime(job.updated_at)}
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
                  <Typography variant="h6">声纹库</Typography>
                  <Typography color="text.secondary">
                    声纹验证与识别属于按需能力，无需每次操作。已有档案时可直接上传待比对音频进行核验。
                  </Typography>
                  <Button variant="outlined" onClick={() => navigate('/voiceprints')}>
                    前往声纹库
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </PageSection>
    </Stack>
  );
}
