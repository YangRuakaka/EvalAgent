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
