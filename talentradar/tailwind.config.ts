import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#f5f8f6',
        card: '#fdfefd',
        ink: '#0e1613',
        'ink-2': '#47554f',
        mut: '#7d8a85',
        line: '#dce4e0',
        brand: {
          DEFAULT: '#0d7a63',
          soft: '#e2f0ec',
          dark: '#075c4a',
        },
        seq: {
          250: '#86b6ef',
          400: '#3987e5',
          550: '#1c5cab',
        },
        ok: '#0ca30c',
        warn: '#fab219',
        crit: '#d03b3b',
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['ui-monospace', 'SF Mono', 'Cascadia Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
