const normalizeCitationList = (value: unknown): any[] => {
	if (Array.isArray(value)) {
		return value;
	}

	if (value === null || value === undefined) {
		return [];
	}

	return [value];
};

export const getCitationDocuments = (citation: any): any[] => {
	return normalizeCitationList(citation?.document ?? citation?.documents);
};

export const getCitationMetadata = (citation: any): any[] => {
	return normalizeCitationList(citation?.metadata);
};

export const getCitationDistances = (citation: any): any[] => {
	return normalizeCitationList(citation?.distances);
};

const getMetadataFallbackDocument = (metadata: any): string => {
	if (!metadata || typeof metadata !== 'object') {
		return '';
	}

	const candidates = [metadata.content, metadata.snippet, metadata.text, metadata.summary];
	for (const candidate of candidates) {
		if (typeof candidate === 'string' && candidate.trim()) {
			return candidate;
		}
	}

	return '';
};

export const getCitationEntries = (citation: any) => {
	const documents = getCitationDocuments(citation);
	const metadata = getCitationMetadata(citation);
	const distances = getCitationDistances(citation);

	const entryCount = Math.max(
		documents.length,
		metadata.length,
		distances.length,
		citation?.source ? 1 : 0
	);

	return Array.from({ length: entryCount }, (_, index) => {
		const document = documents[index];
		const documentText = typeof document === 'string' ? document : `${document ?? ''}`;

		return {
			document: documentText.trim() ? documentText : getMetadataFallbackDocument(metadata[index]),
			metadata: metadata[index],
			distance: distances[index]
		};
	});
};
