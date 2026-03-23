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

	return Array.from({ length: entryCount }, (_, index) => ({
		document: documents[index] ?? '',
		metadata: metadata[index],
		distance: distances[index]
	}));
};
