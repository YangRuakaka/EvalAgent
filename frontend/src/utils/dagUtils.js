import { toRoundedNumber } from './mathUtils';

export const DAG_FOCUS_EVENT_TYPES = new Set([
	'node_click',
	'node_drag_start',
	'node_drag_end',
	'node_pin_toggle',
	'zoom_pan',
]);

export const DAG_EVENT_MIN_INTERVAL_BY_TYPE = {
	zoom_pan: 900,
};

export const normalizeDAGInteractionForExport = (interaction, context = {}) => {
	if (!interaction || typeof interaction !== 'object') {
		return null;
	}

	const type = typeof interaction.type === 'string' ? interaction.type : 'unknown';
	const scope = typeof interaction.scope === 'string' ? interaction.scope : 'trajectory_dag';

	switch (type) {
		case 'node_click':
			return {
				scope,
				type,
				nodeId: interaction.nodeId || null,
			};
		case 'node_drag_start':
			return {
				scope,
				type,
				nodeId: interaction.nodeId || null,
				x: toRoundedNumber(interaction.x, 0),
				y: toRoundedNumber(interaction.y, 0),
			};
		case 'node_pin_toggle':
			return {
				scope,
				type: interaction.isPinned ? 'node_lock' : 'node_unlock',
				nodeId: interaction.nodeId || null,
			};
		case 'node_drag_end':
			return {
				scope,
				type,
				nodeId: interaction.nodeId || null,
				x: toRoundedNumber(interaction.x, 0),
				y: toRoundedNumber(interaction.y, 0),
				isPinned: Boolean(interaction.isPinned),
			};
		case 'zoom_pan':
		{
			const runKey = context.runKey || 'global';
			const scale = toRoundedNumber(interaction.scale, 3);
			if (scale === null) {
				return null;
			}

			const previousScale = context.zoomScaleByRunRef?.current?.get(runKey);
			const baselineScale = Number.isFinite(previousScale) ? previousScale : 1;
			const delta = scale - baselineScale;

			if (Math.abs(delta) < 0.01) {
				context.zoomScaleByRunRef?.current?.set(runKey, scale);
				return null;
			}

			context.zoomScaleByRunRef?.current?.set(runKey, scale);

			return {
				scope,
				type: delta > 0 ? 'zoom_in' : 'zoom_out',
				fromScale: toRoundedNumber(baselineScale, 3),
				toScale: scale,
				translateX: toRoundedNumber(interaction.translateX, 0),
				translateY: toRoundedNumber(interaction.translateY, 0),
			};
		}
		default:
			return null;
	}
};

export const buildDAGInteractionSummary = (interactions) => {
	if (!Array.isArray(interactions) || interactions.length === 0) {
		return {
			totalEvents: 0,
			sessionDurationSeconds: 0,
			countsByType: {},
			countsByRunId: {},
		};
	}

	const countsByType = {};
	const countsByRunId = {};

	interactions.forEach((item) => {
		const type = item?.type || 'unknown';
		const runId = item?.runId || 'unknown';
		countsByType[type] = (countsByType[type] || 0) + 1;
		countsByRunId[runId] = (countsByRunId[runId] || 0) + 1;
	});

	const first = interactions[0];
	const last = interactions[interactions.length - 1];
	const firstTs = Date.parse(first?.recordedAt || '');
	const lastTs = Date.parse(last?.recordedAt || '');
	const sessionDurationSeconds = Number.isFinite(firstTs) && Number.isFinite(lastTs) && lastTs >= firstTs
		? Math.round((lastTs - firstTs) / 1000)
		: 0;

	return {
		totalEvents: interactions.length,
		sessionDurationSeconds,
		countsByType,
		countsByRunId,
	};
};
