import typography from '@tailwindcss/typography';
import containerQuries from '@tailwindcss/container-queries';

/** @type {import('tailwindcss').Config} */
export default {
	darkMode: 'class',
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			colors: {
				primary: {
					50: 'var(--color-primary-50, #eff6ff)',
					100: 'var(--color-primary-100, #dbeafe)',
					200: 'var(--color-primary-200, #bfdbfe)',
					300: 'var(--color-primary-300, #93c5fd)',
					400: 'var(--color-primary-400, #60a5fa)',
					500: 'var(--color-primary-500, #3b82f6)',
					600: 'var(--color-primary-600, #2563eb)',
					700: 'var(--color-primary-700, #1d4ed8)',
					800: 'var(--color-primary-800, #1e40af)',
					900: 'var(--color-primary-900, #1e3a8a)',
					950: 'var(--color-primary-950, #172554)'
				},
				gray: {
					50: 'var(--color-gray-50, #f9f9f9)',
					100: 'var(--color-gray-100, #ececec)',
					200: 'var(--color-gray-200, #e3e3e3)',
					300: 'var(--color-gray-300, #cdcdcd)',
					400: 'var(--color-gray-400, #b4b4b4)',
					500: 'var(--color-gray-500, #9b9b9b)',
					600: 'var(--color-gray-600, #676767)',
					700: 'var(--color-gray-700, #4e4e4e)',
					800: 'var(--color-gray-800, #333)',
					850: 'var(--color-gray-850, #262626)',
					900: 'var(--color-gray-900, #171717)',
					950: 'var(--color-gray-950, #0d0d0d)'
				}
			},
			fontFamily: {
				sans: [
					'HarmonyOS Sans',
					'HarmonyOS Sans SC',
					'Segoe UI',
					'-apple-system',
					'BlinkMacSystemFont',
					'PingFang SC',
					'ui-sans-serif',
					'system-ui',
					'Roboto',
					'Helvetica Neue',
					'Arial',
					'Noto Sans',
					'Hiragino Sans GB',
					'Microsoft YaHei UI',
					'Microsoft YaHei',
					'Source Han Sans CN',
					'WenQuanYi Micro Hei',
					'sans-serif',
					'Apple Color Emoji',
					'Segoe UI Emoji',
					'Segoe UI Symbol',
					'Noto Color Emoji'
				]
			},
			typography: {
				DEFAULT: {
					css: {
						pre: false,
						code: false,
						'pre code': false,
						'code::before': false,
						'code::after': false
					}
				}
			},
			padding: {
				'safe-bottom': 'env(safe-area-inset-bottom)'
			}
		}
	},
	plugins: [typography, containerQuries]
};
