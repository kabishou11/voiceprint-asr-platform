import AddRounded from '@mui/icons-material/AddRounded';
import FingerprintRounded from '@mui/icons-material/FingerprintRounded';
import RecordVoiceOverRounded from '@mui/icons-material/RecordVoiceOverRounded';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  createVoiceprintProfile,
  enrollVoiceprint,
  fetchVoiceprintProfiles,
  identifyVoiceprint,
  uploadAudio,
  verifyVoiceprint,
} from '../../api/client';
import type { VoiceprintProfile } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { AudioUploadField } from '../../components/AudioUploadField';
import { PageSection } from '../../components/PageSection';

const SPEAKER_MAPPING_STORAGE_KEY = 'voiceprint-job-speaker-mappings';

type SpeakerMappingStore = Record<string, Record<string, string>>;

function SectionCard({
  title,
  subtitle,
  children,
  action,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent sx={{ p: 2.2 }}>
        <Stack spacing={1.5}>
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={1}
            justifyContent="space-between"
            alignItems={{ xs: 'flex-start', md: 'center' }}
          >
            <Stack spacing={0.45}>
              <Typography variant="h6">{title}</Typography>
              {subtitle ? (
                <Typography variant="body2" color="text.secondary">
                  {subtitle}
                </Typography>
              ) : null}
            </Stack>
            {action}
          </Stack>
          {children}
        </Stack>
      </CardContent>
    </Card>
  );
}

export function VoiceprintLibraryPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const profilesState = useAsyncData(() => fetchVoiceprintProfiles(), []);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [displayName, setDisplayName] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [enrollFile, setEnrollFile] = useState<File | null>(null);
  const [enrollAssetName, setEnrollAssetName] = useState('');
  const [probeFile, setProbeFile] = useState<File | null>(null);
  const [probeAssetName, setProbeAssetName] = useState('');
  const [enrollResult, setEnrollResult] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<{ score: number; matched: boolean } | null>(null);
  const [identifyResult, setIdentifyResult] = useState<string[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [thresholdText, setThresholdText] = useState('0.7');
  const [topKText, setTopKText] = useState('3');

  const incomingProbeAsset = searchParams.get('probe') ?? '';
  const incomingSpeaker = searchParams.get('speaker') ?? '';
  const incomingJobId = searchParams.get('jobId') ?? '';

  const profiles = profilesState.data?.items ?? [];
  const activeProfileId = selectedProfileId || profiles[0]?.profile_id || '';
  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.profile_id === activeProfileId) ?? null,
    [profiles, activeProfileId],
  );

  const threshold = Number.parseFloat(thresholdText) || 0.7;
  const topK = Math.max(1, Number.parseInt(topKText, 10) || 3);

  const resetMessages = () => {
    setActionError(null);
    setEnrollResult(null);
    setVerifyResult(null);
    setIdentifyResult([]);
  };

  const persistSpeakerMapping = (incomingDisplayName: string) => {
    if (!incomingJobId || !incomingSpeaker || typeof window === 'undefined') {
      return;
    }
    try {
      const raw = window.localStorage.getItem(SPEAKER_MAPPING_STORAGE_KEY);
      const store = raw ? (JSON.parse(raw) as SpeakerMappingStore) : {};
      store[incomingJobId] = {
        ...(store[incomingJobId] ?? {}),
        [incomingSpeaker]: incomingDisplayName,
      };
      window.localStorage.setItem(SPEAKER_MAPPING_STORAGE_KEY, JSON.stringify(store));
      navigate(`/jobs/${incomingJobId}`);
    } catch {
      setActionError('Speaker 回写失败，请稍后重试。');
    }
  };

  const ensureEnrollAsset = async () => {
    if (enrollFile) {
      const uploaded = await uploadAudio(enrollFile);
      setEnrollAssetName(uploaded.asset_name);
      return uploaded.asset_name;
    }
    if (enrollAssetName.trim()) {
      return enrollAssetName.trim();
    }
    throw new Error('请先选择用于注册的音频文件');
  };

  const ensureProbeAsset = async () => {
    if (probeFile) {
      const uploaded = await uploadAudio(probeFile);
      setProbeAssetName(uploaded.asset_name);
      return uploaded.asset_name;
    }
    if ((probeAssetName || incomingProbeAsset).trim()) {
      return (probeAssetName || incomingProbeAsset).trim();
    }
    throw new Error('请先选择待验证或识别的音频文件');
  };

  const handleCreate = async () => {
    if (!displayName.trim()) {
      setActionError('请输入档案名称');
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      const response = await createVoiceprintProfile(displayName.trim(), '3dspeaker-embedding');
      profilesState.setData((current) => ({ items: [response.profile, ...(current?.items ?? [])] }));
      setSelectedProfileId(response.profile.profile_id);
      setDialogOpen(false);
      setDisplayName('');
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : '创建档案失败');
    } finally {
      setBusy(false);
    }
  };

  const handleEnroll = async () => {
    if (!activeProfileId) {
      setActionError('请先选择一个声纹档案');
      return;
    }
    setBusy(true);
    resetMessages();
    try {
      const assetName = await ensureEnrollAsset();
      const response = await enrollVoiceprint(activeProfileId, assetName);
      profilesState.setData((current) => ({
        items: (current?.items ?? []).map((item) =>
          item.profile_id === response.profile.profile_id ? response.profile : item,
        ),
      }));
      setEnrollResult(`注册完成：${response.profile.display_name} 已写入基准音频`);
      setEnrollFile(null);
      setEnrollAssetName('');
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : '声纹注册失败');
    } finally {
      setBusy(false);
    }
  };

  const handleVerify = async () => {
    if (!activeProfileId) {
      setActionError('请先选择一个声纹档案');
      return;
    }
    setBusy(true);
    resetMessages();
    try {
      const assetName = await ensureProbeAsset();
      const response = await verifyVoiceprint(activeProfileId, assetName, threshold);
      setVerifyResult({ score: response.result.score, matched: response.result.matched });
      if (response.result.matched && activeProfile) {
        setEnrollResult(`验证通过：可将 ${incomingSpeaker || '当前 Speaker'} 回写为 ${activeProfile.display_name}`);
      }
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : '声纹验证失败');
    } finally {
      setBusy(false);
    }
  };

  const handleIdentify = async () => {
    setBusy(true);
    resetMessages();
    try {
      const assetName = await ensureProbeAsset();
      const response = await identifyVoiceprint(assetName, topK);
      setIdentifyResult(
        response.result.candidates.map((item) => `${item.rank}. ${item.display_name} · 相似度 ${item.score}`),
      );
      if (response.result.matched && response.result.candidates[0]) {
        setEnrollResult(`识别命中：建议回写为 ${response.result.candidates[0].display_name}`);
      }
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : '声纹识别失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageSection
      title="声纹库"
      loading={profilesState.loading}
      error={profilesState.error}
      actions={
        <Stack direction="row" spacing={1.5}>
          <Button variant="outlined" onClick={profilesState.reload}>
            刷新
          </Button>
          <Button variant="contained" startIcon={<AddRounded />} onClick={() => setDialogOpen(true)}>
            新建档案
          </Button>
        </Stack>
      }
    >
      <Grid container spacing={2.2} alignItems="stretch">
        <Grid size={{ xs: 12, xl: 3.6 }}>
          <SectionCard title="档案列表" subtitle={profiles.length ? `共 ${profiles.length} 个档案` : undefined}>
            {profiles.length ? (
              <List disablePadding sx={{ display: 'grid', gap: 1 }}>
                {profiles.map((profile: VoiceprintProfile) => (
                  <ListItemButton
                    key={profile.profile_id}
                    selected={profile.profile_id === activeProfileId}
                    onClick={() => {
                      setSelectedProfileId(profile.profile_id);
                      resetMessages();
                    }}
                    sx={{
                      alignItems: 'flex-start',
                      borderRadius: 3,
                      px: 1.5,
                      py: 1.25,
                      bgcolor:
                        profile.profile_id === activeProfileId
                          ? alpha('#2f6fed', 0.08)
                          : alpha('#ffffff', 0.72),
                      border: '1px solid',
                      borderColor:
                        profile.profile_id === activeProfileId
                          ? alpha('#2f6fed', 0.16)
                          : alpha('#1c2431', 0.06),
                    }}
                  >
                    <ListItemText
                      primary={
                        <Typography sx={{ fontWeight: 700, lineHeight: 1.3 }}>
                          {profile.display_name}
                        </Typography>
                      }
                      secondary={`样本 ${profile.sample_count}`}
                    />
                  </ListItemButton>
                ))}
              </List>
            ) : (
              <Alert severity="info">当前还没有声纹档案。</Alert>
            )}
          </SectionCard>
        </Grid>

        <Grid size={{ xs: 12, xl: 8.4 }}>
          <Stack spacing={2.2}>
            {incomingProbeAsset ? (
              <Alert severity="info">
                已从任务详情带入资产：{incomingProbeAsset}
                {incomingSpeaker ? `，当前 Speaker：${incomingSpeaker}` : ''}
                {incomingJobId ? `，任务：${incomingJobId}` : ''}
              </Alert>
            ) : null}

            {activeProfile ? (
              <SectionCard
                title={activeProfile.display_name}
                subtitle={`档案 ${activeProfile.profile_id}`}
                action={
                  <Stack direction="row" spacing={1}>
                    <Button variant="outlined" onClick={handleVerify} disabled={busy}>
                      声纹验证
                    </Button>
                    <Button variant="outlined" onClick={handleIdentify} disabled={busy}>
                      声纹识别
                    </Button>
                  </Stack>
                }
              >
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={1.6}
                  alignItems={{ xs: 'flex-start', md: 'center' }}
                >
                  <Avatar sx={{ width: 52, height: 52, bgcolor: 'primary.main' }}>
                    <FingerprintRounded />
                  </Avatar>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip
                      size="small"
                      label={`样本 ${activeProfile.sample_count}`}
                      color={activeProfile.sample_count > 0 ? 'success' : 'default'}
                    />
                    <Chip size="small" variant="outlined" label="本地 3D-Speaker" />
                  </Stack>
                </Stack>
              </SectionCard>
            ) : (
              <Alert severity="info">请选择一个档案开始操作。</Alert>
            )}

            <SectionCard
              title="验证与识别"
              subtitle="上传待比对音频。"
            >
              <Stack spacing={1.5}>
                <AudioUploadField
                  label="待比对音频"
                  fileName={(probeFile?.name ?? probeAssetName ?? incomingProbeAsset) || null}
                  helperText="支持 wav、m4a、mp3、flac。"
                  disabled={busy}
                  error={null}
                  onChange={(file) => {
                    setProbeFile(file);
                    if (file) {
                      setProbeAssetName('');
                    }
                    resetMessages();
                  }}
                />
                <Grid container spacing={1.5}>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField
                      label="验证阈值"
                      value={thresholdText}
                      onChange={(event) => setThresholdText(event.target.value)}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField
                      label="识别候选数"
                      value={topKText}
                      onChange={(event) => setTopKText(event.target.value)}
                    />
                  </Grid>
                </Grid>
                {verifyResult ? (
                  <Stack spacing={1}>
                    <Alert severity={verifyResult.matched ? 'success' : 'warning'}>
                      相似度 {verifyResult.score}，阈值 {threshold.toFixed(2)}，{verifyResult.matched ? '已通过验证' : '未达到阈值'}
                    </Alert>
                    {verifyResult.matched && incomingJobId && incomingSpeaker && activeProfile ? (
                      <Button variant="contained" onClick={() => persistSpeakerMapping(activeProfile.display_name)}>
                        将当前 Speaker 回写为 {activeProfile.display_name}
                      </Button>
                    ) : null}
                  </Stack>
                ) : null}
                {identifyResult.length ? (
                  <Stack spacing={1}>
                    <Typography variant="body2" color="text.secondary">
                      识别结果
                    </Typography>
                    <Stack spacing={0.8}>
                      {identifyResult.map((item) => (
                        <Box
                          key={item}
                          sx={{
                            px: 1.25,
                            py: 0.95,
                            borderRadius: 2.5,
                            bgcolor: alpha('#ffffff', 0.72),
                            border: '1px solid',
                            borderColor: alpha('#1c2431', 0.06),
                          }}
                        >
                          <Typography variant="body2">{item}</Typography>
                        </Box>
                      ))}
                    </Stack>
                    {incomingJobId && incomingSpeaker ? (
                      <Button
                        variant="contained"
                        onClick={() => {
                          const topCandidate = identifyResult[0];
                          if (!topCandidate) {
                            return;
                          }
                          const incomingDisplayName = topCandidate.replace(/^\d+\.\s*/, '').split(' · ')[0]?.trim();
                          if (!incomingDisplayName) {
                            return;
                          }
                          persistSpeakerMapping(incomingDisplayName);
                        }}
                      >
                        将首个候选回写到任务详情
                      </Button>
                    ) : null}
                  </Stack>
                ) : null}
              </Stack>
            </SectionCard>

            <SectionCard
              title="注册基准音频"
              subtitle="为当前档案写入基准音频。"
            >
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <RecordVoiceOverRounded color="action" fontSize="small" />
                  <Typography variant="body2" color="text.secondary">
                    注册音频
                  </Typography>
                </Stack>
                <AudioUploadField
                  label="注册音频"
                  fileName={(enrollFile?.name ?? enrollAssetName) || null}
                  helperText="注册后可用于后续验证与识别。"
                  disabled={busy}
                  error={null}
                  onChange={(file) => {
                    setEnrollFile(file);
                    if (file) {
                      setEnrollAssetName('');
                    }
                    resetMessages();
                  }}
                />
                <Divider />
                <Button variant="outlined" onClick={handleEnroll} disabled={!activeProfile || busy}>
                  开始注册
                </Button>
                {enrollResult ? <Alert severity="success">{enrollResult}</Alert> : null}
                {actionError ? <Alert severity="error">{actionError}</Alert> : null}
              </Stack>
            </SectionCard>
          </Stack>
        </Grid>
      </Grid>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>新建声纹档案</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="档案名称"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              autoFocus
            />
            <Typography variant="body2" color="text.secondary">
              创建后即可使用。
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>取消</Button>
          <Button variant="contained" onClick={handleCreate} disabled={busy}>
            创建
          </Button>
        </DialogActions>
      </Dialog>
    </PageSection>
  );
}
