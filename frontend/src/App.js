import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './App.css';

import PanelHeader from './components/common/PanelHeader';
import ConfigurationView from './components/views/ConfigurationView';
import VisualizationView from './components/views/VisualizationView';
import VerticalTabs from './components/common/VerticalTabs';
import { fetchHistoryLogs } from './services/api';
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

const App = () => {
	const { state: { experiments }, addExperiment, removeExperiment } = useData();
	
	// Derive historyEntries from context for compatibility
	const historyEntries = useMemo(() => Object.values(experiments), [experiments]);

	const handleAddRunEntry = useCallback((runPayload) => {
		const index = Object.keys(experiments).length;
		const nextEntry = processVisualizationData(runPayload, index);
		
		addExperiment(nextEntry);
		setActiveRunId(nextEntry.id);
	}, [experiments, addExperiment]);

	const containerRef = useRef(null);
	// const dragStateRef = useRef(null); // Removed unused ref
	const dragStateRef = useRef({
		type: null,
		startX: 0,
		startLeft: 0,
		containerWidth: 0,
	});

	const [sizes, setSizes] = useState({
		left: 50,
	});
	// const [historyEntries, setHistoryEntries] = useState([]); // Removed local state
	const [activeRunId, setActiveRunId] = useState(null);
	const [isFetchingCache, setIsFetchingCache] = useState(false);
	const [cacheError, setCacheError] = useState(null);
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
		setCacheError(null);

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
			setCacheError(error);
		} finally {
			setIsFetchingCache(false);
		}
	}, [addExperiment]);

	useEffect(() => {
		if (cacheError) {
		}
	}, [cacheError]);

	const beginDrag = (type) => (event) => {
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
	};

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

	const handleCloseTab = (id) => {
		removeExperiment(id);
		
		// Calculate next active ID
		const index = historyEntries.findIndex((item) => item.id === id);
		if (index === -1) return;

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
	};

	return (
		<div className="app-shell">
			<header className="app-shell__banner">
				<div className="panel panel--page">
					<PanelHeader
						title="Eval Agent"
						variant="page"
						onManageCriteria={() => setIsCriteriaManagerOpen(true)}
						onGetCacheData={handleGetCacheData}
						isCacheLoading={isFetchingCache}
					/>
				</div>
			</header>
			<main className="app-layout" ref={containerRef}>
				<section
					className="panel-area panel-area--configuration"
					style={{ flexGrow: sizes.left }}
				>
					<VerticalTabs
						items={[
							{ key: 'persona', label: 'Persona', icon: PersonaIcon, title: 'Persona Generation' },
							{ key: 'environment', label: 'Environment', icon: EnvironmentIcon, title: 'Environment Setting' },
						]}
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
				<CriteriaManagerModal onClose={() => setIsCriteriaManagerOpen(false)} />
			)}
		</div>
	);
};

export default App;
