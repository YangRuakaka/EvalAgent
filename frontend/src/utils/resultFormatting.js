const MARKDOWN_FENCE_PATTERN = /^```(?:md|markdown)\s*\n([\s\S]*?)\n```\s*$/i;

export const resultToText = (value) => {
	if (value === undefined || value === null || value === '') {
		return 'No Result';
	}

	if (typeof value === 'string') {
		return value;
	}

	if (typeof value === 'number' || typeof value === 'boolean') {
		return String(value);
	}

	if (typeof value === 'object') {
		const preferredValue = value.markdown
			?? value.content
			?? value.text
			?? value.result
			?? value.final_result
			?? value.output;

		if (preferredValue !== undefined && preferredValue !== value) {
			return resultToText(preferredValue);
		}

		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return String(value);
		}
	}

	return String(value);
};

export const normalizeMarkdownText = (value) => {
	const text = resultToText(value);
	const fencedMarkdown = text.match(MARKDOWN_FENCE_PATTERN);
	return fencedMarkdown ? fencedMarkdown[1].trim() : text;
};

export const looksLikeMarkdown = (value) => {
	const text = resultToText(value);
	if (MARKDOWN_FENCE_PATTERN.test(text)) {
		return true;
	}

	return [
		/^#{1,6}\s+\S/m,
		/^\s{0,3}(?:[-+*]|\d+[.)])\s+\S/m,
		/^\s{0,3}>\s+\S/m,
		/```[\s\S]*```/m,
		/\*\*[^\n*]+\*\*/m,
		/\[[^\]]+\]\([^)]+\)/m,
		/^\s*\|.+\|\s*$\n\s*\|?\s*:?-{3,}/m,
	].some((pattern) => pattern.test(text));
};
