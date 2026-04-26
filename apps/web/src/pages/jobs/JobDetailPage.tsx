import AccessTimeRounded from '@mui/icons-material/AccessTimeRounded';
import ArticleRounded from '@mui/icons-material/ArticleRounded';
import ContentCopyRounded from '@mui/icons-material/ContentCopyRounded';
import DownloadRounded from '@mui/icons-material/DownloadRounded';
import GraphicEqRounded from '@mui/icons-material/GraphicEqRounded';
import GroupsRounded from '@mui/icons-material/GroupsRounded';
import ReplayRounded from '@mui/icons-material/ReplayRounded';
import SegmentRounded from '@mui/icons-material/SegmentRounded';
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
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { fetchSpeakerAliases, fetchTranscript } from '../../api/client';
import {
  formatDateTime,
  jobTypeLabels,
  type Segment,
  type TranscriptResult,
} from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';
import { MeasuredPretextBlock } from '../../components/PretextText';
import { StatCard } from '../../components/StatCard';
import { StatusChip } from '../../components/StatusChip';

const SPEAKER_MAPPING_STORAGE_KEY = 'voiceprint-job-speaker-mappings';
const POLL_INTERVAL_MS = 3000;
const UNLABELED_SPEAKER_KEY = '__unlabeled__';
const UNLABELED_SPEAKER_LABEL = '未标注说话人';
const PANEL_MAX_HEIGHT = 720;

const SPEAKER_PALETTE = [
  '#2f6fed', '#16a34a', '#ea580c', '#7c3aed', '#0891b2',
  '#be185d', '#ca8a04', '#4f46e5', '#059669', '#dc2626',
];

function speakerColor(index: number): string {
  return SPEAKER_PALETTE[index % SPEAKER_PALETTE.length];
}

type SpeakerMappingStore = Record<string, Record<string, string>>;
type ExportSpeakerGroup = {
  speaker: string | null;
  displaySpeaker: string;
  durationMs: number;
  segments: Segment[];
} | null;
type SegmentWithDisplay = Segment & {
  speakerKey: string;
  displaySpeaker: string;
  rawSpeaker: string | null;
};

type SpeakerGroup = {
  speaker: string;
  displaySpeaker: string;
  rawSpeaker: string | null;
  durationMs: number;
  avgConfidence: number | null;
  segments: SegmentWithDisplay[];
};

function sanitizeSegment(segment: Segment): Segment {
  return {
    start_ms: segment.start_ms,
    end_ms: segment.end_ms,
    text: segment.text,
    speaker: segment.speaker ?? null,
    confidence: segment.confidence ?? null,
  };
}

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
          segments: filteredSegments.map(sanitizeSegment),
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

function getSegmentSpeakerKey(segment: Segment) {
  return segment.speaker?.trim() || UNLABELED_SPEAKER_KEY;
}

function formatDuration(durationMs: number) {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function formatTimelineRange(startMs: number, endMs: number) {
  return `${formatDuration(startMs)} - ${formatDuration(endMs)}`;
}

function TranscriptStatGrid({
  segmentCount,
  speakerCount,
  totalDurationMs,
  alignmentSource,
}: {
  segmentCount: number;
  speakerCount: number;
  totalDurationMs: number;
  alignmentSource: string;
}) {
  return (
    <Grid container spacing={1.5}>
      <Grid size={{ xs: 6, md: 3 }}>
        <StatCard label="总时长" value={formatDuration(totalDurationMs)} icon={<AccessTimeRounded fontSize="small" />} />
      </Grid>
      <Grid size={{ xs: 6, md: 3 }}>
        <StatCard label="分段数" value={segmentCount} icon={<SegmentRounded fontSize="small" />} color="success" />
      </Grid>
      <Grid size={{ xs: 6, md: 3 }}>
        <StatCard label="说话人数" value={speakerCount} icon={<GroupsRounded fontSize="small" />} color="warning" />
      </Grid>
      <Grid size={{ xs: 6, md: 3 }}>
        <StatCard label="对齐来源" value={alignmentSource} icon={<GraphicEqRounded fontSize="small" />} color="primary" />
      </Grid>
    </Grid>
  );
}

function ScrollCard({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={1.6}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1.2}
            justifyContent="space-between"
            alignItems={{ xs: 'flex-start', sm: 'center' }}
          >
            <Stack spacing={0.35}>
              <Typography variant="h6">{title}</Typography>
              {subtitle ? (
                <Typography variant="body2" color="text.secondary">
                  {subtitle}
                </Typography>
              ) : null}
            </Stack>
            {actions}
          </Stack>
          {children}
        </Stack>
      </CardContent>
    </Card>
  );
}

export function JobDetailPage() {
  const navigate = useNavigate();
  const { jobId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const { data, loading, error, reload } = useAsyncData(
    () => fetchTranscript(jobId),
    [jobId],
    {
      enabled: true,
      intervalMs: POLL_INTERVAL_MS,
      pauseWhenHidden: true,
      stopWhen: (result) => {
        const status = result?.job?.status;
        return status === 'succeeded' || status === 'failed';
      },
    },
  );
  const [feedback, setFeedback] = useState<string | null>(null);
  const [speakerAliases, setSpeakerAliases] = useState<Record<string, string>>({});
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>('ALL');
  const isProcessing =
    data?.job?.status === 'pending' || data?.job?.status === 'queued' || data?.job?.status === 'running';
  const isFailed = data?.job?.status === 'failed';

  useEffect(() => {
    if (!jobId || typeof window === 'undefined') {
      setSpeakerAliases({});
      return;
    }
    let active = true;
    fetchSpeakerAliases(jobId)
      .then((response) => {
        if (active && response.aliases && Object.keys(response.aliases).length > 0) {
          setSpeakerAliases(response.aliases);
        } else if (active) {
          try {
            const raw = window.localStorage.getItem(SPEAKER_MAPPING_STORAGE_KEY);
            if (raw) {
              const store = JSON.parse(raw) as SpeakerMappingStore;
              setSpeakerAliases(store[jobId] ?? {});
            }
          } catch {
            setSpeakerAliases({});
          }
        }
      })
      .catch(() => {
        if (!active) return;
        try {
          const raw = window.localStorage.getItem(SPEAKER_MAPPING_STORAGE_KEY);
          if (raw) {
            const store = JSON.parse(raw) as SpeakerMappingStore;
            setSpeakerAliases(store[jobId] ?? {});
          } else {
            setSpeakerAliases({});
          }
        } catch {
          setSpeakerAliases({});
        }
      });
    return () => {
      active = false;
    };
  }, [jobId, searchParams]);

  const segments = data?.transcript?.segments ?? [];
  const transcriptMetadata = data?.transcript?.metadata ?? null;
  const displayTimeline =
    transcriptMetadata?.timelines.find((timeline) => timeline.source === 'display') ?? null;
  const exclusiveTimeline =
    transcriptMetadata?.timelines.find((timeline) => timeline.source === 'exclusive') ?? null;
  const regularTimeline =
    transcriptMetadata?.timelines.find((timeline) => timeline.source === 'regular') ?? null;

  const displaySegments = useMemo<SegmentWithDisplay[]>(() => {
    const speakerNames = new Map<string, string>();
    let nextSpeakerIndex = 1;
    return segments.map((segment) => {
      const speakerKey = getSegmentSpeakerKey(segment);
      if (!speakerNames.has(speakerKey)) {
        speakerNames.set(
          speakerKey,
          speakerKey === UNLABELED_SPEAKER_KEY ? UNLABELED_SPEAKER_LABEL : `Speaker ${nextSpeakerIndex}`,
        );
        if (speakerKey !== UNLABELED_SPEAKER_KEY) {
          nextSpeakerIndex += 1;
        }
      }
      const rawSpeaker = segment.speaker?.trim() || null;
      return {
        ...segment,
        speakerKey,
        rawSpeaker,
        displaySpeaker:
          speakerAliases[speakerKey] ||
          (rawSpeaker ? speakerAliases[rawSpeaker] : undefined) ||
          speakerNames.get(speakerKey) ||
          UNLABELED_SPEAKER_LABEL,
      };
    });
  }, [segments, speakerAliases]);

  const speakerGroups = useMemo<SpeakerGroup[]>(() => {
    const groups = new Map<
      string,
      { speaker: string; segments: SegmentWithDisplay[]; durationMs: number; confidenceValues: number[] }
    >();
    displaySegments.forEach((segment) => {
      const group = groups.get(segment.speakerKey) ?? {
        speaker: segment.speakerKey,
        segments: [],
        durationMs: 0,
        confidenceValues: [],
      };
      group.segments.push(segment);
      group.durationMs += Math.max(0, segment.end_ms - segment.start_ms);
      if (typeof segment.confidence === 'number') {
        group.confidenceValues.push(segment.confidence);
      }
      groups.set(segment.speakerKey, group);
    });
    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        displaySpeaker: group.segments[0]?.displaySpeaker ?? group.speaker,
        rawSpeaker: group.segments[0]?.rawSpeaker ?? null,
        avgConfidence: group.confidenceValues.length
          ? group.confidenceValues.reduce((sum, item) => sum + item, 0) / group.confidenceValues.length
          : null,
      }))
      .sort((left, right) => right.durationMs - left.durationMs);
  }, [displaySegments]);

  const speakerColorMap = useMemo(() => {
    const map = new Map<string, string>();
    speakerGroups.forEach((group, index) => {
      map.set(group.speaker, speakerColor(index));
    });
    return map;
  }, [speakerGroups]);

  const filteredSegments = useMemo(
    () =>
      selectedSpeaker === 'ALL'
        ? displaySegments
        : displaySegments.filter((segment) => segment.speakerKey === selectedSpeaker),
    [displaySegments, selectedSpeaker],
  );

  const selectedSpeakerGroup = useMemo<ExportSpeakerGroup>(() => {
    const group = speakerGroups.find((item) => item.speaker === selectedSpeaker);
    if (!group) {
      return null;
    }
    return {
      speaker: group.rawSpeaker,
      displaySpeaker: group.displaySpeaker,
      durationMs: group.durationMs,
      segments: group.segments.map(sanitizeSegment),
    };
  }, [selectedSpeaker, speakerGroups]);

  const timelineSegments = useMemo(
    () => filteredSegments.filter((segment) => segment.end_ms > segment.start_ms),
    [filteredSegments],
  );
  const timelineStartMs = timelineSegments.length ? timelineSegments[0].start_ms : 0;
  const timelineEndMs = timelineSegments.length
    ? timelineSegments[timelineSegments.length - 1].end_ms
    : timelineStartMs;
  const timelineDurationMs = Math.max(1, timelineEndMs - timelineStartMs);
  const totalDurationMs = useMemo(
    () =>
      displaySegments.reduce(
        (sum, segment) => sum + Math.max(0, segment.end_ms - segment.start_ms),
        0,
      ),
    [displaySegments],
  );
  const fullTranscriptText = useMemo(
    () =>
      selectedSpeakerGroup
        ? selectedSpeakerGroup.segments.map((segment) => segment.text).filter(Boolean).join(' ')
        : data?.transcript?.text ?? '暂无转写结果',
    [data?.transcript?.text, selectedSpeakerGroup],
  );

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
    const body = filteredSegments.map((segment) => {
      const speaker = segment.displaySpeaker;
      return `[${formatTimelineRange(segment.start_ms, segment.end_ms)}] ${speaker}: ${segment.text || '（该片段暂无文本）'}`;
    });
    return [...header, '', fullTranscriptText, '', ...body].join('\n');
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(buildCopyText());
      setFeedback('当前结果已复制到剪贴板。');
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
    link.download = selectedSpeakerGroup?.speaker
      ? `${data.job.job_id}-${selectedSpeakerGroup.speaker}.json`
      : `${data.job.job_id}.json`;
    link.click();
    window.URL.revokeObjectURL(url);
    setFeedback(selectedSpeakerGroup ? '当前说话人结果已导出为 JSON。' : '任务结果已导出为 JSON。');
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
      compact
      title={data?.job?.asset_name ?? '结果'}
      description={
        data?.job ? `${jobTypeLabels[data.job.job_type]} · 更新时间 ${formatDateTime(data.job.updated_at)}` : undefined
      }
      loading={loading}
      error={error}
      actions={
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button variant="outlined" onClick={reload}>刷新</Button>
          <Button variant="outlined" startIcon={<ContentCopyRounded />} onClick={handleCopy} disabled={!data?.job}>复制结果</Button>
          <Button variant="outlined" startIcon={<DownloadRounded />} onClick={handleExport} disabled={!data?.job}>导出 JSON</Button>
          <Button variant="outlined" startIcon={<ArticleRounded />} onClick={() => navigate(`/minutes/${jobId}`)} disabled={!data?.job}>会议纪要</Button>
          <Button variant="contained" startIcon={<ReplayRounded />} onClick={handleRetry} disabled={!data?.job}>快速重跑</Button>
        </Stack>
      }
    >
      {data?.job ? (
        <Stack spacing={2.2}>
          {feedback ? (
            <Alert severity="success" onClose={() => setFeedback(null)}>
              {feedback}
            </Alert>
          ) : null}

          {isProcessing ? (
            <Card>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                    spacing={1}
                  >
                    <Stack spacing={0.3}>
                      <Typography variant="h6">任务正在处理中</Typography>
                      <Typography variant="body2" color="text.secondary">
                        后端会自动刷新结果，完成后显示全文、说话人时间线与分段内容。
                      </Typography>
                    </Stack>
                    <StatusChip status={data.job.status} />
                  </Stack>
                  <LinearProgress />
                </Stack>
              </CardContent>
            </Card>
          ) : null}

          {isFailed ? (
            <Alert severity="error">
              {data.job.error_message || '任务执行失败，请检查模型、GPU、音频格式或重新发起任务。'}
            </Alert>
          ) : null}

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <StatusChip status={data.job.status} />
            <Chip size="small" variant="outlined" label={`语言 ${data.transcript?.language ?? '未标注'}`} />
            <Chip size="small" variant="outlined" label={`Speaker ${speakerGroups.length || 0}`} />
            <Chip
              size="small"
              variant="outlined"
              label={transcriptMetadata?.alignment_source === 'exclusive' ? '对齐 Exclusive' : '对齐 Regular'}
            />
            {exclusiveTimeline ? <Chip size="small" variant="outlined" label={`exclusive ${exclusiveTimeline.segments.length} 段`} /> : null}
            {displayTimeline ? <Chip size="small" variant="outlined" label={`display ${displayTimeline.segments.length} 段`} /> : null}
            {regularTimeline ? <Chip size="small" variant="outlined" label={`regular ${regularTimeline.segments.length} 段`} /> : null}
          </Stack>

          <TranscriptStatGrid
            segmentCount={segments.length}
            speakerCount={speakerGroups.length}
            totalDurationMs={totalDurationMs}
            alignmentSource={transcriptMetadata?.alignment_source === 'exclusive' ? 'Exclusive' : 'Regular'}
          />

          <Grid container spacing={2.2}>
            <Grid size={{ xs: 12, lg: 8 }}>
              <Stack spacing={2.2}>
                <ScrollCard
                  title={selectedSpeakerGroup ? `${selectedSpeakerGroup.displaySpeaker} 全文` : '全文结果'}
                  subtitle={
                    selectedSpeakerGroup
                      ? `${selectedSpeakerGroup.segments.length} 段 · ${formatDuration(selectedSpeakerGroup.durationMs)}`
                      : `完整转录文本 · ${segments.length} 段`
                  }
                >
                  <Box
                    sx={{
                      px: { xs: 1.2, md: 2 },
                      py: 1.6,
                      maxHeight: PANEL_MAX_HEIGHT,
                      overflow: 'auto',
                      bgcolor: alpha('#fafbfc', 0.92),
                      border: '1px solid',
                      borderColor: alpha('#1c2431', 0.06),
                      borderRadius: 3,
                    }}
                  >
                    <MeasuredPretextBlock
                      text={fullTranscriptText}
                      font='400 16px "PingFang SC"'
                      lineHeight={28}
                      typographyProps={{
                        color: 'text.primary',
                        sx: {
                          lineHeight: 1.75,
                          maxWidth: 860,
                        },
                      }}
                    />
                  </Box>
                </ScrollCard>

                <ScrollCard
                  title="分段结果"
                  subtitle={selectedSpeakerGroup ? `仅显示 ${selectedSpeakerGroup.displaySpeaker}` : '按时间顺序展示全部分段'}
                  actions={
                    <Chip
                      size="small"
                      label={selectedSpeakerGroup ? `${selectedSpeakerGroup.segments.length} 条` : `${filteredSegments.length} 条`}
                      variant="outlined"
                    />
                  }
                >
                  {filteredSegments.length ? (
                    <Box sx={{ maxHeight: PANEL_MAX_HEIGHT, overflow: 'auto' }}>
                      <Stack spacing={1}>
                        {filteredSegments.map((segment, index) => (
                          <Box
                            key={`${segment.start_ms}-${segment.end_ms}-${index}`}
                            sx={{
                              px: 1.4,
                              py: 1.2,
                              borderRadius: 3,
                              bgcolor: alpha('#ffffff', 0.74),
                              border: '1px solid',
                              borderColor:
                                selectedSpeaker !== 'ALL' && segment.speakerKey === selectedSpeaker
                                  ? alpha('#2f6fed', 0.18)
                                  : alpha('#1c2431', 0.06),
                              borderLeft: `3px solid ${alpha(speakerColorMap.get(segment.speakerKey) ?? '#64748b', 0.5)}`,
                            }}
                          >
                            <Stack spacing={0.85}>
                              <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1}>
                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                                  <Typography variant="body2" color="text.secondary">
                                    {formatTimelineRange(segment.start_ms, segment.end_ms)}
                                  </Typography>
                                  <Chip size="small" label={segment.displaySpeaker} sx={{ bgcolor: alpha(speakerColorMap.get(segment.speakerKey) ?? '#64748b', 0.12), color: speakerColorMap.get(segment.speakerKey) ?? '#64748b', fontWeight: 600 }} />
                                  {typeof segment.confidence === 'number' ? (
                                    <Chip size="small" variant="outlined" label={`置信度 ${segment.confidence.toFixed(2)}`} />
                                  ) : null}
                                </Stack>
                              </Stack>
                              <Typography variant="body1" sx={{ lineHeight: 1.72, textWrap: 'pretty' }}>
                                {segment.text || '（该片段暂无文本）'}
                              </Typography>
                            </Stack>
                          </Box>
                        ))}
                      </Stack>
                    </Box>
                  ) : (
                    <Alert severity="info">当前筛选条件下暂无分段结果。</Alert>
                  )}
                </ScrollCard>
              </Stack>
            </Grid>

            <Grid size={{ xs: 12, lg: 4 }}>
              <Stack spacing={2.2} sx={{ position: { lg: 'sticky' }, top: { lg: 24 } }}>
                <ScrollCard title="Speaker" subtitle="筛选说话人并快速查看摘要与声纹入口">
                  <Stack spacing={1.2}>
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
                      <Box sx={{ maxHeight: 360, overflow: 'auto' }}>
                        <Stack spacing={1}>
                          {speakerGroups.map((group) => (
                            <Box
                              key={group.speaker}
                              sx={{
                                p: 1.25,
                                borderRadius: 3,
                                bgcolor:
                                  selectedSpeaker === group.speaker ? alpha('#2f6fed', 0.06) : alpha('#ffffff', 0.68),
                                border: '1px solid',
                                borderColor:
                                  selectedSpeaker === group.speaker ? alpha('#2f6fed', 0.18) : alpha('#1c2431', 0.06),
                              }}
                            >
                              <Stack spacing={0.7}>
                                <Stack direction="row" justifyContent="space-between" spacing={1}>
                                  <Typography fontWeight={700}>{group.displaySpeaker}</Typography>
                                  <Chip size="small" label={`${group.segments.length} 段`} />
                                </Stack>
                                {group.rawSpeaker && group.displaySpeaker !== group.rawSpeaker ? (
                                  <Typography variant="body2" color="text.secondary">原标签 {group.rawSpeaker}</Typography>
                                ) : null}
                                <Typography variant="body2" color="text.secondary">
                                  总时长 {formatDuration(group.durationMs)} · 平均置信度 {group.avgConfidence !== null ? group.avgConfidence.toFixed(2) : '—'}
                                </Typography>
                                <Typography variant="body2" sx={{ lineHeight: 1.6 }} color="text.secondary">
                                  {group.segments.slice(0, 1).map((segment) => segment.text).join(' ') || '暂无文本'}
                                </Typography>
                                {data.job.asset_name ? (
                                  <Button
                                    size="small"
                                    variant="text"
                                    sx={{ alignSelf: 'flex-start', px: 0 }}
                                    onClick={() =>
                                      navigate(
                                        `/voiceprints?probe=${encodeURIComponent(
                                          data.job.asset_name ?? '',
                                        )}&speaker=${encodeURIComponent(group.rawSpeaker || group.speaker)}&jobId=${encodeURIComponent(jobId)}`,
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
                      </Box>
                    ) : (
                      <Alert severity="info">当前还没有可复核的 speaker 聚合结果。</Alert>
                    )}
                  </Stack>
                </ScrollCard>

                <ScrollCard title="Speaker 时间线" subtitle="按当前筛选显示时间分布">
                  {timelineSegments.length ? (
                    <Stack spacing={1.2}>
                      <Box
                        sx={{
                          position: 'relative',
                          height: 18,
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
                            2.4,
                          );
                          const isFocused = selectedSpeaker !== 'ALL' && segment.speakerKey === selectedSpeaker;
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
                                opacity: isFocused || selectedSpeaker === 'ALL' ? 0.92 : 0.56,
                              }}
                            />
                          );
                        })}
                      </Box>
                      <Box sx={{ maxHeight: 320, overflow: 'auto' }}>
                        <Stack spacing={0.85}>
                          {timelineSegments.map((segment, index) => (
                            <Box
                              key={`${segment.speakerKey}-${segment.start_ms}-${index}`}
                              sx={{
                                px: 1.2,
                                py: 1,
                                borderRadius: 3,
                                bgcolor: alpha('#ffffff', 0.68),
                                border: '1px solid',
                                borderColor: alpha('#1c2431', 0.06),
                              }}
                              data-testid="speaker-timeline-row"
                            >
                              <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                                <Typography variant="body2" fontWeight={600}>{segment.displaySpeaker}</Typography>
                                <Typography variant="body2" color="text.secondary">{formatTimelineRange(segment.start_ms, segment.end_ms)}</Typography>
                              </Stack>
                            </Box>
                          ))}
                        </Stack>
                      </Box>
                    </Stack>
                  ) : (
                    <Alert severity="info">当前筛选条件下没有可展示的时间线。</Alert>
                  )}
                </ScrollCard>
              </Stack>
            </Grid>
          </Grid>
        </Stack>
      ) : null}
    </PageSection>
  );
}
