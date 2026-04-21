import { Chip } from '@mui/material';
import type { JobStatus } from '../api/types';
import { jobStatusLabels } from '../api/types';

const colorMap: Record<JobStatus, 'default' | 'warning' | 'info' | 'success' | 'error'> = {
  pending: 'default',
  queued: 'warning',
  running: 'info',
  succeeded: 'success',
  failed: 'error',
};

export function StatusChip({ status }: { status: JobStatus }) {
  return <Chip size="small" color={colorMap[status]} label={jobStatusLabels[status]} />;
}
