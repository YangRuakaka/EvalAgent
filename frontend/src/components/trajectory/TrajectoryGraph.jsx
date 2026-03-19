import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import PropTypes from 'prop-types';
import { select } from 'd3-selection';
import { zoom, zoomIdentity } from 'd3-zoom';
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force';
import { drag as d3Drag } from 'd3-drag';
import 'd3-transition';

import useResizeObserver from '../../hooks/useResizeObserver';

import './TrajectoryGraph.css';

const ZOOM_EXTENT = [0.2, 6];
const DEFAULT_FORCE_STRENGTH = -800;
const DEFAULT_LINK_COLOR = '#1e3a8a';
const NODE_RADIUS_SCALE = 1.6;
const NODE_RADIUS_OFFSET = 16;
const NODE_MIN_RADIUS = 48;
const NODE_COLLISION_BUFFER = 50;
const NODE_BORDER_WIDTH = 5;
const NODE_BORDER_GAP = 2;
const LINK_BASE_DISTANCE = 350;
const LINK_DISTANCE_SCALER = 32;
const PARALLEL_LINK_SEPARATION = 128;
const PARALLEL_LINK_OFFSET_MULTIPLIER = 0.6;
const PARALLEL_LINK_CURVE_MULTIPLIER = 0.1;
const PARALLEL_LINK_CONTROL_PULL = 0.4;
const ACTION_CHIP_VERTICAL_NUDGE = 10;
const RENDER_FRAME_SKIP = 2;
const NODE_DRAG_RENDER_FRAME_SKIP = 3;
const NODE_DRAG_LOG_INTERVAL = 90;
const SIMULATION_ALPHA_MIN = 0.02;
const SIMULATION_ALPHA_DECAY = 0.045;
const ICON_PIN = 'M16,12V4H17V2H7V4H8V12L6,14V16H11.2V22H12.8V16H18V14L16,12Z';
const ICON_UNPIN = 'M2,5.27L3.28,4L20,20.72L18.73,22L12.8,16.07V22H11.2V16H6V14L8,12V11.27L2,5.27M16,12L18,14V16H17.82L8,6.18V4H7V2H17V4H16V12Z';
const ACTION_ICON_MAP = {
	click: '🖱',
	scroll: '↕',
	input: '⌨',
	type: '⌨',
	select_option: '☰',
	select: '☰',
	hover: '◎',
	navigate: '⇢',
	go_to_url: '⇢',
	open_tab: '🗂',
	switch_tab: '🗂',
	close_tab: '✕',
	wait: '⏱',
	screenshot: '📸',
	done: '✓',
};


const clampUnit = (value) => {
	const numeric = Number(value);
	if (!Number.isFinite(numeric)) {
		return 0;
	}
	if (numeric <= 0) {
		return 0;
	}
	if (numeric >= 1) {
		return 1;
	}
	return numeric;
};

const HEX_COLOR_PATTERN = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
const RGB_COLOR_PATTERN = /^rgb\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*\)$/i;
const RGBA_COLOR_PATTERN = /^rgba\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$/i;

const colorWithAlpha = (input, alpha = 0.35) => {
	const normalizedAlpha = clampUnit(alpha);
	const fallback = `rgba(37, 99, 235, ${normalizedAlpha})`;
	if (typeof input !== 'string') {
		return fallback;
	}
	const candidate = input.trim();
	if (!candidate) {
		return fallback;
	}
	const hexMatch = candidate.match(HEX_COLOR_PATTERN);
	if (hexMatch) {
		let hex = hexMatch[1];
		if (hex.length === 3) {
			hex = hex
				.split('')
				.map((char) => `${char}${char}`)
				.join('');
		}
		const intValue = Number.parseInt(hex, 16);
		const r = (intValue >> 16) & 255;
		const g = (intValue >> 8) & 255;
		const b = intValue & 255;
		return `rgba(${r}, ${g}, ${b}, ${normalizedAlpha})`;
	}
	const rgbMatch = candidate.match(RGB_COLOR_PATTERN);
	if (rgbMatch) {
		const r = Number(rgbMatch[1]);
		const g = Number(rgbMatch[2]);
		const b = Number(rgbMatch[3]);
		return `rgba(${r}, ${g}, ${b}, ${normalizedAlpha})`;
	}
	const rgbaMatch = candidate.match(RGBA_COLOR_PATTERN);
	if (rgbaMatch) {
		const r = Number(rgbaMatch[1]);
		const g = Number(rgbaMatch[2]);
		const b = Number(rgbaMatch[3]);
		return `rgba(${r}, ${g}, ${b}, ${normalizedAlpha})`;
	}
	return fallback;
};

const easeInOut = (t) => {
	if (t <= 0) {
		return 0;
	}
	if (t >= 1) {
		return 1;
	}
	return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
};

const getMaxConsecutiveConditionRun = (occurrences) => {
	if (!Array.isArray(occurrences) || occurrences.length < 2) {
		return 0;
	}

	const byCondition = new Map();

	occurrences.forEach((entry) => {
		const sequenceIndex = Number.isFinite(entry?.sequenceIndex) ? entry.sequenceIndex : null;
		const position = Number.isFinite(entry?.position) ? entry.position : null;
		if (sequenceIndex === null || position === null) {
			return;
		}
		if (!byCondition.has(sequenceIndex)) {
			byCondition.set(sequenceIndex, []);
		}
		byCondition.get(sequenceIndex).push(position);
	});

	let maxRun = 0;

	byCondition.forEach((positions) => {
		if (!positions.length) {
			return;
		}
		const sorted = positions.slice().sort((a, b) => a - b);
		let currentRun = 1;
		for (let i = 1; i < sorted.length; i += 1) {
			if (sorted[i] === sorted[i - 1] + 1 || sorted[i] === sorted[i - 1]) {
				currentRun += 1;
			} else {
				if (currentRun > maxRun) {
					maxRun = currentRun;
				}
				currentRun = 1;
			}
		}
		if (currentRun > maxRun) {
			maxRun = currentRun;
		}
	});

	return maxRun >= 2 ? maxRun : 0;
};

const markerIdForColor = (color) => {
	if (!color) {
		return 'trajectory-arrowhead-default';
	}

	return `trajectory-arrowhead-${color.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() || 'default'}`;
};

const getLinkEndpointId = (endpoint) => {
	if (typeof endpoint === 'object') {
		return endpoint?.id || null;
	}
	return endpoint || null;
};

const targetWithinSelector = (target, selector) => {
	if (!target || typeof target.closest !== 'function') {
		return false;
	}

	return Boolean(target.closest(selector));
};

const ensureLayoutDefaults = (nodes, width, height) => {
	nodes.forEach((node) => {
		if (typeof node.x !== 'number' || Number.isNaN(node.x)) {
			node.x = width / 2 + (Math.random() - 0.5) * width * 0.1;
		}

		if (typeof node.y !== 'number' || Number.isNaN(node.y)) {
			node.y = height / 2 + (Math.random() - 0.5) * height * 0.1;
		}
	});
};

const computeRectIntersection = (center, target, width, height, padding = 0) => {
	const dx = target.x - center.x;
	const dy = target.y - center.y;

	if (dx === 0 && dy === 0) {
		return { x: center.x, y: center.y - height / 2 - padding };
	}

	const w = width / 2 + padding;
	const h = height / 2 + padding;

	const tanTheta = Math.abs(dy / dx);
	const rectTan = h / w;

	let x, y;

	if (tanTheta <= rectTan) {
		// Intersects left or right
		x = dx > 0 ? w : -w;
		y = x * (dy / dx);
	} else {
		// Intersects top or bottom
		y = dy > 0 ? h : -h;
		x = y * (dx / dy);
	}

	return { x: center.x + x, y: center.y + y };
};

const computeSelfLoopPath = (node, parallelOffsetIndex) => {
	if (!node) {
		return '';
	}

	const cx = node.x || 0;
	const cy = node.y || 0;
	const width = node.width || 48;
	const height = node.height || 32;
	
	const loopIndex = parallelOffsetIndex || 0;
	const loopOffset = Math.abs(loopIndex);
	
	// Attach to top-right corner area
	const cornerX = cx + width / 2;
	const cornerY = cy - height / 2;
	
	const r = 16 + loopOffset * 6;
	const startX = cornerX - 10;
	const startY = cornerY;
	const endX = cornerX;
	const endY = cornerY + 10;
	
	// Cubic bezier loop
	const cp1x = startX + r;
	const cp1y = startY - r * 1.5;
	const cp2x = endX + r * 1.5;
	const cp2y = endY - r;

	return `M ${startX} ${startY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${endX} ${endY}`;
};

const computeLinkGeometry = (link) => {
	const source = link.source;
	const target = link.target;

	if (!source || !target) {
		return null;
	}

	const parallelOffsetIndex =
		link.__parallelCount > 1 ? link.__parallelIndex - (link.__parallelCount - 1) / 2 : 0;

	if (source === target || source.id === target.id) {
		return {
			type: 'self-loop',
			source,
			target,
			parallelOffsetIndex,
		};
	}

	const sx = source.x || 0;
	const sy = source.y || 0;
	const tx = target.x || 0;
	const ty = target.y || 0;
	const dx = tx - sx;
	const dy = ty - sy;
	const distance = Math.sqrt(dx * dx + dy * dy) || 1;

	const perpX = distance === 0 ? 0 : -dy / distance;
	const perpY = distance === 0 ? 0 : dx / distance;

	const offsetMagnitude = Math.abs(parallelOffsetIndex);
	const separationScale = offsetMagnitude
		? PARALLEL_LINK_OFFSET_MULTIPLIER + Math.sqrt(offsetMagnitude) * PARALLEL_LINK_OFFSET_MULTIPLIER * 0.35
		: 0;
	const perpendicularOffset =
		offsetMagnitude === 0
			? 0
			: parallelOffsetIndex * PARALLEL_LINK_SEPARATION * separationScale;

	const virtualTarget = {
		x: tx + perpX * perpendicularOffset,
		y: ty + perpY * perpendicularOffset,
	};

	const virtualSource = {
		x: sx + perpX * perpendicularOffset,
		y: sy + perpY * perpendicularOffset,
	};

	const sourcePadding = 4;
	const targetPadding = 8;

	const start = computeRectIntersection(
		source,
		virtualTarget,
		source.width || 48,
		source.height || 32,
		sourcePadding,
	);
	const end = computeRectIntersection(
		target,
		virtualSource,
		target.width || 48,
		target.height || 32,
		targetPadding,
	);

	const startX = start.x;
	const startY = start.y;
	const endX = end.x;
	const endY = end.y;

	const baseCurveStrength = Math.min(60, distance * 0.2);
	const curveStrength =
		baseCurveStrength + offsetMagnitude * PARALLEL_LINK_SEPARATION * PARALLEL_LINK_CURVE_MULTIPLIER;
	const midX = (startX + endX) / 2;
	const midY = (startY + endY) / 2;
	const perpendicularContribution = Math.abs(perpendicularOffset) * PARALLEL_LINK_CONTROL_PULL;
	const controlX = midX - perpX * (curveStrength + perpendicularContribution);
	const controlY = midY - perpY * (curveStrength + perpendicularContribution);

	return {
		type: 'standard',
		source,
		target,
		parallelOffsetIndex,
		startX,
		startY,
		controlX,
		controlY,
		endX,
		endY,
	};
};

const computeLinkPath = (link) => {
	const geometry = computeLinkGeometry(link);

	if (!geometry) {
		return '';
	}

	if (geometry.type === 'self-loop') {
		return computeSelfLoopPath(geometry.source, geometry.parallelOffsetIndex);
	}

	return `M ${geometry.startX} ${geometry.startY} Q ${geometry.controlX} ${geometry.controlY} ${geometry.endX} ${geometry.endY}`;
};

const computeLinkActionAnchor = (link) => {
	const geometry = computeLinkGeometry(link);

	if (!geometry) {
		return { x: 0, y: 0 };
	}

	if (geometry.type === 'self-loop') {
		const source = geometry.source;
		const loopOffset = Math.abs(geometry.parallelOffsetIndex || 0);
		return {
			x: (source.x || 0) + (source.width || 48) / 2 + 28 + loopOffset * 8,
			y: (source.y || 0) - (source.height || 32) / 2 - 28 - loopOffset * 4 - ACTION_CHIP_VERTICAL_NUDGE,
		};
	}

	const t = 0.5;
	const oneMinusT = 1 - t;
	const x =
		oneMinusT * oneMinusT * geometry.startX
		+ 2 * oneMinusT * t * geometry.controlX
		+ t * t * geometry.endX;
	const y =
		oneMinusT * oneMinusT * geometry.startY
		+ 2 * oneMinusT * t * geometry.controlY
		+ t * t * geometry.endY;

	return {
		x,
		y: y - ACTION_CHIP_VERTICAL_NUDGE,
	};
};

const getActionIcon = (actionType) => {
	const normalized = typeof actionType === 'string' ? actionType.trim().toLowerCase() : '';
	return ACTION_ICON_MAP[normalized] || '•';
};

const TrajectoryGraph = ({
	graph,
	isLoading,
	enableNodeImages,
	emptyMessage,
	containerSize,
	highlightRequest,
	onNodeClick,
	onLinkClick,
	onInteraction,
}) => {
	const containerRef = useRef(null);
	const svgRef = useRef(null);
	const rootLayerRef = useRef(null);
	const linksLayerRef = useRef(null);
	const linkActionsLayerRef = useRef(null);
	const nodesLayerRef = useRef(null);
	const defsRef = useRef(null);
	const simulationRef = useRef(null);
	const zoomStateRef = useRef(zoomIdentity);
	const containerSizeRef = useRef({ width: 0, height: 0 });
	const zoomBehaviourRef = useRef(null);
	const prevMeasuredSizeRef = useRef({ width: 0, height: 0 });
	const previousDataRef = useRef(null);
	const highlightStateRef = useRef({ timers: [] });
	const tooltipRef = useRef(null);
	const tooltipTimeoutRef = useRef(null);
	const persistentNodeStateRef = useRef(new Map());
	const interactionCallbackRef = useRef(onInteraction);
	const onNodeClickRef = useRef(onNodeClick);
	const onLinkClickRef = useRef(onLinkClick);
	const lastMouseMoveLoggedAtRef = useRef(0);
	const lastZoomLoggedAtRef = useRef(0);
	const lastZoomTransformRef = useRef({ k: 1, x: 0, y: 0 });
	const lastDragLoggedAtRef = useRef(0);
	const interactionDepthRef = useRef(0);
	const isNodeDraggingRef = useRef(false);
	const activeDraggedNodeIdRef = useRef(null);
	const activeDragSessionRef = useRef(null);
	const activeSimulationCleanupRef = useRef(null);

	const setInteractionPerformanceMode = useCallback((enabled) => {
		const containerNode = containerRef.current;
		if (!containerNode) {
			return;
		}

		select(containerNode).classed('trajectory-graph--dragging', Boolean(enabled));
	}, []);

	const beginHeavyInteraction = useCallback(() => {
		interactionDepthRef.current += 1;
		if (interactionDepthRef.current === 1) {
			setInteractionPerformanceMode(true);
		}
	}, [setInteractionPerformanceMode]);

	const endHeavyInteraction = useCallback(() => {
		if (interactionDepthRef.current > 0) {
			interactionDepthRef.current -= 1;
		}

		if (interactionDepthRef.current === 0) {
			setInteractionPerformanceMode(false);
		}
	}, [setInteractionPerformanceMode]);

	const emitInteraction = (payload) => {
		const callback = interactionCallbackRef.current;
		if (typeof callback !== 'function' || !payload) {
			return;
		}

		callback({
			scope: 'trajectory_dag',
			...payload,
		});
	};

	useEffect(() => {
		interactionCallbackRef.current = onInteraction;
	}, [onInteraction]);

	useEffect(() => {
		onNodeClickRef.current = onNodeClick;
	}, [onNodeClick]);

	useEffect(() => {
		onLinkClickRef.current = onLinkClick;
	}, [onLinkClick]);

	const cancelHighlightTimers = () => {
		const { timers } = highlightStateRef.current;
		if (Array.isArray(timers)) {
			timers.forEach((timerId) => {
				window.clearTimeout(timerId);
			});
		}
		highlightStateRef.current.timers = [];
	};

	const measuredSize = useResizeObserver(containerRef);
	const width = Number.isFinite(containerSize?.width) && containerSize.width > 0 ? containerSize.width : measuredSize.width;
	const height = Number.isFinite(containerSize?.height) && containerSize.height > 0 ? containerSize.height : measuredSize.height;

	useEffect(() => {
		if (!width || !height) {
			return;
		}

		prevMeasuredSizeRef.current = { width, height };
	}, [width, height]);

	useEffect(
		() => () => {
			cancelHighlightTimers();
			interactionDepthRef.current = 0;
			activeDraggedNodeIdRef.current = null;
			activeDragSessionRef.current = null;
			setInteractionPerformanceMode(false);
			// Cleanup tooltip timeout
			if (tooltipTimeoutRef.current) {
				window.clearTimeout(tooltipTimeoutRef.current);
				tooltipTimeoutRef.current = null;
			}
			// Hide tooltip on unmount
			if (tooltipRef.current) {
				select(tooltipRef.current).style('display', 'none');
			}
		},
		[setInteractionPerformanceMode],
	);

	const data = useMemo(() => {
		const nodes = graph?.nodes ? graph.nodes.map((node) => ({ ...node })) : [];
		const links = graph?.links ? graph.links.map((link) => ({ ...link })) : [];
		const meta = graph?.meta ? { ...graph.meta } : null;

		if (persistentNodeStateRef.current) {
			const stateMap = persistentNodeStateRef.current;
			nodes.forEach((node) => {
				const stored = stateMap.get(node.id);
				if (stored && stored.pinned) {
					node.fx = stored.x;
					node.fy = stored.y;
					node.x = stored.x;
					node.y = stored.y;
					node._pinned = true;
				}
			});
		}

		return { nodes, links, meta };
	}, [graph]);

	useEffect(() => {
		const svgNode = svgRef.current;
		const rootNode = rootLayerRef.current;

		if (!svgNode || !rootNode) {
			return () => {};
		}

		const svg = select(svgNode);
		const root = select(rootNode);

		const zoomBehaviour = zoom()
			.filter((event) => {
				const defaultAllowed = (!event.ctrlKey || event.type === 'wheel') && !event.button;
				if (!defaultAllowed) {
					return false;
				}

				if (event.type === 'wheel') {
					return true;
				}

				return !targetWithinSelector(event.target, '.trajectory-node');
			})
			.scaleExtent(ZOOM_EXTENT)
			.on('start', () => {
				beginHeavyInteraction();
			})
			.on('zoom', (event) => {
				zoomStateRef.current = event.transform;
				root.attr('transform', event.transform);

				const now = Date.now();
				if (now - lastZoomLoggedAtRef.current >= 160) {
					const previousZoom = lastZoomTransformRef.current || { k: 1, x: 0, y: 0 };
					const nextZoom = {
						k: Number(event.transform.k || 1),
						x: Number(event.transform.x || 0),
						y: Number(event.transform.y || 0),
					};
					lastZoomTransformRef.current = nextZoom;
					lastZoomLoggedAtRef.current = now;
					emitInteraction({
						type: 'zoom_pan',
						scale: Number(nextZoom.k.toFixed(4)),
						translateX: Number(nextZoom.x.toFixed(2)),
						translateY: Number(nextZoom.y.toFixed(2)),
						deltaScale: Number((nextZoom.k - previousZoom.k).toFixed(4)),
						deltaX: Number((nextZoom.x - previousZoom.x).toFixed(2)),
						deltaY: Number((nextZoom.y - previousZoom.y).toFixed(2)),
					});
				}
			})
			.on('end', () => {
				endHeavyInteraction();
			});

		zoomBehaviourRef.current = zoomBehaviour;

		svg.call(zoomBehaviour);
		svg.call(zoomBehaviour.transform, zoomStateRef.current);

		return () => {
			svg.on('.zoom', null);
		};
	}, [beginHeavyInteraction, endHeavyInteraction]);

	useEffect(() => {
		// Only run full build when data, layout flag, or image settings change.
		// width and height are deliberately excluded so that resizing doesn't trigger a full rebuild.
		// It only runs when we transition from no-size to having-size.
		if (!width || !height) {
			return () => {};
		}

		select(nodesLayerRef.current).style('will-change', 'transform');
		select(linksLayerRef.current).style('will-change', 'transform');

		const dataChanged = data !== previousDataRef.current;
		previousDataRef.current = data;

		if (dataChanged) {
			simulationRef.current = null;
			persistentNodeStateRef.current.clear();
		}

		if (activeSimulationCleanupRef.current) {
			activeSimulationCleanupRef.current();
			activeSimulationCleanupRef.current = null;
		}

		const { nodes, links, meta } = data;

		if (!nodes.length) {
			select(nodesLayerRef.current).selectAll('*').remove();
			select(linksLayerRef.current).selectAll('*').remove();
			simulationRef.current = null;
			if (width > 0 && height > 0) {
				containerSizeRef.current = { width, height };
			}
			return () => {};
		}

		const previousSimulation = simulationRef.current;
		const previousSize = containerSizeRef.current;
		const previousPositions =
			previousSimulation && typeof previousSimulation.nodes === 'function'
				? new Map(
						previousSimulation
							.nodes()
							.map((node) => [
								node.id,
								{
									x: node.x,
									y: node.y,
									vx: node.vx,
									vy: node.vy,
								},
							]),
				  )
				: null;

		if (previousPositions) {
			nodes.forEach((node) => {
				const previous = previousPositions.get(node.id);
				if (!previous) {
					return;
				}

				if (Number.isFinite(previous.x) && Number.isFinite(previous.y)) {
					if (
						previousSize.width > 0 &&
						previousSize.height > 0 &&
						width > 0 &&
						height > 0
					) {
						const relativeX = previous.x - previousSize.width / 2;
						const relativeY = previous.y - previousSize.height / 2;
						const scaleX = width / previousSize.width;
						const scaleY = height / previousSize.height;

						node.x = width / 2 + relativeX * scaleX;
						node.y = height / 2 + relativeY * scaleY;
					} else {
						node.x = previous.x;
						node.y = previous.y;
					}
				}

				if (Number.isFinite(previous.vx)) {
					node.vx = previous.vx;
				}

				if (Number.isFinite(previous.vy)) {
					node.vy = previous.vy;
				}
			});
		}

		ensureLayoutDefaults(nodes, width, height);

		let minLayoutOrder = Infinity;
		let maxLayoutOrder = -Infinity;

		nodes.forEach((node, index) => {
			const occurrences = Array.isArray(node.occurrences) ? node.occurrences : [];
			const primaryOccurrence = occurrences.reduce((best, occurrence) => {
				if (!best) {
					return occurrence;
				}
				if (occurrence.sequenceIndex < best.sequenceIndex) {
					return occurrence;
				}
				if (occurrence.sequenceIndex === best.sequenceIndex && occurrence.position < best.position) {
					return occurrence;
				}
				return best;
			}, null);

			let layoutOrder = index;

			if (primaryOccurrence) {
				layoutOrder = primaryOccurrence.sequenceIndex * 1000 + primaryOccurrence.position;
			} else if (occurrences.length) {
				layoutOrder = occurrences[0].sequenceIndex * 1000 + occurrences[0].position;
			}

			node.__layoutOrderHint = layoutOrder;
			node.__primaryOccurrence = primaryOccurrence || (occurrences.length ? occurrences[0] : null);
			if (layoutOrder < minLayoutOrder) {
				minLayoutOrder = layoutOrder;
			}
			if (layoutOrder > maxLayoutOrder) {
				maxLayoutOrder = layoutOrder;
			}
		});

		const layoutOrderRange = Math.max(1, maxLayoutOrder - minLayoutOrder);
		const computeTargetX = (node) => {
			const order = typeof node.__layoutOrderHint === 'number' ? node.__layoutOrderHint : minLayoutOrder;
			const normalized = layoutOrderRange === 0 ? 0.5 : (order - minLayoutOrder) / layoutOrderRange;
			const safeWidth = Math.max(width, 1);
			const usableWidth = Math.max(safeWidth - 160, safeWidth * 0.65);
			const padding = Math.max((safeWidth - usableWidth) / 2, 32);
			const target = padding + normalized * usableWidth;
			return Math.min(safeWidth - padding, Math.max(padding, target));
		};

		nodes.forEach((node) => {
			const baseRadius = typeof node.radius === 'number' && node.radius > 0 ? node.radius : 28;
			const scaledRadius = Math.max(baseRadius * NODE_RADIUS_SCALE + NODE_RADIUS_OFFSET, NODE_MIN_RADIUS);
			node.radius = scaledRadius;
			
			// Calculate rectangular dimensions based on radius (which represents importance/weight)
			// Default to 16:10 aspect ratio common for screenshots
			const aspectRatio = 1.6; 
			node.height = scaledRadius * 1.5;
			node.width = node.height * aspectRatio;

			const consecutiveRun = getMaxConsecutiveConditionRun(node.occurrences);
			node.__consecutiveRepeatCount = consecutiveRun > 0 ? consecutiveRun : null;
		});

		const existingSelfLoopNodeIds = new Set();
		links.forEach((link) => {
			const sourceId = typeof link.source === 'object' ? link.source?.id : link.source;
			const targetId = typeof link.target === 'object' ? link.target?.id : link.target;
			if (sourceId && targetId && sourceId === targetId) {
				existingSelfLoopNodeIds.add(sourceId);
			}
		});

		const sequenceColorByIndex = new Map();
		links.forEach((link) => {
			if (Number.isFinite(link.sequenceIndex) && link.color) {
				sequenceColorByIndex.set(link.sequenceIndex, link.color);
			}
		});
		if (meta?.legend?.length) {
			meta.legend.forEach((entry, index) => {
				const color = entry?.color;
				if (!color) {
					return;
				}
				const id = typeof entry.id === 'string' ? entry.id : null;
				let sequenceIndex = Number.isInteger(entry?.sequenceIndex) ? entry.sequenceIndex : null;
				if (sequenceIndex === null && id && id.startsWith('sequence-')) {
					const parsed = Number.parseInt(id.slice('sequence-'.length), 10);
					if (Number.isFinite(parsed)) {
						sequenceIndex = parsed;
					}
				}
				if (sequenceIndex === null) {
					sequenceIndex = index;
				}
				if (!sequenceColorByIndex.has(sequenceIndex)) {
					sequenceColorByIndex.set(sequenceIndex, color);
				}
			});
		}

		const syntheticSelfLinks = nodes
			.filter((node) => node.__consecutiveRepeatCount && !existingSelfLoopNodeIds.has(node.id))
			.map((node) => ({
				id: `__loop__${node.id}`,
				source: node.id,
				target: node.id,
				count: node.__consecutiveRepeatCount,
				sequenceIndex: Number.isFinite(node.__primaryOccurrence?.sequenceIndex)
					? node.__primaryOccurrence.sequenceIndex
					: null,
				sequenceLabel: node.__primaryOccurrence?.sequenceLabel || null,
				color:
					node.__primaryOccurrence && Number.isFinite(node.__primaryOccurrence.sequenceIndex)
						? sequenceColorByIndex.get(node.__primaryOccurrence.sequenceIndex) || node.color || DEFAULT_LINK_COLOR
						: node.color || DEFAULT_LINK_COLOR,
				synthetic: true,
			}));

		const augmentedLinks = syntheticSelfLinks.length ? [...links, ...syntheticSelfLinks] : links;

		const nodeLookup = new Map(nodes.map((node) => [node.id, node]));
		const linksWithRefs = augmentedLinks.map((link) => ({
			...link,
			source: nodeLookup.get(link.source?.id || link.source) || link.source,
			target: nodeLookup.get(link.target?.id || link.target) || link.target,
		}));

		const validLinks = linksWithRefs.filter((link) => {
			const sourceId = typeof link.source === 'object' ? link.source?.id : link.source;
			const targetId = typeof link.target === 'object' ? link.target?.id : link.target;
			return Boolean(sourceId) && Boolean(targetId);
		});

		const nodeLinkColors = new Map();
		const addNodeLinkColor = (nodeId, color) => {
			if (!nodeId) {
				return;
			}
			const normalizedColor = color || DEFAULT_LINK_COLOR;
			const existing = nodeLinkColors.get(nodeId);
			if (existing) {
				if (!existing.includes(normalizedColor)) {
					existing.push(normalizedColor);
				}
			} else {
				nodeLinkColors.set(nodeId, [normalizedColor]);
			}
		};

		validLinks.forEach((link) => {
			const sourceId = typeof link.source === 'object' ? link.source?.id : link.source;
			const targetId = typeof link.target === 'object' ? link.target?.id : link.target;
			const linkColor = link.color || DEFAULT_LINK_COLOR;
			addNodeLinkColor(sourceId, linkColor);
			addNodeLinkColor(targetId, linkColor);
		});

		nodes.forEach((node) => {
			const borderColors = nodeLinkColors.get(node.id);
			node.__linkBorderColors = Array.isArray(borderColors) && borderColors.length
				? borderColors
				: [node.color || DEFAULT_LINK_COLOR];
		});

		const parallelGroupMap = new Map();

		validLinks.forEach((link) => {
			const sourceId = typeof link.source === 'object' ? link.source?.id : link.source;
			const targetId = typeof link.target === 'object' ? link.target?.id : link.target;
			const key = `${sourceId}__${targetId}`;
			if (!parallelGroupMap.has(key)) {
				parallelGroupMap.set(key, []);
			}
			parallelGroupMap.get(key).push(link);
		});

		parallelGroupMap.forEach((group, groupKey) => {
			group.forEach((link, index) => {
				link.__parallelIndex = index;
				link.__parallelCount = group.length;
				link.__key = `${groupKey}#${index}-${link.id}`;
			});
		});

		const simulationLinks = validLinks.filter((link) => {
			const sourceId = typeof link.source === 'object' ? link.source?.id : link.source;
			const targetId = typeof link.target === 'object' ? link.target?.id : link.target;
			return sourceId !== targetId;
		});

		if (validLinks.length) {
		}

		const defs = select(defsRef.current);
		// Remove clip paths as we are using rectangular nodes now
		defs.selectAll('clipPath.trajectory-node__clip').remove();

		const uniqueLinkColors = Array.from(new Set(validLinks.map((link) => link.color).filter(Boolean)));
		const markerData = [
			{ color: null, id: markerIdForColor(null) },
			...uniqueLinkColors.map((color) => ({ color, id: markerIdForColor(color) })),
		];

		const markerSelection = defs.selectAll('marker.trajectory-link__marker').data(markerData, (entry) => entry.id);

		markerSelection.exit().remove();

		const markerEnter = markerSelection
			.enter()
			.append('marker')
			.attr('class', 'trajectory-link__marker');

		markerEnter.append('path').attr('class', 'trajectory-link__arrow');

		markerEnter
			.merge(markerSelection)
			.attr('id', (entry) => entry.id)
			.attr('viewBox', '0 0 24 24')
			.attr('refX', 24)
			.attr('refY', 16)
			.attr('markerWidth', 12)
			.attr('markerHeight', 12)
			.attr('markerUnits', 'userSpaceOnUse')
			.attr('orient', 'auto')
			.select('path')
			.attr('d', 'M 4 4 L 20 12 L 4 20 L 8 12 Z')
			.style('fill', (entry) => entry.color || DEFAULT_LINK_COLOR)
			.style('stroke', (entry) => entry.color || DEFAULT_LINK_COLOR)
			.style('stroke-linejoin', 'round')
			.style('opacity', (entry) => (entry.color ? 0.95 : 0.6));

		const rootLayer = select(rootLayerRef.current);
		const linksLayer = select(linksLayerRef.current);
		const linkActionsLayer = select(linkActionsLayerRef.current);
		const nodesLayer = select(nodesLayerRef.current);

		if (!rootLayer.empty()) {
			rootLayer.attr('transform', zoomStateRef.current);
		}

		const linkSelection = linksLayer
			.selectAll('path.trajectory-link')
			.data(validLinks, (link) => link.__key || link.id);

		linkSelection.exit().remove();

		const linkEnter = linkSelection
			.enter()
			.append('path')
			.attr('class', 'trajectory-link')
			.attr('stroke-width', (link) => Math.max(1.5, Math.log2(link.count + 1) * 1.2));

		const linksMerged = linkEnter.merge(linkSelection);

		linksMerged
			.style('stroke', (link) => link.color || DEFAULT_LINK_COLOR)
			.style('stroke-opacity', (link) => (link.color ? 0.88 : 0.45))
			.attr('marker-end', (link) => `url(#${markerIdForColor(link.color)})`);

		linksMerged.on('click', (event, link) => {
			event.stopPropagation();
			const sourceNodeId = getLinkEndpointId(link?.source);
			const targetNodeId = getLinkEndpointId(link?.target);
			emitInteraction({
				type: 'link_click',
				linkId: link?.id || null,
				actionType: null,
				sourceNodeId,
				targetNodeId,
				count: Number.isFinite(link?.count) ? link.count : null,
				sequenceIndex: Number.isFinite(link?.sequenceIndex) ? link.sequenceIndex : null,
				actionCount: Array.isArray(link?.actionTypes) ? link.actionTypes.length : 0,
			});
			if (typeof onLinkClickRef.current === 'function') {
				onLinkClickRef.current({ link, actionType: null });
			}
		});

		const actionLinks = validLinks.filter((link) => Array.isArray(link.actionTypes) && link.actionTypes.length > 0);
		const linkActionSelection = linkActionsLayer
			.selectAll('g.trajectory-link-actions')
			.data(actionLinks, (link) => link.__key || link.id);

		linkActionSelection.exit().remove();

		const linkActionEnter = linkActionSelection
			.enter()
			.append('g')
			.attr('class', 'trajectory-link-actions');

		const linkActionMerged = linkActionEnter.merge(linkActionSelection);

		linkActionMerged.each(function (link) {
			const actionTypes = Array.isArray(link.actionTypes) ? link.actionTypes : [];
			const chipSelection = select(this)
				.selectAll('g.trajectory-link-action-chip')
				.data(actionTypes, (actionType) => actionType);

			chipSelection.exit().remove();

			const chipEnter = chipSelection
				.enter()
				.append('g')
				.attr('class', 'trajectory-link-action-chip');

			chipEnter.append('rect').attr('class', 'trajectory-link-action-chip__bg');
			chipEnter.append('text').attr('class', 'trajectory-link-action-chip__icon');
			chipEnter.append('text').attr('class', 'trajectory-link-action-chip__label');

			const chipMerged = chipEnter.merge(chipSelection);

			chipMerged
				.attr('transform', (_, idx) => `translate(0, ${(idx - (actionTypes.length - 1) / 2) * 24})`)
				.on('click', (event, actionType) => {
					event.stopPropagation();
					const sourceNodeId = getLinkEndpointId(link?.source);
					const targetNodeId = getLinkEndpointId(link?.target);
					emitInteraction({
						type: 'link_action_click',
						linkId: link?.id || null,
						actionType: actionType || null,
						sourceNodeId,
						targetNodeId,
						sequenceIndex: Number.isFinite(link?.sequenceIndex) ? link.sequenceIndex : null,
					});
					if (typeof onLinkClickRef.current === 'function') {
						onLinkClickRef.current({ link, actionType });
					}
				});

			chipMerged
				.select('.trajectory-link-action-chip__bg')
				.attr('x', -52)
				.attr('y', -9)
				.attr('width', 104)
				.attr('height', 18)
				.attr('rx', 9)
				.attr('ry', 9);

			chipMerged
				.select('.trajectory-link-action-chip__icon')
				.attr('x', -42)
				.attr('y', 4)
				.text((actionType) => getActionIcon(actionType));

			chipMerged
				.select('.trajectory-link-action-chip__label')
				.attr('x', -28)
				.attr('y', 4)
				.text((actionType) => actionType);
		});

		const linksByNodeId = new Map();
		const linkActionsByNodeId = new Map();
		const registerByNodeId = (collection, nodeId, value) => {
			if (!nodeId) {
				return;
			}
			if (!collection.has(nodeId)) {
				collection.set(nodeId, []);
			}
			collection.get(nodeId).push(value);
		};

		linksMerged.each(function (link) {
			const sourceNodeId = getLinkEndpointId(link?.source);
			const targetNodeId = getLinkEndpointId(link?.target);
			const value = { element: this, link };
			registerByNodeId(linksByNodeId, sourceNodeId, value);
			if (targetNodeId !== sourceNodeId) {
				registerByNodeId(linksByNodeId, targetNodeId, value);
			}
		});

		linkActionMerged.each(function (link) {
			const sourceNodeId = getLinkEndpointId(link?.source);
			const targetNodeId = getLinkEndpointId(link?.target);
			const value = { element: this, link };
			registerByNodeId(linkActionsByNodeId, sourceNodeId, value);
			if (targetNodeId !== sourceNodeId) {
				registerByNodeId(linkActionsByNodeId, targetNodeId, value);
			}
		});

		const nodeSelection = nodesLayer
			.selectAll('g.trajectory-node')
			.data(nodes, (node) => node.id);

		nodeSelection.exit().remove();

		const nodeEnter = nodeSelection
			.enter()
			.append('g')
			.attr('class', 'trajectory-node');

		nodeEnter
			.append('rect')
			.attr('class', 'trajectory-node__halo');

		nodeEnter
			.append('image')
			.attr('class', 'trajectory-node__image')
			.attr('referrerPolicy', 'no-referrer');

		nodeEnter
			.append('g')
			.attr('class', 'trajectory-node__outline-group');

		nodeEnter
			.append('text')
			.attr('class', 'trajectory-node__caption')
			.attr('text-anchor', 'middle');

		nodeEnter
			.append('text')
			.attr('class', 'trajectory-node__step-number')
			.attr('text-anchor', 'middle');

		const lockGroup = nodeEnter
			.append('g')
			.attr('class', 'trajectory-node__lock-control');

		lockGroup
			.append('rect')
			.attr('class', 'trajectory-icon-bg')
			.attr('width', 32)
			.attr('height', 32)
			.attr('x', -4)
			.attr('y', -4)
			.attr('rx', 6)
			.attr('ry', 6);

		lockGroup
			.append('path')
			.attr('class', 'trajectory-icon-pin')
			.attr('d', ICON_PIN);

		lockGroup
			.append('path')
			.attr('class', 'trajectory-icon-unpin')
			.attr('d', ICON_UNPIN);

		const nodesMerged = nodeEnter.merge(nodeSelection);

		nodesMerged.classed('is-pinned', (node) => !!node._pinned);

		nodesMerged
			.select('.trajectory-node__lock-control')
			.attr('transform', (node) => {
				const outlineCount = Array.isArray(node.__linkBorderColors) ? node.__linkBorderColors.length : 1;
				const extraLayers = Math.max(outlineCount - 1, 0);
				const outerExpansion = NODE_BORDER_WIDTH + extraLayers * (NODE_BORDER_WIDTH + NODE_BORDER_GAP);
				return `translate(${node.width / 2 + outerExpansion + 2}, ${-node.height / 2 - outerExpansion - 18})`;
			});

		nodesMerged
			.select('.trajectory-node__halo')
			.attr('x', (node) => {
				const outlineCount = Array.isArray(node.__linkBorderColors) ? node.__linkBorderColors.length : 1;
				const extraLayers = Math.max(outlineCount - 1, 0);
				const outerExpansion = NODE_BORDER_WIDTH + extraLayers * (NODE_BORDER_WIDTH + NODE_BORDER_GAP);
				return -(node.width / 2) - 9 - outerExpansion;
			})
			.attr('y', (node) => {
				const outlineCount = Array.isArray(node.__linkBorderColors) ? node.__linkBorderColors.length : 1;
				const extraLayers = Math.max(outlineCount - 1, 0);
				const outerExpansion = NODE_BORDER_WIDTH + extraLayers * (NODE_BORDER_WIDTH + NODE_BORDER_GAP);
				return -(node.height / 2) - 9 - outerExpansion;
			})
			.attr('width', (node) => {
				const outlineCount = Array.isArray(node.__linkBorderColors) ? node.__linkBorderColors.length : 1;
				const extraLayers = Math.max(outlineCount - 1, 0);
				const outerExpansion = NODE_BORDER_WIDTH + extraLayers * (NODE_BORDER_WIDTH + NODE_BORDER_GAP);
				return node.width + 18 + outerExpansion * 2;
			})
			.attr('height', (node) => {
				const outlineCount = Array.isArray(node.__linkBorderColors) ? node.__linkBorderColors.length : 1;
				const extraLayers = Math.max(outlineCount - 1, 0);
				const outerExpansion = NODE_BORDER_WIDTH + extraLayers * (NODE_BORDER_WIDTH + NODE_BORDER_GAP);
				return node.height + 18 + outerExpansion * 2;
			})
			.attr('rx', 12)
			.attr('ry', 12);

		nodesMerged
			.select('.trajectory-node__image')
			.attr('href', (node) => (enableNodeImages ? (node.previewSrc || node.src) : null))
			.attr('x', (node) => -node.width / 2)
			.attr('y', (node) => -node.height / 2)
			.attr('width', (node) => node.width)
			.attr('height', (node) => node.height)
			.style('display', enableNodeImages ? 'block' : 'none');

		nodesMerged.each(function (node) {
			const outlineColors = Array.isArray(node.__linkBorderColors) && node.__linkBorderColors.length
				? node.__linkBorderColors
				: [node.color || DEFAULT_LINK_COLOR];
			const outlineGroup = select(this).select('.trajectory-node__outline-group');
			const outlineSelection = outlineGroup
				.selectAll('rect.trajectory-node__outline')
				.data(outlineColors, (color, index) => `${color}-${index}`);

			outlineSelection.exit().remove();

			const outlineEnter = outlineSelection
				.enter()
				.append('rect')
				.attr('class', 'trajectory-node__outline');

			outlineEnter
				.merge(outlineSelection)
				.attr('x', (_, index) => -(node.width / 2) - NODE_BORDER_WIDTH / 2 - index * (NODE_BORDER_WIDTH + NODE_BORDER_GAP))
				.attr('y', (_, index) => -(node.height / 2) - NODE_BORDER_WIDTH / 2 - index * (NODE_BORDER_WIDTH + NODE_BORDER_GAP))
				.attr('width', (_, index) => node.width + NODE_BORDER_WIDTH + index * 2 * (NODE_BORDER_WIDTH + NODE_BORDER_GAP))
				.attr('height', (_, index) => node.height + NODE_BORDER_WIDTH + index * 2 * (NODE_BORDER_WIDTH + NODE_BORDER_GAP))
				.attr('rx', 6)
				.attr('ry', 6)
				.style('stroke', (color) => color)
				.style('stroke-width', NODE_BORDER_WIDTH)
				.style('fill', 'none');
		});

		nodesMerged
			.select('.trajectory-node__caption')
			.text((node) => (node.__consecutiveRepeatCount ? `${node.__consecutiveRepeatCount}×` : ''))
			.attr('y', (node) => node.height / 2 + 24);

		// Add step numbering and temporal markers
		nodesMerged.each(function (node) {
			const nodeSelection = select(this);
			const occurrences = Array.isArray(node.occurrences) ? node.occurrences : [];
			
			// Find primary occurrence for step number
			const primaryOccurrence = node.__primaryOccurrence || (occurrences.length ? occurrences[0] : null);
			const stepNumber = primaryOccurrence ? (primaryOccurrence.position + 1) : null;
			
			// Update step number text
			const stepNumberText = nodeSelection.select('.trajectory-node__step-number');
			if (stepNumber !== null) {
				stepNumberText
					.text(`Step ${stepNumber}`)
					.attr('y', (node) => -node.height / 2 - 8)
					.style('display', 'block');
			} else {
				stepNumberText.style('display', 'none');
			}
		});

		const simulation = forceSimulation(nodes)
			.force(
				'link',
				forceLink(simulationLinks)
					.id((node) => node.id)
					.distance((link) => {
						const weight = Math.log2((link.count || 0) + 1);
						const preferred = LINK_BASE_DISTANCE - Math.min(160, weight * LINK_DISTANCE_SCALER);
						return Math.max(preferred, 120);
					})
					.strength(0.55),
			)
			.force('charge', forceManyBody().strength(DEFAULT_FORCE_STRENGTH))
			.force('collision', forceCollide().radius((node) => node.radius + NODE_COLLISION_BUFFER))
			.force('center', forceCenter(width / 2, height / 2))
			.force(
				'horizontal',
				forceX((node) => computeTargetX(node)).strength(0.08),
			)
			.force('vertical', forceY(height / 2).strength(0.18))
			.alphaMin(SIMULATION_ALPHA_MIN)
			.alphaDecay(SIMULATION_ALPHA_DECAY);

		if (width > 0 && height > 0) {
			containerSizeRef.current = { width, height };
		}

		simulationRef.current = simulation;
		let tickCount = 0;
		let rafId = null;
		let isDisposed = false;
		const complexityFramePenalty = validLinks.length > 260 ? 2 : validLinks.length > 140 ? 1 : 0;
		const renderFrameSkip =
			(nodes.length > 140 ? 4 : nodes.length > 70 ? 3 : RENDER_FRAME_SKIP) + complexityFramePenalty;
		const dragAlphaTarget = nodes.length > 120 || validLinks.length > 180 ? 0.02 : 0.06;

		const renderScene = () => {
			if (isDisposed) {
				return;
			}

			const draggedNodeId = activeDraggedNodeIdRef.current;
			const shouldUseIncrementalLinkRender = isNodeDraggingRef.current && draggedNodeId;

			if (shouldUseIncrementalLinkRender) {
				const connectedLinks = linksByNodeId.get(draggedNodeId) || [];
				connectedLinks.forEach(({ element, link }) => {
					select(element).attr('d', computeLinkPath(link));
				});

				const connectedLinkActions = linkActionsByNodeId.get(draggedNodeId) || [];
				connectedLinkActions.forEach(({ element, link }) => {
					const anchor = computeLinkActionAnchor(link);
					select(element).attr('transform', `translate(${anchor.x}, ${anchor.y})`);
				});
			} else {
				linksMerged.attr('d', (link) => computeLinkPath(link));
				linkActionMerged.attr('transform', (link) => {
					const anchor = computeLinkActionAnchor(link);
					return `translate(${anchor.x}, ${anchor.y})`;
				});
			}

			nodesMerged.attr('transform', (node) => `translate(${node.x || 0}, ${node.y || 0})`);
		};

		const scheduleRender = () => {
			if (rafId !== null) {
				return;
			}

			rafId = window.requestAnimationFrame(() => {
				rafId = null;
				renderScene();
			});
		};

		const tick = () => {
			tickCount += 1;
			const activeFrameSkip = isNodeDraggingRef.current
				? Math.max(2, Math.min(renderFrameSkip, NODE_DRAG_RENDER_FRAME_SKIP))
				: renderFrameSkip;

			if (tickCount % activeFrameSkip !== 0) {
				return;
			}

			scheduleRender();
		};

		// Add tooltip hover handlers
		const showTooltip = (event, node) => {
			if (!tooltipRef.current) return;
			
			// Clear any existing timeout
			if (tooltipTimeoutRef.current) {
				window.clearTimeout(tooltipTimeoutRef.current);
			}
			
			// Set timeout for delayed display (300-500ms)
			tooltipTimeoutRef.current = window.setTimeout(() => {
				if (!tooltipRef.current) return;
				
				const occurrences = Array.isArray(node.occurrences) ? node.occurrences : [];
				const primaryOccurrence = node.__primaryOccurrence || (occurrences.length ? occurrences[0] : null);
				
				// Build tooltip content
				const stepNumber = primaryOccurrence ? (primaryOccurrence.position + 1) : '?';
				const sequenceLabel = primaryOccurrence?.sequenceLabel || node.__primaryOccurrence?.sequenceLabel || 'Unknown';
				const timestamp = primaryOccurrence?.timestamp || node.__primaryOccurrence?.timestamp || null;
				const stepId = primaryOccurrence?.stepId || node.__primaryOccurrence?.stepId || null;
				const description = primaryOccurrence?.description || node.__primaryOccurrence?.description || null;
				
				// Format timestamp if available
				let formattedTime = '';
				if (timestamp) {
					try {
						const date = new Date(timestamp);
						if (!Number.isNaN(date.getTime())) {
							formattedTime = date.toLocaleString('en-US', {
								month: 'short',
								day: 'numeric',
								hour: '2-digit',
								minute: '2-digit',
							});
						}
					} catch (e) {
						// Ignore date parsing errors
					}
				}
				
				// Update tooltip content
				const tooltip = select(tooltipRef.current);
				tooltip.html(`
					<div class="trajectory-tooltip__step">Step ${stepNumber}</div>
					${stepId ? `<div class="trajectory-tooltip__step-id">${stepId}</div>` : ''}
					<div class="trajectory-tooltip__sequence">${sequenceLabel}</div>
					${description ? `<div class="trajectory-tooltip__description">${description}</div>` : ''}
					${formattedTime ? `<div class="trajectory-tooltip__timestamp">${formattedTime}</div>` : ''}
				`);
				
				// Position tooltip near cursor
				const containerRect = containerRef.current?.getBoundingClientRect();
				if (containerRect) {
					const x = event.clientX - containerRect.left;
					const y = event.clientY - containerRect.top;
					tooltip
						.style('left', `${x + 12}px`)
						.style('top', `${y - 12}px`)
						.style('display', 'block')
						.style('opacity', '0')
						.transition()
						.duration(150)
						.style('opacity', '1');
				}
			}, 350); // 350ms delay
		};
		
		const hideTooltip = () => {
			if (tooltipTimeoutRef.current) {
				window.clearTimeout(tooltipTimeoutRef.current);
				tooltipTimeoutRef.current = null;
			}
			if (tooltipRef.current) {
				const tooltip = select(tooltipRef.current);
				tooltip
					.transition()
					.duration(100)
					.style('opacity', '0')
					.on('end', function() {
						select(this).style('display', 'none');
					});
			}
		};
		
		const togglePin = (node, element) => {
			const wasPinned = !!node._pinned;
			const isPinned = !wasPinned;
			node._pinned = isPinned;

			const stateMap = persistentNodeStateRef.current;
			if (isPinned) {
				node.fx = node.x;
				node.fy = node.y;
				stateMap.set(node.id, {
					pinned: true,
					x: node.x,
					y: node.y,
				});
				select(element).classed('is-pinned', true);
			} else {
				node.fx = null;
				node.fy = null;
				stateMap.delete(node.id);
				select(element).classed('is-pinned', false);

				if (simulationRef.current) {
					simulationRef.current.alpha(0.2).restart();
				}
			}
		};

		nodesMerged
			.on('mouseenter', (event, node) => {
				if (interactionDepthRef.current > 0) {
					return;
				}
				showTooltip(event, node);
			})
			.on('mouseleave', () => {
				hideTooltip();
			})
			.on('click', (event, node) => {
				emitInteraction({
					type: 'node_click',
					nodeId: node?.id || null,
				});
				if (typeof onNodeClickRef.current === 'function') {
					onNodeClickRef.current(node);
				}
			})
			.on('contextmenu', (event, node) => {
				event.preventDefault();
				togglePin(node, event.currentTarget);
				emitInteraction({
					type: 'node_pin_toggle',
					nodeId: node?.id || null,
					isPinned: Boolean(node?._pinned),
				});
			})
			.on('mousemove', (event) => {
				if (interactionDepthRef.current > 0) {
					return;
				}
				// Update tooltip position on mouse move
				if (tooltipRef.current && select(tooltipRef.current).style('display') === 'block') {
					const containerRect = containerRef.current?.getBoundingClientRect();
					if (containerRect) {
						const x = event.clientX - containerRect.left;
						const y = event.clientY - containerRect.top;
						select(tooltipRef.current)
							.style('left', `${x + 12}px`)
							.style('top', `${y - 12}px`);
					}
				}
			});

		nodesMerged.select('.trajectory-node__lock-control').on('click', function (event, node) {
			event.stopPropagation();
			togglePin(node, this.parentNode);
		});

		const dragBehaviour = d3Drag()
			.filter((event) => {
				if (event.button) {
					return false;
				}

				return !targetWithinSelector(event.target, '.trajectory-node__lock-control');
			})
			.on('start', (event, node) => {
				event.sourceEvent?.stopPropagation?.();
				beginHeavyInteraction();
				isNodeDraggingRef.current = true;
				activeDraggedNodeIdRef.current = node?.id || null;
				const startedAt = Date.now();
				const currentZoom = zoomStateRef.current;
				activeDragSessionRef.current = {
					startedAt,
					startX: Number(node?.x) || 0,
					startY: Number(node?.y) || 0,
					lastLoggedX: Number(node?.x) || 0,
					lastLoggedY: Number(node?.y) || 0,
				};
				if (!event.active && simulationRef.current) {
					simulationRef.current.alphaTarget(dragAlphaTarget).restart();
				}
				node.fx = node.x;
				node.fy = node.y;
				scheduleRender();
				emitInteraction({
					type: 'node_drag_start',
					nodeId: node?.id || null,
					x: Number(node?.x?.toFixed?.(2) || node?.x || 0),
					y: Number(node?.y?.toFixed?.(2) || node?.y || 0),
					zoomScale: Number(currentZoom?.k?.toFixed?.(4) || currentZoom?.k || 1),
					pointerX: Number(event?.sourceEvent?.clientX || 0),
					pointerY: Number(event?.sourceEvent?.clientY || 0),
				});
			})
			.on('drag', (event, node) => {
				node.fx = event.x;
				node.fy = event.y;
				activeDraggedNodeIdRef.current = node?.id || null;
				scheduleRender();

				const now = Date.now();
				if (now - lastDragLoggedAtRef.current >= NODE_DRAG_LOG_INTERVAL) {
					const session = activeDragSessionRef.current;
					const lastX = Number.isFinite(session?.lastLoggedX) ? session.lastLoggedX : Number(node?.x || 0);
					const lastY = Number.isFinite(session?.lastLoggedY) ? session.lastLoggedY : Number(node?.y || 0);
					const currentX = Number(event?.x || 0);
					const currentY = Number(event?.y || 0);
					if (session) {
						session.lastLoggedX = currentX;
						session.lastLoggedY = currentY;
					}

					lastDragLoggedAtRef.current = now;
					emitInteraction({
						type: 'node_drag',
						nodeId: node?.id || null,
						x: Number(currentX.toFixed(2)),
						y: Number(currentY.toFixed(2)),
						deltaX: Number((currentX - lastX).toFixed(2)),
						deltaY: Number((currentY - lastY).toFixed(2)),
						elapsedMs: session?.startedAt ? now - session.startedAt : null,
					});
				}
			})
			.on('end', (event, node) => {
				isNodeDraggingRef.current = false;
				activeDraggedNodeIdRef.current = null;
				endHeavyInteraction();
				if (!event.active && simulationRef.current) {
					simulationRef.current.alphaTarget(0);
					simulationRef.current.alpha(0.12).restart();
				}
				if (!node._pinned) {
					node.fx = null;
					node.fy = null;
				} else {
					persistentNodeStateRef.current.set(node.id, {
						pinned: true,
						x: node.x,
						y: node.y,
					});
				}

				const session = activeDragSessionRef.current;
				const dragDurationMs = session?.startedAt ? Date.now() - session.startedAt : null;
				const totalDeltaX = session ? Number(((node?.x || 0) - session.startX).toFixed(2)) : null;
				const totalDeltaY = session ? Number(((node?.y || 0) - session.startY).toFixed(2)) : null;
				activeDragSessionRef.current = null;

				emitInteraction({
					type: 'node_drag_end',
					nodeId: node?.id || null,
					x: Number(node?.x?.toFixed?.(2) || node?.x || 0),
					y: Number(node?.y?.toFixed?.(2) || node?.y || 0),
					isPinned: Boolean(node?._pinned),
					dragDurationMs,
					totalDeltaX,
					totalDeltaY,
				});
				renderScene();
			});

		nodesMerged.call(dragBehaviour);

		simulation.on('tick', tick);
		renderScene();

		const cleanupSimulation = () => {
			isDisposed = true;
			isNodeDraggingRef.current = false;
			activeDraggedNodeIdRef.current = null;
			activeDragSessionRef.current = null;
			if (rafId !== null) {
				window.cancelAnimationFrame(rafId);
				rafId = null;
			}
			interactionDepthRef.current = 0;
			setInteractionPerformanceMode(false);
			simulation.stop();
		};

		activeSimulationCleanupRef.current = cleanupSimulation;

		return () => {
			cleanupSimulation();
		};
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [data, Boolean(width && height), enableNodeImages, beginHeavyInteraction, endHeavyInteraction, setInteractionPerformanceMode]);

	// Separate effect strictly for resizing dimensions
	useEffect(() => {
		if (width > 0 && height > 0 && simulationRef.current && prevMeasuredSizeRef.current) {
			const prevWidth = prevMeasuredSizeRef.current.width;
			const prevHeight = prevMeasuredSizeRef.current.height;
			
			if (prevWidth !== width || prevHeight !== height) {
				containerSizeRef.current = { width, height };
				prevMeasuredSizeRef.current = { width, height };
				
				const simulation = simulationRef.current;
				const simulationNodes = typeof simulation.nodes === 'function' ? simulation.nodes() : [];
				
				if (simulationNodes.length) {
					let minLayoutOrder = Infinity;
					let maxLayoutOrder = -Infinity;

					simulationNodes.forEach((node, index) => {
						const layoutOrder = typeof node.__layoutOrderHint === 'number' ? node.__layoutOrderHint : index;
						if (layoutOrder < minLayoutOrder) minLayoutOrder = layoutOrder;
						if (layoutOrder > maxLayoutOrder) maxLayoutOrder = layoutOrder;
					});

					if (!Number.isFinite(minLayoutOrder) || !Number.isFinite(maxLayoutOrder)) {
						minLayoutOrder = 0;
						maxLayoutOrder = simulationNodes.length - 1;
					}

					const layoutOrderRange = Math.max(1, maxLayoutOrder - minLayoutOrder);
					const computeTargetXForResize = (node) => {
						const order = typeof node.__layoutOrderHint === 'number' ? node.__layoutOrderHint : minLayoutOrder;
						const normalized = layoutOrderRange === 0 ? 0.5 : (order - minLayoutOrder) / layoutOrderRange;
						const safeWidth = Math.max(width, 1);
						const usableWidth = Math.max(safeWidth - 160, safeWidth * 0.65);
						const padding = Math.max((safeWidth - usableWidth) / 2, 32);
						const target = padding + normalized * usableWidth;
						return Math.min(safeWidth - padding, Math.max(padding, target));
					};

					simulation.force('center', forceCenter(width / 2, height / 2));
					simulation.force(
						'horizontal',
						forceX((node) => computeTargetXForResize(node)).strength(0.08),
					);
					simulation.force('vertical', forceY(height / 2).strength(0.18));
					
					simulation.alpha(0.3).restart();
				}
			}
		}
	}, [width, height]);

	useEffect(() => {
		const highlight = highlightRequest;
		const nodesLayerNode = nodesLayerRef.current;
		const linksLayerNode = linksLayerRef.current;
		const rootNode = rootLayerRef.current;

		cancelHighlightTimers();

		if (!nodesLayerNode || !linksLayerNode) {
			return () => {};
		}

		const nodesSelection = select(nodesLayerNode).selectAll('g.trajectory-node');
		const linksSelection = select(linksLayerNode).selectAll('path.trajectory-link');
		const rootSelection = rootNode ? select(rootNode) : null;

		nodesSelection.interrupt();
		linksSelection.interrupt();

		nodesSelection
			.classed('is-active', false)
			.classed('is-traced', false)
			.classed('is-dimmed', false);
		nodesSelection.selectAll('.trajectory-node__halo').style('opacity', null);

		linksSelection
			.classed('is-active', false)
			.classed('is-traced', false)
			.classed('is-dimmed', false)
			.style('stroke-dasharray', null)
			.style('stroke-dashoffset', null)
			.style('filter', null);

		if (rootSelection) {
			rootSelection.style('--trajectory-highlight-color', null).style('--trajectory-highlight-glow', null);
		}

		if (!highlight || !Array.isArray(highlight.nodePath) || !highlight.nodePath.length || !nodesSelection.size()) {
			return () => {
				cancelHighlightTimers();
			};
		}

		const highlightColor = typeof highlight.color === 'string' && highlight.color.trim() ? highlight.color : '#2563eb';
		const highlightGlow = colorWithAlpha(highlight.color, 0.32);

		if (rootSelection) {
			rootSelection
				.style('--trajectory-highlight-color', highlightColor)
				.style('--trajectory-highlight-glow', highlightGlow);
		}

		nodesSelection.classed('is-dimmed', true);
		linksSelection.classed('is-dimmed', true);

		const nodeLookup = new Map();
		nodesSelection.each(function (node) {
			if (node?.id) {
				nodeLookup.set(node.id, select(this));
			}
		});

		if (!nodeLookup.size) {
			nodesSelection.classed('is-dimmed', false);
			linksSelection.classed('is-dimmed', false);
			return () => {
				cancelHighlightTimers();
			};
		}

		const linkLookup = new Map();
		linksSelection.each(function (link) {
			const identifier = link?.id || link?.__key;
			if (identifier) {
				linkLookup.set(identifier, select(this));
			}
		});

		const orderedNodes = highlight.nodePath
			.slice()
			.filter((entry) => entry && entry.nodeId && Number.isFinite(entry.position))
			.sort((a, b) => a.position - b.position);

		if (!orderedNodes.length) {
			nodesSelection.classed('is-dimmed', false);
			linksSelection.classed('is-dimmed', false);
			return () => {
				cancelHighlightTimers();
			};
		}

		const linkByPosition = new Map();
		if (Array.isArray(highlight.linkPath)) {
			highlight.linkPath
				.slice()
				.filter((entry) => entry && entry.linkId && Number.isFinite(entry.position))
				.sort((a, b) => a.position - b.position)
				.forEach((entry) => {
					if (!linkByPosition.has(entry.position)) {
						linkByPosition.set(entry.position, entry);
					}
				});
		}

		const nodeCount = orderedNodes.length;
		// Increased highlight duration - make it longer for better visibility
		const stepDuration = nodeCount > 18 ? 350 : nodeCount > 12 ? 420 : nodeCount > 7 ? 500 : 600;
		const linkDelay = Math.round(stepDuration * 0.35);
		const linkDuration = Math.max(350, Math.round(stepDuration * 0.6));
		const activeReleaseDelay = Math.max(250, Math.round(stepDuration * 0.75));

		const registerTimer = (timerId) => {
			highlightStateRef.current.timers.push(timerId);
		};

		orderedNodes.forEach((step, index) => {
			const baseDelay = index * stepDuration;
			const nodeSelection = nodeLookup.get(step.nodeId);
			if (nodeSelection) {
				const nodeTimerId = window.setTimeout(() => {
					nodeSelection.classed('is-dimmed', false).classed('is-traced', true).classed('is-active', true);
					const releaseId = window.setTimeout(() => {
						nodeSelection.classed('is-active', false);
					}, activeReleaseDelay);
					registerTimer(releaseId);
				}, baseDelay);
				registerTimer(nodeTimerId);
			}

			if (index >= orderedNodes.length - 1) {
				return;
			}

			const linkEntry = linkByPosition.get(step.position);
			if (!linkEntry) {
				return;
			}

			const linkSelection = linkLookup.get(linkEntry.linkId);
			if (!linkSelection) {
				return;
			}

			const linkTimerId = window.setTimeout(() => {
				const pathElement = linkSelection.node();
				if (!pathElement || typeof pathElement.getTotalLength !== 'function') {
					linkSelection.classed('is-dimmed', false).classed('is-traced', true).classed('is-active', true);
					const resetId = window.setTimeout(() => {
						linkSelection.classed('is-active', false);
					}, activeReleaseDelay);
					registerTimer(resetId);
					return;
				}

				const pathLength = pathElement.getTotalLength();
				linkSelection
					.classed('is-dimmed', false)
					.classed('is-traced', true)
					.classed('is-active', true)
					.style('stroke-dasharray', `${pathLength} ${pathLength}`)
					.style('stroke-dashoffset', pathLength)
					.transition()
					.duration(linkDuration)
					.ease(easeInOut)
					.style('stroke-dashoffset', 0)
					.on('end', () => {
						linkSelection
							.classed('is-active', false)
							.style('stroke-dasharray', null)
							.style('stroke-dashoffset', null);
					});
			}, baseDelay + linkDelay);
			registerTimer(linkTimerId);
		});

		const restoreId = window.setTimeout(() => {
			nodesSelection.classed('is-dimmed', false);
			linksSelection.classed('is-dimmed', false);
		}, nodeCount * stepDuration + linkDelay + 500);
		registerTimer(restoreId);

		return () => {
			cancelHighlightTimers();
		};
	}, [highlightRequest, data]);

	const shouldShowPlaceholder = !isLoading && (!data.nodes.length || !width || !height);

	const handleContainerMouseMove = (event) => {
		if (interactionDepthRef.current > 0) {
			return;
		}

		const now = Date.now();
		if (now - lastMouseMoveLoggedAtRef.current < 120) {
			return;
		}

		const containerRect = containerRef.current?.getBoundingClientRect();
		if (!containerRect) {
			return;
		}

		lastMouseMoveLoggedAtRef.current = now;
		emitInteraction({
			type: 'mousemove',
			x: Number((event.clientX - containerRect.left).toFixed(1)),
			y: Number((event.clientY - containerRect.top).toFixed(1)),
			containerWidth: Number(containerRect.width.toFixed(1)),
			containerHeight: Number(containerRect.height.toFixed(1)),
		});
	};

	const handleContainerMouseDown = () => {
		emitInteraction({ type: 'mouse_down' });
	};

	const handleContainerMouseUp = () => {
		emitInteraction({ type: 'mouse_up' });
	};

	const handleContainerWheel = (event) => {
		emitInteraction({
			type: 'mouse_wheel',
			deltaY: Number(event?.deltaY?.toFixed?.(2) || event?.deltaY || 0),
			deltaX: Number(event?.deltaX?.toFixed?.(2) || event?.deltaX || 0),
		});
	};

	return (
		<div
			className="trajectory-graph"
			ref={containerRef}
			onMouseMove={handleContainerMouseMove}
			onMouseDown={handleContainerMouseDown}
			onMouseUp={handleContainerMouseUp}
			onWheel={handleContainerWheel}
		>
			{shouldShowPlaceholder && <p className="trajectory-graph__placeholder">{emptyMessage}</p>}
			<svg ref={svgRef} className="trajectory-graph__svg" role="presentation">
				<defs ref={defsRef} />
				<g ref={rootLayerRef} className="trajectory-graph__root">
					<g ref={linksLayerRef} className="trajectory-graph__links" />
					<g ref={linkActionsLayerRef} className="trajectory-graph__link-actions" />
					<g ref={nodesLayerRef} className="trajectory-graph__nodes" />
				</g>
			</svg>
			<div ref={tooltipRef} className="trajectory-tooltip" role="tooltip" aria-hidden="true" />
			{isLoading && <div className="trajectory-graph__loading">Processing trajectory…</div>}
		</div>
	);
};

TrajectoryGraph.propTypes = {
	graph: PropTypes.shape({
		nodes: PropTypes.arrayOf(
			PropTypes.shape({
				id: PropTypes.string.isRequired,
				src: PropTypes.string.isRequired,
				radius: PropTypes.number,
				occurrences: PropTypes.arrayOf(PropTypes.object),
			}),
		),
		links: PropTypes.arrayOf(
			PropTypes.shape({
				id: PropTypes.string.isRequired,
				source: PropTypes.oneOfType([PropTypes.string, PropTypes.object]).isRequired,
				target: PropTypes.oneOfType([PropTypes.string, PropTypes.object]).isRequired,
				count: PropTypes.number,
				color: PropTypes.string,
				sequenceIndex: PropTypes.number,
				sequenceLabel: PropTypes.string,
			}),
		),
		clusters: PropTypes.arrayOf(
			PropTypes.shape({
				id: PropTypes.string.isRequired,
				label: PropTypes.string,
				nodeIds: PropTypes.arrayOf(PropTypes.string),
				color: PropTypes.string,
			}),
		),
	}),
	isLoading: PropTypes.bool,
	enableNodeImages: PropTypes.bool,
	emptyMessage: PropTypes.string,
	containerSize: PropTypes.shape({
		width: PropTypes.number,
		height: PropTypes.number,
	}),
	highlightRequest: PropTypes.shape({
		id: PropTypes.string,
		label: PropTypes.string,
		color: PropTypes.string,
		sequenceIndex: PropTypes.number,
		nodePath: PropTypes.arrayOf(
			PropTypes.shape({
				nodeId: PropTypes.string.isRequired,
				position: PropTypes.number.isRequired,
			}),
		),
		linkPath: PropTypes.arrayOf(
			PropTypes.shape({
				linkId: PropTypes.string.isRequired,
				position: PropTypes.number.isRequired,
			}),
		),
		nonce: PropTypes.number,
		snapshotKey: PropTypes.string,
	}),
	onNodeClick: PropTypes.func,
	onLinkClick: PropTypes.func,
	onInteraction: PropTypes.func,
};

TrajectoryGraph.defaultProps = {
	graph: { nodes: [], links: [], clusters: [] },
	isLoading: false,
	enableNodeImages: true,
	emptyMessage: 'Select a run to explore its screenshot trajectory.',
	containerSize: null,
	highlightRequest: null,
	onNodeClick: null,
	onLinkClick: null,
	onInteraction: null,
};

export default TrajectoryGraph;
