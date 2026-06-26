import { WEBUI_API_BASE_URL } from '$lib/constants';
import { getTimeRange } from '$lib/utils';
import { parseJsonResponse } from '../response';

export const createNewChat = async (
	token: string,
	chat: object,
	folderId: string | null = null,
	assistantId: string | null = null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/new`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			chat: chat,
			folder_id: folderId ?? null,
			assistant_id: assistantId ?? null
		})
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const importChat = async (
	token: string,
	chat: object,
	meta: object | null,
	pinned?: boolean,
	folderId?: string | null,
	assistantId?: string | null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/import`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			chat: chat,
			meta: meta ?? {},
			pinned: pinned,
			folder_id: folderId,
			assistant_id: assistantId ?? null
		})
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const importChatsBatch = async (
	token: string,
	items: Array<{
		chat: object;
		meta?: object | null;
		pinned?: boolean;
		folder_id?: string | null;
		assistant_id?: string | null;
	}>,
	mode: 'merge' | 'replace' = 'merge'
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/import/batch`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			items,
			mode
		})
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatList = async (token: string = '', page: number | null = null) => {
	let error = null;
	const searchParams = new URLSearchParams();

	if (page !== null) {
		searchParams.append('page', `${page}`);
	}

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/?${searchParams.toString()}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};

export const getChatListByUserId = async (token: string = '', userId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/list/user/${userId}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};

export const getArchivedChatList = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/archived`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};

export const getAllChats = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/all`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatListBySearchText = async (token: string, text: string, page: number = 1) => {
	let error = null;

	const searchParams = new URLSearchParams();
	searchParams.append('text', text);
	searchParams.append('page', `${page}`);

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/search?${searchParams.toString()}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};

export const getChatsByFolderId = async (token: string, folderId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/folder/${folderId}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatListByFolderId = async (token: string, folderId: string, page: number = 1) => {
	let error = null;

	const searchParams = new URLSearchParams();
	searchParams.append('page', `${page}`);

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/chats/folder/${folderId}/list?${searchParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				...(token && { authorization: `Bearer ${token}` })
			}
		}
	)
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatListByAssistantId = async (
	token: string,
	assistantId: string,
	page: number = 1
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	searchParams.append('page', `${page}`);

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/chats/assistant/${assistantId}/list?${searchParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				...(token && { authorization: `Bearer ${token}` })
			}
		}
	)
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};

export const getAllArchivedChats = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/all/archived`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getAllUserChats = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/all/db`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getAllTags = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/all/tags`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getPinnedChatList = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/pinned`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};

export const getChatListByTagName = async (token: string = '', tagName: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/tags`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			name: tagName
		})
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res.map((chat) => ({
		...chat,
		time_range: getTimeRange(chat.updated_at)
	}));
};

export const getChatById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatContextById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/context`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return (
		res ?? {
			tags: [],
			task_ids: [],
			tasks: []
		}
	);
};

export const getSharedChatList = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/shared`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatByShareId = async (token: string, share_id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/share/${share_id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getChatPinnedStatusById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/pinned`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const toggleChatPinnedStatusById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/pin`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const cloneChatById = async (token: string, id: string, title?: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/clone`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			...(title && { title: title })
		})
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const branchChatById = async (
	token: string,
	id: string,
	branchPointMessageId: string,
	title?: string
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/branch`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			branch_point_message_id: branchPointMessageId,
			...(title ? { title } : {})
		})
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const cloneSharedChatById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/clone/shared`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			if ('detail' in err) {
				error = err.detail;
			} else {
				error = err;
			}

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const shareChatById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/share`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateChatFolderIdById = async (
	token: string,
	id: string,
	folderId: string | null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/folder`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			folder_id: folderId ?? null
		})
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const archiveChatById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/archive`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteSharedChatById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/share`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateChatById = async (token: string, id: string, chat: object) => {
	let error = null;
	const chatId = `${id ?? ''}`.trim();
	if (!chatId) {
		throw new Error('Missing chat id.');
	}

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${encodeURIComponent(chatId)}`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			chat: chat
		})
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateChatTitleById = async (token: string, id: string, title: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/title`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			title: title
		})
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateChatComposerStateById = async (
	token: string,
	id: string,
	composerState: object
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/composer-state`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			composer_state: composerState
		})
	})
		.then(parseJsonResponse)
		.then((json) => json)
		.catch((err) => {
			error = err;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteChatById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getTagsById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/tags`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const addTagById = async (token: string, id: string, tagName: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/tags`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			name: tagName
		})
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteTagById = async (token: string, id: string, tagName: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/tags`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			name: tagName
		})
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
export const deleteTagsById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/${id}/tags/all`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteAllChats = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const archiveAllChats = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/chats/archive/all`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(parseJsonResponse)
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

// [REACTION_FEATURE] Commented out - reaction feature disabled for now
// export const getChatMessageReactions = async (
// 	token: string,
// 	chatId: string,
// 	messageId: string
// ) => {
// 	let error = null;
//
// 	const res = await fetch(
// 		`${WEBUI_API_BASE_URL}/chats/${chatId}/messages/${messageId}/reactions`,
// 		{
// 			method: 'GET',
// 			headers: {
// 				Accept: 'application/json',
// 				'Content-Type': 'application/json',
// 				...(token && { authorization: `Bearer ${token}` })
// 			}
// 		}
// 	)
// 		.then(async (res) => {
// 			if (!res.ok) throw await res.json();
// 			return res.json();
// 		})
// 		.catch((err) => {
// 			error = err;
// 			console.log(err);
// 			return null;
// 		});
//
// 	if (error) {
// 		throw error;
// 	}
//
// 	return res;
// };
//
// export const addChatMessageReaction = async (
// 	token: string,
// 	chatId: string,
// 	messageId: string,
// 	name: string
// ) => {
// 	let error = null;
//
// 	const res = await fetch(
// 		`${WEBUI_API_BASE_URL}/chats/${chatId}/messages/${messageId}/reactions/add`,
// 		{
// 			method: 'POST',
// 			headers: {
// 				Accept: 'application/json',
// 				'Content-Type': 'application/json',
// 				...(token && { authorization: `Bearer ${token}` })
// 			},
// 			body: JSON.stringify({ name })
// 		}
// 	)
// 		.then(async (res) => {
// 			if (!res.ok) throw await res.json();
// 			return res.json();
// 		})
// 		.catch((err) => {
// 			error = err;
// 			console.log(err);
// 			return null;
// 		});
//
// 	if (error) {
// 		throw error;
// 	}
//
// 	return res;
// };
//
// export const removeChatMessageReaction = async (
// 	token: string,
// 	chatId: string,
// 	messageId: string,
// 	name: string
// ) => {
// 	let error = null;
//
// 	const res = await fetch(
// 		`${WEBUI_API_BASE_URL}/chats/${chatId}/messages/${messageId}/reactions/remove`,
// 		{
// 			method: 'POST',
// 			headers: {
// 				Accept: 'application/json',
// 				'Content-Type': 'application/json',
// 				...(token && { authorization: `Bearer ${token}` })
// 			},
// 			body: JSON.stringify({ name })
// 		}
// 	)
// 		.then(async (res) => {
// 			if (!res.ok) throw await res.json();
// 			return res.json();
// 		})
// 		.catch((err) => {
// 			error = err;
// 			console.log(err);
// 			return null;
// 		});
//
// 	if (error) {
// 		throw error;
// 	}
//
// 	return res;
// };
