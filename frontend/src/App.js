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
const STUDY_CONDITION_STORAGE_KEY = 'evalagent.userStudy.condition';
const DAG_INTERACTION_STORAGE_KEY = 'evalagent.userStudy.dagInteractions';
const MAX_DAG_INTERACTION_ENTRIES = 5000;
const MOUSEMOVE_SUMMARY_MAX_DURATION_MS = 2500;
const MOUSEMOVE_SUMMARY_MAX_POINTS = 50;
const MOUSEMOVE_SUMMARY_SAMPLE_INTERVAL = 6;

const STUDY_CONDITIONS = [
	{
		id: 'full_system',
		code: 'A',
		trajectoryUseImageHash: true,
		reasoningEvidenceHighlight: true,
	},
	{
		id: 'full_system_without_image_hash',
		code: 'B',
		trajectoryUseImageHash: false,
		reasoningEvidenceHighlight: true,
	},
	{
		id: 'full_system_without_evidence_highlight',
		code: 'C',
		trajectoryUseImageHash: true,
		reasoningEvidenceHighlight: false,
	},
];

const DEFAULT_STUDY_CONDITION_ID = STUDY_CONDITIONS[0].id;

const getStudyConditionById = (conditionId) => {
	const matched = STUDY_CONDITIONS.find((condition) => condition.id === conditionId);
	return matched || STUDY_CONDITIONS[0];
};

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
	const [selectedCacheDataset, setSelectedCacheDataset] = useState('data1');
	const [isFetchingCache, setIsFetchingCache] = useState(false);
	const [isCleaningServerFiles, setIsCleaningServerFiles] = useState(false);
	const [isRestartingBackend, setIsRestartingBackend] = useState(false);
	const [activeConfigTab, setActiveConfigTab] = useState('persona');
	const [isCriteriaManagerOpen, setIsCriteriaManagerOpen] = useState(false);
	const [studyConditionId, setStudyConditionId] = useState(() => {
		if (typeof window === 'undefined') {
			return DEFAULT_STUDY_CONDITION_ID;
		}

		const storedValue = window.localStorage.getItem(STUDY_CONDITION_STORAGE_KEY);
		return getStudyConditionById(storedValue).id;
	});
	const dagInteractionLogsRef = useRef([]);
	const dagInteractionCounterRef = useRef(0);
	const mouseMoveSummaryRef = useRef(null);
	const eventRateLimitRef = useRef({});

	const activeStudyCondition = useMemo(
		() => getStudyConditionById(studyConditionId),
		[studyConditionId],
	);

	const persistDagInteractionLogs = useCallback(() => {
		if (typeof window === 'undefined') {
			return;
		}

		try {
			window.localStorage.setItem(
				DAG_INTERACTION_STORAGE_KEY,
				JSON.stringify(dagInteractionLogsRef.current),
			);
		} catch (error) {
			console.warn('[user-study] Failed to persist DAG interaction logs', error);
		}
	}, []);

	const appendDagInteractionLog = useCallback((entry) => {
		dagInteractionCounterRef.current += 1;
		dagInteractionLogsRef.current = [...dagInteractionLogsRef.current, entry].slice(-MAX_DAG_INTERACTION_ENTRIES);

		if (dagInteractionCounterRef.current % 10 === 0) {
			persistDagInteractionLogs();
		}
	}, [persistDagInteractionLogs]);

	const flushMouseMoveSummary = useCallback((reason = 'flush') => {
		const segment = mouseMoveSummaryRef.current;
		if (!segment) {
			return;
		}

		mouseMoveSummaryRef.current = null;

		if (segment.pointCount < 2) {
			return;
		}

		const durationMs = Math.max(1, segment.endAtMs - segment.startAtMs);
		const averageSpeedPxPerSec = (segment.distancePx / durationMs) * 1000;
		const samplePath = segment.samplePath.slice();
		const lastSample = samplePath[samplePath.length - 1];
		const endPoint = {
			x: segment.endX,
			y: segment.endY,
			tOffsetMs: segment.endAtMs - segment.startAtMs,
		};

		if (!lastSample || lastSample.x !== endPoint.x || lastSample.y !== endPoint.y) {
			if (samplePath.length < 12) {
				samplePath.push(endPoint);
			} else {
				samplePath[samplePath.length - 1] = endPoint;
			}
		}

		appendDagInteractionLog({
			id: `dag-int-${Date.now()}-${dagInteractionCounterRef.current + 1}`,
			timestamp: new Date().toISOString(),
			type: 'mousemove_summary',
			scope: 'trajectory_dag',
			reason,
			runId: segment.runId,
			studyConditionCode: segment.studyConditionCode,
			startedAt: new Date(segment.startAtMs).toISOString(),
			endedAt: new Date(segment.endAtMs).toISOString(),
			durationMs,
			pointCount: segment.pointCount,
			distancePx: Number(segment.distancePx.toFixed(2)),
			averageSpeedPxPerSec: Number(averageSpeedPxPerSec.toFixed(2)),
			start: { x: segment.startX, y: segment.startY },
			end: { x: segment.endX, y: segment.endY },
			bounds: {
				minX: Number(segment.minX.toFixed(1)),
				maxX: Number(segment.maxX.toFixed(1)),
				minY: Number(segment.minY.toFixed(1)),
				maxY: Number(segment.maxY.toFixed(1)),
			},
			samplePath,
		});
	}, [appendDagInteractionLog]);

	useEffect(() => {
		if (typeof window === 'undefined') {
			return;
		}

		try {
			const storedLogs = window.localStorage.getItem(DAG_INTERACTION_STORAGE_KEY);
			if (!storedLogs) {
				return;
			}

			const parsedLogs = JSON.parse(storedLogs);
			if (Array.isArray(parsedLogs)) {
				dagInteractionLogsRef.current = parsedLogs.slice(-MAX_DAG_INTERACTION_ENTRIES);
				dagInteractionCounterRef.current = dagInteractionLogsRef.current.length;
			}
		} catch (error) {
			console.warn('[user-study] Failed to restore DAG interaction logs', error);
		}
	}, []);

	useEffect(() => {
		if (typeof window === 'undefined') {
			return;
		}

		window.localStorage.setItem(STUDY_CONDITION_STORAGE_KEY, activeStudyCondition.id);
	}, [activeStudyCondition.id]);

	useEffect(() => {
		return () => {
			flushMouseMoveSummary('app_unmount');
			persistDagInteractionLogs();
		};
	}, [flushMouseMoveSummary, persistDagInteractionLogs]);

	useEffect(() => {
		if (typeof window === 'undefined') {
			return () => {};
		}

		const timerId = window.setInterval(() => {
			flushMouseMoveSummary('interval');
		}, 3000);

		return () => {
			window.clearInterval(timerId);
		};
	}, [flushMouseMoveSummary]);

	useEffect(() => {
		flushMouseMoveSummary('context_changed');
	}, [activeRunId, activeStudyCondition.code, flushMouseMoveSummary]);

	const handleStudyConditionChange = useCallback((nextConditionId) => {
		setStudyConditionId(getStudyConditionById(nextConditionId).id);
	}, []);

	const handleDAGInteraction = useCallback((interactionPayload) => {
		if (!interactionPayload || typeof interactionPayload !== 'object') {
			return;
		}

		const nowMs = Date.now();
		const runId = activeRunId || null;
		const studyConditionCode = activeStudyCondition.code;
		const type = interactionPayload.type;

		if (type === 'mousemove') {
			const x = Number(interactionPayload.x);
			const y = Number(interactionPayload.y);

			if (!Number.isFinite(x) || !Number.isFinite(y)) {
				return;
			}

			const current = mouseMoveSummaryRef.current;
			const shouldStartNewSegment = !current
				|| current.runId !== runId
				|| current.studyConditionCode !== studyConditionCode;

			if (shouldStartNewSegment) {
				flushMouseMoveSummary('new_segment');
				mouseMoveSummaryRef.current = {
					runId,
					studyConditionCode,
					startAtMs: nowMs,
					endAtMs: nowMs,
					pointCount: 1,
					distancePx: 0,
					startX: x,
					startY: y,
					endX: x,
					endY: y,
					lastX: x,
					lastY: y,
					minX: x,
					maxX: x,
					minY: y,
					maxY: y,
					samplePath: [{ x, y, tOffsetMs: 0 }],
				};
				return;
			}

			const deltaX = x - current.lastX;
			const deltaY = y - current.lastY;
			current.distancePx += Math.sqrt(deltaX * deltaX + deltaY * deltaY);
			current.endAtMs = nowMs;
			current.endX = x;
			current.endY = y;
			current.lastX = x;
			current.lastY = y;
			current.pointCount += 1;
			current.minX = Math.min(current.minX, x);
			current.maxX = Math.max(current.maxX, x);
			current.minY = Math.min(current.minY, y);
			current.maxY = Math.max(current.maxY, y);

			if (
				current.pointCount % MOUSEMOVE_SUMMARY_SAMPLE_INTERVAL === 0
				&& current.samplePath.length < 12
			) {
				current.samplePath.push({
					x,
					y,
					tOffsetMs: nowMs - current.startAtMs,
				});
			}

			if (
				(nowMs - current.startAtMs >= MOUSEMOVE_SUMMARY_MAX_DURATION_MS)
				|| current.pointCount >= MOUSEMOVE_SUMMARY_MAX_POINTS
			) {
				flushMouseMoveSummary('segment_limit');
			}

			return;
		}

		flushMouseMoveSummary('before_non_mouse_event');

		if (type === 'zoom_pan' || type === 'node_drag') {
			const rule = eventRateLimitRef.current[type] || { lastAtMs: 0, lastPayload: null };
			const minIntervalMs = type === 'zoom_pan' ? 450 : 300;
			if (nowMs - rule.lastAtMs < minIntervalMs) {
				return;
			}

			if (type === 'zoom_pan' && rule.lastPayload) {
				const scaleDelta = Math.abs((interactionPayload.scale || 0) - (rule.lastPayload.scale || 0));
				const xDelta = Math.abs((interactionPayload.translateX || 0) - (rule.lastPayload.translateX || 0));
				const yDelta = Math.abs((interactionPayload.translateY || 0) - (rule.lastPayload.translateY || 0));

				if (scaleDelta < 0.01 && xDelta < 8 && yDelta < 8) {
					return;
				}
			}

			eventRateLimitRef.current[type] = {
				lastAtMs: nowMs,
				lastPayload: interactionPayload,
			};
		}

		const entry = {
			id: `dag-int-${Date.now()}-${dagInteractionCounterRef.current + 1}`,
			timestamp: new Date(nowMs).toISOString(),
			runId,
			studyConditionCode,
			...interactionPayload,
		};

		appendDagInteractionLog(entry);
	}, [activeRunId, activeStudyCondition.code, appendDagInteractionLog, flushMouseMoveSummary]);

	const handleExportDAGInteractionLogs = useCallback(() => {
		if (typeof window === 'undefined' || typeof document === 'undefined') {
			return;
		}

		flushMouseMoveSummary('before_export');
		persistDagInteractionLogs();

		const logs = Array.isArray(dagInteractionLogsRef.current)
			? dagInteractionLogsRef.current
			: [];

		const exportPayload = {
			exportedAt: new Date().toISOString(),
			studyConditionCode: activeStudyCondition.code,
			totalEntries: logs.length,
			logs,
		};

		const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
			type: 'application/json;charset=utf-8',
		});
		const url = window.URL.createObjectURL(blob);
		const a = document.createElement('a');
		const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

		a.href = url;
		a.download = `dag_interaction_logs_${timestamp}.json`;
		document.body.appendChild(a);
		a.click();
		a.remove();
		window.URL.revokeObjectURL(url);
	}, [activeStudyCondition.code, flushMouseMoveSummary, persistDagInteractionLogs]);

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
			const response = await fetchHistoryLogs(selectedCacheDataset);

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
	}, [addExperiment, selectedCacheDataset]);

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
			confirmMessage: 'This will clean extra files in backend/cache_history_logs/data1, and only keep buy_milk* items (including screenshots/buy_milk*). Continue?',
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
					>
						<div className="app-study-condition" aria-label="User study condition">
							<label htmlFor="app-study-condition" className="app-study-condition__label">
								Condition
							</label>
							<select
								id="app-study-condition"
								className="app-study-condition__select"
								value={activeStudyCondition.id}
								onChange={(event) => handleStudyConditionChange(event?.target?.value)}
							>
								{STUDY_CONDITIONS.map((condition) => (
									<option key={condition.id} value={condition.id}>
										{condition.code}
									</option>
								))}
							</select>
							<label htmlFor="app-cache-dataset" className="app-study-condition__label">
								Cache
							</label>
							<select
								id="app-cache-dataset"
								className="app-study-condition__select"
								value={selectedCacheDataset}
								onChange={(event) => setSelectedCacheDataset(event?.target?.value || 'data1')}
								disabled={isFetchingCache}
							>
								<option value="data1">Data 1</option>
								<option value="data2">Data 2</option>
								<option value="data3">Data 3</option>
							</select>
							<button
								type="button"
								className="panel__action app-study-condition__export"
								onClick={handleExportDAGInteractionLogs}
							>
								Export DAG Logs
							</button>
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
						trajectoryUseImageHashEnabled={activeStudyCondition.trajectoryUseImageHash}
						reasoningEvidenceHighlightEnabled={activeStudyCondition.reasoningEvidenceHighlight}
						onDAGInteraction={handleDAGInteraction}
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
