import AddRounded from '@mui/icons-material/AddRounded';
import CheckRounded from '@mui/icons-material/CheckRounded';
import DeleteRounded from '@mui/icons-material/DeleteRounded';
import FingerprintRounded from '@mui/icons-material/FingerprintRounded';
import GroupsRounded from '@mui/icons-material/GroupsRounded';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  createVoiceprintGroup,
  createVoiceprintProfile,
  enrollVoiceprint,
  fetchVoiceprintGroups,
  fetchVoiceprintJob,
  fetchVoiceprintProfileDetail,
  fetchVoiceprintProfiles,
  identifyVoiceprint,
  updateVoiceprintGroup,
  uploadAudio,
  verifyVoiceprint,
} from '../../api/client';
import type { VoiceprintJobResponse, VoiceprintProfile } from '../../api/types';
import { useAsyncData } from '../../app/useAsyncData';
import { AudioUploadField } from '../../components/AudioUploadField';
import { PageSection } from '../../components/PageSection';

const SPEAKER_MAPPING_STORAGE_KEY = 'voiceprint-job-speaker-mappings';
type SpeakerMappingStore = Record<string, Record<string, string>>;
type PendingVoiceprintJob = { jobId: string; kind: 'enroll' | 'verify' | 'identify' };

// ─── 档案详情区 ───────────────────────────────────────────────────────────────

function ProfileDetail({
  profile,
  incomingProbeAsset,
  incomingSpeaker,
  incomingJobId,
  scopeGroupId,
  candidateProfileIds,
  onEnrolled,
}: {
  profile: VoiceprintProfile;
  incomingProbeAsset: string;
  incomingSpeaker: string;
  incomingJobId: string;
  scopeGroupId: string;
  candidateProfileIds?: string[];
  onEnrolled: () => void;
}) {
  const navigate = useNavigate();
  const detailState = useAsyncData(() => fetchVoiceprintProfileDetail(profile.profile_id), [profile.profile_id]);
  const [enrollFile, setEnrollFile] = useState<File | null>(null);
  const [enrollAssetName, setEnrollAssetName] = useState('');
  const [probeFile, setProbeFile] = useState<File | null>(null);
  const [probeAssetName, setProbeAssetName] = useState('');
  const [thresholdText, setThresholdText] = useState('0.7');
  const [topKText, setTopKText] = useState('3');
  const [busy, setBusy] = useState(false);
  const [pendingJob, setPendingJob] = useState<PendingVoiceprintJob | null>(null);
  const [verifyResult, setVerifyResult] = useState<{ score: number; matched: boolean } | null>(null);
  const [identifyResult, setIdentifyResult] = useState<Array<{ rank: number; display_name: string; score: number; profile_id?: string }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const threshold = Number.parseFloat(thresholdText) || 0.7;
  const topK = Math.max(1, Number.parseInt(topKText, 10) || 3);

  const ensureAsset = async (file: File | null, assetName: string) => {
    if (file) {
      const uploaded = await uploadAudio(file);
      return uploaded.asset_name;
    }
    if (assetName.trim()) return assetName.trim();
    throw new Error('请先选择音频文件');
  };

  useEffect(() => {
    if (!pendingJob) return undefined;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const job = await fetchVoiceprintJob(pendingJob.jobId);
        if (!active) return;
        if (job.status === 'queued' || job.status === 'running') return;
        setPendingJob(null);
        setBusy(false);
        if (job.status === 'failed') { setError(job.error_message || '任务失败'); return; }
        if (pendingJob.kind === 'enroll') { onEnrolled(); setFeedback('注册完成'); }
        if (pendingJob.kind === 'verify' && job.verification) {
          setVerifyResult({ score: job.verification.score, matched: job.verification.matched });
        }
        if (pendingJob.kind === 'identify' && job.identification) {
          setIdentifyResult(job.identification.candidates);
        }
      } catch { if (active) { setPendingJob(null); setBusy(false); setError('轮询失败'); } }
    }, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [pendingJob, onEnrolled]);

  const handleEnroll = async () => {
    setBusy(true); setError(null); setFeedback(null);
    try {
      const assetName = await ensureAsset(enrollFile, enrollAssetName);
      const res = await enrollVoiceprint(profile.profile_id, assetName);
      if (res.job) { setPendingJob({ jobId: res.job.job_id, kind: 'enroll' }); setFeedback('注册任务已提交'); return; }
      onEnrolled(); setFeedback('注册完成');
    } catch (e) { setError(e instanceof Error ? e.message : '注册失败'); setBusy(false); }
    setBusy(false);
  };

  const handleVerify = async () => {
    setBusy(true); setError(null); setVerifyResult(null);
    try {
      const assetName = await ensureAsset(probeFile, probeAssetName || incomingProbeAsset);
      const res = await verifyVoiceprint(profile.profile_id, assetName, threshold);
      if (res.job) { setPendingJob({ jobId: res.job.job_id, kind: 'verify' }); setFeedback('验证任务已提交'); return; }
      if (res.result) setVerifyResult({ score: res.result.score, matched: res.result.matched });
    } catch (e) { setError(e instanceof Error ? e.message : '验证失败'); }
    setBusy(false);
  };

  const handleIdentify = async () => {
    setBusy(true); setError(null); setIdentifyResult([]);
    try {
      const assetName = await ensureAsset(probeFile, probeAssetName || incomingProbeAsset);
      const scopedProfileIds = candidateProfileIds && candidateProfileIds.length > 0
        ? candidateProfileIds
        : undefined;
      const res = scopedProfileIds
        ? await identifyVoiceprint(assetName, topK, scopedProfileIds)
        : await identifyVoiceprint(assetName, topK);
      if (res.job) { setPendingJob({ jobId: res.job.job_id, kind: 'identify' }); setFeedback('识别任务已提交'); return; }
      if (res.result) setIdentifyResult(res.result.candidates);
    } catch (e) { setError(e instanceof Error ? e.message : '识别失败'); }
    setBusy(false);
  };

  const persistSpeakerMapping = (displayName: string) => {
    if (!incomingJobId || !incomingSpeaker || typeof window === 'undefined') return;
    try {
      const raw = window.localStorage.getItem(SPEAKER_MAPPING_STORAGE_KEY);
      const store = raw ? (JSON.parse(raw) as SpeakerMappingStore) : {};
      store[incomingJobId] = { ...(store[incomingJobId] ?? {}), [incomingSpeaker]: displayName };
      window.localStorage.setItem(SPEAKER_MAPPING_STORAGE_KEY, JSON.stringify(store));
      navigate(`/jobs/${incomingJobId}`);
    } catch { setError('回写失败'); }
  };

  const samples = detailState.data?.samples ?? [];
  const history = detailState.data?.history ?? [];

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1.5} alignItems="center">
        <Avatar sx={{ bgcolor: 'primary.main', width: 44, height: 44 }}>
          <FingerprintRounded />
        </Avatar>
        <Stack>
          <Typography variant="h6">{profile.display_name}</Typography>
          <Typography variant="body2" color="text.secondary">
            {profile.sample_count} 个样本 · {profile.model_key}
          </Typography>
        </Stack>
      </Stack>

      {incomingProbeAsset ? (
        <Alert severity="info">
          来自任务：{incomingProbeAsset}
          {incomingSpeaker ? `，Speaker：${incomingSpeaker}` : ''}
          {scopeGroupId ? `，分组范围：${scopeGroupId}` : ''}
        </Alert>
      ) : null}

      {error ? <Alert severity="error">{error}</Alert> : null}
      {feedback ? <Alert severity="success">{feedback}</Alert> : null}
      {pendingJob ? <Alert severity="info">任务处理中：{pendingJob.jobId}</Alert> : null}

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="subtitle2" fontWeight={700}>注册样本</Typography>
            <AudioUploadField
              label="注册音频"
              fileName={(enrollFile?.name ?? enrollAssetName) || null}
              helperText="wav / m4a / mp3 / flac"
              disabled={busy}
              error={null}
              onChange={(f) => { setEnrollFile(f); if (f) setEnrollAssetName(''); }}
            />
            <Button variant="outlined" onClick={handleEnroll} disabled={busy || (!enrollFile && !enrollAssetName.trim())}>
              开始注册
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="subtitle2" fontWeight={700}>验证 / 识别</Typography>
            <AudioUploadField
              label="待比对音频"
              fileName={(probeFile?.name ?? (probeAssetName || incomingProbeAsset)) || null}
              helperText="wav / m4a / mp3 / flac"
              disabled={busy}
              error={null}
              onChange={(f) => { setProbeFile(f); if (f) setProbeAssetName(''); }}
            />
            <Stack direction="row" spacing={1.5}>
              <TextField label="验证阈值" value={thresholdText} onChange={(e) => setThresholdText(e.target.value)} size="small" />
              <TextField label="识别候选数" value={topKText} onChange={(e) => setTopKText(e.target.value)} size="small" />
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button variant="outlined" onClick={handleVerify} disabled={busy}>验证</Button>
              <Button variant="outlined" onClick={handleIdentify} disabled={busy}>识别</Button>
            </Stack>

            {verifyResult ? (
              <Stack spacing={1}>
                <Alert severity={verifyResult.matched ? 'success' : 'warning'}>
                  相似度 {verifyResult.score.toFixed(3)}，阈值 {threshold.toFixed(2)}，
                  {verifyResult.matched ? '通过验证' : '未通过'}
                </Alert>
                {verifyResult.matched && incomingJobId && incomingSpeaker ? (
                  <Button variant="contained" onClick={() => persistSpeakerMapping(profile.display_name)}>
                    将 {incomingSpeaker} 回写为 {profile.display_name}
                  </Button>
                ) : null}
              </Stack>
            ) : null}

            {identifyResult.length ? (
              <Stack spacing={0.8}>
                <Typography variant="body2" fontWeight={700}>识别候选</Typography>
                {identifyResult.map((c) => (
                  <Box
                    key={c.profile_id ?? c.rank}
                    sx={{ px: 1.2, py: 0.9, borderRadius: 2.5, bgcolor: alpha('#ffffff', 0.72), border: '1px solid', borderColor: alpha('#1c2431', 0.06) }}
                  >
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="body2">{c.rank}. {c.display_name}</Typography>
                      <Typography variant="body2" color="text.secondary">{c.score.toFixed(3)}</Typography>
                    </Stack>
                  </Box>
                ))}
                {incomingJobId && incomingSpeaker && identifyResult[0] ? (
                  <Button variant="contained" onClick={() => persistSpeakerMapping(identifyResult[0].display_name)}>
                    将 {incomingSpeaker} 回写为 {identifyResult[0].display_name}
                  </Button>
                ) : null}
              </Stack>
            ) : null}
          </Stack>
        </CardContent>
      </Card>

      {samples.length > 0 ? (
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="subtitle2" fontWeight={700}>已注册样本（{samples.length}）</Typography>
              {samples.map((s) => (
                <Box key={s.sample_id} sx={{ px: 1.2, py: 0.8, borderRadius: 2.5, bgcolor: alpha('#ffffff', 0.72), border: '1px solid', borderColor: alpha('#1c2431', 0.06) }}>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="body2" noWrap>{s.asset_name}</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem', flexShrink: 0 }}>
                      {s.created_at ? new Date(s.created_at).toLocaleDateString('zh-CN') : '—'}
                    </Typography>
                  </Stack>
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      ) : null}

      {history.length > 0 ? (
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="subtitle2" fontWeight={700}>最近操作</Typography>
              {history.slice(0, 6).map((h) => (
                <Box key={h.job_id} sx={{ px: 1.2, py: 0.8, borderRadius: 2.5, bgcolor: alpha('#ffffff', 0.72), border: '1px solid', borderColor: alpha('#1c2431', 0.06) }}>
                  <Stack direction="row" justifyContent="space-between" spacing={1}>
                    <Stack direction="row" spacing={0.8} alignItems="center">
                      <Chip size="small" label={h.job_type.replace('voiceprint_', '')} />
                      <Typography variant="body2" noWrap sx={{ maxWidth: 160 }}>{h.asset_name ?? h.job_id}</Typography>
                    </Stack>
                    <Chip size="small" variant="outlined" label={h.status} color={h.status === 'succeeded' ? 'success' : h.status === 'failed' ? 'error' : 'default'} />
                  </Stack>
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      ) : null}
    </Stack>
  );
}

// ─── 分组管理区 ───────────────────────────────────────────────────────────────

function GroupPanel({
  profiles,
  groups,
  onGroupsChanged,
}: {
  profiles: VoiceprintProfile[];
  groups: Array<{ group_id: string; display_name: string; profile_ids: string[] }>;
  onGroupsChanged: () => void;
}) {
  const [newGroupName, setNewGroupName] = useState('');
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [editingMembers, setEditingMembers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) return;
    setBusy(true); setError(null);
    try {
      await createVoiceprintGroup(newGroupName.trim());
      setNewGroupName('');
      onGroupsChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '创建失败'); }
    setBusy(false);
  };

  const handleStartEdit = (group: { group_id: string; profile_ids: string[] }) => {
    setEditingGroupId(group.group_id);
    setEditingMembers([...group.profile_ids]);
  };

  const handleSaveEdit = async () => {
    if (!editingGroupId) return;
    setBusy(true); setError(null);
    try {
      await updateVoiceprintGroup(editingGroupId, editingMembers);
      setEditingGroupId(null);
      onGroupsChanged();
    } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
    setBusy(false);
  };

  const toggleMember = (profileId: string) => {
    setEditingMembers((prev) =>
      prev.includes(profileId) ? prev.filter((id) => id !== profileId) : [...prev, profileId],
    );
  };

  return (
    <Stack spacing={1.5}>
      <Typography variant="h6">声纹分组</Typography>
      <Typography variant="body2" color="text.secondary">
        分组用于多人转写时限定候选范围，提升识别准确率。
      </Typography>

      {error ? <Alert severity="error">{error}</Alert> : null}

      <Stack direction="row" spacing={1}>
        <TextField
          fullWidth
          size="small"
          label="新建分组"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void handleCreateGroup(); }}
        />
        <Button variant="outlined" onClick={handleCreateGroup} disabled={busy || !newGroupName.trim()}>
          创建
        </Button>
      </Stack>

      <Stack spacing={1.2}>
        {groups.length ? groups.map((group) => (
          <Card key={group.group_id} variant="outlined">
            <CardContent sx={{ py: 1.4, px: 1.6, '&:last-child': { pb: 1.4 } }}>
              {editingGroupId === group.group_id ? (
                <Stack spacing={1.2}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography fontWeight={700}>{group.display_name}</Typography>
                    <Stack direction="row" spacing={0.8}>
                      <Button size="small" variant="contained" onClick={handleSaveEdit} disabled={busy}>保存</Button>
                      <Button size="small" onClick={() => setEditingGroupId(null)}>取消</Button>
                    </Stack>
                  </Stack>
                  <Stack spacing={0.6}>
                    {profiles.map((p) => (
                      <Stack key={p.profile_id} direction="row" spacing={1} alignItems="center">
                        <Checkbox
                          size="small"
                          checked={editingMembers.includes(p.profile_id)}
                          onChange={() => toggleMember(p.profile_id)}
                        />
                        <Typography variant="body2">{p.display_name}</Typography>
                        <Typography variant="body2" color="text.secondary">({p.sample_count} 样本)</Typography>
                      </Stack>
                    ))}
                  </Stack>
                </Stack>
              ) : (
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Stack spacing={0.5}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <GroupsRounded fontSize="small" color="action" />
                      <Typography fontWeight={700}>{group.display_name}</Typography>
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      {group.profile_ids.length} 个档案
                      {group.profile_ids.length > 0 ? `：${group.profile_ids.map((id) => profiles.find((p) => p.profile_id === id)?.display_name ?? id).join('、')}` : ''}
                    </Typography>
                  </Stack>
                  <Button size="small" onClick={() => handleStartEdit(group)}>编辑成员</Button>
                </Stack>
              )}
            </CardContent>
          </Card>
        )) : (
          <Typography variant="body2" color="text.secondary">暂无分组，创建后可在工作台多人转写时选择。</Typography>
        )}
      </Stack>
    </Stack>
  );
}

// ─── 主页面 ───────────────────────────────────────────────────────────────────

export function VoiceprintLibraryPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const profilesState = useAsyncData(() => fetchVoiceprintProfiles(), []);
  const groupsState = useAsyncData(() => fetchVoiceprintGroups(), []);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newProfileName, setNewProfileName] = useState('');
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const incomingProbeAsset = searchParams.get('probe') ?? '';
  const incomingSpeaker = searchParams.get('speaker') ?? '';
  const incomingJobId = searchParams.get('jobId') ?? '';
  const scopeGroupId = searchParams.get('voiceprintGroupId') ?? '';
  const scopeMode = searchParams.get('voiceprintScope') ?? 'none';

  const profiles = profilesState.data?.items ?? [];
  const groups = groupsState.data?.items ?? [];

  // 如果有分组范围，只展示该分组内的档案
  const visibleProfiles = useMemo(() => {
    if (scopeMode === 'group' && scopeGroupId) {
      const group = groups.find((g) => g.group_id === scopeGroupId);
      if (group && group.profile_ids.length > 0) {
        return profiles.filter((p) => group.profile_ids.includes(p.profile_id));
      }
    }
    return profiles;
  }, [profiles, groups, scopeMode, scopeGroupId]);

  const activeProfile = useMemo(
    () => visibleProfiles.find((p) => p.profile_id === selectedProfileId) ?? visibleProfiles[0] ?? null,
    [visibleProfiles, selectedProfileId],
  );
  const identifyCandidateProfileIds = useMemo(
    () => (scopeMode === 'group' && scopeGroupId ? visibleProfiles.map((p) => p.profile_id) : undefined),
    [scopeMode, scopeGroupId, visibleProfiles],
  );

  const handleCreateProfile = async () => {
    if (!newProfileName.trim()) { setCreateError('请输入档案名称'); return; }
    setBusy(true); setCreateError(null);
    try {
      const res = await createVoiceprintProfile(newProfileName.trim(), '3dspeaker-embedding');
      profilesState.setData((current) => ({ items: [res.profile, ...(current?.items ?? [])] }));
      setSelectedProfileId(res.profile.profile_id);
      setCreateDialogOpen(false);
      setNewProfileName('');
    } catch (e) { setCreateError(e instanceof Error ? e.message : '创建失败'); }
    setBusy(false);
  };

  return (
    <PageSection
      compact
      title="声纹库"
      loading={(profilesState.loading && !profilesState.data) || (groupsState.loading && !groupsState.data)}
      error={profilesState.error ?? groupsState.error}
      actions={
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => { profilesState.reload(); groupsState.reload(); }}>刷新</Button>
          <Button variant="contained" startIcon={<AddRounded />} onClick={() => setCreateDialogOpen(true)}>
            新建档案
          </Button>
        </Stack>
      }
    >
      {scopeMode !== 'none' && scopeGroupId ? (
        <Alert severity="info" sx={{ mb: 1 }}>
          当前仅展示分组 <strong>{groups.find((g) => g.group_id === scopeGroupId)?.display_name ?? scopeGroupId}</strong> 内的档案（共 {visibleProfiles.length} 个）。
          <Button size="small" sx={{ ml: 1 }} onClick={() => navigate('/voiceprints')}>查看全部</Button>
        </Alert>
      ) : null}

      <Grid container spacing={2.2} alignItems="flex-start">
        {/* 左侧：档案列表 */}
        <Grid size={{ xs: 12, md: 3 }}>
          <Card>
            <CardContent>
              <Stack spacing={1}>
                <Typography variant="h6">档案列表</Typography>
                <Typography variant="body2" color="text.secondary">{visibleProfiles.length} 个档案</Typography>
                <Divider />
                {visibleProfiles.length ? (
                  <Stack spacing={0.8}>
                    {visibleProfiles.map((p) => (
                      <Box
                        key={p.profile_id}
                        onClick={() => setSelectedProfileId(p.profile_id)}
                        sx={{
                          px: 1.2,
                          py: 1,
                          borderRadius: 2.5,
                          cursor: 'pointer',
                          bgcolor: p.profile_id === activeProfile?.profile_id ? alpha('#2f6fed', 0.08) : alpha('#ffffff', 0.72),
                          border: '1px solid',
                          borderColor: p.profile_id === activeProfile?.profile_id ? alpha('#2f6fed', 0.18) : alpha('#1c2431', 0.06),
                        }}
                      >
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                          <Typography fontWeight={700} variant="body2">{p.display_name}</Typography>
                          <Chip size="small" label={`${p.sample_count} 样本`} color={p.sample_count > 0 ? 'success' : 'default'} />
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                ) : (
                  <Alert severity="info">暂无档案。</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* 中部：档案详情与操作 */}
        <Grid size={{ xs: 12, md: 5 }}>
          {activeProfile ? (
            <ProfileDetail
              profile={activeProfile}
              incomingProbeAsset={incomingProbeAsset}
              incomingSpeaker={incomingSpeaker}
              incomingJobId={incomingJobId}
              scopeGroupId={scopeGroupId}
              candidateProfileIds={identifyCandidateProfileIds}
              onEnrolled={() => profilesState.reload()}
            />
          ) : (
            <Alert severity="info">请从左侧选择一个档案，或新建档案。</Alert>
          )}
        </Grid>

        {/* 右侧：分组管理 */}
        <Grid size={{ xs: 12, md: 4 }}>
          <Card>
            <CardContent>
              <GroupPanel
                profiles={profiles}
                groups={groups}
                onGroupsChanged={() => groupsState.reload()}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* 新建档案对话框 */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>新建声纹档案</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="档案名称"
              value={newProfileName}
              onChange={(e) => setNewProfileName(e.target.value)}
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') void handleCreateProfile(); }}
            />
            {createError ? <Alert severity="error">{createError}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>取消</Button>
          <Button variant="contained" onClick={handleCreateProfile} disabled={busy}>创建</Button>
        </DialogActions>
      </Dialog>
    </PageSection>
  );
}
