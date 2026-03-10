const DEFAULT_HASH_SIZE = 16;
const DEFAULT_BORDER_IGNORE_RATIO = 0.08;
const hashCache = new Map();
const WORKER_TIMEOUT_MS = 12000;

let hashWorker = null;
let workerRequestId = 0;
const pendingWorkerRequests = new Map();

const WORKER_SOURCE = `
self.onmessage = async (event) => {
	const payload = event && event.data ? event.data : {};
	const id = payload.id;
	const src = payload.src;
	const size = Number.isFinite(payload.size) ? payload.size : 16;
	const borderIgnoreRatio = Number.isFinite(payload.borderIgnoreRatio)
		? Math.min(Math.max(payload.borderIgnoreRatio, 0), 0.3)
		: 0.08;

	const respond = (message) => {
		self.postMessage({ id, ...message });
	};

	try {
		if (!src || typeof src !== 'string') {
			throw new Error('Invalid image source for hashing.');
		}

		if (typeof createImageBitmap === 'undefined' || typeof OffscreenCanvas === 'undefined') {
			throw new Error('Worker image APIs are not available in this environment.');
		}

		const response = await fetch(src);
		if (!response.ok) {
			throw new Error('Failed to fetch image for hashing in worker.');
		}

		const blob = await response.blob();
		const bitmap = await createImageBitmap(blob);

		const canvas = new OffscreenCanvas(size, size);
		const context = canvas.getContext('2d', { willReadFrequently: true });
		if (!context) {
			throw new Error('Failed to acquire worker canvas context.');
		}

		const cropX = bitmap.width * borderIgnoreRatio;
		const cropY = bitmap.height * borderIgnoreRatio;
		const cropWidth = Math.max(1, bitmap.width - cropX * 2);
		const cropHeight = Math.max(1, bitmap.height - cropY * 2);

		context.drawImage(bitmap, cropX, cropY, cropWidth, cropHeight, 0, 0, size, size);
		const imageData = context.getImageData(0, 0, size, size);

		const grayscale = new Float32Array(size * size);
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

		const targetLength = Math.ceil((size * size) / chunkSize);
		respond({ hash: hash.padEnd(targetLength, '0') });
	} catch (error) {
		respond({ error: error && error.message ? error.message : 'Worker hash failed' });
	}
};
`;

const supportsWorkerHashing = () => (
	typeof window !== 'undefined'
	&& typeof Worker !== 'undefined'
	&& typeof URL !== 'undefined'
	&& typeof Blob !== 'undefined'
);

const clearPendingWorkerRequests = (reason = 'Hash worker unavailable') => {
	pendingWorkerRequests.forEach(({ reject, timeoutId }) => {
		window.clearTimeout(timeoutId);
		reject(new Error(reason));
	});
	pendingWorkerRequests.clear();
};

const getHashWorker = () => {
	if (!supportsWorkerHashing()) {
		return null;
	}

	if (hashWorker) {
		return hashWorker;
	}

	try {
		const blob = new Blob([WORKER_SOURCE], { type: 'application/javascript' });
		const workerUrl = URL.createObjectURL(blob);
		hashWorker = new Worker(workerUrl);
		URL.revokeObjectURL(workerUrl);

		hashWorker.onmessage = (event) => {
			const payload = event && event.data ? event.data : {};
			const { id, hash, error } = payload;
			const pending = pendingWorkerRequests.get(id);
			if (!pending) {
				return;
			}

			window.clearTimeout(pending.timeoutId);
			pendingWorkerRequests.delete(id);

			if (error) {
				pending.reject(new Error(error));
				return;
			}

			pending.resolve(hash);
		};

		hashWorker.onerror = () => {
			if (hashWorker) {
				hashWorker.terminate();
				hashWorker = null;
			}
			clearPendingWorkerRequests('Hash worker crashed');
		};
	} catch (error) {
		hashWorker = null;
		return null;
	}

	return hashWorker;
};

const computeImageHashViaWorker = (src, size, borderIgnoreRatio) => {
	const worker = getHashWorker();
	if (!worker) {
		return Promise.reject(new Error('Hash worker is not available'));
	}

	return new Promise((resolve, reject) => {
		workerRequestId += 1;
		const id = workerRequestId;
		const timeoutId = window.setTimeout(() => {
			pendingWorkerRequests.delete(id);
			reject(new Error('Hash worker timed out'));
		}, WORKER_TIMEOUT_MS);

		pendingWorkerRequests.set(id, { resolve, reject, timeoutId });
		worker.postMessage({ id, src, size, borderIgnoreRatio });
	});
};

const normalizeHashSource = (src) => {
	if (typeof src !== 'string') {
		return '';
	}

	const trimmed = src.trim();
	if (!trimmed) {
		return '';
	}

	if (typeof window === 'undefined' || !window.location) {
		return trimmed;
	}

	try {
		return new URL(trimmed, window.location.href).toString();
	} catch {
		return trimmed;
	}
};

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

const computeAverageHash = (image, size, borderIgnoreRatio = DEFAULT_BORDER_IGNORE_RATIO) => {
	const dimension = size;
	const canvas = document.createElement('canvas');
	canvas.width = dimension;
	canvas.height = dimension;
	const context = canvas.getContext('2d', { willReadFrequently: true });

	if (!context) {
		throw new Error('Failed to acquire 2D context for image hashing.');
	}

	const normalizedBorderIgnoreRatio = Number.isFinite(borderIgnoreRatio)
		? Math.min(Math.max(borderIgnoreRatio, 0), 0.3)
		: DEFAULT_BORDER_IGNORE_RATIO;
	const cropX = image.naturalWidth * normalizedBorderIgnoreRatio;
	const cropY = image.naturalHeight * normalizedBorderIgnoreRatio;
	const cropWidth = Math.max(1, image.naturalWidth - cropX * 2);
	const cropHeight = Math.max(1, image.naturalHeight - cropY * 2);

	context.drawImage(image, cropX, cropY, cropWidth, cropHeight, 0, 0, dimension, dimension);

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

const hashBinaryContent = async (src) => {
	if (!src) {
		return null;
	}

	try {
		const response = await fetch(src);
		if (!response.ok) {
			return null;
		}

		const buffer = await response.arrayBuffer();
		if (!buffer || buffer.byteLength === 0) {
			return null;
		}

		if (typeof window !== 'undefined' && window.crypto?.subtle) {
			const digest = await window.crypto.subtle.digest('SHA-1', buffer);
			return bufferToHex(digest);
		}

		const bytes = new Uint8Array(buffer);
		let hash = 0;
		for (let i = 0; i < bytes.length; i += 1) {
			hash = (hash << 5) - hash + bytes[i];
			hash |= 0;
		}

		return Math.abs(hash).toString(16);
	} catch {
		return null;
	}
};

export const computeImageHash = async (src, options = {}) => {
	const normalizedSrc = normalizeHashSource(src);
	if (!normalizedSrc) {
		return null;
	}

	const contentKey = `${normalizedSrc}::content-sha1`;
	if (hashCache.has(contentKey)) {
		return hashCache.get(contentKey);
	}

	const contentHash = await hashBinaryContent(normalizedSrc);
	if (contentHash) {
		const normalizedContentHash = `sha1-${contentHash}`;
		hashCache.set(contentKey, normalizedContentHash);
		return normalizedContentHash;
	}

	const size = options.hashSize || DEFAULT_HASH_SIZE;
	const borderIgnoreRatio = Number.isFinite(options.borderIgnoreRatio)
		? Math.min(Math.max(options.borderIgnoreRatio, 0), 0.3)
		: DEFAULT_BORDER_IGNORE_RATIO;
	const key = `${normalizedSrc}::${size}::${borderIgnoreRatio}`;

	if (hashCache.has(key)) {
		return hashCache.get(key);
	}

	try {
		const hash = await computeImageHashViaWorker(normalizedSrc, size, borderIgnoreRatio);
		hashCache.set(key, hash);
		return hash;
	} catch (error) {
		try {
			const image = await loadImage(normalizedSrc);
			const hash = computeAverageHash(image, size, borderIgnoreRatio);
			hashCache.set(key, hash);
			return hash;
		} catch (mainThreadError) {
			const fallback = await hashBinaryContent(normalizedSrc);
			hashCache.set(key, fallback);
			return fallback;
		}
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
