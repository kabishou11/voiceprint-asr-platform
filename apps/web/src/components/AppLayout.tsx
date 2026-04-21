import HomeRounded from '@mui/icons-material/HomeRounded';
import ManageSearchRounded from '@mui/icons-material/ManageSearchRounded';
import MicRounded from '@mui/icons-material/MicRounded';
import RadarRounded from '@mui/icons-material/RadarRounded';
import {
  Avatar,
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

const drawerWidth = 288;

const navItems = [
  { label: '工作台', to: '/', icon: <HomeRounded fontSize="small" /> },
  { label: '任务中心', to: '/jobs', icon: <ManageSearchRounded fontSize="small" /> },
  { label: '声纹库', to: '/voiceprints', icon: <MicRounded fontSize="small" /> },
  { label: '模型状态', to: '/system/models', icon: <RadarRounded fontSize="small" /> },
];

function resolveCurrentPage(pathname: string) {
  const matched = navItems.find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`));
  return matched?.label ?? '业务页面';
}

export function AppLayout() {
  const location = useLocation();

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
            borderRight: '1px solid rgba(255,255,255,0.06)',
            px: 2,
            py: 2,
          },
        }}
      >
        <Stack spacing={3} sx={{ height: '100%' }}>
          <Stack spacing={2} sx={{ px: 1.5, pt: 1.5 }}>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Avatar
                sx={{
                  bgcolor: 'primary.main',
                  width: 48,
                  height: 48,
                  fontWeight: 800,
                }}
              >
                VP
              </Avatar>
              <Box>
                <Typography variant="h6" sx={{ color: '#f8fafc' }}>
                  智能语音平台
                </Typography>
                <Typography variant="body2" sx={{ color: alpha('#e2e8f0', 0.72) }}>
                  转写、分离、声纹一体化工作台
                </Typography>
              </Box>
            </Stack>
            <Chip
              size="small"
              label="企业版工作台"
              sx={{
                alignSelf: 'flex-start',
                bgcolor: alpha('#60a5fa', 0.18),
                color: '#bfdbfe',
              }}
            />
          </Stack>

          <List sx={{ px: 0.5 }}>
            {navItems.map((item) => (
              <ListItemButton
                key={item.to}
                component={NavLink}
                to={item.to}
                sx={{
                  borderRadius: 4,
                  px: 2,
                  py: 1.2,
                  mb: 1,
                  color: alpha('#e2e8f0', 0.86),
                  '&.active': {
                    bgcolor: alpha('#2563eb', 0.22),
                    color: '#ffffff',
                    boxShadow: 'inset 0 0 0 1px rgba(96,165,250,0.18)',
                  },
                  '&:hover': {
                    bgcolor: alpha('#ffffff', 0.06),
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

          <Box sx={{ px: 1.5, mt: 'auto' }}>
            <Divider sx={{ borderColor: alpha('#ffffff', 0.08), mb: 2 }} />
            <Stack spacing={0.75}>
              <Typography variant="body2" sx={{ color: alpha('#e2e8f0', 0.66) }}>
                当前页面
              </Typography>
              <Typography variant="subtitle1" sx={{ color: '#f8fafc', fontWeight: 700 }}>
                {resolveCurrentPage(location.pathname)}
              </Typography>
            </Stack>
          </Box>
        </Stack>
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, px: { xs: 2, md: 4 }, py: { xs: 2, md: 4 } }}>
        <Outlet />
      </Box>
    </Box>
  );
}
