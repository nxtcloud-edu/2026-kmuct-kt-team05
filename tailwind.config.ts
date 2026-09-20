import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/ui/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // 경로 모드별 색. 색상만으로 구분하지 않고 선 스타일/아이콘도 함께 쓴다.
        route: {
          fastest: '#2563eb',       // blue-600
          stairs: '#7c3aed',        // violet-600
          barrier: '#059669',       // emerald-600
          dry: '#0891b2',           // cyan-600
        },
        ink: {
          DEFAULT: '#0f172a',
          soft: '#475569',
          faint: '#94a3b8',
        },
      },
      fontFamily: {
        sans: [
          'var(--font-sans)',
          'system-ui',
          '"Malgun Gothic"',
          '"Apple SD Gothic Neo"',
          'sans-serif',
        ],
      },
      keyframes: {
        'draw-path': {
          from: { strokeDashoffset: '1200' },
          to: { strokeDashoffset: '0' },
        },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-pin': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.55', transform: 'scale(1.35)' },
        },
      },
      animation: {
        'draw-path': 'draw-path 420ms cubic-bezier(0.22, 1, 0.36, 1) forwards',
        'fade-up': 'fade-up 220ms ease-out both',
        'pulse-pin': 'pulse-pin 1.8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};

export default config;
