import CheckCircleOutlineRounded from '@mui/icons-material/CheckCircleOutlineRounded';
import ErrorOutlineRounded from '@mui/icons-material/ErrorOutlineRounded';
import HourglassEmptyRounded from '@mui/icons-material/HourglassEmptyRounded';
import RefreshRounded from '@mui/icons-material/RefreshRounded';
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  Divider,
  Grid,
  IconButton,
  Stack,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchJobs } from '../../api/client';
import { formatDateTime, jobTypeLabels, type JobDetail } from '../../api/types';
import { BalancedPretextText, MeasuredPretextBlock } from '../../components/PretextText';
import { PageSection } from '../../components/PageSection';
import { StatCard } from '../../components/StatCard';
import { StatusChip } from '../../components/StatusChip';

const POLL_INTERVAL_MS = 5000;

interface ExpandedJobs {
  [jobId: string]: boolean;
}

function JobCard({ job, expanded, onToggle }: { job: JobDetail; expanded: boolean; onToggle: () => void }) {
  const navigate = useNavigate();

  const resultSummary = useMemo(() => {
    if (!job.result) return null;
    const text = job.result.text ?? '';
    return text.length > 120 ? text.slice(0, 120) + '...' : text;
  }, [job.result]);

  const segmentCount = job.result?.segments.length ?? 0;

  return (
    <Card
      sx={{
        border: '1px solid',
        borderColor: alpha('#1c2431', 0.07),
        transition: 'box-shadow 0.2s',
        '&:hover': {
          boxShadow: '0 4px 16px rgba(15,23,42,0.08)',
        },
      }}
    >
      <CardContent sx={{ pb: expanded ? 2 : 1.5 }}>
        {/* Header row */}
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          justifyContent="space-between"
          alignItems={{ xs: 'flex-start', md: 'center' }}
          spacing={1.5}
        >
          <Stack spacing={0.75} flex={1} minWidth={0}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="h6" sx={{ wordBreak: 'break-all' }}>
                {job.asset_name ?? job.job_id}
              </Typography>
              <StatusChip status={job.status} />
              <Chip size="small" variant="outlined" label={jobTypeLabels[job.job_type]} />
            </Stack>
            <Typography variant="body2" color="text.secondary">
              任务编号 {job.job_id}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              创建 {formatDateTime(job.created_at)} · 更新 {formatDateTime(job.updated_at)}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            {job.status === 'succeeded' && job.asset_name ? (
              <Button
                size="small"
                variant="outlined"
                onClick={(e) => {
                  e.stopPropagation();
                  const params = new URLSearchParams({
                    asset: job.asset_name ?? '',
                    mode: job.job_type === 'multi_speaker_transcription' ? 'multi' : 'single',
                  });
                  navigate(`/?${params.toString()}`);
                }}
              >
                重新发起
              </Button>
            ) : null}
            <IconButton size="small" onClick={onToggle} title={expanded ? '收起详情' : '展开详情'}>
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                style={{
                  transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
                  transition: 'transform 0.2s',
                }}
              >
                <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </IconButton>
          </Stack>
        </Stack>

        {/* Expandable detail */}
        <Collapse in={expanded}>
          <Divider sx={{ my: 2 }} />
          <Stack spacing={1.8}>
            {/* Error message */}
            {job.error_message ? (
              <Alert severity="error">
                <AlertTitle>任务失败</AlertTitle>
                {job.error_message}
              </Alert>
            ) : null}

            {/* Result */}
            {job.status === 'succeeded' && job.result ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2" color="text.secondary">
                  转写结果
                </Typography>
                <Box
                  sx={{
                    p: 1.6,
                    borderRadius: 4,
                    bgcolor: alpha('#ffffff', 0.66),
                    border: '1px solid',
                    borderColor: alpha('#1c2431', 0.06),
                  }}
                >
                  <Stack spacing={0.8}>
                    {job.result.language ? (
                      <Typography variant="body2" color="text.secondary">
                        语言: {job.result.language}
                      </Typography>
                    ) : null}
                    <Typography variant="body2" color="text.secondary">
                      分段数: {segmentCount}
                    </Typography>
                    {resultSummary ? (
                      <Typography
                        variant="body2"
                        sx={{
                          mt: 0.5,
                          textWrap: 'pretty',
                          wordBreak: 'break-word',
                          color: 'text.primary',
                          fontFamily: '"PingFang SC", "Microsoft YaHei", sans-serif',
                        }}
                      >
                        {resultSummary}
                      </Typography>
                    ) : null}
                  </Stack>
                </Box>
                <Button
                  size="small"
                  variant="text"
                  component="a"
                  href={`/jobs/${job.job_id}`}
                  sx={{ alignSelf: 'flex-start', px: 0 }}
                >
                  在详情页查看完整结果 →
                </Button>
              </Stack>
            ) : job.status !== 'failed' ? (
              <Alert severity="info">任务尚在处理中，结果暂不可用。</Alert>
            ) : null}
          </Stack>
        </Collapse>
      </CardContent>
    </Card>
  );
}

export function TaskQueuePage() {
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ExpandedJobs>({});
  const [refreshing, setRefreshing] = useState(false);

  const loadJobs = useCallback(async (isManual = false) => {
    if (isManual) {
      setLoading(true);
    }
    try {
      const data = await fetchJobs();
      setJobs(data.items);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载任务失败');
    } finally {
      if (isManual) {
        setLoading(false);
      }
    }
  }, []);

  // Auto-poll
  useEffect(() => {
    loadJobs();
    const timer = setInterval(() => loadJobs(false), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [loadJobs]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadJobs(true);
    setRefreshing(false);
  }, [loadJobs]);

  const stats = useMemo(() => {
    const counts = { queued: 0, running: 0, succeeded: 0, failed: 0 };
    jobs.forEach((job) => {
      if (job.status in counts) {
        counts[job.status as keyof typeof counts]++;
      }
    });
    return counts;
  }, [jobs]);

  const toggleExpanded = useCallback((jobId: string) => {
    setExpanded((prev) => ({ ...prev, [jobId]: !prev[jobId] }));
  }, []);

  return (
    <PageSection
      title="任务队列与异步执行监控"
      eyebrow="实时状态"
      eyebrowColor="primary"
      description="这里专门承接后台异步任务。即使你刷新页面或切换页面，任务也会继续在后端运行，并在这里持续可见。"
      loading={loading}
      error={error}
      actions={
        <Button
          variant="outlined"
          startIcon={<RefreshRounded />}
          onClick={handleRefresh}
          disabled={refreshing}
          size="small"
        >
          {refreshing ? '刷新中...' : '刷新'}
        </Button>
      }
    >
      <Card>
        <CardContent>
          <Stack spacing={2}>
            <BalancedPretextText
              text="任务不会因为刷新界面而消失，前端只是切换视图，后端异步任务仍会继续运行"
              font='500 38px "Iowan Old Style"'
              lineHeight={46}
              targetLines={2}
              minWidth={360}
              maxWidth={860}
              typographyProps={{
                variant: 'h4',
                sx: { maxWidth: 860 },
              }}
            />
            <MeasuredPretextBlock
              text="任务队列页会持续轮询任务状态。正在排队、处理中、已完成和失败的任务都会在这里保留，不再要求你靠记忆回到某个页面找刚刚发起的任务。"
              font='400 16px "PingFang SC"'
              lineHeight={30}
              typographyProps={{
                color: 'text.secondary',
                sx: { maxWidth: 860, lineHeight: 1.85 },
              }}
            />
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip size="small" color="warning" label={`处理中 ${stats.queued + stats.running}`} />
              <Chip size="small" color="success" label={`已完成 ${stats.succeeded}`} />
              <Chip size="small" label={`自动轮询 ${POLL_INTERVAL_MS / 1000}s`} variant="outlined" />
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      {/* Stats row */}
      <Grid container spacing={2}>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatCard
            label="处理中"
            value={stats.queued + stats.running}
            icon={<HourglassEmptyRounded fontSize="small" />}
            color="warning"
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatCard
            label="已完成"
            value={stats.succeeded}
            icon={<CheckCircleOutlineRounded fontSize="small" />}
            color="success"
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatCard
            label="失败"
            value={stats.failed}
            icon={<ErrorOutlineRounded fontSize="small" />}
            color="error"
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatCard
            label="全部任务"
            value={jobs.length}
            color="primary"
          />
        </Grid>
      </Grid>

      {/* Job list */}
      <Stack spacing={2}>
        {jobs.length ? (
          jobs.map((job) => (
            <JobCard
              key={job.job_id}
              job={job}
              expanded={!!expanded[job.job_id]}
              onToggle={() => toggleExpanded(job.job_id)}
            />
          ))
        ) : (
          <Alert severity="info">暂无任务，请到转写工作台发起任务。</Alert>
        )}
      </Stack>
    </PageSection>
  );
}
