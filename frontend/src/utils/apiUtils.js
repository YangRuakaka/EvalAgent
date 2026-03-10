export const getResponseErrorDetail = (response) => {
	if (!response) {
		return 'No response from server';
	}

	if (typeof response.data === 'string') {
		return response.data;
	}

	return response.data?.detail || `HTTP ${response.status}`;
};
