import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './App.css';

import PanelHeader from './components/common/PanelHeader';
import ConfigurationView from './components/views/ConfigurationView';
import VisualizationView from './components/views/VisualizationView';
import VerticalTabs from './components/common/VerticalTabs';
import { cleanupServerFiles, fetchHistoryLogs, restartBackendService } from './services/api';
import { PersonaIcon, EnvironmentIcon } from './components/common/icons';
import { processVisualizationData } from './components/views/utils/visualizationDataProcessor';
import { useData } from './context/DataContext';
import CriteriaManagerModal from './components/criteria/CriteriaManagerModal';

const clamp = (value, min, max) => {
	if (Number.isNaN(value)) {
		return min;
	}

	if (min > max) {
		return min;
	}

	return Math.min(Math.max(value, min), max);
};

const MIN_LEFT = 0;
const MIN_CENTER = 1;

const CONFIG_TABS = [
	{ key: 'persona', label: 'Persona', icon: PersonaIcon, title: 'Persona Generation' },
	{ key: 'environment', label: 'Task', icon: EnvironmentIcon, title: 'Environment Setting' },
];

const DATA_SOURCE_OPTIONS = [
	{ value: 'data1', label: 'Data 1' },
	{ value: 'data2', label: 'Data 2' },
	{ value: 'data3', label: 'Data 3' },
];

const SYSTEM_VARIANT_OPTIONS = [
	{
		value: 'A',
		label: 'A',
		trajectoryUseImageHashEnabled: true,
		reasoningEvidenceHighlightEnabled: true,
	},
	{
		value: 'B',
		label: 'B',
		trajectoryUseImageHashEnabled: false,
		reasoningEvidenceHighlightEnabled: true,
	},
	{
		value: 'C',
		label: 'C',
		trajectoryUseImageHashEnabled: true,
		reasoningEvidenceHighlightEnabled: false,
	},
];

const DAG_FOCUS_EVENT_TYPES = new Set([
	'node_click',
	'node_drag_start',
	'node_drag_end',
	'node_pin_toggle',
	'zoom_pan',
]);

const DAG_EVENT_MIN_INTERVAL_BY_TYPE = {
	zoom_pan: 900,
};

const toRoundedNumber = (value, digits = 0) => {
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) {
		return null;
	}

	return Number(parsed.toFixed(digits));
};

const normalizeDAGInteractionForExport = (interaction, context = {}) => {
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

const buildDAGInteractionSummary = (interactions) => {
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

const getResponseErrorDetail = (response) => {
	if (!response) {
		return 'No response from server';
	}

	if (typeof response.data === 'string') {
		return response.data;
	}

	return response.data?.detail || `HTTP ${response.status}`;
};

const normalizeLogEntries = (value) => {
	if (!Array.isArray(value)) {
		return [];
	}

	return value
		.map((item) => (typeof item === 'string' ? item : (item === null || item === undefined ? '' : String(item))))
		.map((item) => item.trim())
		.filter(Boolean);
};

const computeSuffixPrefixOverlap = (existing, incoming) => {
	if (!Array.isArray(existing) || !Array.isArray(incoming) || existing.length === 0 || incoming.length === 0) {
		return 0;
	}

	const maxOverlap = Math.min(existing.length, incoming.length);
	for (let overlap = maxOverlap; overlap > 0; overlap -= 1) {
		let isMatch = true;
		for (let index = 0; index < overlap; index += 1) {
			if (existing[existing.length - overlap + index] !== incoming[index]) {
				isMatch = false;
				break;
			}
		}

		if (isMatch) {
			return overlap;
		}
	}

	return 0;
};

const mergeRunLogs = ({ existingLogs, snapshotLogs, appendLogs }) => {
	let merged = Array.isArray(existingLogs) ? existingLogs : [];

	if (Array.isArray(snapshotLogs) && snapshotLogs.length > 0) {
		const overlap = computeSuffixPrefixOverlap(merged, snapshotLogs);
		if (overlap < snapshotLogs.length) {
			merged = merged.concat(snapshotLogs.slice(overlap));
		}
	}

	if (Array.isArray(appendLogs) && appendLogs.length > 0) {
		const overlap = computeSuffixPrefixOverlap(merged, appendLogs);
		if (overlap < appendLogs.length) {
			merged = merged.concat(appendLogs.slice(overlap));
		}
	}

	return merged;
};

const App = () => {
	const { state: { experiments }, addExperiment, removeExperiment } = useData();
	const experimentEntries = useMemo(() => Object.values(experiments), [experiments]);
	const historyEntryCount = experimentEntries.length;
	const [environmentRunTabs, setEnvironmentRunTabs] = useState({});

	const environmentRunTabEntries = useMemo(
		() => Object.values(environmentRunTabs).sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0)),
		[environmentRunTabs],
	);

	const historyEntries = useMemo(
		() => [...experimentEntries, ...environmentRunTabEntries],
		[experimentEntries, environmentRunTabEntries],
	);

	const handleEnvironmentRunStateChange = useCallback((nextState) => {
		if (!nextState || typeof nextState !== 'object' || !nextState.runId) {
			return;
		}

		const { runId } = nextState;
		let shouldActivateNewTab = false;

		setEnvironmentRunTabs((prev) => {
			const currentCount = Object.keys(prev).length;
			const existing = prev[runId];

			if (!existing) {
				shouldActivateNewTab = true;
			}

			const incomingSnapshotLogs = normalizeLogEntries(nextState.logs);
			const incomingAppendLogs = normalizeLogEntries(nextState.appendLogs);
			const mergedLogs = mergeRunLogs({
				existingLogs: existing?.logs || [],
				snapshotLogs: incomingSnapshotLogs,
				appendLogs: incomingAppendLogs,
			});

			const taskName = typeof nextState.taskName === 'string' && nextState.taskName.trim()
				? nextState.taskName.trim()
				: (existing?.taskName || '');

			const status = nextState.status ?? existing?.status ?? null;

			return {
				...prev,
				[runId]: {
					id: runId,
					createdAt: existing?.createdAt || Date.now(),
					taskName,
					label: taskName || existing?.label || `Environment Run ${currentCount + (existing ? 0 : 1)}`,
					description: typeof status === 'string' && status.trim()
						? status.trim().toUpperCase()
						: undefined,
					status,
					isRunning: typeof nextState.isRunning === 'boolean'
						? nextState.isRunning
						: Boolean(existing?.isRunning),
					logs: mergedLogs,
					error: nextState.error !== undefined ? nextState.error : (existing?.error || null),
				},
			};
		});

		if (shouldActivateNewTab) {
			setActiveRunId(runId);
		}
	}, []);

	const handleAddRunEntry = useCallback((runPayload, options = {}) => {
		const { activate = true } = options;
		const index = historyEntryCount;
		const nextEntry = processVisualizationData(runPayload, index);
		
		addExperiment(nextEntry);

		if (activate) {
			setActiveRunId(nextEntry.id);
		}

		return nextEntry;
	}, [historyEntryCount, addExperiment]);

	const containerRef = useRef(null);
	const dragStateRef = useRef(null);
	const cacheRunsByDataSourceRef = useRef(new Map());
	const dagInteractionCounterRef = useRef(0);
	const dagInteractionLastRecordedAtRef = useRef(new Map());
	const dagZoomScaleByRunRef = useRef(new Map());

	const [sizes, setSizes] = useState({
		left: 50,
	});
	const [activeRunId, setActiveRunId] = useState(null);
	const [selectedDataSource, setSelectedDataSource] = useState('data1');
	const [selectedSystemVariant, setSelectedSystemVariant] = useState('A');
	const [trajectoryRefreshNonce, setTrajectoryRefreshNonce] = useState(0);
	const [isFetchingCache, setIsFetchingCache] = useState(false);
	const [isCleaningServerFiles, setIsCleaningServerFiles] = useState(false);
	const [isRestartingBackend, setIsRestartingBackend] = useState(false);
	const [activeConfigTab, setActiveConfigTab] = useState('persona');
	const [isCriteriaManagerOpen, setIsCriteriaManagerOpen] = useState(false);
	const [dagInteractions, setDagInteractions] = useState([]);

	const activeRun = useMemo(
		() => experimentEntries.find((item) => item.id === activeRunId) ?? null,
		[experimentEntries, activeRunId],
	);

	const activeEnvironmentRunTab = useMemo(
		() => environmentRunTabs[activeRunId] || null,
		[environmentRunTabs, activeRunId],
	);

	const activeSystemVariant = useMemo(
		() => SYSTEM_VARIANT_OPTIONS.find((option) => option.value === selectedSystemVariant) || SYSTEM_VARIANT_OPTIONS[0],
		[selectedSystemVariant],
	);
	const historyLogScreenshotMode = 'proxy';

	useEffect(() => {
		const handlePointerMove = (event) => {
			if (!dragStateRef.current) {
				return;
			}

			event.preventDefault();

			const { type, startX, startLeft, containerWidth } = dragStateRef.current;

			if (type === 'left') {
				if (!containerWidth) {
					return;
				}

				const deltaPercent = ((event.clientX - startX) / containerWidth) * 100;

				setSizes((prev) => {
					const maxLeft = 100 - MIN_CENTER;
					const safeMax = Math.max(MIN_LEFT, maxLeft);
					const nextLeft = clamp(startLeft + deltaPercent, MIN_LEFT, safeMax);
					const centerWidthPercent = 100 - nextLeft;

					if (centerWidthPercent < MIN_CENTER) {
						const adjustedLeft = 100 - MIN_CENTER;
						return { ...prev, left: clamp(adjustedLeft, MIN_LEFT, safeMax) };
					}

					return { ...prev, left: nextLeft };
				});

				return;
			}
		};

		const stopDragging = () => {
			if (!dragStateRef.current) {
				return;
			}

			dragStateRef.current = null;
			document.body.style.cursor = '';
			document.body.style.userSelect = '';
			document.body.classList.remove('is-resizing', 'is-resizing--vertical', 'is-resizing--horizontal');
		};

		window.addEventListener('mousemove', handlePointerMove);
		window.addEventListener('mouseup', stopDragging);

		return () => {
			window.removeEventListener('mousemove', handlePointerMove);
			window.removeEventListener('mouseup', stopDragging);
		};
	}, []);

	const handleGetCacheData = useCallback(async () => {
		setIsFetchingCache(true);

		const cacheKey = `${selectedDataSource}::${historyLogScreenshotMode}`;
		const cachedRun = cacheRunsByDataSourceRef.current.get(cacheKey);
		if (cachedRun?.id) {
			addExperiment(cachedRun);
			setActiveRunId(cachedRun.id);
		}

		try {
			const response = await fetchHistoryLogs({
				dataSource: selectedDataSource,
				screenshotMode: historyLogScreenshotMode,
			});

			if (!response.ok) {
				const error = new Error(`Failed to fetch history logs (status ${response.status})`);
				error.response = response;
				throw error;
			}
			
			const nextEntry = handleAddRunEntry(response.data, { activate: true });
			if (nextEntry?.id) {
				cacheRunsByDataSourceRef.current.set(cacheKey, nextEntry);
			}

		} catch (error) {
			alert(`Get cache data failed: ${error?.message || 'unknown error'}`);
		} finally {
			setIsFetchingCache(false);
		}
	}, [addExperiment, handleAddRunEntry, historyLogScreenshotMode, selectedDataSource]);

	const runConfirmedServerAction = useCallback(async ({
		confirmMessage,
		setLoading,
		action,
		onSuccess,
		onFailurePrefix,
	}) => {
		const confirmed = window.confirm(confirmMessage);
		if (!confirmed) {
			return;
		}

		setLoading(true);
		try {
			const response = await action();
			if (!response.ok || !response.data?.ok) {
				throw new Error(getResponseErrorDetail(response));
			}

			onSuccess(response);
		} catch (error) {
			alert(`${onFailurePrefix}: ${error?.message || 'unknown error'}`);
		} finally {
			setLoading(false);
		}
	}, []);

	const handleCleanupServerFiles = useCallback(async () => {
		await runConfirmedServerAction({
			confirmMessage: 'This will delete temporary Browser Agent run files under browser_agent_runs/ only. history_logs/ will not be touched. Continue?',
			setLoading: setIsCleaningServerFiles,
			action: cleanupServerFiles,
			onSuccess: (response) => {
				const deletedCount = Array.isArray(response.data.deleted) ? response.data.deleted.length : 0;
				const preservedCount = Array.isArray(response.data.preserved) ? response.data.preserved.length : 0;
				const skippedCount = Array.isArray(response.data.skipped) ? response.data.skipped.length : 0;
				const failedCount = Array.isArray(response.data.failed) ? response.data.failed.length : 0;
				alert(`Server cleanup completed. Deleted: ${deletedCount}, Preserved: ${preservedCount}, Skipped: ${skippedCount}, Failed: ${failedCount}`);
			},
			onFailurePrefix: 'Cleanup failed',
		});
	}, [runConfirmedServerAction]);

	const handleRestartBackend = useCallback(async () => {
		await runConfirmedServerAction({
			confirmMessage: 'This will restart the backend service. Ongoing backend tasks may stop temporarily. Continue?',
			setLoading: setIsRestartingBackend,
			action: restartBackendService,
			onSuccess: () => {
				alert('Backend restart requested. Please wait a few seconds before next operation.');
			},
			onFailurePrefix: 'Restart failed',
		});
	}, [runConfirmedServerAction]);

	const beginDrag = useCallback((type) => (event) => {
		event.preventDefault();

		const containerRect = containerRef.current?.getBoundingClientRect();

		dragStateRef.current = {
			type,
			startX: event.clientX,
			startLeft: sizes.left,
			containerWidth: containerRect ? containerRect.width : 0,
		};

		document.body.style.userSelect = 'none';
		document.body.style.cursor = 'col-resize';
		document.body.classList.add('is-resizing', 'is-resizing--vertical');
	}, [sizes.left]);

	const openCriteriaManager = useCallback(() => {
		setIsCriteriaManagerOpen(true);
	}, []);

	const closeCriteriaManager = useCallback(() => {
		setIsCriteriaManagerOpen(false);
	}, []);

	const handleDAGInteraction = useCallback((interaction) => {
		if (!interaction || typeof interaction !== 'object') {
			return;
		}

		const type = typeof interaction.type === 'string' ? interaction.type : 'unknown';
		if (!DAG_FOCUS_EVENT_TYPES.has(type)) {
			return;
		}

		const runKey = activeRunId || 'global';
		const now = Date.now();
		const throttleKey = `${runKey}::${type}`;
		const minInterval = DAG_EVENT_MIN_INTERVAL_BY_TYPE[type] || 0;
		const lastRecordedAt = dagInteractionLastRecordedAtRef.current.get(throttleKey) || 0;
		if (minInterval > 0 && now - lastRecordedAt < minInterval) {
			return;
		}

		dagInteractionLastRecordedAtRef.current.set(throttleKey, now);

		const normalizedPayload = normalizeDAGInteractionForExport(interaction, {
			runKey,
			zoomScaleByRunRef: dagZoomScaleByRunRef,
		});
		if (!normalizedPayload) {
			return;
		}

		dagInteractionCounterRef.current += 1;
		const normalizedInteraction = {
			sequence: dagInteractionCounterRef.current,
			recordedAt: new Date(now).toISOString(),
			runId: activeRunId || null,
			...normalizedPayload,
		};

		setDagInteractions((prev) => [...prev, normalizedInteraction]);
	}, [activeRunId]);

	const handleExportDAGInteractions = useCallback(() => {
		if (!dagInteractions.length) {
			alert('No DAG interaction data to export.');
			return;
		}

		const timestamp = new Date();
		const summary = buildDAGInteractionSummary(dagInteractions);
		const payload = {
			exportVersion: 'dag_interactions_focused_v2',
			granularity: 'focused',
			exportedAt: timestamp.toISOString(),
			count: dagInteractions.length,
			summary,
			samplingPolicy: {
				focusEventTypes: Array.from(DAG_FOCUS_EVENT_TYPES),
				minIntervalMsByType: DAG_EVENT_MIN_INTERVAL_BY_TYPE,
			},
			interactions: dagInteractions,
		};
		const fileName = `dag_interactions_${timestamp.toISOString().replace(/[:.]/g, '-')}.json`;

		let objectUrl = null;
		try {
			const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
			objectUrl = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = objectUrl;
			anchor.download = fileName;
			document.body.appendChild(anchor);
			anchor.click();
			document.body.removeChild(anchor);

			setDagInteractions([]);
			dagInteractionCounterRef.current = 0;
			dagInteractionLastRecordedAtRef.current.clear();
			dagZoomScaleByRunRef.current.clear();
			alert(`Exported ${payload.count} focused DAG interactions.`);
		} catch (error) {
			alert(`Failed to export DAG interactions: ${error?.message || 'unknown error'}`);
		} finally {
			if (objectUrl) {
				URL.revokeObjectURL(objectUrl);
			}
		}
	}, [dagInteractions]);

	const centerWeight = Math.max(MIN_CENTER, 100 - sizes.left);

	useEffect(() => {
		if (!historyEntries.length) {
			if (activeRunId !== null) {
				setActiveRunId(null);
			}
			return;
		}

		if (!historyEntries.some((item) => item.id === activeRunId)) {
			setActiveRunId(historyEntries[0].id);
		}
	}, [historyEntries, activeRunId]);

	const handleCloseTab = useCallback((id) => {
		const index = historyEntries.findIndex((item) => item.id === id);
		if (index === -1) {
			return;
		}

		if (experiments[id]) {
			removeExperiment(id);
		}

		setEnvironmentRunTabs((prev) => {
			if (!prev[id]) {
				return prev;
			}

			const next = { ...prev };
			delete next[id];
			return next;
		});

		const nextItems = [...historyEntries.slice(0, index), ...historyEntries.slice(index + 1)];
		
		setActiveRunId((current) => {
			if (current && current !== id && nextItems.some((item) => item.id === current)) {
				return current;
			}

			if (!nextItems.length) {
				return null;
			}

			const fallbackIndex = index >= nextItems.length ? nextItems.length - 1 : index;
			return nextItems[fallbackIndex].id;
		});
	}, [historyEntries, experiments, removeExperiment]);

	const handleDataSourceChange = useCallback((event) => {
		setSelectedDataSource(event.target.value);
	}, []);

	const handleSystemVariantChange = useCallback((event) => {
		setSelectedSystemVariant(event.target.value);
		setTrajectoryRefreshNonce((prev) => prev + 1);
	}, []);

	return (
		<div className="app-shell">
			<header className="app-shell__banner">
				<div className="panel panel--page">
					<PanelHeader
						title="Eval Agent"
						variant="page"
						onExportData={handleExportDAGInteractions}
						isExportDisabled={!dagInteractions.length}
						onCleanupServer={handleCleanupServerFiles}
						onRestartBackend={handleRestartBackend}
						onGetCacheData={handleGetCacheData}
						isCacheLoading={isFetchingCache}
						isCleanupLoading={isCleaningServerFiles}
						isRestartLoading={isRestartingBackend}
					>
						<div className="app-shell__header-selectors" aria-label="Data and preset selectors">
							<label className="app-shell__header-field" htmlFor="app-shell-data-source">
								<span>Data</span>
								<select
									id="app-shell-data-source"
									value={selectedDataSource}
									onChange={handleDataSourceChange}
								>
									{DATA_SOURCE_OPTIONS.map((option) => (
										<option key={option.value} value={option.value}>{option.label}</option>
									))}
								</select>
							</label>
								<label className="app-shell__header-field" htmlFor="app-shell-system-variant">
									<span>Preset</span>
								<select
										id="app-shell-system-variant"
										value={selectedSystemVariant}
										onChange={handleSystemVariantChange}
								>
										{SYSTEM_VARIANT_OPTIONS.map((option) => (
											<option key={option.value} value={option.value}>{option.label}</option>
										))}
								</select>
							</label>
						</div>
					</PanelHeader>
				</div>
			</header>
			<main className="app-layout" ref={containerRef}>
				<section
					className="panel-area panel-area--configuration"
					style={{ flexGrow: sizes.left }}
				>
					<VerticalTabs
						items={CONFIG_TABS}
						activeKey={activeConfigTab}
						onChange={setActiveConfigTab}
						containerClassName="config-vertical-tabs"
					/>

					<ConfigurationView 
						onAddRun={handleAddRunEntry}
						activeTab={activeConfigTab}
						onTabChange={setActiveConfigTab}
						onGetCacheData={handleGetCacheData}
						isCacheLoading={isFetchingCache}
						onEnvironmentRunStateChange={handleEnvironmentRunStateChange}
					/>
				</section>

				<div
					className="divider divider--vertical"
					role="separator"
					aria-orientation="vertical"
					tabIndex={0}
					onMouseDown={beginDrag('left')}
				/>

				<section
					className="panel-area panel-area--visualization"
					style={{ flexGrow: centerWeight }}
				>
					<VisualizationView
						activeRun={activeRun}
						historyEntries={historyEntries}
						activeRunId={activeRunId}
						onSelectRun={setActiveRunId}
						onCloseRun={handleCloseTab}
						onManageCriteria={openCriteriaManager}
						onDAGInteraction={handleDAGInteraction}
						trajectoryUseImageHashEnabled={activeSystemVariant.trajectoryUseImageHashEnabled}
						trajectoryRefreshNonce={trajectoryRefreshNonce}
						reasoningEvidenceHighlightEnabled={activeSystemVariant.reasoningEvidenceHighlightEnabled}
						showBackendLogs={Boolean(activeEnvironmentRunTab)}
						backendLogs={activeEnvironmentRunTab?.logs || []}
						backendRunStatus={activeEnvironmentRunTab?.status || null}
					/>
				</section>
			</main>
			{isCriteriaManagerOpen && (
				<CriteriaManagerModal onClose={closeCriteriaManager} />
			)}
		</div>
	);
};

export default App;
