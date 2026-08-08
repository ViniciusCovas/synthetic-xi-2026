import type { Config } from 'tailwindcss'

// Identidad "centro de mando": fondo verde-negro profundo, acento petróleo,
// datos en mono. Las páginas usan solo estos tokens — cambiar la paleta
// entera se hace aquí, sin tocar componentes.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#0a0f0d',
        card: '#111815',
        raise: '#16201c',
        ink: '#edf3f0',
        'ink-2': '#a7b6af',
        mut: '#66756e',
        line: '#1e2a25',
        brand: {
          DEFAULT: '#2fae91',
          soft: '#12332a',
          dark: '#5ecdb2',
        },
        seq: {
          250: '#86b6ef',
          400: '#3987e5',
          550: '#5598e7',
        },
        ok: '#34c759',
        warn: '#e8b13c',
        crit: '#e66767',
      },
      fontFamily: {
        sans: ['"Instrument Sans Variable"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 24px rgba(47, 174, 145, 0.12)',
      },
    },
  },
  plugins: [],
} satisfies Config
