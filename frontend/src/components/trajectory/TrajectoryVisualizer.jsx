import React, { useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';

import PanelHeader from '../common/PanelHeader';
import { TrajectoryIcon } from '../common/icons';
import TrajectoryGraph from './TrajectoryGraph';
import buildTrajectoryGraph from './utils/graphBuilder';
import ScreenshotPopUp from './ScreenshotPopUp';
import useResizeObserver from '../../hooks/useResizeObserver';

import './TrajectoryVisualizer.css';

const EMPTY_GRAPH = Object.freeze({ nodes: [], links: [], clusters: [], meta: {} });

const DEFAULT_CLUSTER_THRESHOLD = 0;

const PersonaPopUp = ({ entry, onClose }) => {
	if (!entry) return null;
	const { fullPersona, label } = entry;

	let content = null;
	if (typeof fullPersona === 'string') {
		content = fullPersona;
	} else if (typeof fullPersona === 'object' && fullPersona !== null) {
		if (fullPersona.content && typeof fullPersona.content === 'string') {
			content = fullPersona.content;
		} else if (fullPersona.description && typeof fullPersona.description === 'string') {
			content = fullPersona.description;
		} else {
			content = JSON.stringify(fullPersona, null, 2);
		}
	} else {
		content = String(fullPersona);
	}

	return (
		<div className="trajectory-modal" onClick={onClose} style={{ zIndex: 10000 }}>
			<div
				className="trajectory-modal__content"
				onClick={(e) => e.stopPropagation()}
				style={{ maxWidth: '600px', maxHeight: '80vh', padding: '24px', overflowY: 'auto' }}
			>
				<button
					type="button"
					className="trajectory-modal__close"
					onClick={onClose}
					aria-label="Close details"
				>
					<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
						<line x1="18" y1="6" x2="6" y2="18"></line>
						<line x1="6" y1="6" x2="18" y2="18"></line>
					</svg>
				</button>
				<h3 style={{ marginTop: 0, marginBottom: '1rem', fontSize: '1.1rem', color: '#1e293b' }}>Persona Details</h3>
				<div style={{ marginBottom: '1rem', fontSize: '0.9rem', color: '#64748b' }}>
					<strong>Run:</strong> {label}
				</div>
				<div
					className="trajectory-modal__memory-content"
					style={{
						fontSize: '0.9rem',
						lineHeight: '1.5',
						whiteSpace: 'pre-wrap',
						background: '#f8fafc',
						padding: '12px',
						borderRadius: '6px',
						border: '1px solid #e2e8f0',
					}}
				>
					{content}
				</div>
			</div>
		</div>
	);
};

const buildHighlightSnapshot = (entry, meta) => {
 const nodeCount = Array.isArray(entry?.nodePath) ? entry.nodePath.length : 0;
 const linkCount = Array.isArray(entry?.linkPath) ? entry.linkPath.length : 0;
 const totalScreens = Number.isFinite(meta?.totalScreenshots) ? meta.totalScreenshots : 0;
	const totalNodes = Number.isFinite(meta?.totalNodes) ? meta.totalNodes : 0;
	const totalLinks = Number.isFinite(meta?.totalLinks) ? meta.totalLinks : 0;
	return `${entry?.id || 'sequence'}:${nodeCount}:${linkCount}:${totalScreens}:${totalNodes}:${totalLinks}`;
};

const TrajectoryVisualizer = ({ trajectory, conditions }) => {
	const [graph, setGraph] = useState(EMPTY_GRAPH);
	const [isProcessing, setIsProcessing] = useState(false);
	const [error, setError] = useState(null);
	const [clusterThreshold, setClusterThreshold] = useState(DEFAULT_CLUSTER_THRESHOLD);
	const [filterType, setFilterType] = useState('all'); // 'all' | 'model' | 'persona' | 'task'
	const [filterValue, setFilterValue] = useState(null);
	const [activeLegendId, setActiveLegendId] = useState(null);
	const [highlightRequest, setHighlightRequest] = useState(null);
	const [selectedNode, setSelectedNode] = useState(null);
	const [viewingPersonaEntry, setViewingPersonaEntry] = useState(null);
	const [isFullscreen, setIsFullscreen] = useState(false);
	const graphShellRef = useRef(null);
	const containerRef = useRef(null);

	const { width: shellWidth, height: shellHeight } = useResizeObserver(graphShellRef);

	const graphSize = useMemo(() => {
		if (shellWidth > 0 && shellHeight > 0) {
			return { width: shellWidth, height: shellHeight };
		}

		return null;
	}, [shellWidth, shellHeight]);

	const hasTrajectory = Boolean(trajectory?.details);

	useEffect(() => {
		let isMounted = true;

		if (!hasTrajectory) {
			setGraph(EMPTY_GRAPH);
			setError(null);
			setIsProcessing(false);
			return () => {
				isMounted = false;
			};
		}

		setIsProcessing(true);
		setError(null);

		buildTrajectoryGraph(trajectory, {
			hash: { hashSize: 16 },
			clusterThreshold,
			conditions: conditions || [],
		})
			.then((result) => {
				if (isMounted) {
					setGraph(result);
				}
			})
			.catch((err) => {
				if (isMounted) {
					console.error('[trajectory] Failed to build graph', err);
					setGraph(EMPTY_GRAPH);
					setError(err);
				}
			})
			.finally(() => {
				if (isMounted) {
					setIsProcessing(false);
				}
			});

		return () => {
			isMounted = false;
		};
	}, [clusterThreshold, hasTrajectory, trajectory, conditions]);

	const handleClusterThresholdChange = (event) => {
		const nextValue = Number(event?.target?.value);
		if (Number.isFinite(nextValue)) {
			setClusterThreshold(nextValue);
		}
	};


	const legendEntries = useMemo(() => {
		const details = Array.isArray(trajectory?.details) ? trajectory.details : [];
		const colorMap = new Map();
		if (Array.isArray(graph?.links)) {
			graph.links.forEach(link => {
				if (typeof link.sequenceIndex === 'number' && link.color) {
					if (!colorMap.has(link.sequenceIndex)) {
						colorMap.set(link.sequenceIndex, link.color);
					}
				}
			});
		}
		const nodePathMap = new Map();
		const linkPathMap = new Map();
		if (Array.isArray(graph?.nodes)) {
			graph.nodes.forEach((node) => {
				if (Array.isArray(node.occurrences)) {
					node.occurrences.forEach((occ) => {
						if (typeof occ.sequenceIndex === 'number') {
							if (!nodePathMap.has(occ.sequenceIndex)) nodePathMap.set(occ.sequenceIndex, []);
							nodePathMap.get(occ.sequenceIndex).push({ nodeId: node.id, position: occ.position });
						}
					});
				}
			});
		}
		if (Array.isArray(graph?.links)) {
			graph.links.forEach((link) => {
				if (typeof link.sequenceIndex === 'number' && link.id) {
					if (!linkPathMap.has(link.sequenceIndex)) linkPathMap.set(link.sequenceIndex, []);
					const pos = typeof link.position === 'number' ? link.position : (link.source && link.target ? 0 : 0);
					linkPathMap.get(link.sequenceIndex).push({ linkId: link.id, position: pos });
				}
			});
		}
		return details.map((item, index) => {
			const model = item.model || '';
			const personaValue = item.value || item.metadata?.value || item.persona?.value || '';
			const taskName = item.task?.name || item.metadata?.task?.name || '';
			const runIndex = item.run_index !== undefined ? item.run_index : index;
			const label = `#${runIndex} ${model}${personaValue ? ' (' + personaValue + ')' : ''}${taskName ? ' - ' + taskName : ''}`;
			const color = colorMap.get(index) || '#1e3a8a';
			const nodePath = (nodePathMap.get(index) || []).slice().sort((a, b) => a.position - b.position);
			let linkPath = [];
			if (Array.isArray(graph?.links) && nodePath.length > 1) {
				for (let i = 0; i < nodePath.length - 1; i++) {
					const from = nodePath[i].nodeId;
					const to = nodePath[i + 1].nodeId;
					const pos = nodePath[i].position;
					const link = graph.links.find(
						l => l.sequenceIndex === index &&
							((l.source?.id || l.source) === from) &&
							((l.target?.id || l.target) === to)
					);
					if (link) {
						linkPath.push({ linkId: link.id, position: pos });
					}
				}
			}

			const fullPersona = item.persona || item.metadata?.persona || null;

			return {
				id: `${model}-${personaValue}-${taskName}-${index}`,
				model,
				personaValue,
				taskName,
				runIndex,
				label,
				color,
				sequenceIndex: index,
				nodePath,
				linkPath,
				fullPersona,
			};
		});
	}, [trajectory, graph]);

	// derive available filter options from legendEntries
	const availableModels = useMemo(() => {
		const set = new Set();
		legendEntries.forEach((e) => { if (e.model) set.add(e.model); });
		return Array.from(set);
	}, [legendEntries]);

	const availablePersonas = useMemo(() => {
		const set = new Set();
		legendEntries.forEach((e) => { if (e.personaValue) set.add(e.personaValue); });
		return Array.from(set);
	}, [legendEntries]);

	const availableTasks = useMemo(() => {
		const set = new Set();
		legendEntries.forEach((e) => { if (e.taskName) set.add(e.taskName); });
		return Array.from(set);
	}, [legendEntries]);

	useEffect(() => {
		// if filter type changes, reset filterValue to a sensible default
		if (filterType === 'all') {
			setFilterValue(null);
			return;
		}
		if (filterType === 'model') {
			setFilterValue((prev) => (prev && availableModels.includes(prev) ? prev : (availableModels[0] || null)));
			return;
		}
		if (filterType === 'persona') {
			setFilterValue((prev) => (prev && availablePersonas.includes(prev) ? prev : (availablePersonas[0] || null)));
			return;
		}
		if (filterType === 'task') {
			setFilterValue((prev) => (prev && availableTasks.includes(prev) ? prev : (availableTasks[0] || null)));
			return;
		}
	}, [filterType, availableModels, availablePersonas, availableTasks]);

	// compute a filtered view of the graph according to selected filter
	const filteredGraph = useMemo(() => {
		// Single-dimensional filtering
		if (filterType === 'all' || !filterValue) return graph;

		const allowedSeq = new Set(
			legendEntries
				.filter((e) => {
					if (filterType === 'model') return e.model === filterValue;
					if (filterType === 'persona') return e.personaValue === filterValue;
					if (filterType === 'task') return e.taskName === filterValue;
					return false;
				})
				.map((e) => e.sequenceIndex),
		);

		if (!allowedSeq.size) {
			return { nodes: [], links: [], clusters: [], meta: graph?.meta || {} };
		}

		const links = Array.isArray(graph?.links) ? graph.links.filter((l) => allowedSeq.has(l.sequenceIndex)) : [];
		const nodeIdsFromLinks = new Set(links.map((l) => (l.source?.id || l.source) || (l.target?.id || l.target)).flat());

		const nodes = Array.isArray(graph?.nodes)
			? graph.nodes.filter((n) => {
				if (nodeIdsFromLinks.has(n.id)) return true;
				if (Array.isArray(n.occurrences)) {
					return n.occurrences.some((occ) => allowedSeq.has(occ.sequenceIndex));
				}
				return false;
			})
			: [];

		const nodeIdSet = new Set(nodes.map((n) => n.id));
		const clusters = Array.isArray(graph?.clusters)
			? graph.clusters
				.map((c) => ({ ...c, nodeIds: (c.nodeIds || []).filter((id) => nodeIdSet.has(id)) }))
				.filter((c) => (c.nodeIds || []).length > 0)
			: [];

		return { nodes, links, clusters, meta: graph?.meta || {} };
	}, [graph, filterType, filterValue, legendEntries]);

	// compute visible legend entries according to the same filter
	const visibleLegendEntries = useMemo(() => {
		if (filterType === 'all' || !filterValue) return legendEntries;
		return legendEntries.filter((e) => {
			if (filterType === 'model') return e.model === filterValue;
			if (filterType === 'persona') return e.personaValue === filterValue;
			if (filterType === 'task') return e.taskName === filterValue;
			return false;
		});
	}, [legendEntries, filterType, filterValue]);

	useEffect(() => {
		if (!activeLegendId) {
			return;
		}

		const matchingEntry = visibleLegendEntries.find((entry) => entry.id === activeLegendId);
		if (!matchingEntry) {
			setActiveLegendId(null);
			setHighlightRequest(null);
			return;
		}

		const snapshotKey = buildHighlightSnapshot(matchingEntry, graph?.meta);
		setHighlightRequest((prev) => {
			if (prev && prev.id === matchingEntry.id && prev.snapshotKey === snapshotKey) {
				return prev;
			}
			return {
				id: matchingEntry.id,
				label: matchingEntry.label,
				color: matchingEntry.color,
				sequenceIndex: matchingEntry.sequenceIndex,
				nodePath: matchingEntry.nodePath.map((step) => ({ ...step })),
				linkPath: matchingEntry.linkPath.map((step) => ({ ...step })),
				nonce: Date.now(),
				snapshotKey,
			};
		});
	}, [activeLegendId, visibleLegendEntries, graph]);

		// clear active legend if it becomes invisible due to filter changes
		useEffect(() => {
			if (activeLegendId && !visibleLegendEntries.find((e) => e.id === activeLegendId)) {
				setActiveLegendId(null);
				setHighlightRequest(null);
			}
		}, [activeLegendId, visibleLegendEntries]);

	const handleLegendActivate = (entry) => {
		if (!entry) {
			setActiveLegendId(null);
			setHighlightRequest(null);
			return;
		}

		setActiveLegendId(entry.id);
		const snapshotKey = buildHighlightSnapshot(entry, graph?.meta);
		setHighlightRequest({
			id: entry.id,
			label: entry.label,
			color: entry.color,
			sequenceIndex: entry.sequenceIndex,
			nodePath: entry.nodePath.map((step) => ({ ...step })),
			linkPath: entry.linkPath.map((step) => ({ ...step })),
			nonce: Date.now(),
			snapshotKey,
		});
	};

	const handleNodeClick = (node) => {
		if (node && node.src) {
			setSelectedNode(node);
		}
	};

	const toggleFullscreen = () => {
		if (!containerRef.current) return;

		if (!document.fullscreenElement) {
			containerRef.current.requestFullscreen().catch((err) => {
				console.error(`Error attempting to enable fullscreen: ${err.message} (${err.name})`);
			});
		} else {
			document.exitFullscreen();
		}
	};

	useEffect(() => {
		const handleFullscreenChange = () => {
			setIsFullscreen(Boolean(document.fullscreenElement));
		};

		document.addEventListener('fullscreenchange', handleFullscreenChange);
		return () => {
			document.removeEventListener('fullscreenchange', handleFullscreenChange);
		};
	}, []);

	return (
		<div className={`trajectory-panel${isFullscreen ? ' is-fullscreen' : ''}`} ref={containerRef}>
			<PanelHeader title="Trajectory" icon={<TrajectoryIcon />}>
				<label className="trajectory-threshold" htmlFor="trajectory-cluster-threshold">
					<span className="trajectory-threshold__label">Cluster Threshold</span>
					<input
						type="range"
						id="trajectory-cluster-threshold"
						min="0"
						max="128"
						step="1"
						value={clusterThreshold}
						onChange={handleClusterThresholdChange}
						aria-label="Adjust cluster grouping sensitivity"
					/>
					<span className="trajectory-threshold__value">{clusterThreshold}</span>
				</label>

				<div className="trajectory-filter" aria-label="Trajectory filter controls">
					<label className="trajectory-filter__label" htmlFor="trajectory-filter-type">Filter</label>
					<select
						id="trajectory-filter-type"
						value={filterType}
						onChange={(e) => setFilterType(e?.target?.value)}
						aria-label="Choose filter type"
					>
						<option value="all">All</option>
						<option value="model">Model</option>
						<option value="persona">Persona</option>
					</select>
					<select
						id="trajectory-filter-value"
						value={filterValue || ''}
						onChange={(e) => setFilterValue(e?.target?.value)}
						disabled={filterType === 'all'}
						aria-label="Choose filter value"
					>
						<option value="">--</option>
						{filterType === 'model' && availableModels.map((m) => (
							<option key={`m-${m}`} value={m}>{m}</option>
						))}
						{filterType === 'persona' && availablePersonas.map((p) => (
							<option key={`p-${p}`} value={p}>{p}</option>
						))}
						{filterType === 'task' && availableTasks.map((t) => (
							<option key={`t-${t}`} value={t}>{t}</option>
						))}
					</select>
				</div>

				<button
					type="button"
					className="trajectory-fullscreen-toggle"
					onClick={toggleFullscreen}
					aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
					title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
				>
					{isFullscreen ? (
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
							<path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
						</svg>
					) : (
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
							<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
						</svg>
					)}
				</button>
			</PanelHeader>
			<div className="trajectory-panel__body">
					{visibleLegendEntries.length > 0 && (
						<div className="trajectory-legend" aria-label="Sequence color legend" role="list">
						{visibleLegendEntries.map((entry) => (
							<div
								className={`trajectory-legend__item${entry.id === activeLegendId ? ' trajectory-legend__item--active' : ''}`}
								role="listitem"
								key={entry.id}
							>
								<button
									type="button"
									className="trajectory-legend__control"
									aria-pressed={entry.id === activeLegendId}
									onClick={() => handleLegendActivate(entry)}
								>
									<span
										className="trajectory-legend__swatch"
										style={{ backgroundColor: entry.color }}
									/>
									<span className="trajectory-legend__label">{entry.label}</span>
								</button>
								{entry.fullPersona && (
									<button
										type="button"
										className="trajectory-legend__info-btn"
										onClick={(e) => {
											e.stopPropagation();
											setViewingPersonaEntry(entry);
										}}
										title="View persona details"
										aria-label="View persona"
										style={{
											marginLeft: '4px',
											background: 'none',
											border: 'none',
											padding: '2px', // increased hit area slightly with flex centering
											cursor: 'pointer',
											color: '#64748b',
											display: 'flex',
											alignItems: 'center',
											opacity: 0.6,
											transition: 'opacity 0.2s',
										}}
										onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
										onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.6')}
									>
										<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
											<circle cx="12" cy="12" r="10"></circle>
											<line x1="12" y1="16" x2="12" y2="12"></line>
											<line x1="12" y1="8" x2="12.01" y2="8"></line>
										</svg>
									</button>
								)}
							</div>
						))}
					</div>
				)}
				{error && (
					<p className="trajectory-error" role="alert">
						We could not parse trajectory data. Please try again shortly.
					</p>
				)}
				<div className="trajectory-graph__shell" ref={graphShellRef}>
					<TrajectoryGraph
						graph={filteredGraph}
						isLoading={isProcessing}
						containerSize={graphSize}
						emptyMessage={hasTrajectory ? 'Preparing visualization…' : 'Select a run to explore its screenshot trajectory.'}
						highlightRequest={highlightRequest}
						onNodeClick={handleNodeClick}
					/>
				</div>
			</div>
			{selectedNode && (
				<ScreenshotPopUp
					node={selectedNode}
					legendEntries={legendEntries}
					onClose={() => setSelectedNode(null)}
				/>
			)}
			<PersonaPopUp
				entry={viewingPersonaEntry}
				onClose={() => setViewingPersonaEntry(null)}
			/>
		</div>
	);
};

TrajectoryVisualizer.propTypes = {
	trajectory: PropTypes.shape({
		steps: PropTypes.number,
		maxReturn: PropTypes.number,
		avgReturn: PropTypes.number,
		length: PropTypes.string,
		details: PropTypes.oneOfType([
			PropTypes.arrayOf(
				PropTypes.shape({
					screenshots: PropTypes.array,
				}),
			),
			PropTypes.shape({ screenshots: PropTypes.array }),
		]),
	}),
	conditions: PropTypes.arrayOf(
		PropTypes.shape({
			id: PropTypes.string,
			model: PropTypes.string,
			persona: PropTypes.string,
		}),
	),
};

TrajectoryVisualizer.defaultProps = {
	trajectory: undefined,
	conditions: [],
};

export default TrajectoryVisualizer;
