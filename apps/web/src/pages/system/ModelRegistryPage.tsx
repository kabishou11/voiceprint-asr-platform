import {
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  Stack,
  Typography,
} from '@mui/material';

import {
  fetchModels,
} from '../../api/client';
import {
  modelAvailabilityLabels,
  modelTaskLabels,
  providerLabels,
} from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { PageSection } from '../../components/PageSection';

export function ModelRegistryPage() {
  const { data, loading, error, reload } = useAsyncData(() => fetchModels(), []);

  return (
    <PageSection
      title="模型状态"
      description="查看当前平台已接入模型、服务用途和可用状态。"
      loading={loading}
      error={error}
      actions={
        <Button variant="outlined" onClick={reload}>
          刷新
        </Button>
      }
    >
      <Grid container spacing={3}>
        {(data?.items ?? []).map((item) => (
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
                      <Chip label={modelAvailabilityLabels[item.availability]} color={item.availability === 'available' ? 'success' : 'default'} />
                      {item.experimental ? <Chip label="实验性" color="warning" /> : null}
                    </Stack>
                  </Stack>
                  <Grid container spacing={2}>
                    {[
                      { label: '模型标识', value: item.key },
                      { label: '服务提供方', value: providerLabels[item.provider] ?? item.provider },
                      { label: '适用能力', value: modelTaskLabels[item.task] },
                    ].map((field) => (
                      <Grid key={field.label} size={{ xs: 12, sm: 4 }}>
                        <Card variant="outlined" sx={{ borderRadius: 4 }}>
                          <CardContent>
                            <Typography variant="body2" color="text.secondary">
                              {field.label}
                            </Typography>
                            <Typography sx={{ mt: 1, fontWeight: 700 }}>{field.value}</Typography>
                          </CardContent>
                        </Card>
                      </Grid>
                    ))}
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
