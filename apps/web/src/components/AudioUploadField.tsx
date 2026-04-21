import AudioFileRounded from '@mui/icons-material/AudioFileRounded';
import UploadFileRounded from '@mui/icons-material/UploadFileRounded';
import {
  Alert,
  Box,
  Button,
  Stack,
  Typography,
} from '@mui/material';
import { useId, useRef } from 'react';

interface AudioUploadFieldProps {
  accept?: string;
  disabled?: boolean;
  error?: string | null;
  fileName?: string | null;
  helperText?: string;
  label: string;
  onChange: (file: File | null) => void;
}

export function AudioUploadField({
  accept = '.wav,.m4a,.mp3,.flac,audio/*',
  disabled = false,
  error,
  fileName,
  helperText,
  label,
  onChange,
}: AudioUploadFieldProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <Stack spacing={1.25}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Box
        sx={{
          border: '1px dashed',
          borderColor: error ? 'error.main' : 'divider',
          borderRadius: 4,
          p: 2,
          bgcolor: 'background.default',
        }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ xs: 'stretch', sm: 'center' }}>
          <Button
            component="label"
            htmlFor={inputId}
            variant="outlined"
            startIcon={<UploadFileRounded />}
            disabled={disabled}
          >
            选择音频
          </Button>
          <input
            id={inputId}
            ref={inputRef}
            type="file"
            accept={accept}
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              onChange(file);
            }}
          />
          <Stack spacing={0.5} sx={{ minWidth: 0 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <AudioFileRounded fontSize="small" color="primary" />
              <Typography noWrap>{fileName || '尚未选择文件'}</Typography>
            </Stack>
            {helperText ? (
              <Typography variant="body2" color="text.secondary">
                {helperText}
              </Typography>
            ) : null}
          </Stack>
          {fileName ? (
            <Button
              color="inherit"
              disabled={disabled}
              onClick={() => {
                if (inputRef.current) {
                  inputRef.current.value = '';
                }
                onChange(null);
              }}
            >
              清除
            </Button>
          ) : null}
        </Stack>
      </Box>
      {error ? <Alert severity="error">{error}</Alert> : null}
    </Stack>
  );
}
