import ArticleRounded from '@mui/icons-material/ArticleRounded';
import { Alert, Box, Button, Card, CardContent, Chip, Divider, Stack, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchJobs } from '../../api/client';
import {
  formatDateTime,
  isTranscriptionJobType,
  jobDisplayName,
  jobTypeLabels,
} from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';
import { StatusChip } from '../../components/StatusChip';

export function MeetingMinutesIndexPage() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useAsyncData(() => fetchJobs(), []);
  const jobs = useMemo(
    () =>
      (data?.items ?? []).filter(
        (job) => job.status === 'succeeded' && isTranscriptionJobType(job.job_type),
      ),
    [data?.items],
  );

  return (
    <PageSection
      compact
      title="会议纪要"
      description="从已完成的转写任务继续进入纪要工作流。"
      loading={loading}
      error={error}
      actions={<Button variant="outlined" onClick={reload}>刷新</Button>}
    >
      {jobs.length ? (
        <Card>
          <CardContent sx={{ p: 0 }}>
            <Box sx={{ display: { xs: 'none', md: 'block' }, px: 2, py: 1.1, bgcolor: alpha('#1c2431', 0.02) }}>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: 'minmax(320px, 2.5fr) 130px 140px 160px 132px',
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
              {jobs.map((job) => (
                <Box
                  key={job.job_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/minutes/${job.job_id}`)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      navigate(`/minutes/${job.job_id}`);
                    }
                  }}
                  sx={{
                    px: 2,
                    py: 1.35,
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
                      gridTemplateColumns: { xs: '1fr', md: 'minmax(320px, 2.5fr) 130px 140px 160px 132px' },
                      gap: { xs: 1.05, md: 2 },
                      alignItems: 'center',
                    }}
                  >
                    <Stack spacing={0.4} sx={{ minWidth: 0 }}>
                      <Typography sx={{ fontWeight: 700, lineHeight: 1.35 }} noWrap>
                        {jobDisplayName(job)}
                      </Typography>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip size="small" variant="outlined" label={jobTypeLabels[job.job_type]} />
                        <Chip size="small" variant="outlined" label="可生成纪要" />
                      </Stack>
                    </Stack>

                    <Box>
                      <StatusChip status={job.status} />
                    </Box>

                    <Typography variant="body2" color="text.secondary">
                      {jobTypeLabels[job.job_type]}
                    </Typography>

                    <Typography variant="body2" color="text.secondary">
                      {formatDateTime(job.updated_at)}
                    </Typography>

                    <Box>
                      <Button
                        size="small"
                        startIcon={<ArticleRounded />}
                        onClick={(event) => {
                          event.stopPropagation();
                          navigate(`/minutes/${job.job_id}`);
                        }}
                      >
                        打开纪要
                      </Button>
                    </Box>
                  </Box>
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      ) : (
        <Alert severity="info">暂无已完成的转写任务。完成转写后可在这里生成会议纪要。</Alert>
      )}
    </PageSection>
  );
}
