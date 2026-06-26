type CopyFormattedSettings =
	| {
			copyFormatted?: boolean;
			copyFormattedUserSet?: boolean;
	  }
	| null
	| undefined;

export const resolveCopyFormattedPreference = (settings: CopyFormattedSettings) => {
	return settings?.copyFormattedUserSet ? (settings.copyFormatted ?? true) : true;
};
