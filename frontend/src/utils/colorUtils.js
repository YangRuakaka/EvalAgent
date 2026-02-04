/**
 * Generate consistent pastel colors from a string ID
 * @param {string} id - The unique identifier for the criteria
 * @returns {Object} An object containing backgroundColor, borderColor, and color
 */
export const getCriteriaColorStyles = (id) => {
	if (!id) {
		return {
			backgroundColor: '#f8fafc',
			borderColor: '#e2e8f0',
			color: '#475569',
		};
	}
	let hash = 0;
	for (let i = 0; i < id.length; i++) {
		hash = id.charCodeAt(i) + ((hash << 5) - hash);
	}
	const hue = Math.abs(hash % 360);
	return {
		backgroundColor: `hsl(${hue}, 85%, 96%)`,
		borderColor: `hsl(${hue}, 60%, 85%)`,
		color: `hsl(${hue}, 70%, 30%)`,
	};
};
