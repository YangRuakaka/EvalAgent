const DEFAULT_HASH_SIZE = 16;
const hashCache = new Map();

const bufferToHex = (buffer) => {
	const bytes = new Uint8Array(buffer);
	const hex = [];
	bytes.forEach((byte) => {
		hex.push(byte.toString(16).padStart(2, '0'));
	});
	return hex.join('');
};

const loadImage = (src) => {
	return new Promise((resolve, reject) => {
		if (!src) {
			reject(new Error('Invalid image source for hashing.'));
			return;
		}

		const image = new Image();
		image.crossOrigin = 'Anonymous';
		image.decoding = 'async';
		image.referrerPolicy = 'no-referrer';

		image.onload = () => resolve(image);
		image.onerror = (event) => {
			reject(new Error(`Failed to load image for hashing: ${src} (${event?.message || 'unknown error'})`));
		};

		// Add timeout to prevent hanging indefinitely
		setTimeout(() => {
			if (!image.complete) {
				// Stop loading
				image.src = '';
				reject(new Error('Image load timed out'));
			}
		}, 5000); // 5 seconds timeout

		image.src = src;

		if (image.complete && image.naturalWidth !== 0) {
			resolve(image);
		}
	});
};

const computeAverageHash = (image, size) => {
	const dimension = size;
	const canvas = document.createElement('canvas');
	canvas.width = dimension;
	canvas.height = dimension;
	const context = canvas.getContext('2d', { willReadFrequently: true });

	if (!context) {
		throw new Error('Failed to acquire 2D context for image hashing.');
	}

	context.drawImage(image, 0, 0, dimension, dimension);

	let imageData;

	try {
		imageData = context.getImageData(0, 0, dimension, dimension);
	} catch (error) {
		throw new Error(`Unable to read image data for hashing (possible CORS issue): ${error.message}`);
	}

	const grayscale = new Float32Array(dimension * dimension);

	for (let i = 0; i < imageData.data.length; i += 4) {
		const r = imageData.data[i];
		const g = imageData.data[i + 1];
		const b = imageData.data[i + 2];
		grayscale[i / 4] = 0.299 * r + 0.587 * g + 0.114 * b;
	}

	const average = grayscale.reduce((sum, value) => sum + value, 0) / grayscale.length;

	let bits = '';
	for (let i = 0; i < grayscale.length; i += 1) {
		bits += grayscale[i] >= average ? '1' : '0';
	}

	const chunkSize = 4;
	let hash = '';
	for (let i = 0; i < bits.length; i += chunkSize) {
		const chunk = bits.slice(i, i + chunkSize);
		hash += parseInt(chunk, 2).toString(16);
	}

	return hash.padEnd(Math.ceil((dimension * dimension) / chunkSize), '0');
};

const hashStringFallback = async (value) => {
	if (!value) {
		return '0';
	}

	if (typeof window !== 'undefined' && window.crypto?.subtle) {
		try {
			const encoder = new TextEncoder();
			const buffer = encoder.encode(value);
			const digest = await window.crypto.subtle.digest('SHA-1', buffer);
			return bufferToHex(digest);
		} catch (error) {
			// fall through to manual hash
		}
	}

	let hash = 0;

	for (let i = 0; i < value.length; i += 1) {
		hash = (hash << 5) - hash + value.charCodeAt(i);
		hash |= 0;
	}

	return Math.abs(hash).toString(16);
};

export const computeImageHash = async (src, options = {}) => {
	const key = `${src}::${options.hashSize || DEFAULT_HASH_SIZE}`;

	if (hashCache.has(key)) {
		return hashCache.get(key);
	}

	const size = options.hashSize || DEFAULT_HASH_SIZE;

	try {
		const image = await loadImage(src);
		const hash = computeAverageHash(image, size);
		hashCache.set(key, hash);
		return hash;
	} catch (error) {
		const fallback = await hashStringFallback(src);
		hashCache.set(key, fallback);
		return fallback;
	}
};

export const hammingDistance = (hashA, hashB) => {
	if (!hashA && !hashB) {
		return 0;
	}

	if (!hashA || !hashB) {
		return Math.max(hashA?.length || 0, hashB?.length || 0) * 4;
	}

	const a = hashA.padEnd(Math.max(hashA.length, hashB.length), '0');
	const b = hashB.padEnd(Math.max(hashA.length, hashB.length), '0');

	let distance = 0;

	for (let i = 0; i < a.length; i += 1) {
		const digitA = parseInt(a[i], 16);
		const digitB = parseInt(b[i], 16);
		const xor = digitA ^ digitB;
		distance += xor.toString(2).replace(/0/g, '').length;
	}

	return distance;
};

export const hashesAreSimilar = (hashA, hashB, threshold = 8) => {
	return hammingDistance(hashA, hashB) <= threshold;
};

export default computeImageHash;
