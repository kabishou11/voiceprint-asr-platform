import GraphicEqRounded from '@mui/icons-material/GraphicEqRounded';
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
import { alpha } from '@mui/material/styles';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { createDiarization, fetchJobs, fetchModels, uploadAudio } from '../../api/client';
import { formatDateTime, jobTypeLabels } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { AudioUploadField } from '../../components/AudioUploadField';
import { PageSection } from '../../components/PageSection';
import { StatusChip } from '../../components/StatusChip';

export function DiarizationPage() {
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadedAssetName, setUploadedAssetName] = useState('');
  const [numSpeakersText, setNumSpeakersText] = useState('');
  const [minSpeakersText, setMinSpeakersText] = useState('');
  const [maxSpeakersText, setMaxSpeakersText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const modelsState = useAsyncData(() => fetchModels(), []);
  const jobsState = useAsyncData(
    () => fetchJobs({ page: 1, page_size: 10, job_type: 'diarization' }),
    [],
    { enabled: true, intervalMs: 5000, pauseWhenHidden: true },
  );

  const diarizationModels = useMemo(
    () => (modelsState.data?.items ?? []).filter((m) => m.task === 'diarization' && m.status !== 'load_failed'),
    [modelsState.data],
  );
  const [diarizationModel, setDiarizationModel] = useState('3dspeaker-diarization');

  const recentJobs = jobsState.data?.items ?? [];

  const parseInteger = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return null;
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
      const response = await createDiarization({
        asset_name: assetName,
        diarization_model: diarizationModel,
        num_speakers: parseInteger(numSpeakersText),
        min_speakers: parseInteger(minSpeakersText),
        max_speakers: parseInteger(maxSpeakersText),
      });
      navigate(`/jobs/${response.job_id}`);
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : '创建任务失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PageSection
      compact
      title="说话人分离"
      description="独立执行说话人分离，输出 Speaker 时间线，不依赖文本转写。"
      loading={modelsState.loading}
      error={modelsState.error}
    >
      <Grid container spacing={2.2}>
        <Grid size={{ xs: 12, xl: 8 }}>
          <Card>
            <CardContent>
              <Stack spacing={2}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <GraphicEqRounded color="primary" />
                  <Typography variant="h6">新建分离任务</Typography>
                </Stack>

                <AudioUploadField
                  label="音频"
                  fileName={selectedFile?.name ?? (uploadedAssetName || null)}
                  helperText="支持 wav、m4a、mp3、flac。"
                  onChange={(file) => {
                    setSelectedFile(file);
                    if (file) setUploadedAssetName('');
                  }}
                />

                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                  <TextField
                    select
                    fullWidth
                    label="分离模型"
                    value={diarizationModel}
                    onChange={(e) => setDiarizationModel(e.target.value)}
                  >
                    {diarizationModels.length ? (
                      diarizationModels.map((m) => (
                        <MenuItem key={m.key} value={m.key}>{m.display_name}</MenuItem>
                      ))
                    ) : (
                      <MenuItem value="3dspeaker-diarization">3D-Speaker Diarization</MenuItem>
                    )}
                  </TextField>
                </Stack>

                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                  <TextField label="已知说话人数" value={numSpeakersText} onChange={(e) => setNumSpeakersText(e.target.value)} fullWidth />
                  <TextField label="最少说话人数" value={minSpeakersText} onChange={(e) => setMinSpeakersText(e.target.value)} fullWidth />
                  <TextField label="最多说话人数" value={maxSpeakersText} onChange={(e) => setMaxSpeakersText(e.target.value)} fullWidth />
                </Stack>

                {submitError ? <Alert severity="error">{submitError}</Alert> : null}

                <Button
                  variant="contained"
                  onClick={handleSubmit}
                  disabled={submitting || (!selectedFile && !uploadedAssetName.trim())}
                >
                  {submitting ? '创建中' : '开始分离'}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, xl: 4 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Stack spacing={1.5}>
                <Typography variant="h6">最近分离任务</Typography>
                {recentJobs.length ? (
                  <Stack spacing={1}>
                    {recentJobs.map((job) => (
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
                            <Typography fontWeight={700} noWrap sx={{ fontSize: '0.9rem' }}>
                              {job.asset_name ?? job.job_id}
                            </Typography>
                            <StatusChip status={job.status} />
                          </Stack>
                          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.82rem' }}>
                            {formatDateTime(job.updated_at)}
                          </Typography>
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                ) : (
                  <Alert severity="info">暂无分离任务。</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </PageSection>
  );
}
