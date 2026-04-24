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
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { fetchMeetingMinutes, fetchTranscript } from '../../api/client';
import {
  formatDateTime,
  jobTypeLabels,
  type MeetingMinutesResponse,
  type Segment,
  type TranscriptResult,
} from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';
import { BalancedPretextText, MeasuredPretextBlock } from '../../components/PretextText';
import { StatusChip } from '../../components/StatusChip';

const SPEAKER_MAPPING_STORAGE_KEY = 'voiceprint-job-speaker-mappings';
const POLL_INTERVAL_MS = 3000;

type SpeakerMappingStore = Record<string, Record<string, string>>;
type ExportSpeakerGroup = {
  speaker: string;
  displaySpeaker: string;
  durationMs: number;
  segments: Segment[];
} | null;

export function buildJobExportDocument(params: {
  job: unknown;
  transcript: TranscriptResult | null | undefined;
  filteredSegments: Segment[];
  selectedSpeakerGroup: ExportSpeakerGroup;
  speakerAliases: Record<string, string>;
}) {
  const { job, transcript, filteredSegments, selectedSpeakerGroup, speakerAliases } = params;
  return {
    job,
    transcript: transcript
      ? {
          ...transcript,
          text: selectedSpeakerGroup
            ? selectedSpeakerGroup.segments.map((segment) => segment.text).filter(Boolean).join(' ')
            : transcript.text,
          segments: filteredSegments,
        }
      : null,
    timeline_metadata: transcript?.metadata ?? null,
    speaker_focus:
      selectedSpeakerGroup
        ? {
            speaker: selectedSpeakerGroup.speaker,
            display_name: selectedSpeakerGroup.displaySpeaker,
            duration_ms: selectedSpeakerGroup.durationMs,
            segment_count: selectedSpeakerGroup.segments.length,
          }
        : null,
    speaker_aliases: speakerAliases,
    exported_at: new Date().toISOString(),
  };
}

function InfoMetric({
  label,
  value,
  wide = false,
}: {
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <Box
      sx={{
        p: 1.7,
        borderRadius: 4,
        minHeight: wide ? 108 : undefined,
        bgcolor: alpha('#ffffff', 0.74),
        border: '1px solid',
        borderColor: alpha('#1c2431', 0.06),
      }}
    >
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography
        variant="h6"
        sx={{
          mt: 1,
          wordBreak: 'break-word',
          textWrap: 'pretty',
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}

export function JobDetailPage() {
  const navigate = useNavigate();
  const { jobId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const { data, loading, error, reload, setData } = useAsyncData(() => fetchTranscript(jobId), [jobId]);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [speakerAliases, setSpeakerAliases] = useState<Record<string, string>>({});
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>('ALL');
  const [minutes, setMinutes] = useState<MeetingMinutesResponse | null>(null);
  const [minutesError, setMinutesError] = useState<string | null>(null);
  const isProcessing =
    data?.job?.status === 'pending' || data?.job?.status === 'queued' || data?.job?.status === 'running';
  const isFailed = data?.job?.status === 'failed';
  const isSucceeded = data?.job?.status === 'succeeded';

  useEffect(() => {
    if (!jobId || !isProcessing) {
      return undefined;
    }

    let active = true;
    const timer = window.setInterval(() => {
      void fetchTranscript(jobId)
        .then((result) => {
          if (active) {
            setData(result);
          }
        })
        .catch(() => {
          // 保持当前页面状态，用户仍可手动刷新查看具体错误。
        });
    }, POLL_INTERVAL_MS);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [isProcessing, jobId, setData]);

  useEffect(() => {
    if (!jobId || !isSucceeded) {
      setMinutes(null);
      setMinutesError(null);
      return;
    }

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
          setMinutesError(reason instanceof Error ? reason.message : '会议纪要生成失败');
        }
      });

    return () => {
      active = false;
    };
  }, [isSucceeded, jobId]);

  useEffect(() => {
    if (!jobId || typeof window === 'undefined') {
      setSpeakerAliases({});
      return;
    }
    try {
      const raw = window.localStorage.getItem(SPEAKER_MAPPING_STORAGE_KEY);
      if (!raw) {
        setSpeakerAliases({});
        return;
      }
      const store = JSON.parse(raw) as SpeakerMappingStore;
      setSpeakerAliases(store[jobId] ?? {});
    } catch {
      setSpeakerAliases({});
    }
  }, [jobId, searchParams]);

  const segments = data?.transcript?.segments ?? [];
  const transcriptMetadata = data?.transcript?.metadata ?? null;
  const displayTimeline =
    transcriptMetadata?.timelines.find((timeline) => timeline.source === 'display') ?? null;
  const exclusiveTimeline =
    transcriptMetadata?.timelines.find((timeline) => timeline.source === 'exclusive') ?? null;
  const regularTimeline =
    transcriptMetadata?.timelines.find((timeline) => timeline.source === 'regular') ?? null;

  const speakerGroups = useMemo(() => {
    const groups = new Map<
      string,
      { speaker: string; segments: typeof segments; durationMs: number; confidenceValues: number[] }
    >();
    segments.forEach((segment) => {
      const speaker = segment.speaker ?? '未标注说话人';
      const group = groups.get(speaker) ?? {
        speaker,
        segments: [],
        durationMs: 0,
        confidenceValues: [],
      };
      group.segments.push(segment);
      group.durationMs += Math.max(0, segment.end_ms - segment.start_ms);
      if (typeof segment.confidence === 'number') {
        group.confidenceValues.push(segment.confidence);
      }
      groups.set(speaker, group);
    });
    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        avgConfidence: group.confidenceValues.length
          ? group.confidenceValues.reduce((sum, item) => sum + item, 0) /
            group.confidenceValues.length
          : null,
        displaySpeaker: speakerAliases[group.speaker] || group.speaker,
      }))
      .sort((left, right) => right.durationMs - left.durationMs);
  }, [segments, speakerAliases]);

  const filteredSegments = useMemo(
    () =>
      selectedSpeaker === 'ALL'
        ? segments
        : segments.filter((segment) => (segment.speaker ?? '未标注说话人') === selectedSpeaker),
    [segments, selectedSpeaker],
  );
  const selectedSpeakerGroup = useMemo(
    () => speakerGroups.find((group) => group.speaker === selectedSpeaker) ?? null,
    [speakerGroups, selectedSpeaker],
  );
  const timelineSegments = useMemo(() => {
    const source =
      selectedSpeaker === 'ALL'
        ? displayTimeline?.segments ?? filteredSegments
        : (displayTimeline?.segments ?? filteredSegments).filter(
            (segment) => (segment.speaker ?? '未标注说话人') === selectedSpeaker,
          );
    return source.filter((segment) => segment.end_ms > segment.start_ms);
  }, [displayTimeline?.segments, filteredSegments, selectedSpeaker]);
  const timelineStartMs = timelineSegments.length ? timelineSegments[0].start_ms : 0;
  const timelineEndMs = timelineSegments.length
    ? timelineSegments[timelineSegments.length - 1].end_ms
    : timelineStartMs;
  const timelineDurationMs = Math.max(1, timelineEndMs - timelineStartMs);

  const formatDuration = (durationMs: number) => `${(durationMs / 1000).toFixed(1)} 秒`;

  const buildExportPayload = () =>
    JSON.stringify(
      buildJobExportDocument({
        job: data?.job ?? null,
        transcript: data?.transcript ?? null,
        filteredSegments,
        selectedSpeakerGroup,
        speakerAliases,
      }),
      null,
      2,
    );

  const buildCopyText = () => {
    const header = [
      `任务 ${data?.job?.job_id ?? '—'}`,
      `文件 ${data?.job?.asset_name ?? '—'}`,
      `类型 ${data?.job ? jobTypeLabels[data.job.job_type] : '—'}`,
      `状态 ${data?.job?.status ?? '—'}`,
    ];
    const body = speakerGroups.flatMap((group) =>
      group.segments.map((segment) => {
        const speaker = speakerAliases[segment.speaker ?? ''] || segment.speaker || '未标注说话人';
        return `[${segment.start_ms}-${segment.end_ms}] ${speaker}: ${segment.text || '（该片段暂无文本）'}`;
      }),
    );
    return [...header, '', data?.transcript?.text ?? '', '', ...body].join('\n');
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(buildCopyText());
      setFeedback('全文结果已复制到剪贴板。');
    } catch {
      setFeedback('当前环境不支持剪贴板写入。');
    }
  };

  const handleExport = () => {
    if (typeof window === 'undefined' || !data?.job) {
      return;
    }
    const blob = new Blob([buildExportPayload()], { type: 'application/json;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const link = window.document.createElement('a');
    link.href = url;
    link.download = selectedSpeakerGroup
      ? `${data.job.job_id}-${selectedSpeakerGroup.speaker}.json`
      : `${data.job.job_id}.json`;
    link.click();
    window.URL.revokeObjectURL(url);
    setFeedback(selectedSpeakerGroup ? '当前 Speaker 结果已导出为 JSON。' : '任务结果已导出为 JSON。');
  };

  const handleRetry = () => {
    if (!data?.job?.asset_name) {
      setFeedback('当前任务缺少资产名，无法快速重跑。');
      return;
    }
    const params = new URLSearchParams({
      asset: data.job.asset_name,
      language: data.transcript?.language ?? 'zh-cn',
      mode: data.job.job_type === 'multi_speaker_transcription' ? 'multi' : 'single',
    });
    navigate(`/?${params.toString()}`);
  };

  return (
    <PageSection
      title="结果"
      loading={loading}
      error={error}
      actions={
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button variant="outlined" onClick={reload}>
            刷新结果
          </Button>
          <Button variant="outlined" onClick={handleCopy} disabled={!data?.job}>
            复制全文
          </Button>
          <Button variant="outlined" onClick={handleExport} disabled={!data?.job}>
            {selectedSpeakerGroup ? '导出当前 Speaker JSON' : '导出 JSON'}
          </Button>
          <Button variant="contained" onClick={handleRetry} disabled={!data?.job}>
            快速重跑
          </Button>
        </Stack>
      }
    >
      {data?.job ? (
        <Stack spacing={3}>
          {feedback ? (
            <Alert severity="success" onClose={() => setFeedback(null)}>
              {feedback}
            </Alert>
          ) : null}

          {isProcessing ? (
            <Card>
              <CardContent>
                <Stack spacing={2}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                    spacing={1.5}
                  >
                    <Stack spacing={0.4}>
                      <Typography variant="h6">{data.job.asset_name ?? data.job.job_id}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {jobTypeLabels[data.job.job_type]} · 自动刷新 {POLL_INTERVAL_MS / 1000}s
                      </Typography>
                    </Stack>
                    <StatusChip status={data.job.status} />
                  </Stack>
                  <LinearProgress />
                  <Typography variant="body2" color="text.secondary">
                    任务正在后端执行，完成后会自动展示全文、时间戳、Speaker 时间线和分段结果。
                  </Typography>
                </Stack>
              </CardContent>
            </Card>
          ) : null}

          {isFailed ? (
            <Alert severity="error">
              {data.job.error_message || '任务执行失败，请检查模型、GPU、音频格式或重新发起任务。'}
            </Alert>
          ) : null}

          {!isProcessing ? (
          <>
          {minutes ? (
            <Card>
              <CardContent>
                <Grid container spacing={2.5}>
                  <Grid size={{ xs: 12, lg: 5 }}>
                    <Stack spacing={1.4}>
                      <Typography variant="h6">会议纪要</Typography>
                      <Typography
                        variant="body1"
                        sx={{
                          lineHeight: 1.9,
                          textWrap: 'pretty',
                          color: 'text.primary',
                        }}
                      >
                        {minutes.summary}
                      </Typography>
                    </Stack>
                  </Grid>
                  <Grid size={{ xs: 12, lg: 4 }}>
                    <Stack spacing={1.1}>
                      <Typography variant="subtitle1">要点</Typography>
                      {minutes.key_points.length ? (
                        minutes.key_points.slice(0, 5).map((point, index) => (
                          <Typography key={`${point}-${index}`} variant="body2" color="text.secondary">
                            {index + 1}. {point}
                          </Typography>
                        ))
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          暂无可提取要点。
                        </Typography>
                      )}
                    </Stack>
                  </Grid>
                  <Grid size={{ xs: 12, lg: 3 }}>
                    <Stack spacing={1.1}>
                      <Typography variant="subtitle1">行动项</Typography>
                      {minutes.action_items.length ? (
                        minutes.action_items.slice(0, 5).map((item, index) => (
                          <Chip
                            key={`${item}-${index}`}
                            label={item}
                            variant="outlined"
                            sx={{ justifyContent: 'flex-start', height: 'auto', py: 0.7, '& .MuiChip-label': { whiteSpace: 'normal' } }}
                          />
                        ))
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          未检测到明确行动项。
                        </Typography>
                      )}
                    </Stack>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          ) : minutesError ? (
            <Alert severity="warning">{minutesError}</Alert>
          ) : null}

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, xl: 8 }}>
              <Card>
                <CardContent>
                  <Stack spacing={2.3}>
                  <Stack
                      direction={{ xs: 'column', lg: 'row' }}
                      justifyContent="space-between"
                      spacing={2}
                    >
                      <Stack spacing={0.6}>
                        <BalancedPretextText
                          text={data.job.asset_name ?? '未命名文件'}
                          font='500 34px "Iowan Old Style"'
                          lineHeight={39}
                          targetLines={2}
                          minWidth={320}
                          maxWidth={620}
                          typographyProps={{
                            variant: 'h3',
                            sx: {
                              fontSize: { xs: '1.7rem', md: '2.1rem' },
                              maxWidth: 620,
                            },
                          }}
                        />
                        <Typography color="text.secondary" sx={{ maxWidth: 620, textWrap: 'pretty', fontSize: '0.93rem' }}>
                          {jobTypeLabels[data.job.job_type]} · 更新时间 {formatDateTime(data.job.updated_at)}
                        </Typography>
                      </Stack>
                      <Stack spacing={1} alignItems={{ xs: 'flex-start', lg: 'flex-end' }}>
                        <StatusChip status={data.job.status} />
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                          <Chip size="small" variant="outlined" label={`语言 ${data.transcript?.language ?? '未标注'}`} />
                          <Chip size="small" variant="outlined" label={`Speaker ${speakerGroups.length}`} />
                          <Chip
                            size="small"
                            variant="outlined"
                            label={
                              transcriptMetadata?.alignment_source === 'exclusive'
                                ? '对齐 Exclusive'
                                : '对齐 Regular'
                            }
                          />
                        </Stack>
                      </Stack>
                    </Stack>

                    <Grid container spacing={1.5}>
                      <Grid size={{ xs: 12, md: 4 }}>
                        <InfoMetric label="任务类型" value={jobTypeLabels[data.job.job_type]} />
                      </Grid>
                      <Grid size={{ xs: 12, md: 4 }}>
                        <InfoMetric label="分段数" value={String(segments.length)} />
                      </Grid>
                      <Grid size={{ xs: 12, md: 4 }}>
                        <InfoMetric
                          label="对齐时间轴"
                          value={
                            transcriptMetadata?.alignment_source === 'exclusive'
                              ? 'Exclusive'
                              : 'Regular'
                          }
                        />
                      </Grid>
                    </Grid>

                    <Box
                      sx={{
                        p: 1.25,
                        borderRadius: 3,
                        bgcolor: alpha('#ffffff', 0.68),
                        border: '1px solid',
                        borderColor: alpha('#1c2431', 0.06),
                      }}
                    >
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {exclusiveTimeline ? (
                          <Chip size="small" variant="outlined" label={`exclusive ${exclusiveTimeline.segments.length} 段`} />
                        ) : null}
                        {displayTimeline ? (
                          <Chip size="small" variant="outlined" label={`display ${displayTimeline.segments.length} 段`} />
                        ) : null}
                        {regularTimeline ? (
                          <Chip size="small" variant="outlined" label={`regular ${regularTimeline.segments.length} 段`} />
                        ) : null}
                      </Stack>
                    </Box>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>

            <Grid size={{ xs: 12, xl: 4 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Stack spacing={1.2}>
                    <Typography variant="h6">Speaker</Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      <Chip
                        label={`全部 ${segments.length} 段`}
                        color={selectedSpeaker === 'ALL' ? 'primary' : 'default'}
                        onClick={() => setSelectedSpeaker('ALL')}
                      />
                      {speakerGroups.map((group) => (
                        <Chip
                          key={group.speaker}
                          label={`${group.displaySpeaker} · ${group.segments.length} 段`}
                          color={selectedSpeaker === group.speaker ? 'primary' : 'default'}
                          onClick={() => setSelectedSpeaker(group.speaker)}
                        />
                      ))}
                    </Stack>
                    <Divider />
                    {speakerGroups.length ? (
                      <Stack spacing={1.2}>
                        {speakerGroups.map((group) => (
                          <Box
                            key={group.speaker}
                            sx={{
                              p: 1.35,
                              borderRadius: 4,
                              bgcolor:
                                selectedSpeaker === group.speaker
                                  ? alpha('#2f6fed', 0.06)
                                  : alpha('#ffffff', 0.66),
                              border: '1px solid',
                              borderColor:
                                selectedSpeaker === group.speaker
                                  ? alpha('#2f6fed', 0.16)
                                  : alpha('#1c2431', 0.06),
                            }}
                          >
                            <Stack spacing={0.9}>
                              <Stack direction="row" justifyContent="space-between" spacing={1}>
                                <Typography fontWeight={700}>{group.displaySpeaker}</Typography>
                                <Chip size="small" label={`${group.segments.length} 段`} />
                              </Stack>
                              {group.displaySpeaker !== group.speaker ? (
                                <Typography variant="body2" color="text.secondary">
                                  原标签 {group.speaker}
                                </Typography>
                              ) : null}
                              <Typography variant="body2" color="text.secondary">
                                总时长 {formatDuration(group.durationMs)} · 平均置信度{' '}
                                {group.avgConfidence !== null ? group.avgConfidence.toFixed(2) : '—'}
                              </Typography>
                              <Box
                                sx={{
                                  px: 0.1,
                                  py: 0.25,
                                  borderRadius: 2.5,
                                }}
                              >
                                <MeasuredPretextBlock
                                  text={
                                    group.segments
                                      .slice(0, 2)
                                      .map((segment) => segment.text)
                                      .join(' / ') || '暂无文本'
                                  }
                                  font='400 14px "PingFang SC"'
                                  lineHeight={25}
                                  typographyProps={{
                                    variant: 'body2',
                                    color: 'text.secondary',
                                    sx: {
                                      lineHeight: 1.75,
                                    },
                                  }}
                                />
                              </Box>
                              {data.job.asset_name ? (
                                <Button
                                  size="small"
                                  variant="text"
                                  sx={{ alignSelf: 'flex-start', px: 0 }}
                                  onClick={() =>
                                    navigate(
                                      `/voiceprints?probe=${encodeURIComponent(
                                        data.job.asset_name ?? '',
                                      )}&speaker=${encodeURIComponent(group.speaker)}&jobId=${encodeURIComponent(jobId)}`,
                                    )
                                  }
                                >
                                  对这个 Speaker 做声纹处理
                                </Button>
                              ) : null}
                            </Stack>
                          </Box>
                        ))}
                      </Stack>
                    ) : (
                      <Alert severity="info">当前还没有可复核的 speaker 聚合结果。</Alert>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Grid container spacing={3}>
            <Grid size={{ xs: 12, xl: 4.2 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Stack spacing={2}>
                    <Typography variant="h6">
                      {selectedSpeakerGroup ? selectedSpeakerGroup.displaySpeaker : '全文结果'}
                    </Typography>
                    {selectedSpeakerGroup ? (
                      <Alert severity="info">
                        {selectedSpeakerGroup.displaySpeaker} · {formatDuration(selectedSpeakerGroup.durationMs)} · {selectedSpeakerGroup.segments.length} 段
                      </Alert>
                    ) : null}
                    <Box
                      sx={{
                        p: 1.6,
                        borderRadius: 4,
                        bgcolor: alpha('#ffffff', 0.68),
                        border: '1px solid',
                        borderColor: alpha('#1c2431', 0.06),
                        minHeight: 220,
                      }}
                    >
                      <MeasuredPretextBlock
                        text={
                          selectedSpeakerGroup
                            ? selectedSpeakerGroup.segments
                                .map((segment) => segment.text)
                                .filter(Boolean)
                                .join(' ')
                            : data.transcript?.text ?? '暂无转写结果'
                        }
                        font='400 16px "PingFang SC"'
                        lineHeight={31}
                        typographyProps={{
                          color: 'text.secondary',
                          sx: {
                            lineHeight: 1.95,
                          },
                        }}
                      />
                    </Box>
                    {data.job.error_message ? <Alert severity="error">{data.job.error_message}</Alert> : null}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>

            <Grid size={{ xs: 12, xl: 3.2 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Stack spacing={2}>
                    <Typography variant="h6">Speaker 时间线</Typography>
                    {timelineSegments.length ? (
                      <Stack spacing={1.2}>
                        <Box
                          sx={{
                            position: 'relative',
                            height: 20,
                            borderRadius: 999,
                            overflow: 'hidden',
                            bgcolor: alpha('#cbd5e1', 0.34),
                          }}
                          data-testid="speaker-timeline-overview"
                        >
                          {timelineSegments.map((segment, index) => {
                            const left = ((segment.start_ms - timelineStartMs) / timelineDurationMs) * 100;
                            const width = Math.max(
                              ((segment.end_ms - segment.start_ms) / timelineDurationMs) * 100,
                              3,
                            );
                            const isFocused =
                              selectedSpeaker !== 'ALL' &&
                              (segment.speaker ?? '未标注说话人') === selectedSpeaker;
                            return (
                              <Box
                                key={`${segment.start_ms}-${segment.end_ms}-${index}`}
                                data-testid="speaker-timeline-segment"
                                sx={{
                                  position: 'absolute',
                                  left: `${left}%`,
                                  width: `${width}%`,
                                  top: 0,
                                  bottom: 0,
                                  bgcolor: isFocused ? 'primary.main' : 'secondary.main',
                                  opacity: isFocused || selectedSpeaker === 'ALL' ? 0.92 : 0.54,
                                }}
                              />
                            );
                          })}
                        </Box>
                        <Stack spacing={0.9}>
                          {timelineSegments.map((segment, index) => {
                            const speakerKey = segment.speaker ?? '未标注说话人';
                            return (
                              <Box
                                key={`${speakerKey}-${segment.start_ms}-${index}`}
                                sx={{
                                  p: 1.15,
                                  borderRadius: 3.5,
                                  bgcolor: alpha('#ffffff', 0.68),
                                  border: '1px solid',
                                  borderColor: alpha('#1c2431', 0.06),
                                }}
                                data-testid="speaker-timeline-row"
                              >
                                <Stack direction="row" justifyContent="space-between" spacing={2}>
                                  <Typography variant="body2" fontWeight={600}>
                                    {speakerAliases[segment.speaker ?? ''] || speakerKey}
                                  </Typography>
                                  <Typography variant="body2" color="text.secondary">
                                    {segment.start_ms}ms - {segment.end_ms}ms
                                  </Typography>
                                </Stack>
                              </Box>
                            );
                          })}
                        </Stack>
                      </Stack>
                    ) : (
                      <Alert severity="info">当前筛选条件下没有可展示的时间线。</Alert>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>

            <Grid size={{ xs: 12, xl: 4.6 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Stack spacing={2}>
                    <Typography variant="h6">分段结果</Typography>
                    {filteredSegments.length ? (
                      <Stack spacing={1.2}>
                        {filteredSegments.map((segment, index) => (
                          <Box
                            key={`${segment.start_ms}-${index}`}
                            sx={{
                              p: 1.5,
                              borderRadius: 4,
                              bgcolor: alpha('#ffffff', 0.72),
                              border: '1px solid',
                              borderColor:
                                selectedSpeaker !== 'ALL' && segment.speaker === selectedSpeaker
                                  ? alpha('#2f6fed', 0.18)
                                  : alpha('#1c2431', 0.06),
                            }}
                          >
                            <Stack spacing={1}>
                              <Stack direction="row" justifyContent="space-between" alignItems="center">
                                <Typography variant="body2" color="text.secondary">
                                  {segment.start_ms}ms - {segment.end_ms}ms
                                </Typography>
                                <Stack direction="row" spacing={1} alignItems="center">
                                  {typeof segment.confidence === 'number' ? (
                                    <Chip
                                      size="small"
                                      variant="outlined"
                                      label={`置信度 ${segment.confidence.toFixed(2)}`}
                                    />
                                  ) : null}
                                  <Typography variant="body2" fontWeight={700}>
                                    {speakerAliases[segment.speaker ?? ''] ||
                                      segment.speaker ||
                                      '未标注说话人'}
                                  </Typography>
                                </Stack>
                              </Stack>
                              <Divider />
                              <MeasuredPretextBlock
                                text={segment.text || '（该片段暂无文本）'}
                                font='400 15px "PingFang SC"'
                                lineHeight={28}
                                typographyProps={{
                                  sx: {
                                    textWrap: 'pretty',
                                  },
                                }}
                              />
                            </Stack>
                          </Box>
                        ))}
                      </Stack>
                    ) : (
                      <Alert severity="info">当前筛选条件下没有可展示的分段结果。</Alert>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
          </>
          ) : null}
        </Stack>
      ) : (
        <Alert severity="info">请输入有效任务 ID。</Alert>
      )}
    </PageSection>
  );
}
