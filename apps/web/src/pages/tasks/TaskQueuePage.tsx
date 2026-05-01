import CheckCircleOutlineRounded from '@mui/icons-material/CheckCircleOutlineRounded';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
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

import { cancelJob, deleteJob, fetchHealth, fetchJobs, retryJob } from '../../api/client';
import { formatDateTime, jobTypeLabels, type HealthResponse, type JobDetail } from '../../api/types';
import { PageSection } from '../../components/PageSection';
import { StatCard } from '../../components/StatCard';
import { StatusChip } from '../../components/StatusChip';

const POLL_INTERVAL_MS = 5000;

interface ExpandedJobs {
  [jobId: string]: boolean;
}

function isTranscriptResult(result: JobDetail['result']): result is NonNullable<JobDetail['result']> & { text: string; segments: Array<unknown>; language?: string | null } {
  return !!result && typeof result === 'object' && 'text' in result && 'segments' in result;
}

function JobCard({
  job,
  expanded,
  onToggle,
  onDelete,
  onCancel,
  onRetry,
  deleting,
  canceling,
  retrying,
  queueBlocked,
}: {
  job: JobDetail;
  expanded: boolean;
  onToggle: () => void;
  onDelete: (jobId: string) => void;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  deleting: boolean;
  canceling: boolean;
  retrying: boolean;
  queueBlocked: boolean;
}) {
  const navigate = useNavigate();

  const resultSummary = useMemo(() => {
    if (!isTranscriptResult(job.result)) return null;
    const text = job.result.text ?? '';
    return text.length > 120 ? text.slice(0, 120) + '...' : text;
  }, [job.result]);

  const segmentCount = isTranscriptResult(job.result) ? job.result.segments.length : 0;

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
            {job.status === 'queued' || job.status === 'running' ? (
              <Button
                size="small"
                color="warning"
                variant="text"
                onClick={(e) => {
                  e.stopPropagation();
                  onCancel(job.job_id);
                }}
                disabled={canceling}
              >
                {canceling ? '取消中' : '取消'}
              </Button>
            ) : null}
            {job.status === 'failed' || job.status === 'canceled' ? (
              <Button
                size="small"
                variant="outlined"
                startIcon={<RefreshRounded />}
                onClick={(e) => {
                  e.stopPropagation();
                  onRetry(job.job_id);
                }}
                disabled={retrying}
              >
                {retrying ? '重试中' : '重试'}
              </Button>
            ) : null}
            <Button
              size="small"
              color="error"
              variant="text"
              startIcon={<DeleteOutlineRounded />}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(job.job_id);
              }}
              disabled={deleting}
            >
              {deleting ? '删除中' : '删除'}
            </Button>
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
            {job.status === 'failed' && job.error_message ? (
              <Alert severity="error">
                <AlertTitle>任务失败</AlertTitle>
                {job.error_message}
              </Alert>
            ) : null}

            {job.status === 'canceled' ? (
              <Alert severity="info">
                <AlertTitle>任务已取消</AlertTitle>
                {job.status_explanation ?? '任务已被标记为取消，后续结果不会覆盖该状态。'}
              </Alert>
            ) : null}

            {queueBlocked && (job.status === 'queued' || job.status === 'running') ? (
              <Alert severity="warning">
                Worker 未连接，这个任务不会继续推进。建议删除后重建。
              </Alert>
            ) : null}

            {/* Result */}
            {job.status === 'succeeded' && job.result ? (
              <Stack spacing={1}>
                <Typography variant="subtitle2" color="text.secondary">
                  {isTranscriptResult(job.result) ? '转写结果' : '任务结果'}
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
                    {isTranscriptResult(job.result) && job.result.language ? (
                      <Typography variant="body2" color="text.secondary">
                        语言: {job.result.language}
                      </Typography>
                    ) : null}
                    {isTranscriptResult(job.result) ? (
                      <Typography variant="body2" color="text.secondary">
                        分段数: {segmentCount}
                      </Typography>
                    ) : null}
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
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        当前结果类型需要进入详情页查看完整内容。
                      </Typography>
                    )}
                  </Stack>
                </Box>
                <Button
                  size="small"
                  variant="text"
                  component="a"
                  href={`/jobs/${job.job_id}`}
                  sx={{ alignSelf: 'flex-start', px: 0 }}
                >
                  查看详情
                </Button>
              </Stack>
            ) : job.status !== 'failed' && job.status !== 'canceled' ? (
              <Alert severity="info">任务尚在处理中，结果暂不可用。</Alert>
            ) : null}
          </Stack>
        </Collapse>
      </CardContent>
    </Card>
  );
}

function RuntimeModeAlert({ health }: { health: HealthResponse | null }) {
  if (!health) {
    return null;
  }

  if (health.async_available) {
    return (
      <Alert severity="success">
        <AlertTitle>异步队列已就绪</AlertTitle>
        Broker 与 Worker 均在线，新任务会进入 Celery 队列异步执行。
      </Alert>
    );
  }

  if (!health.broker_available) {
    return (
      <Alert severity="warning">
        <AlertTitle>异步队列不可用</AlertTitle>
        Redis Broker 不可用，新转写任务默认会快速失败，不会在 API 请求线程里同步跑模型。
        仅本地小音频调试时可启用同步回退。错误：{health.broker_error ?? 'broker_unavailable'}
      </Alert>
    );
  }

  if (!health.worker_available) {
    return (
      <Alert severity="warning">
        <AlertTitle>Worker 未连接</AlertTitle>
        Redis Broker 可用，但没有检测到在线 Worker。新转写任务默认会快速失败，已排队任务不会继续推进。错误：
        {health.worker_error ?? 'worker_offline'}
      </Alert>
    );
  }

  return (
    <Alert severity="info">
      <AlertTitle>同步执行模式</AlertTitle>
      当前执行模式为 {health.execution_mode ?? 'sync'}，新任务可能由 API 进程直接处理。
    </Alert>
  );
}

export function TaskQueuePage() {
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ExpandedJobs>({});
  const [refreshing, setRefreshing] = useState(false);
  const [deletingJobIds, setDeletingJobIds] = useState<Set<string>>(new Set());
  const [cancelingJobIds, setCancelingJobIds] = useState<Set<string>>(new Set());
  const [retryingJobIds, setRetryingJobIds] = useState<Set<string>>(new Set());
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const loadJobs = useCallback(async (isManual = false) => {
    if (isManual) {
      setLoading(true);
    }
    try {
      const [data, runtime] = await Promise.all([fetchJobs(), fetchHealth()]);
      setJobs(data.items);
      setHealth(runtime);
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
    const counts = { queued: 0, running: 0, succeeded: 0, failed: 0, canceled: 0 };
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

  const handleDelete = useCallback(async (jobId: string) => {
    setDeletingJobIds((prev) => new Set(prev).add(jobId));
    try {
      await deleteJob(jobId);
      setJobs((current) => current.filter((item) => item.job_id !== jobId));
      setExpanded((current) => {
        const next = { ...current };
        delete next[jobId];
        return next;
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '删除任务失败');
    } finally {
      setDeletingJobIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  }, []);

  const handleCancel = useCallback(async (jobId: string) => {
    setCancelingJobIds((prev) => new Set(prev).add(jobId));
    try {
      const updated = await cancelJob(jobId);
      setJobs((current) => current.map((item) => (item.job_id === jobId ? updated : item)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '取消任务失败');
    } finally {
      setCancelingJobIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  }, []);

  const handleRetry = useCallback(async (jobId: string) => {
    setRetryingJobIds((prev) => new Set(prev).add(jobId));
    try {
      const created = await retryJob(jobId);
      setJobs((current) => [created, ...current.filter((item) => item.job_id !== created.job_id)]);
      setExpanded((current) => ({ ...current, [created.job_id]: true }));
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '重试任务失败');
    } finally {
      setRetryingJobIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  }, []);

  const queueBlocked = !!health?.broker_available && !health?.worker_available;
  const executionLabel = health?.async_available ? '异步模式' : '队列未就绪';

  return (
    <PageSection
      title="任务队列"
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
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip size="small" color="warning" label={`处理中 ${stats.queued + stats.running}`} />
        <Chip size="small" color="success" label={`已完成 ${stats.succeeded}`} />
        <Chip size="small" color="default" label={`已取消 ${stats.canceled}`} />
        <Chip
          size="small"
          color={health?.async_available ? 'success' : 'warning'}
          label={executionLabel}
          variant={health ? 'filled' : 'outlined'}
        />
        <Chip size="small" label={`自动轮询 ${POLL_INTERVAL_MS / 1000}s`} variant="outlined" />
      </Stack>

      <RuntimeModeAlert health={health} />

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
              onDelete={handleDelete}
              onCancel={handleCancel}
              onRetry={handleRetry}
              deleting={deletingJobIds.has(job.job_id)}
              canceling={cancelingJobIds.has(job.job_id)}
              retrying={retryingJobIds.has(job.job_id)}
              queueBlocked={queueBlocked}
            />
          ))
        ) : (
          <Alert severity="info">暂无任务，请到转写工作台发起任务。</Alert>
        )}
      </Stack>
    </PageSection>
  );
}
