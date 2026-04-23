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
import { BalancedPretextText, MeasuredPretextBlock } from '../../components/PretextText';

const SPEAKER_MAPPING_STORAGE_KEY = 'voiceprint-job-speaker-mappings';

type SpeakerMappingStore = Record<string, Record<string, string>>;

function SoftPanel({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 4,
        bgcolor: alpha('#ffffff', 0.72),
        border: '1px solid',
        borderColor: alpha('#1c2431', 0.06),
      }}
    >
      {children}
    </Box>
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
      title="声纹库与身份回写工作台"
      eyebrow="身份核验"
      eyebrowColor="secondary"
      description="这里既是 1:1 验证与 1:N 识别入口，也是从任务详情把某个 speaker 回写成真实身份的闭环操作台。"
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
        <Grid size={{ xs: 12, xl: 7.8 }}>
          <Card>
            <CardContent>
              <Stack spacing={2.2}>
                <BalancedPretextText
                  text="声纹库现在不仅是档案列表，更是任务结果里 speaker 身份确认的最后一公里"
                  font='500 40px "Iowan Old Style"'
                  lineHeight={48}
                  targetLines={2}
                  minWidth={360}
                  maxWidth={760}
                  typographyProps={{
                    variant: 'h4',
                    sx: { maxWidth: 760 },
                  }}
                />
                <MeasuredPretextBlock
                  text="当你从任务详情页带着 probe、speaker 和 jobId 进入这里时，验证通过或识别命中后，可以直接把结果回写到任务详情，形成更完整的多人转写复核闭环。"
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

                {incomingProbeAsset ? (
                  <Alert severity="info">
                    已从任务详情带入资产：{incomingProbeAsset}
                    {incomingSpeaker ? `，当前 Speaker：${incomingSpeaker}` : ''}
                    {incomingJobId ? `，任务：${incomingJobId}` : ''}
                  </Alert>
                ) : null}

                {activeProfile ? (
                  <SoftPanel>
                    <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems={{ xs: 'flex-start', md: 'center' }}>
                      <Avatar sx={{ width: 56, height: 56, bgcolor: 'primary.main' }}>
                        <FingerprintRounded />
                      </Avatar>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="h5">{activeProfile.display_name}</Typography>
                        <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
                          <Chip size="small" label={`样本 ${activeProfile.sample_count}`} color={activeProfile.sample_count > 0 ? 'success' : 'default'} />
                          <Chip size="small" variant="outlined" label={`档案 ${activeProfile.profile_id}`} />
                        </Stack>
                      </Box>
                      <Stack direction="row" spacing={1.5}>
                        <Button variant="outlined" onClick={handleVerify} disabled={busy}>
                          声纹验证
                        </Button>
                        <Button variant="outlined" onClick={handleIdentify} disabled={busy}>
                          声纹识别
                        </Button>
                      </Stack>
                    </Stack>
                  </SoftPanel>
                ) : (
                  <Alert severity="info">请选择一个档案开始操作。</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, xl: 4.2 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Stack spacing={1.8}>
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
                        sx={{
                          borderRadius: 3.5,
                          mb: 1,
                          bgcolor:
                            profile.profile_id === activeProfileId
                              ? alpha('#2f6fed', 0.06)
                              : alpha('#ffffff', 0.68),
                          border: '1px solid',
                          borderColor:
                            profile.profile_id === activeProfileId
                              ? alpha('#2f6fed', 0.16)
                              : alpha('#1c2431', 0.06),
                        }}
                      >
                        <ListItemText
                          primary={profile.display_name}
                          secondary={`样本 ${profile.sample_count}`}
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
      </Grid>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card>
            <CardContent>
              <Stack spacing={1.6}>
                <Typography variant="h6">上传待比对音频</Typography>
                <Typography variant="body2" color="text.secondary">
                  这里优先承接任务详情带来的上下文，也支持你直接上传新音频做验证或识别。
                </Typography>
                <AudioUploadField
                  label="选择用于验证 / 识别的音频文件"
                  fileName={(probeFile?.name ?? probeAssetName ?? incomingProbeAsset) || null}
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
                <Grid container spacing={1.5}>
                  <Grid size={{ xs: 6 }}>
                    <TextField
                      label="验证阈值"
                      value={thresholdText}
                      onChange={(event) => setThresholdText(event.target.value)}
                    />
                  </Grid>
                  <Grid size={{ xs: 6 }}>
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
                    {identifyResult.map((item) => (
                      <Chip key={item} label={item} sx={{ justifyContent: 'flex-start' }} />
                    ))}
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
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, lg: 5 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Stack spacing={1.6}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <RecordVoiceOverRounded color="action" fontSize="small" />
                  <Typography variant="h6">注册基准音频（可选）</Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  当你需要把某个身份真正写入声纹库时，上传注册音频即可。验证与识别本身不依赖这一步，但注册后候选会更稳定。
                </Typography>
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
                <Button variant="outlined" onClick={handleEnroll} disabled={!activeProfile || busy}>
                  开始注册
                </Button>
                {enrollResult ? <Alert severity="success">{enrollResult}</Alert> : null}
                {actionError ? <Alert severity="error">{actionError}</Alert> : null}
              </Stack>
            </CardContent>
          </Card>
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
              新建后即可上传基准音频，或直接使用该档案执行验证与识别。
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
