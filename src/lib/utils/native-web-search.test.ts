import { describe, expect, it } from 'vitest';

import {
	buildWebSearchModeOptions,
	getSmartWebSearchRouteLabel,
	resolveConfiguredDefaultWebSearchMode
} from './native-web-search';

const t = (key: string) => key;
const zhT = (key: string) =>
	(
		({
			'Smart Web Search': '智能联网搜索',
			'Smart · Model Native': '智能 · 原生优先',
			'Smart · HaloWebUI': '智能 · HaloWebUI',
			Recommended: '推荐'
		}) as Record<string, string>
	)[key] ?? key;

describe('native web search mode options', () => {
	it('offers smart web search when only HaloWebUI search is enabled', () => {
		const options = buildWebSearchModeOptions(
			t,
			{
				features: {
					enable_halo_web_search: true,
					enable_native_web_search: false
				}
			},
			[{ id: 'local-model', owned_by: 'anthropic' }]
		);

		expect(options.map((option) => option.value)).toContain('auto');
		expect(options.find((option) => option.value === 'auto')?.disabled).toBeFalsy();
		expect(options.find((option) => option.value === 'native')).toBeUndefined();
	});

	it('keeps smart web search disabled when no route can search', () => {
		const options = buildWebSearchModeOptions(
			t,
			{
				features: {
					enable_halo_web_search: false,
					enable_native_web_search: true
				}
			},
			[{ id: 'local-model', owned_by: 'anthropic' }]
		);

		expect(options.find((option) => option.value === 'auto')?.disabled).toBe(true);
	});

	it('labels smart web search as model-native first for supported models', () => {
		const config = {
			features: {
				enable_halo_web_search: true,
				enable_native_web_search: true
			}
		};
		const models = [{ id: 'gpt-5.5', owned_by: 'openai' }];
		const options = buildWebSearchModeOptions(t, config, models);
		const auto = options.find((option) => option.value === 'auto');

		expect(auto?.shortLabel).toBe('Smart · Model Native');
		expect(auto?.description).toBe('自动判断是否需要联网，适合日常使用。');
		expect(getSmartWebSearchRouteLabel(t, config, models)).toBe('Smart · Model Native');
	});

	it('keeps smart web search on HaloWebUI for unverified compatible models', () => {
		const config = {
			features: {
				enable_halo_web_search: true,
				enable_native_web_search: true
			}
		};
		const models = [{ id: 'future-model', owned_by: 'openai' }];
		const options = buildWebSearchModeOptions(t, config, models);
		const auto = options.find((option) => option.value === 'auto');

		expect(auto?.shortLabel).toBe('Smart · HaloWebUI');
		expect(auto?.description).toBe('自动判断是否需要联网，适合日常使用。');
		expect(auto?.disabled).toBeFalsy();
	});

	it('uses concise Chinese labels and descriptions for all web search modes', () => {
		const options = buildWebSearchModeOptions(
			zhT,
			{
				features: {
					enable_halo_web_search: true,
					enable_native_web_search: true
				}
			},
			[{ id: 'gpt-5.5', owned_by: 'openai' }]
		);

		expect(options.find((option) => option.value === 'off')).toMatchObject({
			label: '关闭联网',
			description: '本次对话不联网。'
		});
		expect(options.find((option) => option.value === 'halo')).toMatchObject({
			label: 'HaloWebUI 搜索',
			description: '使用 HaloWebUI 搜索网页。'
		});
		expect(options.find((option) => option.value === 'native')).toMatchObject({
			label: '模型原生联网',
			description: '使用模型自带的联网搜索。'
		});
		expect(options.find((option) => option.value === 'auto')).toMatchObject({
			label: '智能联网搜索',
			shortLabel: '智能 · 原生优先',
			description: '自动判断是否需要联网，适合日常使用。'
		});
	});

	it('does not automatically try unverified native-only models', () => {
		const options = buildWebSearchModeOptions(
			t,
			{
				features: {
					enable_halo_web_search: false,
					enable_native_web_search: true
				}
			},
			[{ id: 'future-model', owned_by: 'openai' }]
		);

		expect(options.find((option) => option.value === 'auto')?.disabled).toBe(true);
		expect(options.find((option) => option.value === 'native')?.disabled).toBeFalsy();
	});

	it('keeps new chats off when the admin default is missing or off', () => {
		expect(
			resolveConfiguredDefaultWebSearchMode(
				t,
				{
					features: {
						enable_halo_web_search: true,
						enable_native_web_search: true
					}
				},
				[{ id: 'gpt-5', owned_by: 'openai' }],
				true
			)
		).toBe('off');

		expect(
			resolveConfiguredDefaultWebSearchMode(
				t,
				{
					features: {
						enable_halo_web_search: true,
						enable_native_web_search: true,
						default_web_search_mode: 'off'
					}
				},
				[{ id: 'gpt-5', owned_by: 'openai' }],
				true
			)
		).toBe('off');
	});

	it('uses the configured smart default only when a search route is available', () => {
		expect(
			resolveConfiguredDefaultWebSearchMode(
				t,
				{
					features: {
						enable_halo_web_search: true,
						enable_native_web_search: false,
						default_web_search_mode: 'auto'
					}
				},
				[{ id: 'local-model', owned_by: 'anthropic' }],
				true
			)
		).toBe('auto');

		expect(
			resolveConfiguredDefaultWebSearchMode(
				t,
				{
					features: {
						enable_halo_web_search: false,
						enable_native_web_search: false,
						default_web_search_mode: 'auto'
					}
				},
				[{ id: 'local-model', owned_by: 'anthropic' }],
				true
			)
		).toBe('off');
	});

	it('falls back to off when the configured native default cannot be used', () => {
		expect(
			resolveConfiguredDefaultWebSearchMode(
				t,
				{
					features: {
						enable_halo_web_search: true,
						enable_native_web_search: false,
						default_web_search_mode: 'native'
					}
				},
				[{ id: 'gpt-5', owned_by: 'openai' }],
				true
			)
		).toBe('off');

		expect(
			resolveConfiguredDefaultWebSearchMode(
				t,
				{
					features: {
						enable_halo_web_search: true,
						enable_native_web_search: true,
						default_web_search_mode: 'native'
					}
				},
				[{ id: 'local-model', owned_by: 'anthropic' }],
				true
			)
		).toBe('off');
	});

	it('keeps new chats off when the user cannot use web search', () => {
		expect(
			resolveConfiguredDefaultWebSearchMode(
				t,
				{
					features: {
						enable_halo_web_search: true,
						enable_native_web_search: true,
						default_web_search_mode: 'auto'
					}
				},
				[{ id: 'gpt-5', owned_by: 'openai' }],
				false
			)
		).toBe('off');
	});
});
