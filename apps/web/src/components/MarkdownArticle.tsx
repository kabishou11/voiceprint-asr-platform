import { Box, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function MarkdownArticle({ content }: { content: string }) {
  return (
    <Box
      sx={{
        color: 'text.primary',
        lineHeight: 1.8,
        maxWidth: 780,
        '& h1': {
          fontSize: '1.28rem',
          fontWeight: 700,
          mt: 0,
          mb: 1.2,
          pb: 0.8,
          borderBottom: '2px solid',
          borderColor: alpha('#2f6fed', 0.18),
          lineHeight: 1.25,
        },
        '& h2': {
          fontSize: '1.1rem',
          fontWeight: 700,
          mt: 2,
          mb: 1,
          pb: 0.6,
          borderBottom: '1px solid',
          borderColor: alpha('#1c2431', 0.08),
          lineHeight: 1.25,
        },
        '& h3': {
          fontSize: '1rem',
          fontWeight: 700,
          mt: 1.6,
          mb: 0.8,
          lineHeight: 1.3,
        },
        '& h4': {
          fontSize: '0.95rem',
          fontWeight: 700,
          mt: 1.3,
          mb: 0.6,
          lineHeight: 1.3,
        },
        '& p': {
          my: 0.85,
          textWrap: 'pretty',
        },
        '& ul, & ol': {
          my: 0.85,
          pl: 2.4,
        },
        '& li': {
          my: 0.4,
          pl: 0.4,
          position: 'relative',
          '&::marker': {
            color: alpha('#2f6fed', 0.6),
          },
        },
        '& strong': {
          fontWeight: 700,
        },
        '& em': {
          fontStyle: 'italic',
        },
        '& code': {
          px: 0.55,
          py: 0.18,
          borderRadius: 1.5,
          bgcolor: alpha('#1c2431', 0.06),
          fontFamily: '"JetBrains Mono", "Consolas", monospace',
          fontSize: '0.86em',
        },
        '& pre': {
          m: 0,
          my: 1.2,
          p: 1.4,
          borderRadius: 3,
          overflow: 'auto',
          bgcolor: alpha('#1c2431', 0.04),
          border: '1px solid',
          borderColor: alpha('#1c2431', 0.06),
        },
        '& pre code': {
          p: 0,
          bgcolor: 'transparent',
        },
        '& blockquote': {
          m: 0,
          my: 1.1,
          px: 1.6,
          py: 0.7,
          borderLeft: '3px solid',
          borderColor: alpha('#2f6fed', 0.45),
          color: 'text.secondary',
          bgcolor: alpha('#2f6fed', 0.03),
          borderRadius: '0 8px 8px 0',
          fontStyle: 'italic',
        },
        '& hr': {
          border: 0,
          borderTop: '1px solid',
          borderColor: alpha('#1c2431', 0.08),
          my: 1.8,
        },
        '& table': {
          width: '100%',
          borderCollapse: 'collapse',
          my: 1.2,
          fontSize: '0.92rem',
        },
        '& thead': {
          bgcolor: alpha('#1c2431', 0.04),
        },
        '& th': {
          borderBottom: '2px solid',
          borderColor: alpha('#1c2431', 0.12),
          px: 1,
          py: 0.75,
          textAlign: 'left',
          fontWeight: 700,
          fontSize: '0.88rem',
        },
        '& td': {
          borderBottom: '1px solid',
          borderColor: alpha('#1c2431', 0.06),
          px: 1,
          py: 0.7,
          textAlign: 'left',
        },
        '& tr:nth-of-type(even) td': {
          bgcolor: alpha('#1c2431', 0.015),
        },
        '& a': {
          color: '#2f6fed',
          textDecoration: 'none',
          '&:hover': {
            textDecoration: 'underline',
          },
        },
        '& img': {
          maxWidth: '100%',
          borderRadius: 2,
        },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <Typography component="p" variant="body1" sx={{ lineHeight: 1.8 }}>
              {children}
            </Typography>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </Box>
  );
}
