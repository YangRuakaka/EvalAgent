import { toRoundedNumber } from './mathUtils';

export const DAG_FOCUS_EVENT_TYPES = new Set([
	'node_click',
	'node_drag_start',
	'node_drag',
	'node_drag_end',
	'node_pin_toggle',
	'link_click',
	'link_action_click',
	'zoom_pan',
	'mouse_wheel',
	'mousemove',
	'mouse_down',
	'mouse_up',
	'graph_refresh',
]);

export const DAG_EVENT_MIN_INTERVAL_BY_TYPE = {
	zoom_pan: 320,
	node_drag: 90,
	mouse_wheel: 120,
	mousemove: 220,
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
				zoomScale: toRoundedNumber(interaction.zoomScale, 3),
				pointerX: toRoundedNumber(interaction.pointerX, 0),
				pointerY: toRoundedNumber(interaction.pointerY, 0),
			};
		case 'node_drag':
			return {
				scope,
				type,
				nodeId: interaction.nodeId || null,
				x: toRoundedNumber(interaction.x, 1),
				y: toRoundedNumber(interaction.y, 1),
				deltaX: toRoundedNumber(interaction.deltaX, 1),
				deltaY: toRoundedNumber(interaction.deltaY, 1),
				elapsedMs: toRoundedNumber(interaction.elapsedMs, 0),
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
				dragDurationMs: toRoundedNumber(interaction.dragDurationMs, 0),
				totalDeltaX: toRoundedNumber(interaction.totalDeltaX, 1),
				totalDeltaY: toRoundedNumber(interaction.totalDeltaY, 1),
			};
		case 'link_click':
			return {
				scope,
				type,
				linkId: interaction.linkId || null,
				sourceNodeId: interaction.sourceNodeId || null,
				targetNodeId: interaction.targetNodeId || null,
				count: toRoundedNumber(interaction.count, 0),
				sequenceIndex: toRoundedNumber(interaction.sequenceIndex, 0),
				actionCount: toRoundedNumber(interaction.actionCount, 0),
			};
		case 'link_action_click':
			return {
				scope,
				type,
				linkId: interaction.linkId || null,
				actionType: interaction.actionType || null,
				sourceNodeId: interaction.sourceNodeId || null,
				targetNodeId: interaction.targetNodeId || null,
				sequenceIndex: toRoundedNumber(interaction.sequenceIndex, 0),
			};
		case 'zoom_pan': {
			const runKey = context.runKey || 'global';
			const scale = toRoundedNumber(interaction.scale, 3);
			const translateX = toRoundedNumber(interaction.translateX, 0);
			const translateY = toRoundedNumber(interaction.translateY, 0);
			if (scale === null || translateX === null || translateY === null) {
				return null;
			}

			const previousScale = context.zoomScaleByRunRef?.current?.get(runKey);
			const baselineScale = Number.isFinite(previousScale) ? previousScale : 1;
			const previousTranslate = context.zoomTranslateByRunRef?.current?.get(runKey) || { x: 0, y: 0 };

			const deltaScale = toRoundedNumber(scale - baselineScale, 3);
			const deltaX = toRoundedNumber(translateX - (toRoundedNumber(previousTranslate.x, 0) || 0), 0);
			const deltaY = toRoundedNumber(translateY - (toRoundedNumber(previousTranslate.y, 0) || 0), 0);

			context.zoomScaleByRunRef?.current?.set(runKey, scale);
			context.zoomTranslateByRunRef?.current?.set(runKey, {
				x: translateX,
				y: translateY,
			});

			let intent = 'pan';
			if (Math.abs(deltaScale || 0) >= 0.01) {
				intent = deltaScale > 0 ? 'zoom_in' : 'zoom_out';
			}

			return {
				scope,
				type,
				intent,
				fromScale: toRoundedNumber(baselineScale, 3),
				toScale: scale,
				deltaScale,
				translateX,
				translateY,
				deltaX,
				deltaY,
			};
		}
		case 'mouse_wheel':
			return {
				scope,
				type,
				deltaX: toRoundedNumber(interaction.deltaX, 1),
				deltaY: toRoundedNumber(interaction.deltaY, 1),
			};
		case 'mousemove':
			return {
				scope,
				type,
				x: toRoundedNumber(interaction.x, 1),
				y: toRoundedNumber(interaction.y, 1),
				containerWidth: toRoundedNumber(interaction.containerWidth, 1),
				containerHeight: toRoundedNumber(interaction.containerHeight, 1),
			};
		case 'mouse_down':
		case 'mouse_up':
			return {
				scope,
				type,
			};
		case 'graph_refresh':
			return {
				scope,
				type,
				trigger: interaction.trigger || 'manual_button',
				refreshNonce: toRoundedNumber(interaction.refreshNonce, 0),
				manualRefreshNonce: toRoundedNumber(interaction.manualRefreshNonce, 0),
			};
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
