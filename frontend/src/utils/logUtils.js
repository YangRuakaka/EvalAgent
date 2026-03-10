export const normalizeLogEntries = (value) => {
	if (!Array.isArray(value)) {
		return [];
	}

	return value
		.map((item) => (typeof item === 'string' ? item : (item === null || item === undefined ? '' : String(item))))
		.map((item) => item.trim())
		.filter(Boolean);
};

export const computeSuffixPrefixOverlap = (existing, incoming) => {
	if (!Array.isArray(existing) || !Array.isArray(incoming) || existing.length === 0 || incoming.length === 0) {
		return 0;
	}

	const maxOverlap = Math.min(existing.length, incoming.length);
	for (let overlap = maxOverlap; overlap > 0; overlap -= 1) {
		let isMatch = true;
		for (let index = 0; index < overlap; index += 1) {
			if (existing[existing.length - overlap + index] !== incoming[index]) {
				isMatch = false;
				break;
			}
		}

		if (isMatch) {
			return overlap;
		}
	}

	return 0;
};

export const mergeRunLogs = ({ existingLogs, snapshotLogs, appendLogs }) => {
	let merged = Array.isArray(existingLogs) ? existingLogs : [];

	if (Array.isArray(snapshotLogs) && snapshotLogs.length > 0) {
		const overlap = computeSuffixPrefixOverlap(merged, snapshotLogs);
		if (overlap < snapshotLogs.length) {
			merged = merged.concat(snapshotLogs.slice(overlap));
		}
	}

	if (Array.isArray(appendLogs) && appendLogs.length > 0) {
		const overlap = computeSuffixPrefixOverlap(merged, appendLogs);
		if (overlap < appendLogs.length) {
			merged = merged.concat(appendLogs.slice(overlap));
		}
	}

	return merged;
};
