import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useCallback, useState } from 'react';

import { fetchModels, loadModel, unloadModel } from '../../api/client';
import { modelStatusLabels, modelTaskLabels, providerLabels } from '../../api/types';
import type { GPUInfo, ModelInfoWithStatus } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';

interface GPUStatusProps {
  gpu: GPUInfo;
}

function GPUStatus({ gpu }: GPUStatusProps) {
  if (!gpu.cuda_available) {
    return (
      <Alert severity="warning">
        CUDA 不可用。请检查 GPU 驱动和 PyTorch。
      </Alert>
    );
  }

  const total = gpu.total_memory_mb ?? 0;
  const used = gpu.used_memory_mb ?? 0;
  const free = total - used;
  const percent = total > 0 ? Math.round((used / total) * 100) : 0;

  return (
    <Box
      sx={{
        p: 2,
        borderRadius: 4,
        bgcolor: alpha('#ffffff', 0.72),
        border: '1px solid',
        borderColor: alpha('#1c2431', 0.06),
      }}
    >
      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="body2" color="text.secondary">
          GPU:
        </Typography>
        <Typography fontWeight={700}>{gpu.name ?? '未知GPU'}</Typography>
        <Chip
          size="small"
          label={`显存: ${(free / 1024).toFixed(1)}GB / ${(total / 1024).toFixed(1)}GB (${percent}%)`}
          color={percent > 80 ? 'error' : percent > 60 ? 'warning' : 'default'}
          variant="outlined"
        />
      </Stack>
      <LinearProgress
        variant="determinate"
        value={percent}
        sx={{ mt: 1.5, height: 8, borderRadius: 4 }}
      />
    </Box>
  );
}

interface ModelCardProps {
  model: ModelInfoWithStatus;
  onLoad: (key: string) => void;
  onUnload: (key: string) => void;
  loading: boolean;
}

function ModelCard({ model, onLoad, onUnload, loading }: ModelCardProps) {
  const isLoaded = model.status === 'loaded';
  const isLoading = model.status === 'loading';
  const isFailed = model.status === 'load_failed';

  return (
    <Card
      sx={{
        transition: 'box-shadow 0.2s',
        '&:hover': {
          boxShadow: '0 4px 20px rgba(28,36,49,0.08)',
        },
      }}
    >
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
            <Stack spacing={0.5} flex={1}>
              <Typography variant="h6">{model.display_name}</Typography>
              <Typography color="text.secondary" fontSize="small">
                {providerLabels[model.provider] ?? model.provider} · {modelTaskLabels[model.task as keyof typeof modelTaskLabels]}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1} alignItems="center" flexShrink={0}>
              <Chip
                label={modelStatusLabels[model.status]}
                color={
                  isLoaded ? 'success' : isFailed ? 'error' : isLoading ? 'warning' : 'default'
                }
                size="small"
              />
              {model.experimental ? (
                <Chip label="实验性" color="warning" size="small" />
              ) : null}
            </Stack>
          </Stack>

          {isLoading && model.load_progress !== null && (
            <Box>
              <Stack direction="row" justifyContent="space-between" spacing={1} mb={0.5}>
                <Typography variant="body2" color="text.secondary">
                  加载进度
                </Typography>
                <Typography variant="body2" fontWeight={600}>
                  {Math.round(model.load_progress * 100)}%
                </Typography>
              </Stack>
              <LinearProgress variant="determinate" value={model.load_progress * 100} />
            </Box>
          )}

          {model.gpu_memory_mb !== null && (
            <Typography variant="body2" color="text.secondary">
              GPU 显存占用: {(model.gpu_memory_mb / 1024).toFixed(1)}GB
            </Typography>
          )}

          {model.error && (
            <Alert severity="error" sx={{ py: 0.5 }}>
              {model.error}
            </Alert>
          )}

          <Stack direction="row" spacing={1.5}>
            {isLoaded ? (
              <Button
                variant="outlined"
                color="warning"
                size="small"
                onClick={() => onUnload(model.key)}
                disabled={loading}
                startIcon={loading ? <CircularProgress size={14} /> : undefined}
              >
                卸载
              </Button>
            ) : (
              <Button
                variant="contained"
                size="small"
                onClick={() => onLoad(model.key)}
                disabled={loading || isLoading}
                startIcon={
                  isLoading ? <CircularProgress size={14} color="inherit" /> : undefined
                }
              >
                {isLoading ? '加载中' : '加载'}
              </Button>
            )}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

interface ModelListStatsProps {
  items: ModelInfoWithStatus[];
}

function ModelListStats({ items }: ModelListStatsProps) {
  const loadedCount = items.filter((m) => m.status === 'loaded').length;
  const unloadedCount = items.filter((m) => m.status === 'unloaded').length;
  const loadingCount = items.filter((m) => m.status === 'loading').length;
  const failedCount = items.filter((m) => m.status === 'load_failed').length;

  return (
    <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
      <Typography variant="body2" color="text.secondary">
        已加载 {loadedCount} 个
      </Typography>
      <Typography variant="body2" color="text.secondary">
        未加载 {unloadedCount} 个
      </Typography>
      {loadingCount > 0 && (
        <Typography variant="body2" color="warning.main">
          加载中 {loadingCount} 个
        </Typography>
      )}
      {failedCount > 0 && (
        <Typography variant="body2" color="error.main">
          失败 {failedCount} 个
        </Typography>
      )}
    </Stack>
  );
}

export function ModelManagementPage() {
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const { data, loading, error: fetchError, reload } = useAsyncData(() => fetchModels(), []);

  const items = data?.items ?? [];
  const gpu = data?.gpu ?? null;

  const handleLoad = useCallback(
    async (modelKey: string) => {
      setLoadingKeys((prev) => new Set(prev).add(modelKey));
      setError(null);
      try {
        await loadModel(modelKey);
        reload();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        setLoadingKeys((prev) => {
          const next = new Set(prev);
          next.delete(modelKey);
          return next;
        });
      }
    },
    [reload],
  );

  const handleUnload = useCallback(
    async (modelKey: string) => {
      setLoadingKeys((prev) => new Set(prev).add(modelKey));
      setError(null);
      try {
        await unloadModel(modelKey);
        reload();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '卸载失败');
      } finally {
        setLoadingKeys((prev) => {
          const next = new Set(prev);
          next.delete(modelKey);
          return next;
        });
      }
    },
    [reload],
  );

  const isLoadingKey = useCallback(
    (key: string) => loadingKeys.has(key),
    [loadingKeys],
  );

  const loadedCount = items.filter((item) => item.status === 'loaded').length;
  const queueingCount = items.filter((item) => item.status === 'loading').length;
  const failedCount = items.filter((item) => item.status === 'load_failed').length;

  return (
    <PageSection
      title="模型"
      description="加载、卸载、显存、错误。"
      loading={loading}
      error={fetchError}
      actions={
        <Button variant="outlined" onClick={reload}>
          刷新
        </Button>
      }
    >
      <Stack spacing={3}>
        {error && (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <Card>
          <CardContent>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip size="small" color="success" label={`已加载 ${loadedCount}`} />
              <Chip size="small" color="warning" label={`加载中 ${queueingCount}`} />
              <Chip size="small" color={failedCount ? 'error' : 'default'} label={`失败 ${failedCount}`} />
              {gpu ? (
                <Chip
                  size="small"
                  variant="outlined"
                  label={gpu.cuda_available ? `${gpu.name ?? 'GPU'} 已连接` : 'CUDA 未就绪'}
                />
              ) : null}
            </Stack>
          </CardContent>
        </Card>

        {gpu && <GPUStatus gpu={gpu} />}

        {items.length > 0 && <ModelListStats items={items} />}

        <Grid container spacing={2.5}>
          {items.map((model) => (
            <Grid key={model.key} size={{ xs: 12, md: 6 }}>
              <ModelCard
                model={model}
                onLoad={handleLoad}
                onUnload={handleUnload}
                loading={isLoadingKey(model.key)}
              />
            </Grid>
          ))}
        </Grid>

        {items.length === 0 && !loading && (
          <Typography color="text.secondary" textAlign="center" py={4}>
            未检测到任何已注册的模型。
          </Typography>
        )}
      </Stack>
    </PageSection>
  );
}
