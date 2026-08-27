export const getScreenshotDataUri = (screenshot) => {
	if (typeof screenshot !== 'string') return null;

	const trimmed = screenshot.trim();
	if (!trimmed) return null;

	if (trimmed.startsWith('data:')) {
		return trimmed;
	}

	// Preserve absolute, protocol-relative, and same-origin proxy URLs.
	// Cached screenshots use paths such as /api/v1/history-logs/screenshot?...,
	// whose endpoint path intentionally has no image-file extension.
	if (/^(https?:)?\/\//i.test(trimmed) || trimmed.startsWith('/')) {
		return trimmed;
	}

	const normalized = trimmed.replace(/\s+/g, '').replace(/^data:[^,]+,/, '');
	const looksLikeBase64 =
		normalized.length >= 16
		&& normalized.length % 4 === 0
		&& /^[A-Za-z0-9+/=]+$/.test(normalized);

	if (looksLikeBase64) {
		return `data:image/png;base64,${normalized}`;
	}

	return null;
};
