import ArticleRounded from '@mui/icons-material/ArticleRounded';
import { Alert, Button, Card, CardContent, Stack, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';

import { fetchJobs } from '../../api/client';
import { formatDateTime, jobTypeLabels } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';
import { StatusChip } from '../../components/StatusChip';

export function MeetingMinutesIndexPage() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useAsyncData(() => fetchJobs(), []);
  const jobs = (data?.items ?? []).filter((job) => job.status === 'succeeded');

  return (
    <PageSection
      title="会议纪要"
      loading={loading}
      error={error}
      actions={<Button variant="outlined" onClick={reload}>刷新</Button>}
    >
      <Stack spacing={1.5}>
        {jobs.length ? (
          jobs.map((job) => (
            <Card key={job.job_id}>
              <CardContent>
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  justifyContent="space-between"
                  alignItems={{ xs: 'flex-start', md: 'center' }}
                  spacing={1.5}
                >
                  <Stack spacing={0.4}>
                    <Typography variant="h6">{job.asset_name || job.job_id}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {jobTypeLabels[job.job_type]} · {formatDateTime(job.updated_at)}
                    </Typography>
                  </Stack>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <StatusChip status={job.status} />
                    <Button
                      variant="contained"
                      startIcon={<ArticleRounded />}
                      onClick={() => navigate(`/minutes/${job.job_id}`)}
                    >
                      打开纪要
                    </Button>
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          ))
        ) : (
          <Alert severity="info">暂无已完成任务。完成转写后可在这里生成会议纪要。</Alert>
        )}
      </Stack>
    </PageSection>
  );
}
