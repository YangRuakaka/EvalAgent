import { VALUE_VARIATION_OPTIONS } from '../config/constants';

export const getPersonaBaseName = (content) => {
	if (!content) {
		return 'Persona';
	}

	const trimmed = content.trim();
	if (!trimmed) {
		return 'Persona';
	}

	const [firstWord] = trimmed.split(/\s+/);
	return firstWord || 'Persona';
};

export const assignPersonaNames = (personas) => {
	const counts = {};

	return personas.map((persona) => {
		const baseName = getPersonaBaseName(persona.content);
		const nextCount = (counts[baseName] || 0) + 1;
		counts[baseName] = nextCount;
		const suffix = nextCount === 1 ? '' : String(nextCount - 1).padStart(2, '0');

		return { ...persona, name: `${baseName}${suffix}` };
	});
};

export const createDefaultVariationContent = (_personaContent, _valueLabel) => '';

export const VALUE_TAG_OPEN_TOKEN = '__VALUE_TAG_OPEN__';
export const VALUE_TAG_CLOSE_TOKEN = '__VALUE_TAG_CLOSE__';

export const orderVariationEntries = (variationMap) =>
	VALUE_VARIATION_OPTIONS.map((option) => variationMap.get(option.value)).filter(Boolean);

export const escapeHtml = (value) => {
	if (value === null || value === undefined) {
		return '';
	}
	return String(value)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;');
};

export const formatVariationContent = (content, highlightColor) => {
	const safeColor = highlightColor || '#111111';
	const raw = String(content ?? '');
	// Handle both uppercase and lowercase VALUE tags for robustness
	const withTokens = raw
		.split('<VALUE>').join(VALUE_TAG_OPEN_TOKEN)
		.split('</VALUE>').join(VALUE_TAG_CLOSE_TOKEN)
		.split('<value>').join(VALUE_TAG_OPEN_TOKEN)
		.split('</value>').join(VALUE_TAG_CLOSE_TOKEN);
	const escaped = escapeHtml(withTokens);
	return escaped
		.split(VALUE_TAG_OPEN_TOKEN)
		.join(`<span style="color: ${safeColor}; font-weight: 600;">`)
		.split(VALUE_TAG_CLOSE_TOKEN)
		.join('</span>');
};
