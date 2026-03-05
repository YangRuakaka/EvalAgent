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
	{ key: 'environment', label: 'Environment', icon: EnvironmentIcon, title: 'Environment Setting' },
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

const App = () => {
	const { state: { experiments }, addExperiment, removeExperiment } = useData();
	
	// Derive historyEntries from context for compatibility
	const historyEntries = useMemo(() => Object.values(experiments), [experiments]);
	const historyEntryCount = historyEntries.length;

	const handleAddRunEntry = useCallback((runPayload) => {
		const index = historyEntryCount;
		const nextEntry = processVisualizationData(runPayload, index);
		
		addExperiment(nextEntry);
		setActiveRunId(nextEntry.id);
	}, [historyEntryCount, addExperiment]);

	const containerRef = useRef(null);
	const dragStateRef = useRef(null);

	const [sizes, setSizes] = useState({
		left: 50,
	});
	const [activeRunId, setActiveRunId] = useState(null);
	const [isFetchingCache, setIsFetchingCache] = useState(false);
	const [isCleaningServerFiles, setIsCleaningServerFiles] = useState(false);
	const [isRestartingBackend, setIsRestartingBackend] = useState(false);
	const [activeConfigTab, setActiveConfigTab] = useState('persona');
	const [isCriteriaManagerOpen, setIsCriteriaManagerOpen] = useState(false);

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

		try {
			const response = await fetchHistoryLogs();

			if (!response.ok) {
				const error = new Error(`Failed to fetch history logs (status ${response.status})`);
				error.response = response;
				throw error;
			}
			
			const processedData = processVisualizationData(response.data);

			addExperiment(processedData);
			setActiveRunId(processedData.id);

		} catch (error) {
			alert(`Get cache data failed: ${error?.message || 'unknown error'}`);
		} finally {
			setIsFetchingCache(false);
		}
	}, [addExperiment]);

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
			confirmMessage: 'This will clean extra files in backend/history_logs, and only keep buy_milk* items (including screenshots/buy_milk*). Continue?',
			setLoading: setIsCleaningServerFiles,
			action: cleanupServerFiles,
			onSuccess: (response) => {
				const deletedCount = Array.isArray(response.data.deleted) ? response.data.deleted.length : 0;
				const failedCount = Array.isArray(response.data.failed) ? response.data.failed.length : 0;
				alert(`History logs cleanup completed. Deleted: ${deletedCount}, Failed: ${failedCount}`);
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
	const activeRun = useMemo(
		() => historyEntries.find((item) => item.id === activeRunId) ?? null,
		[historyEntries, activeRunId],
	);

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
		removeExperiment(id);
		
		// Calculate next active ID
		const index = historyEntries.findIndex((item) => item.id === id);
		if (index === -1) {
			return;
		}

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
	}, [historyEntries, removeExperiment]);

	return (
		<div className="app-shell">
			<header className="app-shell__banner">
				<div className="panel panel--page">
					<PanelHeader
						title="Eval Agent"
						variant="page"
						onManageCriteria={openCriteriaManager}
						onCleanupServer={handleCleanupServerFiles}
						onRestartBackend={handleRestartBackend}
						onGetCacheData={handleGetCacheData}
						isCacheLoading={isFetchingCache}
						isCleanupLoading={isCleaningServerFiles}
						isRestartLoading={isRestartingBackend}
					/>
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
