import CheckCircleOutlineRounded from '@mui/icons-material/CheckCircleOutlineRounded';
import ErrorOutlineRounded from '@mui/icons-material/ErrorOutlineRounded';
import HourglassEmptyRounded from '@mui/icons-material/HourglassEmptyRounded';
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

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
  return <Chip label={`${label} ${value}`} color={color} sx={{ fontWeight: 700, fontSize: 13 }} />;
}

export function JobListPage() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useAsyncData(() => fetchJobs(), []);
  const [statusFilter, setStatusFilter] = useState('all');
  const [jobTypeFilter, setJobTypeFilter] = useState('all');
  const [keyword, setKeyword] = useState('');

  const { filteredJobs, statCounts } = useMemo(() => {
    const items = data?.items ?? [];
    const counts = { all: items.length, queued: 0, running: 0, succeeded: 0, failed: 0 };
    items.forEach((job) => {
      if (job.status in counts) {
        counts[job.status as keyof typeof counts]++;
      }
    });
    const normalizedKeyword = keyword.trim().toLowerCase();
    const filtered = items.filter((job) => {
      if (statusFilter !== 'all' && job.status !== statusFilter) {
        return false;
      }
      if (jobTypeFilter !== 'all' && job.job_type !== jobTypeFilter) {
        return false;
      }
      if (!normalizedKeyword) {
        return true;
      }
      return (
        (job.asset_name ?? '').toLowerCase().includes(normalizedKeyword) ||
        job.job_id.toLowerCase().includes(normalizedKeyword)
      );
    });
    return { filteredJobs: filtered, statCounts: counts };
  }, [data?.items, jobTypeFilter, keyword, statusFilter]);

  return (
    <PageSection
      title="任务中心"
      loading={loading}
      error={error}
      actions={
        <Button variant="outlined" onClick={reload}>
          刷新
        </Button>
      }
    >
      <Stack direction="row" spacing={1.25} flexWrap="wrap" useFlexGap>
        <StatChip label="全部" value={statCounts.all} color="primary" />
        <StatChip label="处理中" value={statCounts.queued + statCounts.running} color="warning" />
        <StatChip label="已完成" value={statCounts.succeeded} color="success" />
        {statCounts.failed > 0 ? <StatChip label="失败" value={statCounts.failed} color="error" /> : null}
      </Stack>

      <Card>
        <Box
          sx={{
            px: 2,
            py: 1.6,
            borderBottom: '1px solid',
            borderColor: alpha('#1c2431', 0.06),
          }}
        >
          <Stack direction={{ xs: 'column', xl: 'row' }} spacing={1.25}>
            <TextField
              size="small"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索文件名或任务号"
              sx={{ minWidth: { xs: '100%', xl: 260 } }}
            />
            <TextField
              select
              size="small"
              value={jobTypeFilter}
              onChange={(event) => setJobTypeFilter(event.target.value)}
              sx={{ minWidth: { xs: '100%', md: 160 } }}
            >
              <MenuItem value="all">全部类型</MenuItem>
              <MenuItem value="transcription">单人转写</MenuItem>
              <MenuItem value="multi_speaker_transcription">多人转写</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              sx={{ minWidth: { xs: '100%', md: 150 } }}
            >
              <MenuItem value="all">全部状态</MenuItem>
              <MenuItem value="queued">排队中</MenuItem>
              <MenuItem value="running">处理中</MenuItem>
              <MenuItem value="succeeded">已完成</MenuItem>
              <MenuItem value="failed">失败</MenuItem>
            </TextField>
          </Stack>
        </Box>

        <Box sx={{ display: { xs: 'none', md: 'block' }, px: 2, py: 1.1, bgcolor: alpha('#1c2431', 0.02) }}>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'minmax(280px, 2.4fr) 120px 132px 160px 120px',
              gap: 2,
              alignItems: 'center',
            }}
          >
            <Typography variant="body2" color="text.secondary">文件</Typography>
            <Typography variant="body2" color="text.secondary">状态</Typography>
            <Typography variant="body2" color="text.secondary">类型</Typography>
            <Typography variant="body2" color="text.secondary">更新时间</Typography>
            <Typography variant="body2" color="text.secondary">操作</Typography>
          </Box>
        </Box>

        <Stack divider={<Divider flexItem />}>
          {filteredJobs.length ? (
            filteredJobs.map((job) => (
              <Box
                key={job.job_id}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/jobs/${job.job_id}`)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    navigate(`/jobs/${job.job_id}`);
                  }
                }}
                sx={{
                  px: 2,
                  py: 1.45,
                  cursor: 'pointer',
                  transition: 'background-color 0.18s ease',
                  '&:hover': {
                    bgcolor: alpha('#2f6fed', 0.03),
                  },
                }}
              >
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: 'minmax(280px, 2.4fr) 120px 132px 160px 120px' },
                    gap: { xs: 1.1, md: 2 },
                    alignItems: 'center',
                  }}
                >
                  <Stack spacing={0.35} sx={{ minWidth: 0 }}>
                    <Typography sx={{ fontWeight: 700, lineHeight: 1.35 }} noWrap>
                      {job.asset_name ?? job.job_id}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" noWrap>
                      {job.job_id}
                    </Typography>
                  </Stack>

                  <Box>
                    <StatusChip status={job.status} />
                  </Box>

                  <Box>
                    <Chip size="small" variant="outlined" label={jobTypeLabels[job.job_type]} />
                  </Box>

                  <Typography variant="body2" color="text.secondary">
                    {formatDateTime(job.updated_at)}
                  </Typography>

                  <Box>
                    <Button size="small" onClick={(event) => {
                      event.stopPropagation();
                      navigate(`/jobs/${job.job_id}`);
                    }}>
                      {job.job_type === 'multi_speaker_transcription' ? '复核' : '查看'}
                    </Button>
                  </Box>
                </Box>
              </Box>
            ))
          ) : (
            <Box sx={{ p: 2 }}>
              <Alert severity="info">当前筛选条件下暂无任务。</Alert>
            </Box>
          )}
        </Stack>
      </Card>
    </PageSection>
  );
}
