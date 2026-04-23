import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import HomeRounded from '@mui/icons-material/HomeRounded';
import ManageSearchRounded from '@mui/icons-material/ManageSearchRounded';
import MicRounded from '@mui/icons-material/MicRounded';
import MonitorHeartRounded from '@mui/icons-material/MonitorHeartRounded';
import SearchRounded from '@mui/icons-material/SearchRounded';
import {
  Box,
  Chip,
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { BrandLogo } from './BrandLogo';

const drawerWidth = 264;

const navItems = [
  { label: '工作台', to: '/', icon: <HomeRounded fontSize="small" /> },
  { label: '任务中心', to: '/jobs', icon: <ManageSearchRounded fontSize="small" /> },
  { label: '声纹库', to: '/voiceprints', icon: <MicRounded fontSize="small" /> },
  { label: '模型状态', to: '/system/models', icon: <MonitorHeartRounded fontSize="small" /> },
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
            px: 2.25,
            py: 2.5,
          },
        }}
      >
        <Stack spacing={3.25} sx={{ height: '100%' }}>
          <Stack spacing={1.25} sx={{ px: 1.25, pt: 0.5 }}>
            <BrandLogo
              size={48}
              title="智能语音平台"
              subtitle="ASR Platform"
            />
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ px: 0.25, maxWidth: 210 }}
            >
              面向多人转写、说话人分离与声纹核验的极简工作台。
            </Typography>
          </Stack>

          <Stack spacing={1.25} sx={{ px: 0.75 }}>
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{
                px: 1.4,
                py: 1.05,
                borderRadius: 999,
                bgcolor: alpha('#ffffff', 0.74),
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <SearchRounded sx={{ fontSize: 18, color: 'text.secondary' }} />
              <Typography variant="body2" color="text.secondary">
                搜索任务、speaker、档案
              </Typography>
            </Stack>
            <Stack
              sx={{
                px: 1.35,
                py: 1.2,
                borderRadius: 5,
                bgcolor: alpha('#ffffff', 0.56),
                border: '1px solid',
                borderColor: alpha('#1c2431', 0.06),
              }}
            >
              <Stack direction="row" spacing={1} alignItems="center">
                <AutoAwesomeRounded sx={{ fontSize: 16, color: 'primary.main' }} />
                <Typography variant="body2" color="text.primary" sx={{ fontWeight: 600 }}>
                  高精度链路
                </Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.7 }}>
                当前默认走本地 GPU 推理，工作台会优先直达多人转写与说话人分离主路径。
              </Typography>
            </Stack>
          </Stack>

          <List sx={{ px: 0.5 }}>
            {navItems.map((item) => (
              <ListItemButton
                key={item.to}
                component={NavLink}
                to={item.to}
                sx={{
                  borderRadius: 4.5,
                  px: 1.55,
                  py: 1.15,
                  mb: 0.5,
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
                <Stack direction="row" spacing={1.5} alignItems="center">
                  {item.icon}
                  <ListItemText primary={item.label} />
                </Stack>
              </ListItemButton>
            ))}
          </List>

          <Box sx={{ px: 1.25, mt: 'auto' }}>
            <Divider sx={{ borderColor: alpha('#1c2431', 0.08), mb: 2 }} />
            <Stack spacing={1.25}>
              <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: '0.08em' }}>
                当前页面
              </Typography>
              <Typography
                variant="h6"
                sx={{
                  fontFamily:
                    '"Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif',
                }}
              >
                {resolveCurrentPage(location.pathname)}
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Chip
                  size="small"
                  label="Claude 风格工作台"
                  sx={{
                    bgcolor: alpha('#ffffff', 0.82),
                    color: 'text.secondary',
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                />
                <Chip
                  size="small"
                  label="GPU Ready"
                  sx={{
                    bgcolor: alpha('#2f6fed', 0.08),
                    color: 'primary.main',
                  }}
                />
              </Stack>
              <Box
                sx={{
                  mt: 0.75,
                  p: 1.4,
                  borderRadius: 4,
                  background:
                    'linear-gradient(135deg, rgba(255,255,255,0.78) 0%, rgba(240,249,255,0.88) 100%)',
                  border: '1px solid',
                  borderColor: alpha('#1c2431', 0.06),
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  结果页优先展示稳定时间线，工作台首页则优先聚焦上传与任务创建。
                </Typography>
              </Box>
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
        <Box sx={{ maxWidth: 1280, mx: 'auto' }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
