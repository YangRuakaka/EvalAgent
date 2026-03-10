export const createBrowserAgentRunId = () => {
	if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
		return crypto.randomUUID();
	}
	return `run_${Date.now()}_${Math.random().toString(16).slice(2)}`;
};

export const extractErrorMessage = (data, fallbackMessage = 'Failed to generate persona. Please try again.') => {
	if (!data) {
		return fallbackMessage;
	}

	if (typeof data === 'string') {
		return data;
	}

	if (data.error_message) {
		return data.error_message;
	}

	if (Array.isArray(data.detail)) {
		const detailMessage = data.detail
			.map((item) => {
				if (!item) {
					return null;
				}
				if (typeof item === 'string') {
					return item;
				}
				if (item.msg) {
					return item.msg;
				}
				return JSON.stringify(item);
			})
			.filter(Boolean)
			.join('; ');

		if (detailMessage) {
			return detailMessage;
		}
	}

	if (typeof data.detail === 'string' && data.detail.trim()) {
		return data.detail;
	}

	if (data.message) {
		return data.message;
	}

	return fallbackMessage;
};
