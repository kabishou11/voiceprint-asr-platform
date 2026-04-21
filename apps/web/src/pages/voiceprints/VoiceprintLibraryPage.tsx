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
  Grid,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';

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

export function VoiceprintLibraryPage() {
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

  const profiles = profilesState.data?.items ?? [];
  const activeProfileId = selectedProfileId || profiles[0]?.profile_id || '';
  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.profile_id === activeProfileId) ?? null,
    [profiles, activeProfileId],
  );

  const resetMessages = () => {
    setActionError(null);
    setEnrollResult(null);
    setVerifyResult(null);
    setIdentifyResult([]);
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
    if (probeAssetName.trim()) {
      return probeAssetName.trim();
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
      const response = await verifyVoiceprint(activeProfileId, assetName, 0.7);
      setVerifyResult({ score: response.result.score, matched: response.result.matched });
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
      const response = await identifyVoiceprint(assetName, 3);
      setIdentifyResult(
        response.result.candidates.map((item) => `${item.rank}. ${item.display_name} · 相似度 ${item.score}`),
      );
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : '声纹识别失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageSection
      title="声纹库"
      description="集中管理声纹档案，并上传真实音频完成注册、验证与识别操作。"
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
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Stack spacing={2}>
                <Typography variant="h6">档案列表</Typography>
                {profiles.length ? (
                  <List disablePadding>
                    {profiles.map((profile: VoiceprintProfile) => (
                      <ListItemButton
                        key={profile.profile_id}
                        selected={profile.profile_id === activeProfileId}
                        onClick={() => {
                          setSelectedProfileId(profile.profile_id);
                          resetMessages();
                        }}
                        sx={{ borderRadius: 3, mb: 1 }}
                      >
                        <ListItemText
                          primary={profile.display_name}
                          secondary={`样本 ${profile.sample_count} · ${profile.model_key}`}
                        />
                      </ListItemButton>
                    ))}
                  </List>
                ) : (
                  <Alert severity="info">当前还没有声纹档案。</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          <Stack spacing={3}>
            <Card>
              <CardContent>
                {activeProfile ? (
                  <Stack spacing={2.5}>
                    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'flex-start', md: 'center' }}>
                      <Avatar sx={{ width: 56, height: 56, bgcolor: 'primary.main' }}>
                        <FingerprintRounded />
                      </Avatar>
                      <Box>
                        <Typography variant="h5">{activeProfile.display_name}</Typography>
                        <Typography color="text.secondary">档案编号 {activeProfile.profile_id}</Typography>
                      </Box>
                    </Stack>
                    <Grid container spacing={2}>
                      {[
                        { label: '样本数', value: String(activeProfile.sample_count) },
                        { label: '模型', value: activeProfile.model_key },
                        { label: '待比对音频', value: (probeFile?.name ?? probeAssetName) || '尚未上传' },
                      ].map((item) => (
                        <Grid key={item.label} size={{ xs: 12, md: 4 }}>
                          <Card variant="outlined" sx={{ borderRadius: 4 }}>
                            <CardContent>
                              <Typography variant="body2" color="text.secondary">
                                {item.label}
                              </Typography>
                              <Typography variant="h6" sx={{ mt: 1 }}>
                                {item.value}
                              </Typography>
                            </CardContent>
                          </Card>
                        </Grid>
                      ))}
                    </Grid>
                  </Stack>
                ) : (
                  <Alert severity="info">请选择一个档案开始操作。</Alert>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="h6">注册基准音频</Typography>
                  <AudioUploadField
                    label="选择用于注册的音频文件"
                    fileName={(enrollFile?.name ?? enrollAssetName) || null}
                    helperText="上传一段代表该档案身份的音频，注册后可用于后续验证与识别。"
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
                  <Button variant="contained" onClick={handleEnroll} disabled={!activeProfile || busy}>
                    开始注册
                  </Button>
                  {enrollResult ? <Alert severity="success">{enrollResult}</Alert> : null}
                </Stack>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="h6">上传待比对音频</Typography>
                  <AudioUploadField
                    label="选择用于验证 / 识别的音频文件"
                    fileName={(probeFile?.name ?? probeAssetName) || null}
                    helperText="支持 wav、m4a、mp3、flac；点击验证或识别时会先上传文件，再调用后端声纹能力。"
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
                </Stack>
              </CardContent>
            </Card>

            <Grid container spacing={3}>
              <Grid size={{ xs: 12, lg: 6 }}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Stack spacing={2}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <RecordVoiceOverRounded color="primary" />
                        <Typography variant="h6">声纹验证</Typography>
                      </Stack>
                      <Typography color="text.secondary">上传一段待比对音频，对选中的档案执行 1:1 核验。</Typography>
                      <Button variant="contained" onClick={handleVerify} disabled={!activeProfile || busy}>
                        开始验证
                      </Button>
                      {verifyResult ? (
                        <Alert severity={verifyResult.matched ? 'success' : 'warning'}>
                          相似度 {verifyResult.score}，{verifyResult.matched ? '已通过验证' : '未达到阈值'}
                        </Alert>
                      ) : null}
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
              <Grid size={{ xs: 12, lg: 6 }}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Stack spacing={2}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <FingerprintRounded color="primary" />
                        <Typography variant="h6">声纹识别</Typography>
                      </Stack>
                      <Typography color="text.secondary">上传一段待比对音频，在声纹库中返回最相近的候选档案。</Typography>
                      <Button variant="outlined" onClick={handleIdentify} disabled={busy}>
                        开始识别
                      </Button>
                      {identifyResult.length ? (
                        <Stack spacing={1}>
                          {identifyResult.map((item) => (
                            <Chip key={item} label={item} sx={{ justifyContent: 'flex-start' }} />
                          ))}
                        </Stack>
                      ) : null}
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {actionError ? <Alert severity="error">{actionError}</Alert> : null}
          </Stack>
        </Grid>
      </Grid>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>新建声纹档案</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="档案名称" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
            <Typography variant="body2" color="text.secondary">
              创建后即可用于注册、验证和识别流程。
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
