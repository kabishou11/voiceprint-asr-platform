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
import { MarkdownArticle } from '../../components/MarkdownArticle';
import { PageSection } from '../../components/PageSection';
import { StatCard } from '../../components/StatCard';

const PANEL_MAX_HEIGHT = 520;

function MinutesColumn({ title, items }: { title: string; items: string[] }) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={1.2}>
          <Typography variant="h6">{title}</Typography>
          {items.length ? (
            <Stack spacing={0.9}>
              {items.map((item, index) => (
                <Box
                  key={`${title}-${item}-${index}`}
                  sx={{
                    px: 1.2,
                    py: 1.05,
                    borderRadius: 3,
                    bgcolor: alpha('#ffffff', 0.7),
                    border: '1px solid',
                    borderColor: alpha('#1c2431', 0.06),
                  }}
                >
                  <Typography variant="body2" sx={{ textWrap: 'pretty', lineHeight: 1.6 }}>
                    {index + 1}. {item}
                  </Typography>
                </Box>
              ))}
            </Stack>
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

  const [minutesNotGenerated, setMinutesNotGenerated] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    setMinutesNotGenerated(false);
    void fetchMeetingMinutes(jobId)
      .then((result) => {
        if (active) {
          setMinutes(result);
          setMinutesError(null);
          setMinutesNotGenerated(false);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setMinutes(null);
          const msg = reason instanceof Error ? reason.message : '';
          if (msg.includes('尚未生成') || msg.includes('404')) {
            setMinutesNotGenerated(true);
            setMinutesError(null);
          } else {
            setMinutesNotGenerated(false);
            setMinutesError(msg || '会议纪要加载失败');
          }
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
      (transcript?.segments ?? []).map((segment) => segment.speaker || '未标注说话人'),
    ).size;
    return { segmentCount, speakerCount };
  }, [transcript?.segments]);
  const totalDurationMs = useMemo(
    () => (minutes?.speaker_stats ?? []).reduce((sum, item) => sum + item.duration_ms, 0),
    [minutes?.speaker_stats],
  );
  const totalSegments = useMemo(
    () => (minutes?.speaker_stats ?? []).reduce((sum, item) => sum + item.segment_count, 0),
    [minutes?.speaker_stats],
  );

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
      compact
      title={job?.asset_name || minutes?.title || '会议纪要'}
      description="会议纪要是独立产物，不会污染原文转写视图。"
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
      <Stack spacing={2.2}>
        {generating ? <LinearProgress /> : null}
        {feedback ? <Alert severity="success" onClose={() => setFeedback(null)}>{feedback}</Alert> : null}
        {minutesError ? <Alert severity="warning">{minutesError}</Alert> : null}
        {minutesNotGenerated && !minutes ? (
          <Alert severity="info">
            当前任务尚未生成会议纪要。点击上方"AI 生成"或"本地生成"按钮开始。
          </Alert>
        ) : null}

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip label={minutes?.mode === 'llm' ? `模型生成 · ${minutes.model ?? 'LLM'}` : '本地规则'} color={minutes?.mode === 'llm' ? 'primary' : 'default'} />
          <Chip label={`${stats.speakerCount} 位说话人`} variant="outlined" />
          <Chip label={`${stats.segmentCount} 段`} variant="outlined" />
        </Stack>

        <Grid container spacing={1.5}>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="转录分段" value={stats.segmentCount} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="说话人数" value={stats.speakerCount} color="warning" />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="纪要模式" value={minutes?.mode === 'llm' ? '模型' : '本地'} color="success" />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <StatCard label="总时长" value={`${(totalDurationMs / 1000).toFixed(1)} 秒`} />
          </Grid>
        </Grid>

        <Grid container spacing={2.2}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <Stack spacing={2.2}>
              <Card>
                <CardContent>
                  <Stack spacing={1.6}>
                    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.2}>
                      <Stack spacing={0.4}>
                        <Typography variant="h6">摘要</Typography>
                        <Typography variant="body2" color="text.secondary">
                          优先展示本次会议的主结论与关键背景。
                        </Typography>
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
                    <Divider />
                    <Typography variant="body1" sx={{ fontSize: '1rem', lineHeight: 1.72, textWrap: 'pretty' }}>
                      {minutes?.summary || '点击“AI 生成”调用 MiniMax-M2.7，或点击“本地生成”使用规则引擎生成纪要。'}
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {(minutes?.keywords ?? [])
                        .filter((keyword, index, list) => keyword.trim().length > 1 && list.indexOf(keyword) === index)
                        .slice(0, 8)
                        .map((keyword) => (
                          <Chip key={keyword} size="small" label={keyword} variant="outlined" />
                        ))}
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>

              {minutes ? (
                <Grid container spacing={2.2}>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <MinutesColumn title="核心要点" items={minutes.key_points} />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <MinutesColumn title="议题" items={minutes.topics} />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <MinutesColumn title="决策" items={minutes.decisions} />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <MinutesColumn title="行动项" items={minutes.action_items} />
                  </Grid>
                  <Grid size={{ xs: 12 }}>
                    <MinutesColumn title="风险与阻塞" items={minutes.risks} />
                  </Grid>
                </Grid>
              ) : null}
            </Stack>
          </Grid>

          <Grid size={{ xs: 12, lg: 4 }}>
            <Stack spacing={2.2} sx={{ position: { lg: 'sticky' }, top: { lg: 24 } }}>
              <Card>
                <CardContent>
                  <Stack spacing={1.3}>
                    <Typography variant="h6">说话人贡献</Typography>
                    {minutes?.speaker_stats?.length ? (
                      <Box sx={{ maxHeight: 320, overflow: 'auto' }}>
                        <Stack spacing={1}>
                          {minutes.speaker_stats.map((speaker) => {
                            const value = totalDurationMs > 0
                              ? (speaker.duration_ms / totalDurationMs) * 100
                              : totalSegments > 0
                                ? (speaker.segment_count / totalSegments) * 100
                                : 0;
                            return (
                              <Box key={speaker.speaker} sx={{ px: 1.1, py: 1, borderRadius: 3, bgcolor: alpha('#ffffff', 0.7), border: '1px solid', borderColor: alpha('#1c2431', 0.06) }}>
                                <Stack spacing={0.65}>
                                  <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                                    <Typography fontWeight={700}>{speaker.speaker}</Typography>
                                    <Typography color="text.secondary" variant="body2">
                                      {speaker.segment_count} 段 · {(speaker.duration_ms / 1000).toFixed(1)} 秒
                                    </Typography>
                                  </Stack>
                                  <LinearProgress variant="determinate" value={Math.min(100, value)} sx={{ borderRadius: 99 }} />
                                </Stack>
                              </Box>
                            );
                          })}
                        </Stack>
                      </Box>
                    ) : (
                      <Alert severity="info">暂无可展示的说话人统计。</Alert>
                    )}
                  </Stack>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <Stack spacing={1.3}>
                    <Typography variant="h6">Markdown 预览</Typography>
                    <Box
                      sx={{
                        p: 1.4,
                        borderRadius: 3,
                        bgcolor: alpha('#1c2431', 0.03),
                        maxHeight: 420,
                        overflow: 'auto',
                      }}
                    >
                      <MarkdownArticle content={minutes?.markdown || '暂无纪要内容。'} />
                    </Box>
                  </Stack>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <Stack spacing={1.3}>
                    <Typography variant="h6">模型思考</Typography>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', lineHeight: 1.62 }}
                    >
                      {minutes?.reasoning || '当前纪要未返回 reasoning_details。'}
                    </Typography>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>
          </Grid>
        </Grid>
      </Stack>
    </PageSection>
  );
}
