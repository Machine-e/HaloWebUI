import { describe, expect, it } from 'vitest';

import { formatConnectionErrorToast, formatModelFetchErrorToast } from './connection-errors';

const t = (key: string) =>
	(
		({
			'Connection failed': 'Connection failed',
			'connection.error.check_key_matches_url': 'Check the API key and URL.',
			'connection.error.model_list_auth_failed':
				'The model-list request was rejected. Add model IDs manually if needed.',
			'error.reason.api_auth_error': 'API key invalid or insufficient permissions',
			'error.title.model_list_auth_failed': 'Model-list authentication failed'
		}) as Record<string, string>
	)[key] ?? key;

describe('connection error formatting', () => {
	it('recognizes upstream invalid token as an API authentication error', () => {
		expect(formatConnectionErrorToast('OpenAI: Invalid token (request id: req_123)', t)).toEqual({
			title: 'OpenAI：API key invalid or insufficient permissions',
			description: 'Check the API key and URL.'
		});
	});

	it('uses a model-list specific message when fetching models is rejected by auth', () => {
		expect(formatModelFetchErrorToast('OpenAI: Invalid token (request id: req_123)', t)).toEqual({
			title: 'OpenAI：Model-list authentication failed',
			description: 'The model-list request was rejected. Add model IDs manually if needed.'
		});
	});

	it('keeps provider context for wrapped upstream authentication payloads', () => {
		expect(
			formatModelFetchErrorToast(
				"OpenAI: External Error: {'message': 'Invalid token (request id: req_123)', 'type': 'invalid_request_error'}",
				t
			)
		).toEqual({
			title: 'OpenAI：Model-list authentication failed',
			description: 'The model-list request was rejected. Add model IDs manually if needed.'
		});
	});
});
