import CheckCircleOutlineRounded from '@mui/icons-material/CheckCircleOutlineRounded';
import HomeRounded from '@mui/icons-material/HomeRounded';
import ArticleRounded from '@mui/icons-material/ArticleRounded';
import KeyboardDoubleArrowLeftRounded from '@mui/icons-material/KeyboardDoubleArrowLeftRounded';
import KeyboardDoubleArrowRightRounded from '@mui/icons-material/KeyboardDoubleArrowRightRounded';
import ManageSearchRounded from '@mui/icons-material/ManageSearchRounded';
import MicRounded from '@mui/icons-material/MicRounded';
import MonitorHeartRounded from '@mui/icons-material/MonitorHeartRounded';
import {
  Box,
  Chip,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { fetchJobs, fetchModels } from '../api/client';
import { useAsyncData } from '../app/useAsyncData';
import { BrandLogo } from './BrandLogo';

const expandedDrawerWidth = 248;
const collapsedDrawerWidth = 92;
const SIDEBAR_COLLAPSED_STORAGE_KEY = 'voiceprint-sidebar-collapsed';
const STATUS_POLL_INTERVAL_MS = 5000;

const navItems = [
  { label: '工作台', to: '/', icon: <HomeRounded fontSize="small" /> },
  { label: '任务队列', to: '/tasks', icon: <CheckCircleOutlineRounded fontSize="small" /> },
  { label: '任务中心', to: '/jobs', icon: <ManageSearchRounded fontSize="small" /> },
  { label: '会议纪要', to: '/minutes', icon: <ArticleRounded fontSize="small" /> },
  { label: '声纹库', to: '/voiceprints', icon: <MicRounded fontSize="small" /> },
  { label: '模型', to: '/system/models', icon: <MonitorHeartRounded fontSize="small" /> },
];

function resolveCurrentPage(pathname: string) {
  const matched = navItems.find((item) =>
    item.to === '/'
      ? pathname === '/'
      : pathname === item.to || pathname.startsWith(`${item.to}/`),
  );
  return matched?.label ?? '业务页面';
}

export function AppLayout() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') {
      return false;
    }
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === 'true';
  });
  const jobsState = useAsyncData(() => fetchJobs(), []);
  const modelsState = useAsyncData(() => fetchModels(), []);
  const runningCount = useMemo(
    () =>
      (jobsState.data?.items ?? []).filter(
        (job) => job.status === 'queued' || job.status === 'running',
      ).length,
    [jobsState.data],
  );
  const loadedModelCount = useMemo(
    () =>
      (modelsState.data?.items ?? []).filter((model) => model.status === 'loaded').length,
    [modelsState.data],
  );
  const gpuReady = modelsState.data?.gpu?.cuda_available ?? false;
  const drawerWidth = collapsed ? collapsedDrawerWidth : expandedDrawerWidth;

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(collapsed));
  }, [collapsed]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      jobsState.reload();
      modelsState.reload();
    }, STATUS_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [jobsState.reload, modelsState.reload]);

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', color: 'text.primary' }}>
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
            borderRight: '1px solid rgba(28,36,49,0.06)',
            px: collapsed ? 1.25 : 2.25,
            py: 2.5,
            overflowX: 'hidden',
            transition: 'width 0.2s ease, padding 0.2s ease',
          },
        }}
      >
        <Stack spacing={3.25} sx={{ height: '100%' }}>
          <Stack spacing={1.5} sx={{ px: collapsed ? 0.25 : 1.25, pt: 0.5 }}>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <BrandLogo
                size={collapsed ? 40 : 44}
                title="智能语音平台"
                subtitle="ASR Platform"
                withWordmark={!collapsed}
              />
              <Tooltip title={collapsed ? '展开侧边栏' : '收起侧边栏'}>
                <IconButton
                  size="small"
                  aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
                  onClick={() => setCollapsed((current) => !current)}
                  sx={{ flexShrink: 0 }}
                >
                  {collapsed ? (
                    <KeyboardDoubleArrowRightRounded fontSize="small" />
                  ) : (
                    <KeyboardDoubleArrowLeftRounded fontSize="small" />
                  )}
                </IconButton>
              </Tooltip>
            </Stack>
            <Stack
              direction={collapsed ? 'column' : 'row'}
              spacing={1}
              flexWrap="wrap"
              useFlexGap
              alignItems={collapsed ? 'center' : 'stretch'}
            >
              <Chip
                size="small"
                label={`运行中 ${runningCount}`}
                color={runningCount ? 'warning' : 'default'}
              />
              <Chip size="small" label={`模型 ${loadedModelCount}`} variant="outlined" />
              <Chip size="small" label={gpuReady ? 'GPU' : 'CPU'} color={gpuReady ? 'success' : 'default'} />
            </Stack>
          </Stack>

          <List sx={{ px: 0.5 }}>
            {navItems.map((item) => (
              <Tooltip key={item.to} title={collapsed ? item.label : ''} placement="right">
                <ListItemButton
                  component={NavLink}
                  to={item.to}
                  sx={{
                    borderRadius: 4.5,
                    px: collapsed ? 1 : 1.55,
                    py: 1.15,
                    mb: 0.5,
                    minHeight: 48,
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    color: alpha('#1c2431', 0.78),
                    '&.active': {
                      bgcolor: alpha('#ffffff', 0.92),
                      color: '#111827',
                      boxShadow:
                        '0 18px 32px rgba(28,36,49,0.05), inset 0 0 0 1px rgba(47,111,237,0.13)',
                    },
                    '&:hover': {
                      bgcolor: alpha('#ffffff', 0.68),
                    },
                  }}
                >
                  <Stack
                    direction="row"
                    spacing={collapsed ? 0 : 1.5}
                    alignItems="center"
                    justifyContent={collapsed ? 'center' : 'flex-start'}
                  >
                    {item.icon}
                    {collapsed ? null : <ListItemText primary={item.label} />}
                  </Stack>
                </ListItemButton>
              </Tooltip>
            ))}
          </List>

          <Box sx={{ px: collapsed ? 0.25 : 1.25, mt: 'auto' }}>
            <Stack spacing={1} alignItems={collapsed ? 'center' : 'flex-start'}>
              {collapsed ? null : (
                <Typography variant="body2" color="text.secondary">
                  {resolveCurrentPage(location.pathname)}
                </Typography>
              )}
              <Stack
                direction={collapsed ? 'column' : 'row'}
                spacing={1}
                flexWrap="wrap"
                useFlexGap
                alignItems={collapsed ? 'center' : 'stretch'}
              >
                <Chip size="small" label={`任务 ${runningCount}`} variant="outlined" />
                <Chip size="small" label={`模型 ${loadedModelCount}`} variant="outlined" />
              </Stack>
            </Stack>
          </Box>
        </Stack>
      </Drawer>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          minWidth: 0,
          px: { xs: 2, md: 4, xl: 6 },
          py: { xs: 2.5, md: 3.5 },
        }}
      >
        <Box sx={{ maxWidth: 1480, mx: 'auto' }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
