import { describe, expect, it } from 'vitest';

import { getModelChatDisplayName } from './model-display';

describe('getModelChatDisplayName', () => {
	it('shows function pipe models with the connection suffix', () => {
		expect(
			getModelChatDisplayName({
				id: 'official_pipe.model_id_1',
				name: 'model_1',
				connection_name: 'Official Pipe'
			})
		).toBe('model_1 | Official Pipe');
	});
});
