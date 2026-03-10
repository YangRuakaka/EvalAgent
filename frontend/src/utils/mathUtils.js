export const clamp = (value, min, max) => {
	if (Number.isNaN(value)) {
		return min;
	}

	if (min > max) {
		return min;
	}

	return Math.min(Math.max(value, min), max);
};

export const toRoundedNumber = (value, digits = 0) => {
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) {
		return null;
	}

	return Number(parsed.toFixed(digits));
};
