import { Box, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function MarkdownArticle({ content }: { content: string }) {
  return (
    <Box
      sx={{
        color: 'text.primary',
        lineHeight: 1.72,
        '& h1, & h2, & h3, & h4': {
          mt: 0,
          mb: 1.1,
          lineHeight: 1.2,
          fontWeight: 700,
        },
        '& h1': { fontSize: '1.18rem' },
        '& h2': { fontSize: '1.05rem', mt: 1.7 },
        '& h3': { fontSize: '0.98rem', mt: 1.4 },
        '& p': { my: 0.9, textWrap: 'pretty' },
        '& ul, & ol': {
          my: 0.9,
          pl: 2.4,
        },
        '& li': {
          my: 0.45,
        },
        '& strong': {
          fontWeight: 700,
        },
        '& code': {
          px: 0.55,
          py: 0.2,
          borderRadius: 1.5,
          bgcolor: alpha('#1c2431', 0.06),
          fontFamily: '"JetBrains Mono", "Consolas", monospace',
          fontSize: '0.86em',
        },
        '& pre': {
          m: 0,
          p: 1.4,
          borderRadius: 3,
          overflow: 'auto',
          bgcolor: alpha('#1c2431', 0.04),
        },
        '& pre code': {
          p: 0,
          bgcolor: 'transparent',
        },
        '& blockquote': {
          m: 0,
          my: 1.1,
          px: 1.4,
          py: 0.6,
          borderLeft: '3px solid',
          borderColor: alpha('#2f6fed', 0.45),
          color: 'text.secondary',
          bgcolor: alpha('#2f6fed', 0.03),
          borderRadius: 2,
        },
        '& hr': {
          border: 0,
          borderTop: '1px solid',
          borderColor: alpha('#1c2431', 0.08),
          my: 1.5,
        },
        '& table': {
          width: '100%',
          borderCollapse: 'collapse',
          my: 1.2,
          fontSize: '0.92rem',
        },
        '& th, & td': {
          borderBottom: '1px solid',
          borderColor: alpha('#1c2431', 0.08),
          px: 1,
          py: 0.8,
          textAlign: 'left',
        },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <Typography component="p" variant="body2">{children}</Typography>,
        }}
      >
        {content}
      </ReactMarkdown>
    </Box>
  );
}
