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

// Utilities
import { getResponseErrorDetail } from './utils/apiUtils';

// Hooks
import { usePanelResizer } from './hooks/usePanelResizer';
import { useDagInteractions } from './hooks/useDagInteractions';
import { useEnvironmentRuns } from './hooks/useEnvironmentRuns';

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

const App = () => {
	const { state: { experiments }, addExperiment, removeExperiment } = useData();
	const experimentEntries = useMemo(() => Object.values(experiments), [experiments]);
	const historyEntryCount = experimentEntries.length;

	const [activeRunId, setActiveRunId] = useState(null);
	const [selectedDataSource, setSelectedDataSource] = useState('data1');
	const [selectedSystemVariant, setSelectedSystemVariant] = useState('A');
	const [trajectoryRefreshNonce, setTrajectoryRefreshNonce] = useState(0);
	const [isFetchingCache, setIsFetchingCache] = useState(false);
	const [isCleaningServerFiles, setIsCleaningServerFiles] = useState(false);
	const [isRestartingBackend, setIsRestartingBackend] = useState(false);
	const [activeConfigTab, setActiveConfigTab] = useState('persona');
	const [isCriteriaManagerOpen, setIsCriteriaManagerOpen] = useState(false);
	
	const cacheRunsByDataSourceRef = useRef(new Map());
    const MIN_CENTER = 1;

	// Custom Hooks
	const { sizes, containerRef, beginDrag } = usePanelResizer(50);
	const { dagInteractions, handleDAGInteraction, handleExportDAGInteractions } = useDagInteractions(activeRunId);
	const { 
		environmentRunTabs, 
		environmentRunTabEntries, 
		handleEnvironmentRunStateChange,
		removeEnvironmentRun 
	} = useEnvironmentRuns(setActiveRunId);

	const historyEntries = useMemo(
		() => [...experimentEntries, ...environmentRunTabEntries],
		[experimentEntries, environmentRunTabEntries],
	);

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

		removeEnvironmentRun(id);

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
	}, [historyEntries, experiments, removeExperiment, removeEnvironmentRun]);

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