import CheckCircleOutlineRounded from '@mui/icons-material/CheckCircleOutlineRounded';
import ErrorOutlineRounded from '@mui/icons-material/ErrorOutlineRounded';
import HourglassEmptyRounded from '@mui/icons-material/HourglassEmptyRounded';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Grid,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { useMemo, useState } from 'react';

import { fetchJobs } from '../../api/client';
import { formatDateTime, jobTypeLabels } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';
import { StatusChip } from '../../components/StatusChip';

function StatChip({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: 'primary' | 'success' | 'error' | 'warning';
}) {
  return (
    <Chip
      label={`${label} ${value}`}
      color={color}
      sx={{ fontWeight: 700, fontSize: 13 }}
    />
  );
}

export function JobListPage() {
  const { data, loading, error, reload } = useAsyncData(() => fetchJobs(), []);
  const [statusFilter, setStatusFilter] = useState('all');

  const { filteredJobs, statCounts } = useMemo(() => {
    const items = data?.items ?? [];
    const counts = { all: items.length, queued: 0, running: 0, succeeded: 0, failed: 0 };
    items.forEach((job) => {
      if (job.status in counts) {
        counts[job.status as keyof typeof counts]++;
      }
    });
    const filtered =
      statusFilter === 'all' ? items : items.filter((job) => job.status === statusFilter);
    return { filteredJobs: filtered, statCounts: counts };
  }, [data?.items, statusFilter]);

  return (
    <PageSection
      title="任务中心"
      eyebrow="处理记录"
      eyebrowColor="primary"
      description="集中查看当前任务、处理状态和结果入口。"
      loading={loading}
      error={error}
      actions={
        <Stack direction="row" spacing={1.5}>
          <TextField
            select
            size="small"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="all">全部状态</MenuItem>
            <MenuItem value="queued">排队中</MenuItem>
            <MenuItem value="running">处理中</MenuItem>
            <MenuItem value="succeeded">已完成</MenuItem>
            <MenuItem value="failed">失败</MenuItem>
          </TextField>
          <Button variant="outlined" onClick={reload}>
            刷新
          </Button>
        </Stack>
      }
    >
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
        <StatChip label="全部" value={statCounts.all} color="primary" />
        <StatChip label="处理中" value={statCounts.queued + statCounts.running} color="warning" />
        <StatChip label="已完成" value={statCounts.succeeded} color="success" />
        {statCounts.failed > 0 ? (
          <StatChip label="失败" value={statCounts.failed} color="error" />
        ) : null}
      </Stack>

      <Stack spacing={2}>
        {filteredJobs.length ? (
          filteredJobs.map((job) => (
            <Card key={job.job_id}>
              <CardActionArea component={RouterLink} to={`/jobs/${job.job_id}`}>
                <CardContent>
                  <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
                    <Stack spacing={1}>
                      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                        <Typography variant="h6">{job.asset_name ?? job.job_id}</Typography>
                        <Chip size="small" variant="outlined" label={jobTypeLabels[job.job_type]} />
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        任务编号 {job.job_id}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        更新时间 {formatDateTime(job.updated_at)}
                      </Typography>
                    </Stack>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <StatusChip status={job.status} />
                      <Button size="small">查看详情</Button>
                    </Stack>
                  </Stack>
                </CardContent>
              </CardActionArea>
            </Card>
          ))
        ) : (
          <Alert severity="info">当前筛选条件下暂无任务。</Alert>
        )}
      </Stack>
    </PageSection>
  );
}
