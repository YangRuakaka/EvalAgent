import { schemeTableau10 } from 'd3-scale-chromatic';

import { computeImageHash, hashesAreSimilar } from './imageHash';

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

const DEFAULT_CLUSTER_THRESHOLD = 12;
const FIRST_CONDITION_HASH = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff';

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

const SCHEME_PATTERN = /^[a-z][a-z0-9+.-]*:/i;

const extractMimeType = (raw, metadata) => {
	// 后端不返回 MIME 类型，始终使用 image/png 作为默认值
	// 因为所有 screenshots 都是 PNG/JPG 格式
	return 'image/png';
};

const sanitizeBase64 = (value) => value.replace(/\s+/g, '').replace(/^data:[^,]+,/, '');

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

	// 后端只返回 base64 string，无需处理 object 格式
	if (typeof raw === 'string') {
		const src = resolveImageSource(raw, null, normalizedMetadata);

		if (!src) {
			return null;
		}

		return {
			src,
			alt: normalizedMetadata.alt || undefined,
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
			
			// Get step descriptions array from entry (matches screenshot indices)
			const stepDescriptions = asArray(entry?.step_descriptions);
			// Get model outputs array from entry (matches screenshot indices)
			const modelOutputs = asArray(entry?.model_outputs || entry?.history_payload?.model_outputs);
			
			const screenshotsRaw = asArray(entry?.screenshots)
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

const buildClusters = (nodes, { similarityThreshold = DEFAULT_CLUSTER_THRESHOLD } = {}) => {
	const clusterAssignments = new Map();
	const clusterColors = new Map();
	const clusters = [];

	nodes.forEach((node, index) => {
		if (clusterAssignments.has(node.id)) {
			return;
		}

		const clusterId = `cluster-${clusters.length}`;
		clusterAssignments.set(node.id, clusterId);

		const members = [node];

		for (let j = index + 1; j < nodes.length; j += 1) {
			const candidate = nodes[j];

			if (clusterAssignments.has(candidate.id)) {
				continue;
			}

			if (node.isConditionFirst !== candidate.isConditionFirst) {
				continue;
			}

			if (hashesAreSimilar(node.hash, candidate.hash, similarityThreshold)) {
				clusterAssignments.set(candidate.id, clusterId);
				members.push(candidate);
			}
		}

		const color = COLOR_PALETTE[clusters.length % COLOR_PALETTE.length];

		clusters.push({
			id: clusterId,
			label: `Cluster ${clusters.length + 1}`,
			color,
			nodeIds: members.map((member) => member.id),
			representativeNodeId: node.id,
		});
		clusterColors.set(clusterId, color);

		members.forEach((member) => {
			member.clusterId = clusterId;
			member.color = color;
		});
	});

	nodes.forEach((node) => {
		if (!node.clusterId) {
			node.clusterId = clusterAssignments.get(node.id) || null;
			if (node.clusterId && clusterColors.has(node.clusterId)) {
				node.color = clusterColors.get(node.clusterId);
			}
		}
	});

	return clusters;
};

export const buildTrajectoryGraph = async (trajectory, options = {}) => {
	const sequences = extractScreenshotSequences(trajectory);
	const conditions = Array.isArray(options.conditions) ? options.conditions : [];
	
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

	await Promise.all(
		sequences.map(async (sequence, sequenceIndex) => {
			const screenshots = sequence.screenshots;

			for (let position = 0; position < screenshots.length; position += 1) {
				const screenshot = screenshots[position];
				const occurrenceId = `${sequenceIndex}-${position}`;
				const isConditionFirstScreenshot = position === 0;
				const hash = isConditionFirstScreenshot
					? null
					: await computeImageHash(screenshot.src, options.hash);
				const nodeId = isConditionFirstScreenshot ? 'node-condition-first' : `node-${hash}`;

				if (!nodeMap.has(nodeId)) {
					nodeMap.set(nodeId, {
						id: nodeId,
						hash: isConditionFirstScreenshot ? FIRST_CONDITION_HASH : hash,
						src: screenshot.src,
						alt: screenshot.alt,
						occurrences: [],
						weight: 0,
						isConditionFirst: isConditionFirstScreenshot,
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
		})
	);

	const nodes = Array.from(nodeMap.values());

	nodes.forEach((node) => {
		node.radius = 18 + Math.log2(node.weight + 1) * 12;
	});

	const linksMap = new Map();

	sequences.forEach((sequence, sequenceIndex) => {
		const screenshots = sequence.screenshots;

		for (let position = 0; position < screenshots.length - 1; position += 1) {
			const currentNodeId = sequenceNodeIds[sequenceIndex][position];
			const nextNodeId = sequenceNodeIds[sequenceIndex][position + 1];
			const currentShot = screenshots[position];
			const nextShot = screenshots[position + 1];

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
			link.count += 1;
			link.occurrences.push({ sequenceIndex, position });
		}
	});

	const links = Array.from(linksMap.values()).map((link) => {
		const personas = link.personas ? Array.from(link.personas) : [];
		return {
			...link,
			persona: link.persona || personas[0] || null,
			personas,
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

	const clusters = buildClusters(nodes, { similarityThreshold: options.clusterThreshold });

	return {
		nodes,
		links,
		clusters,
		meta: {
			totalSequences: sequences.length,
			totalScreenshots: occurrences.length,
			totalNodes: nodes.length,
			totalLinks: links.length,
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
