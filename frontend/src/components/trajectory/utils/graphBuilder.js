import { schemeTableau10 } from 'd3-scale-chromatic';

import { computeImageHash, hashesAreSimilar } from './imageHash';
import { generatePreviewImage } from './imagePreview';

const COLOR_PALETTE = schemeTableau10 || [
	'#1f77b4',
	'#ff7f0e',
	'#2ca02c',
	'#d62728',
	'#9467bd',
	'#8c564b',
	'#e377c2',
	'#7f7f7f',
	'#bcbd22',
	'#17becf',
];

const DEFAULT_HASH_CONCURRENCY = 8;

const asArray = (value) => {
	if (!value) {
		return [];
	}

	return Array.isArray(value) ? value : [value];
};

const coerceText = (value) => {
	if (typeof value !== 'string') {
		return null;
	}

	const trimmed = value.trim();

	return trimmed.length > 0 ? trimmed : null;
};

const firstNonEmptyText = (...values) => {
	for (const value of values) {
		const text = coerceText(value);
		if (text) {
			return text;
		}
	}

	return null;
};

const normalizeHashValue = (value) => {
	const hash = coerceText(value);
	return hash ? hash.toLowerCase() : null;
};

const getEntryScreenshots = (entry) => {
	if (Array.isArray(entry?.screenshots)) {
		return entry.screenshots;
	}

	if (Array.isArray(entry?.history_payload?.screenshots)) {
		return entry.history_payload.screenshots;
	}

	return [];
};

const extractScreenshotHash = (raw, metadata) => firstNonEmptyText(
	metadata?.imageHash,
	metadata?.image_hash,
	typeof raw === 'string' ? null : raw?.imageHash,
	typeof raw === 'string' ? null : raw?.image_hash,
	typeof raw === 'string' ? null : raw?.metadata?.imageHash,
	typeof raw === 'string' ? null : raw?.metadata?.image_hash,
	typeof raw === 'string' ? null : raw?.meta?.imageHash,
	typeof raw === 'string' ? null : raw?.meta?.image_hash,
);

const getEntryScreenshotHashes = (entry, screenshots) => {
	const hashList = Array.isArray(entry?.screenshot_hashes)
		? entry.screenshot_hashes
		: (Array.isArray(entry?.history_payload?.screenshot_hashes) ? entry.history_payload.screenshot_hashes : []);

	if (!Array.isArray(screenshots) || !screenshots.length) {
		return [];
	}

	return screenshots.map((item, index) => firstNonEmptyText(hashList[index], extractScreenshotHash(item)));
};

const extractActionTypes = (actionPayload) => {
	if (!actionPayload) {
		return [];
	}

	const actionItems = Array.isArray(actionPayload) ? actionPayload : [actionPayload];
	const actionTypes = [];

	actionItems.forEach((item) => {
		if (!item || typeof item !== 'object') {
			return;
		}

		const payload = item.root && typeof item.root === 'object' ? item.root : item;
		const keys = Object.keys(payload);
		if (!keys.length) {
			return;
		}

		const actionType = coerceText(keys[0]);
		if (!actionType) {
			return;
		}

		actionTypes.push(actionType.toLowerCase());
	});

	return Array.from(new Set(actionTypes));
};

const SCHEME_PATTERN = /^[a-z][a-z0-9+.-]*:/i;

const extractMimeType = (raw, metadata) => {
	// 后端使用 URL/proxy 传图时不提供 MIME，base64 回退场景统一默认 image/png
	return 'image/png';
};

const sanitizeBase64 = (value) => value.replace(/\s+/g, '').replace(/^data:[^,]+,/, '');

const runWithConcurrencyLimit = async (items, concurrency, worker) => {
	if (!Array.isArray(items) || items.length === 0) {
		return [];
	}

	const limit = Number.isFinite(concurrency) && concurrency > 0
		? Math.max(1, Math.floor(concurrency))
		: DEFAULT_HASH_CONCURRENCY;

	const results = new Array(items.length);
	let nextIndex = 0;

	const runWorker = async () => {
		while (true) {
			const currentIndex = nextIndex;
			nextIndex += 1;
			if (currentIndex >= items.length) {
				return;
			}

			results[currentIndex] = await worker(items[currentIndex], currentIndex);
		}
	};

	const workerCount = Math.min(limit, items.length);
	await Promise.all(Array.from({ length: workerCount }, () => runWorker()));

	return results;
};

const preloadImageSource = (src) => new Promise((resolve) => {
	if (typeof src !== 'string' || !src.trim()) {
		resolve(false);
		return;
	}

	const image = new Image();
	let settled = false;
	const finish = (ok) => {
		if (settled) {
			return;
		}
		settled = true;
		resolve(ok);
	};

	image.crossOrigin = 'Anonymous';
	image.decoding = 'async';
	image.referrerPolicy = 'no-referrer';
	image.onload = () => finish(true);
	image.onerror = () => finish(false);

	window.setTimeout(() => finish(false), 12000);
	image.src = src;

	if (image.complete && image.naturalWidth !== 0) {
		finish(true);
	}
});

const isLikelyBase64Image = (value) => {
	if (!value || typeof value !== 'string') {
		return false;
	}

	const trimmed = value.trim();

	if (!trimmed) {
		return false;
	}

	if (SCHEME_PATTERN.test(trimmed) || trimmed.startsWith('//')) {
		return false;
	}

	if (trimmed.length < 16) {
		return false;
	}

	const normalized = sanitizeBase64(trimmed);

	if (normalized.length % 4 !== 0) {
		return false;
	}

	return /^[A-Za-z0-9+/=]+$/.test(normalized);
};

const resolveImageSource = (value, raw, metadata) => {
	if (!value) {
		return null;
	}

	if (typeof value !== 'string') {
		return null;
	}

	const trimmed = value.trim();

	if (!trimmed) {
		return null;
	}

	if (trimmed.startsWith('//')) {
		return `https:${trimmed}`;
	}

	if (trimmed.startsWith('data:')) {
		return trimmed;
	}

	if (SCHEME_PATTERN.test(trimmed)) {
		return trimmed;
	}

	if (isLikelyBase64Image(trimmed)) {
		const mimeType = extractMimeType(raw, metadata);
		const payload = sanitizeBase64(trimmed);
		return `data:${mimeType};base64,${payload}`;
	}

	return trimmed;
};

const normalizeScreenshot = (raw, metadata) => {
	if (!raw) {
		return null;
	}

	const normalizedMetadata = metadata ? { ...metadata } : {};
	const personaCandidate =
		coerceText(normalizedMetadata.persona) ||
		(typeof raw === 'string' ? null : coerceText(raw?.persona)) ||
		(typeof raw === 'string' ? null : coerceText(raw?.metadata?.persona));

	if (personaCandidate) {
		normalizedMetadata.persona = personaCandidate;
	} else if (Object.prototype.hasOwnProperty.call(normalizedMetadata, 'persona')) {
		delete normalizedMetadata.persona;
	}

	// 当前后端返回 URL/proxy 字符串；这里保留字符串路径解析
	if (typeof raw === 'string') {
		const src = resolveImageSource(raw, null, normalizedMetadata);
		const imageHash = extractScreenshotHash(raw, normalizedMetadata);

		if (!src) {
			return null;
		}

		return {
			src,
			alt: normalizedMetadata.alt || undefined,
			imageHash: imageHash || null,
			raw,
			...normalizedMetadata,
		};
	}

	return null;
};

const extractScreenshotSequences = (trajectory) => {
	if (!trajectory) {
		return [];
	}

	const { details } = trajectory;

	if (!details) {
		return [];
	}

	const detailArray = asArray(details);

	return detailArray
		.map((entry, detailIndex) => {
			const stepId = entry?.id || entry?.step_id || detailIndex;
			const titleCandidate =
				entry?.label ||
				entry?.name ||
				entry?.title ||
				entry?.description;
			const fallbackLabel = typeof stepId === 'string' ? stepId : `Sequence ${detailIndex + 1}`;
			const task =
				coerceText(entry?.task) ||
				coerceText(entry?.goal) ||
				coerceText(entry?.objective) ||
				coerceText(entry?.metadata?.task);
			const value =
				coerceText(entry?.value) ||
				coerceText(entry?.metadata?.value) ||
				coerceText(entry?.conditionMetadata?.value);
			const runIndex =
				(entry?.run_index !== undefined ? entry.run_index :
				(entry?.metadata?.run_index !== undefined ? entry.metadata.run_index :
				(entry?.conditionMetadata?.run_index !== undefined ? entry.conditionMetadata.run_index : null)));
			const conditionPersona =
				coerceText(entry?.conditionMetadata?.persona) ||
				coerceText(entry?.conditionSummary?.persona) ||
				coerceText(entry?.conditionTask?.persona);
			const entryPersona =
				coerceText(entry?.persona) ||
				coerceText(entry?.metadata?.persona) ||
				conditionPersona;
			const baseLabel = titleCandidate || fallbackLabel;
			
			const screenshotsInput = getEntryScreenshots(entry);
			// Get step descriptions array from entry (matches screenshot indices)
			const stepDescriptions = asArray(entry?.step_descriptions || entry?.history_payload?.step_descriptions);
			// Get model outputs array from entry (matches screenshot indices)
			const modelOutputs = asArray(entry?.model_outputs || entry?.history_payload?.model_outputs);
			// Get precomputed screenshot hashes array from entry (matches screenshot indices)
			const screenshotHashes = getEntryScreenshotHashes(entry, screenshotsInput);
			
			const screenshotsRaw = screenshotsInput
				.map((item, screenshotIndex) => {
					const screenshotPersona =
						coerceText(item?.persona) ||
						coerceText(item?.metadata?.persona) ||
						coerceText(item?.meta?.persona);

					// Get the description for this specific screenshot step
					const stepDescription = stepDescriptions[screenshotIndex] || null;
					// Get the model output for this specific screenshot step
					const specificModelOutput = modelOutputs[screenshotIndex] || null;

					return normalizeScreenshot(item, {
						detailIndex,
						screenshotIndex,
						stepId,
						timestamp: entry?.timestamp || entry?.created_at,
						label: baseLabel,
						persona: screenshotPersona || entryPersona || conditionPersona || null,
						imageHash: screenshotHashes[screenshotIndex] || null,
						description: stepDescription,
						model_output: specificModelOutput || entry?.model_output || entry,
					});
				})
				.filter(Boolean);

			if (!screenshotsRaw.length) {
				return null;
			}

			const personaCandidates = [conditionPersona]
				.filter(Boolean)
				.concat(
					screenshotsRaw
						.map((shot) => coerceText(shot.persona))
						.filter(Boolean),
				);
			if (!personaCandidates.length && entryPersona) {
				personaCandidates.push(entryPersona);
			}

			const personas = Array.from(new Set(personaCandidates));
			const primaryPersona = conditionPersona || personas[0] || null;
			const displayPersona = value || primaryPersona;
			const combinedLabel = [task, displayPersona].filter(Boolean).join(' + ');
			const label = combinedLabel || baseLabel;
			const legendLabel = value || conditionPersona || primaryPersona || label;
			const screenshots = screenshotsRaw.map((shot) => ({ ...shot, label }));

			return {
				detailIndex,
				stepId,
				label,
				legendLabel,
				modelValue: value || null,
				runIndex: runIndex !== null ? runIndex : null,
				task: task || null,
				persona: primaryPersona,
				conditionPersona: conditionPersona || null,
				personas,
				screenshots,
			};
		})
		.filter(Boolean);
};

export const buildTrajectoryGraph = async (trajectory, options = {}) => {
	const sequences = extractScreenshotSequences(trajectory);
	const conditions = Array.isArray(options.conditions) ? options.conditions : [];
	const useImageHash = options.useImageHash !== false;
	const strictHashMatch = options.strictHashMatch === true;
	const hashOptions = options.hash || {};
	const hashSize = Number.isFinite(hashOptions.hashSize) && hashOptions.hashSize > 0
		? Math.floor(hashOptions.hashSize)
		: 16;
	const perceptualHashLength = Math.ceil((hashSize * hashSize) / 4);
	const hashSimilarityThreshold = Number.isFinite(options.hashSimilarityThreshold) && options.hashSimilarityThreshold >= 0
		? Math.floor(options.hashSimilarityThreshold)
		: (strictHashMatch ? 0 : Math.max(8, Math.round((hashSize * hashSize) * 0.09)));
	const usePreviewImage = options.usePreviewImage !== false;
	const previewConcurrency = Number.isFinite(options.previewConcurrency) && options.previewConcurrency > 0
		? Math.floor(options.previewConcurrency)
		: 4;
	const previewOptions = options.preview || {};
	
	// 构建条件数据映射：sequenceIndex -> {model, persona, run_index}
	const conditionMap = new Map();
	conditions.forEach((condition, index) => {
		conditionMap.set(index, {
			model: condition.model || null,
			persona: condition.persona || null,
			run_index: condition.run_index !== undefined ? condition.run_index : index,
		});
	});

	if (!sequences.length) {
		return {
			nodes: [],
			links: [],
			clusters: [],
			meta: {
				totalSequences: 0,
				totalScreenshots: 0,
				totalNodes: 0,
				totalLinks: 0,
				legend: [],
			},
		};
	}

	const nodeMap = new Map();
	const occurrences = [];
	const sequenceNodeIds = sequences.map(() => []);
	const sequenceLinkPaths = sequences.map(() => []);
	const sequenceColors = sequences.map((sequence, index) => sequence.color || COLOR_PALETTE[index % COLOR_PALETTE.length]);
	const hashConcurrency = Number.isFinite(options.hashConcurrency) && options.hashConcurrency > 0
		? Math.floor(options.hashConcurrency)
		: DEFAULT_HASH_CONCURRENCY;
	const canonicalPerceptualHashes = [];
	const canonicalHashMap = new Map();

	const resolveCanonicalHash = (hash) => {
		const normalizedHash = normalizeHashValue(hash);
		if (!normalizedHash) {
			return null;
		}

		if (canonicalHashMap.has(normalizedHash)) {
			return canonicalHashMap.get(normalizedHash);
		}

		if (strictHashMatch) {
			canonicalHashMap.set(normalizedHash, normalizedHash);
			return normalizedHash;
		}

		if (normalizedHash.length !== perceptualHashLength) {
			canonicalHashMap.set(normalizedHash, normalizedHash);
			return normalizedHash;
		}

		const matchingCanonicalHash = canonicalPerceptualHashes.find(
			(existingHash) => hashesAreSimilar(existingHash, normalizedHash, hashSimilarityThreshold),
		);

		const canonicalHash = matchingCanonicalHash || normalizedHash;
		if (!matchingCanonicalHash) {
			canonicalPerceptualHashes.push(canonicalHash);
		}

		canonicalHashMap.set(normalizedHash, canonicalHash);
		return canonicalHash;
	};

	const hashTasks = [];
	sequences.forEach((sequence, sequenceIndex) => {
		const screenshots = sequence.screenshots;
		for (let position = 0; position < screenshots.length; position += 1) {
			hashTasks.push({
				sequenceIndex,
				position,
				screenshot: screenshots[position],
			});
		}
	});

	if (useImageHash && hashTasks.length > 0) {
		await runWithConcurrencyLimit(
			hashTasks,
			hashConcurrency,
			async (task) => {
				const src = coerceText(task?.screenshot?.src);
				if (!src) {
					return null;
				}
				await preloadImageSource(src);
				return null;
			},
		);
	}

	const hashedTasks = await runWithConcurrencyLimit(
		hashTasks,
		hashConcurrency,
		async (task) => {
			if (!useImageHash) {
				return { ...task, hash: null };
			}

			const src = coerceText(task?.screenshot?.src);
			if (!src) {
				return { ...task, hash: null };
			}

			const hash = await computeImageHash(src, options.hash);
			return { ...task, hash: normalizeHashValue(hash) };
		},
	);

	const validHashCount = hashedTasks.reduce((count, task) => (
		normalizeHashValue(task?.hash) ? count + 1 : count
	), 0);
	if (useImageHash && hashedTasks.length > 0 && validHashCount < hashedTasks.length) {
		const failedSources = hashedTasks
			.filter((task) => !normalizeHashValue(task?.hash))
			.map((task) => task?.screenshot?.src)
			.filter((src) => typeof src === 'string' && src.trim())
			.slice(0, 5);
		console.warn('[trajectory] Some screenshots failed to produce content hash; those nodes cannot be merged by image.', {
			total: hashedTasks.length,
			valid: validHashCount,
			missing: hashedTasks.length - validHashCount,
			failedSources,
		});
	}

	const hashByOccurrence = new Map();
	hashedTasks.forEach((task) => {
		hashByOccurrence.set(`${task.sequenceIndex}-${task.position}`, resolveCanonicalHash(task.hash));
	});

	if (useImageHash && hashByOccurrence.size > 0) {
		const uniqueHashes = new Set();
		hashByOccurrence.forEach((value) => {
			if (value) {
				uniqueHashes.add(value);
			}
		});
		console.debug('[trajectory] Image hash merge stats', {
			totalScreenshots: hashByOccurrence.size,
			uniqueHashes: uniqueHashes.size,
		});
	}

	sequences.forEach((sequence, sequenceIndex) => {
		const screenshots = sequence.screenshots;

		for (let position = 0; position < screenshots.length; position += 1) {
			const screenshot = screenshots[position];
			const occurrenceId = `${sequenceIndex}-${position}`;
			const hash = hashByOccurrence.get(`${sequenceIndex}-${position}`) || null;
			const nodeId = useImageHash && hash
				? `node-${hash}`
				: `node-seq-${sequenceIndex}-pos-${position}`;

			if (!nodeMap.has(nodeId)) {
				nodeMap.set(nodeId, {
					id: nodeId,
					hash: useImageHash ? hash : `NO_HASH_${sequenceIndex}_${position}`,
					src: screenshot.src,
					alt: screenshot.alt,
					occurrences: [],
					weight: 0,
				});
			}

			const node = nodeMap.get(nodeId);

			// 从 conditionMap 获取模型和 persona 信息
			const conditionInfo = conditionMap.get(sequenceIndex) || {};

			node.occurrences.push({
				sequenceIndex,
				sequenceLabel: sequence.label,
				sequenceTask: sequence.task,
				sequencePersona: sequence.persona,
				screenshotPersona: screenshot.persona || null,
				position,
				detailIndex: screenshot.detailIndex,
				stepId: screenshot.stepId,
				timestamp: screenshot.timestamp,
				description: screenshot.description || null,
				raw: screenshot.raw,
				model_output: screenshot.model_output,
				// 添加模型、persona 和 run_index 信息
				agentModel: conditionInfo.model || sequence.modelValue || null,
				agentValue: sequence.modelValue || null,
				agentPersona: conditionInfo.persona || null,
				agentRunIndex: conditionInfo.run_index !== undefined ? conditionInfo.run_index : (sequence.runIndex !== null ? sequence.runIndex : null),
			});
			node.weight += 1;

			occurrences.push({
				occurrenceId,
				nodeId,
				sequenceIndex,
				position,
			});

			sequenceNodeIds[sequenceIndex][position] = nodeId;
		}
	});

	const nodes = Array.from(nodeMap.values());

	nodes.forEach((node) => {
		node.radius = 18 + Math.log2(node.weight + 1) * 12;
	});

	if (usePreviewImage && nodes.length > 0) {
		const previewTasks = await runWithConcurrencyLimit(
			nodes,
			previewConcurrency,
			async (node) => {
				const previewSrc = await generatePreviewImage(node.src, previewOptions);
				return {
					id: node.id,
					previewSrc,
				};
			},
		);

		const previewByNodeId = new Map(previewTasks.map((entry) => [entry.id, entry.previewSrc]));
		nodes.forEach((node) => {
			node.previewSrc = previewByNodeId.get(node.id) || node.src;
		});
	}

	const linksMap = new Map();

	sequences.forEach((sequence, sequenceIndex) => {
		const screenshots = sequence.screenshots;

		for (let position = 0; position < screenshots.length - 1; position += 1) {
			const currentNodeId = sequenceNodeIds[sequenceIndex][position];
			const nextNodeId = sequenceNodeIds[sequenceIndex][position + 1];
			const currentShot = screenshots[position];
			const nextShot = screenshots[position + 1];
			const actionPayload = currentShot?.model_output?.action || null;
			const actionSummary = currentShot?.description || null;

			if (!currentNodeId || !nextNodeId) {
				continue;
			}

			if (currentNodeId === nextNodeId) {
				continue;
			}

			const key = `${currentNodeId}__${nextNodeId}__${sequenceIndex}`;

			if (!linksMap.has(key)) {
				linksMap.set(key, {
					id: key,
					source: currentNodeId,
					target: nextNodeId,
					count: 0,
					occurrences: [],
					sequenceIndex,
					sequenceLabel: sequence.label,
					personas: new Set(),
					actionTypes: new Set(),
				});
			}

			const link = linksMap.get(key);
			const personaCandidatesForLink = [
				coerceText(currentShot?.persona),
				coerceText(nextShot?.persona),
				coerceText(sequence.persona),
			].filter(Boolean);
			const linkPersona = personaCandidatesForLink[0] || null;

			if (linkPersona) {
				if (!link.persona) {
					link.persona = linkPersona;
				}
				if (link.personas) {
					link.personas.add(linkPersona);
				}
			}
			const actionTypes = extractActionTypes(actionPayload);
			actionTypes.forEach((actionType) => {
				if (link.actionTypes) {
					link.actionTypes.add(actionType);
				}
			});
			link.count += 1;
			link.occurrences.push({
				sequenceIndex,
				position,
				action: actionPayload,
				actionTypes,
				actionSummary,
				fromStepId: currentShot?.stepId || null,
				toStepId: nextShot?.stepId || null,
				modelOutput: currentShot?.model_output || null,
			});
		}
	});

	const links = Array.from(linksMap.values()).map((link) => {
		const personas = link.personas ? Array.from(link.personas) : [];
		const actionTypes = link.actionTypes ? Array.from(link.actionTypes) : [];
		return {
			...link,
			persona: link.persona || personas[0] || null,
			personas,
			actionTypes,
			color: sequenceColors[link.sequenceIndex] || '#1f2937',
		};
	});

	links.forEach((link) => {
		const { sequenceIndex } = link;
		if (!Number.isInteger(sequenceIndex) || sequenceIndex < 0 || sequenceIndex >= sequenceLinkPaths.length) {
			return;
		}
		const occurrencesForLink = Array.isArray(link.occurrences)
			? link.occurrences
					.slice()
					.sort((a, b) => a.position - b.position)
			: [];
		occurrencesForLink.forEach((occurrence) => {
			if (!Number.isFinite(occurrence.position)) {
				return;
			}
			sequenceLinkPaths[sequenceIndex].push({
				linkId: link.id,
				position: occurrence.position,
				sourceId: link.source,
				targetId: link.target,
			});
		});
	});

	const sequenceNodePaths = sequenceNodeIds.map((nodeIds) =>
		nodeIds
			.map((nodeId, position) => (nodeId ? { nodeId, position } : null))
			.filter(Boolean),
	);

	const sequenceLinkPathsSorted = sequenceLinkPaths.map((entries) =>
		entries
			.slice()
			.sort((a, b) => a.position - b.position),
	);

	const clusters = [];

	return {
		nodes,
		links,
		clusters,
		meta: {
			totalSequences: sequences.length,
			totalScreenshots: occurrences.length,
			totalNodes: nodes.length,
			totalLinks: links.length,
			hashingEnabled: useImageHash,
			hashTaskCount: hashedTasks.length,
			validHashCount,
			isHashComplete: !useImageHash || validHashCount >= hashedTasks.length,
			legend: sequences.map((sequence, index) => {
				const conditionPersonaLabel = coerceText(sequence.conditionPersona);
				const personaLabel = Array.isArray(sequence.personas) && sequence.personas.length
					? sequence.personas.join(' / ')
					: sequence.persona;
				const finalLabel =
					conditionPersonaLabel || personaLabel || sequence.legendLabel || sequence.label || `Sequence ${index + 1}`;

				return {
					id: `sequence-${index}`,
					label: finalLabel,
					legendLabel: finalLabel,
					task: sequence.task || null,
					persona: sequence.persona || null,
					conditionPersona: conditionPersonaLabel || null,
					personas: Array.isArray(sequence.personas) ? sequence.personas : [],
					stepId: sequence.stepId,
					color: sequenceColors[index],
					sequenceIndex: index,
					nodePath: sequenceNodePaths[index] || [],
					linkPath: sequenceLinkPathsSorted[index] || [],
				};
			}),
		},
	};
};

export default buildTrajectoryGraph;
