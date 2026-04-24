import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import ContentCopyRounded from '@mui/icons-material/ContentCopyRounded';
import DownloadRounded from '@mui/icons-material/DownloadRounded';
import ReplayRounded from '@mui/icons-material/ReplayRounded';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { fetchMeetingMinutes, fetchTranscript, generateMeetingMinutes } from '../../api/client';
import type { MeetingMinutesResponse } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';

function MinutesColumn({ title, items }: { title: string; items: string[] }) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Stack spacing={1.3}>
          <Typography variant="h6">{title}</Typography>
          {items.length ? (
            items.map((item, index) => (
              <Box
                key={`${title}-${item}-${index}`}
                sx={{
                  p: 1.25,
                  borderRadius: 3,
                  bgcolor: alpha('#ffffff', 0.68),
                  border: '1px solid',
                  borderColor: alpha('#1c2431', 0.06),
                }}
              >
                <Typography variant="body2" sx={{ textWrap: 'pretty' }}>
                  {index + 1}. {item}
                </Typography>
              </Box>
            ))
          ) : (
            <Typography variant="body2" color="text.secondary">
              暂无明确内容。
            </Typography>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

export function MeetingMinutesPage() {
  const { jobId = '' } = useParams();
  const navigate = useNavigate();
  const transcriptState = useAsyncData(() => fetchTranscript(jobId), [jobId]);
  const [minutes, setMinutes] = useState<MeetingMinutesResponse | null>(null);
  const [minutesError, setMinutesError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    void fetchMeetingMinutes(jobId)
      .then((result) => {
        if (active) {
          setMinutes(result);
          setMinutesError(null);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setMinutes(null);
          setMinutesError(reason instanceof Error ? reason.message : '会议纪要加载失败');
        }
      });
    return () => {
      active = false;
    };
  }, [jobId]);

  const job = transcriptState.data?.job ?? null;
  const transcript = transcriptState.data?.transcript ?? null;
  const stats = useMemo(() => {
    const segmentCount = transcript?.segments.length ?? 0;
    const speakerCount = new Set(
      (transcript?.segments ?? []).map((segment, index) => segment.speaker || `Speaker ${index + 1}`),
    ).size;
    return { segmentCount, speakerCount };
  }, [transcript?.segments]);

  const handleGenerate = async (useLlm: boolean) => {
    setGenerating(true);
    setMinutesError(null);
    try {
      const result = await generateMeetingMinutes(jobId, useLlm);
      setMinutes(result);
      setFeedback(useLlm ? 'AI 会议纪要已生成。' : '本地会议纪要已生成。');
    } catch (reason) {
      setMinutesError(reason instanceof Error ? reason.message : '会议纪要生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!minutes) return;
    try {
      await navigator.clipboard.writeText(minutes.markdown);
      setFeedback('Markdown 会议纪要已复制。');
    } catch {
      setFeedback('当前环境不支持剪贴板写入。');
    }
  };

  const handleDownload = () => {
    if (!minutes || typeof window === 'undefined') return;
    const blob = new Blob([minutes.markdown], { type: 'text/markdown;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const link = window.document.createElement('a');
    link.href = url;
    link.download = `${job?.asset_name || jobId}-minutes.md`;
    link.click();
    window.URL.revokeObjectURL(url);
  };

  return (
    <PageSection
      title="会议纪要"
      loading={transcriptState.loading}
      error={transcriptState.error}
      actions={
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button variant="outlined" onClick={() => navigate(`/jobs/${jobId}`)}>
            查看原文
          </Button>
          <Button variant="outlined" startIcon={<ReplayRounded />} onClick={() => handleGenerate(false)} disabled={generating}>
            本地生成
          </Button>
          <Button variant="contained" startIcon={<AutoAwesomeRounded />} onClick={() => handleGenerate(true)} disabled={generating}>
            AI 生成
          </Button>
        </Stack>
      }
    >
      <Stack spacing={2.4}>
        {generating ? <LinearProgress /> : null}
        {feedback ? <Alert severity="success" onClose={() => setFeedback(null)}>{feedback}</Alert> : null}
        {minutesError ? <Alert severity="warning">{minutesError}</Alert> : null}

        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
                <Stack spacing={0.8}>
                  <Typography variant="h3" sx={{ fontSize: { xs: '1.8rem', md: '2.4rem' } }}>
                    {job?.asset_name || minutes?.title || jobId}
                  </Typography>
                  <Typography color="text.secondary">
                    会议纪要是独立产物，不会污染原文转写视图。
                  </Typography>
                </Stack>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="flex-start">
                  <Chip label={minutes?.mode === 'llm' ? `AI: ${minutes.model ?? 'LLM'}` : '本地规则'} color={minutes?.mode === 'llm' ? 'primary' : 'default'} />
                  <Chip label={`${stats.speakerCount} speakers`} variant="outlined" />
                  <Chip label={`${stats.segmentCount} 段`} variant="outlined" />
                </Stack>
              </Stack>
              <Divider />
              <Typography variant="body1" sx={{ fontSize: '1.05rem', lineHeight: 1.9, textWrap: 'pretty' }}>
                {minutes?.summary || '点击“AI 生成”调用 MiniMax-M2.7，或点击“本地生成”使用规则引擎生成纪要。'}
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {(minutes?.keywords ?? []).slice(0, 12).map((keyword) => (
                  <Chip key={keyword} size="small" label={keyword} variant="outlined" />
                ))}
              </Stack>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button variant="outlined" startIcon={<ContentCopyRounded />} onClick={handleCopy} disabled={!minutes}>
                  复制 Markdown
                </Button>
                <Button variant="outlined" startIcon={<DownloadRounded />} onClick={handleDownload} disabled={!minutes}>
                  下载 .md
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        {minutes ? (
          <>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, lg: 3 }}>
                <MinutesColumn title="核心要点" items={minutes.key_points} />
              </Grid>
              <Grid size={{ xs: 12, lg: 3 }}>
                <MinutesColumn title="决策" items={minutes.decisions} />
              </Grid>
              <Grid size={{ xs: 12, lg: 3 }}>
                <MinutesColumn title="行动项" items={minutes.action_items} />
              </Grid>
              <Grid size={{ xs: 12, lg: 3 }}>
                <MinutesColumn title="风险与阻塞" items={minutes.risks} />
              </Grid>
            </Grid>

            <Grid container spacing={2}>
              <Grid size={{ xs: 12, lg: 4 }}>
                <MinutesColumn title="议题" items={minutes.topics} />
              </Grid>
              <Grid size={{ xs: 12, lg: 4 }}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Stack spacing={1.3}>
                      <Typography variant="h6">Speaker 贡献</Typography>
                      {minutes.speaker_stats.map((speaker) => (
                        <Box key={speaker.speaker}>
                          <Stack direction="row" justifyContent="space-between" spacing={2}>
                            <Typography fontWeight={700}>{speaker.speaker}</Typography>
                            <Typography color="text.secondary">
                              {speaker.segment_count} 段 · {(speaker.duration_ms / 1000).toFixed(1)} 秒
                            </Typography>
                          </Stack>
                          <LinearProgress
                            variant="determinate"
                            value={Math.min(100, speaker.segment_count * 12)}
                            sx={{ mt: 0.8, borderRadius: 99 }}
                          />
                        </Box>
                      ))}
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
              <Grid size={{ xs: 12, lg: 4 }}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Stack spacing={1.3}>
                      <Typography variant="h6">模型思考</Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}
                      >
                        {minutes.reasoning || '当前纪要未返回 reasoning_details。'}
                      </Typography>
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            <Card>
              <CardContent>
                <Stack spacing={1.3}>
                  <Typography variant="h6">Markdown 预览</Typography>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      p: 2,
                      borderRadius: 4,
                      bgcolor: alpha('#1c2431', 0.04),
                      whiteSpace: 'pre-wrap',
                      fontFamily: '"JetBrains Mono", "Consolas", monospace',
                      fontSize: '0.88rem',
                      lineHeight: 1.75,
                    }}
                  >
                    {minutes.markdown}
                  </Box>
                </Stack>
              </CardContent>
            </Card>
          </>
        ) : null}
      </Stack>
    </PageSection>
  );
}
