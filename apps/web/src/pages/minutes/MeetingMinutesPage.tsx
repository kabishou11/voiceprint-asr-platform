import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import ContentCopyRounded from '@mui/icons-material/ContentCopyRounded';
import DownloadRounded from '@mui/icons-material/DownloadRounded';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import ReplayRounded from '@mui/icons-material/ReplayRounded';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
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
import type { MeetingMinutesEvidenceItem, MeetingMinutesResponse } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { MarkdownArticle } from '../../components/MarkdownArticle';
import { PageSection } from '../../components/PageSection';
import { StatCard } from '../../components/StatCard';

const PANEL_MAX_HEIGHT = 520;

const COLUMN_COLORS: Record<string, string> = {
  '核心要点': '#2f6fed',
  '决策': '#16a34a',
  '行动项': '#ea580c',
  '风险与阻塞': '#dc2626',
  '议题': '#7c3aed',
};

const EVIDENCE_LABELS: Record<string, string> = {
  decisions: '决策',
  action_items: '行动项',
  risks: '风险',
};

const LOW_EVIDENCE_THRESHOLD = 0.35;

interface EvidenceSummary {
  total: number;
  averageScore: number | null;
  lowCount: number;
  categories: Array<{
    key: string;
    label: string;
    items: MeetingMinutesEvidenceItem[];
    averageScore: number | null;
    lowCount: number;
  }>;
}

function formatEvidenceScore(score?: number | null) {
  if (typeof score !== 'number' || Number.isNaN(score)) {
    return '未评分';
  }
  return `${Math.round(score * 100)}%`;
}

function formatEvidenceTime(item: MeetingMinutesEvidenceItem) {
  const start = typeof item.start_ms === 'number' ? item.start_ms : null;
  const end = typeof item.end_ms === 'number' ? item.end_ms : null;
  if (start === null && end === null) {
    return '无时间戳';
  }
  const formatSeconds = (value: number) => `${(value / 1000).toFixed(1)}s`;
  if (start !== null && end !== null) {
    return `${formatSeconds(start)} - ${formatSeconds(end)}`;
  }
  return start !== null ? `${formatSeconds(start)} 起` : `${formatSeconds(end as number)} 止`;
}

function averageEvidenceScore(items: MeetingMinutesEvidenceItem[]) {
  const scores = items
    .map((item) => item.evidence_score)
    .filter((score): score is number => typeof score === 'number' && !Number.isNaN(score));
  if (!scores.length) {
    return null;
  }
  return scores.reduce((sum, score) => sum + score, 0) / scores.length;
}

function summarizeEvidence(evidence?: MeetingMinutesResponse['evidence']): EvidenceSummary {
  const categories = Object.entries(evidence ?? {})
    .filter(([, items]) => Array.isArray(items) && items.length > 0)
    .map(([key, items]) => {
      const lowCount = items.filter((item) => typeof item.evidence_score === 'number' && item.evidence_score < LOW_EVIDENCE_THRESHOLD).length;
      return {
        key,
        label: EVIDENCE_LABELS[key] ?? key,
        items,
        averageScore: averageEvidenceScore(items),
        lowCount,
      };
    });
  const allItems = categories.flatMap((category) => category.items);
  return {
    total: allItems.length,
    averageScore: averageEvidenceScore(allItems),
    lowCount: categories.reduce((sum, category) => sum + category.lowCount, 0),
    categories,
  };
}

function MinutesColumn({ title, items }: { title: string; items: string[] }) {
  const accentColor = COLUMN_COLORS[title] ?? '#64748b';
  return (
    <Card>
      <CardContent>
        <Stack spacing={1.2}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Box sx={{ width: 4, height: 18, borderRadius: 2, bgcolor: accentColor, flexShrink: 0 }} />
            <Typography variant="h6">{title}</Typography>
          </Stack>
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
                    borderLeft: `3px solid ${alpha(accentColor, 0.5)}`,
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

function EvidenceDiagnostics({ summary }: { summary: EvidenceSummary }) {
  if (!summary.total) {
    return (
      <Card>
        <CardContent>
          <Stack spacing={1.2}>
            <Typography variant="h6">证据覆盖</Typography>
            <Alert severity="info">当前纪要未返回 evidence，暂无法核验决策、行动项与风险的转写来源。</Alert>
          </Stack>
        </CardContent>
      </Card>
    );
  }

  const severity = summary.lowCount > 0 ? 'warning' : 'success';
  return (
    <Card>
      <CardContent>
        <Stack spacing={1.35}>
          <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
            <Typography variant="h6">证据覆盖</Typography>
            <Chip
              size="small"
              color={summary.lowCount > 0 ? 'warning' : 'success'}
              label={`平均 ${formatEvidenceScore(summary.averageScore)}`}
            />
          </Stack>
          <Alert severity={severity}>
            已关联 {summary.total} 条证据，{summary.lowCount ? `${summary.lowCount} 条低证据需要复核。` : '当前证据可信度良好。'}
          </Alert>
          <Stack spacing={1}>
            {summary.categories.map((category) => (
              <Accordion key={category.key} disableGutters elevation={0} sx={{ border: '1px solid', borderColor: alpha('#1c2431', 0.08), borderRadius: 2.5, '&:before': { display: 'none' } }}>
                <AccordionSummary expandIcon={<ExpandMoreRounded />}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography fontWeight={700}>{category.label}</Typography>
                    <Chip size="small" variant="outlined" label={`${category.items.length} 条`} />
                    <Chip size="small" variant="outlined" label={`平均 ${formatEvidenceScore(category.averageScore)}`} />
                    {category.lowCount ? <Chip size="small" color="warning" label={`${category.lowCount} 条低证据`} /> : null}
                  </Stack>
                </AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={1}>
                    {category.items.slice(0, 5).map((item, index) => (
                      <Box key={`${category.key}-${item.item ?? item.segment ?? index}`} sx={{ p: 1.1, borderRadius: 2.5, bgcolor: alpha('#ffffff', 0.72), border: '1px solid', borderColor: alpha('#1c2431', 0.06) }}>
                        <Stack spacing={0.55}>
                          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                            <Chip size="small" color={(item.evidence_score ?? 1) < LOW_EVIDENCE_THRESHOLD ? 'warning' : 'default'} label={formatEvidenceScore(item.evidence_score)} />
                            <Typography variant="caption" color="text.secondary">
                              {item.speaker || '未知说话人'} · {formatEvidenceTime(item)}
                            </Typography>
                          </Stack>
                          <Typography variant="body2" fontWeight={700} sx={{ textWrap: 'pretty' }}>
                            {item.item || '未命名纪要条目'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ textWrap: 'pretty', lineHeight: 1.55 }}>
                            {item.reason || item.segment || '无证据说明。'}
                          </Typography>
                        </Stack>
                      </Box>
                    ))}
                    {category.items.length > 5 ? (
                      <Typography variant="caption" color="text.secondary">
                        还有 {category.items.length - 5} 条证据未展开展示，可在接口返回中查看完整 evidence。
                      </Typography>
                    ) : null}
                  </Stack>
                </AccordionDetails>
              </Accordion>
            ))}
          </Stack>
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
  const evidenceSummary = useMemo(() => summarizeEvidence(minutes?.evidence), [minutes?.evidence]);

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
          <Chip label={minutes?.reasoning ? 'reasoning 已返回' : '无 reasoning'} variant="outlined" />
          <Chip label={evidenceSummary.total ? `证据 ${evidenceSummary.total} 条` : '无证据'} variant="outlined" />
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

              <EvidenceDiagnostics summary={evidenceSummary} />

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

              <Accordion disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreRounded />}>
                  <Stack spacing={0.35}>
                    <Typography variant="h6">模型思考</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {minutes?.reasoning ? '已返回 reasoning_details，展开查看模型归纳过程。' : '当前纪要未返回 reasoning_details。'}
                    </Typography>
                  </Stack>
                </AccordionSummary>
                <AccordionDetails>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto', lineHeight: 1.62 }}
                  >
                    {minutes?.reasoning || '当前纪要未返回 reasoning_details。'}
                  </Typography>
                </AccordionDetails>
              </Accordion>
            </Stack>
          </Grid>
        </Grid>
      </Stack>
    </PageSection>
  );
}
