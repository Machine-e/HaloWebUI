export interface ConnectionErrorToastContent {
	title: string;
	description?: string;
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

const PROVIDER_PREFIX_RE = /^(OpenAI|Gemini|Anthropic|Ollama):\s*/;
const INVALID_API_KEY_RE =
	/invalid_api_key|Incorrect API key provided|invalid api key|authentication failed|unauthorized/i;
const RESPONSES_API_ERROR_RE = /responses api|\/responses/i;
const HTTP_STATUS_RES = [
	/Responses API upstream error \((\d{3})\)/i,
	/\bHTTP\s*(\d{3})\b/i,
	/\bstatus\s*[:=]\s*(\d{3})\b/i
];
const INVALID_PARAM_RES = [
	/Invalid ['"]([^'"]+)['"]/i,
	/Unknown parameter:\s*['"]([^'"]+)['"]/i,
	/['"]param['"]\s*:\s*['"]([^'"]+)['"]/i
];
const MIN_VALUE_RE =
	/Expected a value >=\s*([0-9]+(?:\.[0-9]+)?)\s*,?\s*but got\s*([0-9]+(?:\.[0-9]+)?)/i;

const getRawErrorText = (error: unknown): string =>
	error instanceof Error ? error.message : typeof error === 'string' ? error : `${error ?? ''}`;

const localizeKnownFragments = (text: string, t: Translate): string =>
	text
		.replaceAll('URL is required', t('URL is required'))
		.replaceAll('Network Problem', t('Network Problem'))
		.replaceAll('Open WebUI: Server Connection Error', t('Open WebUI: Server Connection Error'));

const stripTransportWrappers = (text: string): string =>
	text
		.replace(/^Unexpected error:\s*/i, '')
		.replace(/^External Error:\s*/i, '')
		.trim();

const extractPayloadMessage = (text: string): string => {
	const messageMatch = text.match(/['"]message['"]:\s*['"]([\s\S]*?)['"],\s*['"]type['"]/);
	return messageMatch?.[1] ?? text;
};

const normalizeWhitespace = (text: string): string =>
	text
		.replaceAll('\\n', ' ')
		.replace(/\s+/g, ' ')
		.trim();

const extractStatusCode = (text: string): number | null => {
	for (const pattern of HTTP_STATUS_RES) {
		const match = text.match(pattern);
		if (!match) continue;
		const status = Number(match[1]);
		if (Number.isFinite(status) && status >= 400) return status;
	}
	return null;
};

const extractInvalidParam = (text: string): string | null => {
	for (const pattern of INVALID_PARAM_RES) {
		const match = text.match(pattern);
		if (match?.[1]) return match[1];
	}
	return null;
};

const extractMinValueRange = (text: string): { expected: string; actual: string } | null => {
	const match = text.match(MIN_VALUE_RE);
	if (!match) return null;
	return {
		expected: match[1],
		actual: match[2]
	};
};

export const formatConnectionErrorToast = (
	error: unknown,
	t: Translate
): ConnectionErrorToastContent => {
	const raw = getRawErrorText(error);
	const providerMatch = raw.match(PROVIDER_PREFIX_RE);
	const providerPrefix = providerMatch ? `${providerMatch[1]}：` : '';
	const providerStripped = providerMatch ? raw.slice(providerMatch[0].length) : raw;
	const simplifiedDetail = normalizeWhitespace(
		extractPayloadMessage(stripTransportWrappers(providerStripped))
	);
	const localizedSimpleDetail = localizeKnownFragments(simplifiedDetail, t);

	if (INVALID_API_KEY_RE.test(providerStripped)) {
		return {
			title: `${providerPrefix}${t('error.reason.api_auth_error')}`,
			description: t('connection.error.check_key_matches_url')
		};
	}

	if (RESPONSES_API_ERROR_RE.test(providerStripped)) {
		const status = extractStatusCode(providerStripped) ?? extractStatusCode(simplifiedDetail);
		const param = extractInvalidParam(providerStripped) ?? extractInvalidParam(simplifiedDetail);
		const minValue = extractMinValueRange(providerStripped) ?? extractMinValueRange(simplifiedDetail);

		if (param) {
			return {
				title: `${providerPrefix}${t('error.title.responses_api_invalid_parameter', { param })}`,
				description: minValue
					? t('error.body.responses_api_min_value', {
							param,
							expected: minValue.expected,
							actual: minValue.actual
						})
					: t('error.suggestion.check_responses_api_compat')
			};
		}

		return {
			title: `${providerPrefix}${
				status
					? t('error.title.responses_api_request_failed_with_status', { status })
					: t('error.title.responses_api_request_failed')
			}`,
			description: localizedSimpleDetail !== simplifiedDetail ? localizedSimpleDetail : undefined
		};
	}

	if (
		localizedSimpleDetail === t('URL is required') ||
		localizedSimpleDetail === t('Network Problem') ||
		localizedSimpleDetail === t('Open WebUI: Server Connection Error')
	) {
		return {
			title: providerPrefix ? `${providerPrefix}${localizedSimpleDetail}` : localizedSimpleDetail
		};
	}

	if (
		/Unexpected error:|External Error:/.test(providerStripped) ||
		providerStripped.includes("{'message':") ||
		providerStripped.includes('{"message":')
	) {
		return {
			title: providerPrefix ? `${providerPrefix}${t('Connection failed')}` : t('Connection failed'),
			description: localizedSimpleDetail
		};
	}

	const fallback = localizeKnownFragments(providerStripped, t);
	return {
		title: providerPrefix ? `${providerPrefix}${fallback}` : fallback
	};
};
