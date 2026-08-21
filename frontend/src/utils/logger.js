const isDevelopment = process.env.NODE_ENV !== 'production';

export const debugLog = (...args) => {
	if (isDevelopment) {
		console.debug(...args);
	}
};

export const debugInfo = (...args) => {
	if (isDevelopment) {
		console.info(...args);
	}
};
