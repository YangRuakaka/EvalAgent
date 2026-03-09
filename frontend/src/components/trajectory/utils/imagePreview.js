const DEFAULT_MAX_DIMENSION = 320;
const DEFAULT_PREVIEW_QUALITY = 0.72;
const DEFAULT_TIMEOUT_MS = 8000;
const previewCache = new Map();

const clampNumber = (value, min, max, fallback) => {
	const numeric = Number(value);
	if (!Number.isFinite(numeric)) {
		return fallback;
	}
	return Math.min(max, Math.max(min, numeric));
};

const loadImage = (src, timeoutMs = DEFAULT_TIMEOUT_MS) => new Promise((resolve, reject) => {
	if (!src || typeof src !== 'string') {
		reject(new Error('Invalid image source for preview generation.'));
		return;
	}

	const image = new Image();
	image.crossOrigin = 'anonymous';
	image.decoding = 'async';
	image.referrerPolicy = 'no-referrer';

	const timeoutId = window.setTimeout(() => {
		image.src = '';
		reject(new Error('Image preview generation timed out.'));
	}, timeoutMs);

	image.onload = () => {
		window.clearTimeout(timeoutId);
		resolve(image);
	};

	image.onerror = () => {
		window.clearTimeout(timeoutId);
		reject(new Error('Failed to load image for preview generation.'));
	};

	image.src = src;

	if (image.complete && image.naturalWidth > 0 && image.naturalHeight > 0) {
		window.clearTimeout(timeoutId);
		resolve(image);
	}
});

const buildPreviewDataUrl = (image, options = {}) => {
	const maxDimension = clampNumber(options.maxDimension, 96, 1024, DEFAULT_MAX_DIMENSION);
	const quality = clampNumber(options.quality, 0.2, 0.95, DEFAULT_PREVIEW_QUALITY);
	const outputType = typeof options.type === 'string' && options.type.trim()
		? options.type.trim()
		: 'image/webp';

	const sourceWidth = Math.max(1, image.naturalWidth || image.width || 1);
	const sourceHeight = Math.max(1, image.naturalHeight || image.height || 1);
	const largestDimension = Math.max(sourceWidth, sourceHeight);

	if (largestDimension <= maxDimension) {
		return null;
	}

	const scale = maxDimension / largestDimension;
	const targetWidth = Math.max(1, Math.round(sourceWidth * scale));
	const targetHeight = Math.max(1, Math.round(sourceHeight * scale));

	const canvas = document.createElement('canvas');
	canvas.width = targetWidth;
	canvas.height = targetHeight;

	const context = canvas.getContext('2d', { alpha: false });
	if (!context) {
		return null;
	}

	context.imageSmoothingEnabled = true;
	context.imageSmoothingQuality = 'high';
	context.drawImage(image, 0, 0, targetWidth, targetHeight);

	let preview = null;
	try {
		preview = canvas.toDataURL(outputType, quality);
	} catch (error) {
		try {
			preview = canvas.toDataURL('image/jpeg', quality);
		} catch (fallbackError) {
			preview = null;
		}
	}

	if (!preview || typeof preview !== 'string') {
		return null;
	}

	return preview;
};

export const generatePreviewImage = async (src, options = {}) => {
	if (!src || typeof src !== 'string') {
		return src;
	}

	if (typeof window === 'undefined' || typeof document === 'undefined') {
		return src;
	}

	const cacheKey = `${src}::${JSON.stringify({
		maxDimension: options.maxDimension,
		quality: options.quality,
		type: options.type,
	})}`;

	if (previewCache.has(cacheKey)) {
		return previewCache.get(cacheKey);
	}

	try {
		const image = await loadImage(src, options.timeoutMs || DEFAULT_TIMEOUT_MS);
		const preview = buildPreviewDataUrl(image, options);
		const result = preview || src;
		previewCache.set(cacheKey, result);
		return result;
	} catch (error) {
		previewCache.set(cacheKey, src);
		return src;
	}
};

export default generatePreviewImage;