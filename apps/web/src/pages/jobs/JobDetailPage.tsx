import {
  Alert,
  Button,
  Card,
  CardContent,
  Divider,
  Grid,
  Stack,
  Typography,
} from '@mui/material';
import { useParams } from 'react-router-dom';

import { fetchTranscript } from '../../api/client';
import { formatDateTime, jobTypeLabels } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';
import { StatusChip } from '../../components/StatusChip';

export function JobDetailPage() {
  const { jobId = '' } = useParams();
  const { data, loading, error, reload } = useAsyncData(() => fetchTranscript(jobId), [jobId]);

  const segments = data?.transcript?.segments ?? [];

  return (
    <PageSection
      title="任务详情"
      description="查看任务摘要、转写全文和分段结果。"
      loading={loading}
      error={error}
      actions={
        <Button variant="outlined" onClick={reload}>
          刷新结果
        </Button>
      }
    >
      {data?.job ? (
        <Stack spacing={3}>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary">
                    文件名
                  </Typography>
                  <Typography variant="h6" sx={{ mt: 1, wordBreak: 'break-all' }}>
                    {data.job.asset_name ?? '未命名文件'}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid size={{ xs: 6, lg: 3 }}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary">
                    任务类型
                  </Typography>
                  <Typography variant="h6" sx={{ mt: 1 }}>
                    {jobTypeLabels[data.job.job_type]}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid size={{ xs: 6, lg: 3 }}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary">
                    状态
                  </Typography>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                    <StatusChip status={data.job.status} />
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
            <Grid size={{ xs: 6, lg: 3 }}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary">
                    分段数
                  </Typography>
                  <Typography variant="h6" sx={{ mt: 1 }}>
                    {segments.length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid size={{ xs: 12, lg: 9 }}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary">
                    更新时间
                  </Typography>
                  <Typography variant="h6" sx={{ mt: 1 }}>
                    {formatDateTime(data.job.updated_at)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Grid container spacing={3}>
            <Grid size={{ xs: 12, lg: 5 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Stack spacing={2}>
                    <Typography variant="h6">全文结果</Typography>
                    <Typography color="text.secondary" sx={{ lineHeight: 1.9 }}>
                      {data.transcript?.text ?? '暂无转写结果'}
                    </Typography>
                    {data.job.error_message ? (
                      <Alert severity="error">{data.job.error_message}</Alert>
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
            <Grid size={{ xs: 12, lg: 7 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Stack spacing={2}>
                    <Typography variant="h6">分段结果</Typography>
                    {segments.length ? (
                      <Stack spacing={1.5}>
                        {segments.map((segment, index) => (
                          <Card
                            key={`${segment.start_ms}-${index}`}
                            variant="outlined"
                            sx={{ borderRadius: 4 }}
                          >
                            <CardContent>
                              <Stack spacing={1}>
                                <Stack direction="row" justifyContent="space-between" alignItems="center">
                                  <Typography variant="body2" color="text.secondary">
                                    {segment.start_ms}ms - {segment.end_ms}ms
                                  </Typography>
                                  <Typography variant="body2" fontWeight={700}>
                                    {segment.speaker ?? '未标注说话人'}
                                  </Typography>
                                </Stack>
                                <Divider />
                                <Typography>{segment.text || '（该片段暂无文本）'}</Typography>
                              </Stack>
                            </CardContent>
                          </Card>
                        ))}
                      </Stack>
                    ) : (
                      <Alert severity="info">当前任务还没有可展示的分段结果。</Alert>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Stack>
      ) : (
        <Alert severity="info">请输入有效任务 ID。</Alert>
      )}
    </PageSection>
  );
}
