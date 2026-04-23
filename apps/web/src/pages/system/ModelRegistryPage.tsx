import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  Stack,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';

import { fetchModels } from '../../api/client';
import {
  modelAvailabilityLabels,
  modelTaskLabels,
  providerLabels,
} from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';
import { BalancedPretextText, MeasuredPretextBlock } from '../../components/PretextText';

function MetricBlock({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <Box
      sx={{
        p: 1.6,
        borderRadius: 4,
        bgcolor: alpha('#ffffff', 0.72),
        border: '1px solid',
        borderColor: alpha('#1c2431', 0.06),
      }}
    >
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography sx={{ mt: 1, fontWeight: 700 }}>{value}</Typography>
    </Box>
  );
}

export function ModelRegistryPage() {
  const { data, loading, error, reload } = useAsyncData(() => fetchModels(), []);
  const items = data?.items ?? [];
  const unavailableItems = items.filter((item) => item.availability === 'unavailable');
  const unavailableCount = unavailableItems.length;
  const pyannoteUnavailable = unavailableItems.some((item) => item.key === 'pyannote-community-1');
  const asrUnavailable = unavailableItems.some((item) => item.key === 'funasr-nano');
  const threeDSpeakerReady = items.some(
    (item) => item.key === '3dspeaker-diarization' && item.availability === 'available',
  );
  const voiceprintReady = items.some(
    (item) => item.key === '3dspeaker-embedding' && item.availability === 'available',
  );
  const availableCount = items.filter((item) => item.availability === 'available').length;

  return (
    <PageSection
      title="模型状态与本地推理边界"
      description="这里不再只是列模型清单，而是明确当前哪些能力已经进入真实本地 GPU 路径，哪些能力仍处于离线权重或运行时约束之外。"
      loading={loading}
      error={error}
      actions={
        <Button variant="outlined" onClick={reload}>
          刷新
        </Button>
      }
    >
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, xl: 7.5 }}>
          <Card>
            <CardContent>
              <Stack spacing={2.2}>
                <BalancedPretextText
                  text="当前平台已把本地模型、CUDA 运行时与任务链路绑定成一套真实可用的推理体系"
                  font='500 40px "Iowan Old Style"'
                  lineHeight={48}
                  targetLines={2}
                  minWidth={360}
                  maxWidth={760}
                  typographyProps={{
                    variant: 'h4',
                    sx: {
                      maxWidth: 760,
                    },
                  }}
                />
                <MeasuredPretextBlock
                  text="模型状态页现在更强调真实可用性而不是配置存在性。只有当本地模型文件、依赖和 CUDA 运行时同时满足时，任务工作台才会允许进入高精度推理路径。"
                  font='400 16px "PingFang SC"'
                  lineHeight={30}
                  typographyProps={{
                    color: 'text.secondary',
                    sx: {
                      maxWidth: 760,
                      lineHeight: 1.85,
                    },
                  }}
                />
                <Grid container spacing={1.5}>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <MetricBlock label="模型总数" value={String(items.length)} />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <MetricBlock label="已就绪" value={String(availableCount)} />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <MetricBlock label="未就绪" value={String(unavailableCount)} />
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <MetricBlock
                      label="主链路状态"
                      value={threeDSpeakerReady && !asrUnavailable ? 'GPU Ready' : '待补齐'}
                    />
                  </Grid>
                </Grid>
                {unavailableCount > 0 ? (
                  <Alert severity="warning">
                    当前有 {unavailableCount} 个模型未进入真实本地推理路径。系统会只启用已就绪模型，不再把空目录当作可用模型。
                  </Alert>
                ) : null}
                {asrUnavailable ? (
                  <Alert severity="error">
                    当前高精度推理运行时未就绪。常见原因是项目环境只安装了 CPU 版 `torch`，即使机器上存在 NVIDIA 显卡和驱动，模型也不会进入真实 CUDA 推理。
                  </Alert>
                ) : (
                  <Alert severity="success">
                    当前项目运行时已识别到 CUDA GPU，高精度转写链路已进入真实 GPU 推理模式。
                  </Alert>
                )}
                {threeDSpeakerReady || voiceprintReady ? (
                  <Alert severity="success">
                    3D-Speaker 本地模型已就绪，当前多人转写主链路与声纹能力可以走真实本地推理；最小实跑已验证通过。
                  </Alert>
                ) : null}
                {pyannoteUnavailable ? (
                  <Alert severity="info">
                    `pyannote-community-1` 仍未补齐。该模型来自 Hugging Face 的 gated repo，需要有权限的 token 才能下载完整离线包；在此之前，复杂重叠说话增强不会启用。
                  </Alert>
                ) : null}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, xl: 4.5 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Stack spacing={1.8}>
                <Typography variant="h6">能力提示</Typography>
                {[
                  {
                    title: 'ASR',
                    desc: asrUnavailable
                      ? '当前还不能进入真实高精度转写。'
                      : 'FunASR 已在本地 GPU 上进入真实推理路径。',
                    active: !asrUnavailable,
                  },
                  {
                    title: 'Diarization',
                    desc: threeDSpeakerReady
                      ? '3D-Speaker + FSMN-VAD 已被工作台主路径启用。'
                      : '说话人分离仍缺本地模型或运行时。',
                    active: threeDSpeakerReady,
                  },
                  {
                    title: 'Voiceprint',
                    desc: voiceprintReady
                      ? '声纹识别和验证可与多人链路共享运行时。'
                      : '声纹推理尚未进入真实本地路径。',
                    active: voiceprintReady,
                  },
                  {
                    title: 'Overlap refine',
                    desc: pyannoteUnavailable
                      ? 'pyannote 复杂重叠增强当前仍受离线权重权限限制。'
                      : 'pyannote 已可作为复杂场景增强路径。',
                    active: !pyannoteUnavailable,
                  },
                ].map((item) => (
                  <Box
                    key={item.title}
                    sx={{
                      p: 1.45,
                      borderRadius: 4,
                      bgcolor: alpha('#ffffff', 0.7),
                      border: '1px solid',
                      borderColor: alpha('#1c2431', 0.06),
                    }}
                  >
                    <Stack spacing={0.8}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Chip
                          size="small"
                          label={item.active ? '已就绪' : '未就绪'}
                          color={item.active ? 'success' : 'default'}
                        />
                        <Typography fontWeight={700}>{item.title}</Typography>
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {item.desc}
                      </Typography>
                    </Stack>
                  </Box>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {items.map((item) => (
          <Grid key={item.key} size={{ xs: 12, md: 6 }}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Stack spacing={2}>
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                    <Stack spacing={0.5}>
                      <Typography variant="h6">{item.display_name}</Typography>
                      <Typography color="text.secondary">
                        {providerLabels[item.provider] ?? item.provider} · {modelTaskLabels[item.task]}
                      </Typography>
                    </Stack>
                    <Stack direction="row" spacing={1}>
                      <Chip
                        label={modelAvailabilityLabels[item.availability]}
                        color={
                          item.availability === 'available'
                            ? 'success'
                            : item.availability === 'unavailable'
                              ? 'error'
                              : 'default'
                        }
                      />
                      {item.experimental ? <Chip label="实验性" color="warning" /> : null}
                    </Stack>
                  </Stack>
                  <Grid container spacing={1.25}>
                    <Grid size={{ xs: 12, sm: 4 }}>
                      <MetricBlock label="模型标识" value={item.key} />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 4 }}>
                      <MetricBlock
                        label="服务提供方"
                        value={providerLabels[item.provider] ?? item.provider}
                      />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 4 }}>
                      <MetricBlock label="适用能力" value={modelTaskLabels[item.task]} />
                    </Grid>
                  </Grid>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </PageSection>
  );
}
