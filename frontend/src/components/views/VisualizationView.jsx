import React, { useState, useMemo, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import VerticalTabs from '../common/VerticalTabs';
import HistoryTabs from '../common/HistoryTabs';
import TrajectoryVisualizer from '../trajectory/TrajectoryVisualizer';
import ReasoningPanel from '../reasoning/ReasoningPanel';
import EvaluationPanel from '../evaluation/evaluationPanel';
import {
	TrajectoryIcon, ReasoningIcon, EvaluationIcon } from '../common/icons';
import { useData } from '../../context/DataContext';
import { evaluateExperiment } from '../../services/api';
import './VisualizationView.css';

const EVALUATION_MODEL_OPTIONS = [
	{ value: 'gpt-4o-mini', label: 'OpenAI GPT-4o mini' },
	{ value: 'gpt-4o', label: 'OpenAI GPT-4o' },
	{ value: 'deepseek-chat', label: 'DeepSeek Chat' },
	{ value: 'claude-3-5-sonnet-20240620', label: 'Claude 3.5 Sonnet' },
	{ value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro' },
];

const TRAJECTORY_COLOR_PALETTE = [
	'#1f77b4',
	'#ff7f0e',
	'#2ca02c',
	'#d62728',
	'#9467bd',
	'#8c564b',
	'#e377c2',
	'#7f7f7f',
	'#bcbd22',
	'#17becf',
];

const RIGHT_PANEL_TABS = [
	{ key: 'trajectory', label: 'Trajectory', icon: TrajectoryIcon, title: 'Trajectory' },
	{ key: 'reasoning', label: 'Reasoning', icon: ReasoningIcon, title: 'Reasoning Process' },
	{ key: 'evaluation', label: 'Evaluation', icon: EvaluationIcon, title: 'Evaluation' },
];

const createDefaultExperimentState = () => ({
	selectedCriteriaIds: [],
	selectedConditionIds: [],
});

const VisualizationView = ({
	activeRun,
	historyEntries,
	activeRunId,
	onSelectRun,
	onCloseRun,
	onManageCriteria,
	trajectoryUseImageHashEnabled,
	trajectoryRefreshNonce,
	reasoningEvidenceHighlightEnabled,
	onDAGInteraction,
	showBackendLogs,
	backendLogs,
	backendRunStatus,
}) => {
	const { state: { mappings, criterias, evaluationResponses }, updateEvaluationResponse } = useData();
	const [activeTab, setActiveTab] = useState('trajectory');
	const [evaluateModel, setEvaluateModel] = useState('gpt-4o-mini');
	const [evaluationLoadingByRunId, setEvaluationLoadingByRunId] = useState({});
	const [reasoningNavigationRequest, setReasoningNavigationRequest] = useState(null);
	const [experimentStates, setExperimentStates] = useState({});
	const [evaluationResponse, setEvaluationResponse] = useState(null);

	const currentExperimentState = useMemo(
		() => experimentStates[activeRunId] || createDefaultExperimentState(),
		[experimentStates, activeRunId],
	);

	const {
		selectedCriteriaIds,
		selectedConditionIds,
	} = currentExperimentState;

	const effectiveTrajectoryUseImageHash = trajectoryUseImageHashEnabled !== false;
	const effectiveReasoningEvidenceHighlight = reasoningEvidenceHighlightEnabled !== false;
	const shouldShowBackendLogs = showBackendLogs === true;

	const isEvaluatingCurrentRun = useMemo(() => {
		if (!activeRunId) {
			return false;
		}
		return Boolean(evaluationLoadingByRunId[activeRunId]);
	}, [activeRunId, evaluationLoadingByRunId]);

	const updateActiveExperimentState = useCallback((nextPartialState) => {
		if (!activeRunId) {
			return;
		}

		setExperimentStates((prev) => {
			const current = prev[activeRunId] || createDefaultExperimentState();
			const nextPartial = typeof nextPartialState === 'function'
				? nextPartialState(current)
				: nextPartialState;

			return {
				...prev,
				[activeRunId]: {
					...current,
					...nextPartial,
				},
			};
		});
	}, [activeRunId]);

	const setSelectedCriteriaIds = useCallback((ids) => {
		updateActiveExperimentState({ selectedCriteriaIds: ids });
	}, [updateActiveExperimentState]);

	const setSelectedConditionIds = useCallback((ids) => {
		updateActiveExperimentState({ selectedConditionIds: ids });
	}, [updateActiveExperimentState]);

	const handleTrajectoryNavigateToReasoning = useCallback((payload) => {
		if (!payload) {
			return;
		}

		const agentIndex = Number.isFinite(payload.agentIndex) ? payload.agentIndex : null;
		const stepIndex = Number.isFinite(payload.stepIndex) ? payload.stepIndex : null;

		if (agentIndex === null || stepIndex === null) {
			return;
		}

		setReasoningNavigationRequest({
			agentIndex,
			stepIndex,
			nonce: Date.now(),
		});
		setActiveTab('reasoning');
	}, []);

	useEffect(() => {
		if (activeRunId && evaluationResponses && evaluationResponses[activeRunId]) {
			setEvaluationResponse(evaluationResponses[activeRunId]);
		} else {
			setEvaluationResponse(null);
		}
	}, [activeRunId, evaluationResponses]);

	const experimentsData = useMemo(() => {
		if (!activeRun) return null;
		
		let conditionsWithEvaluation = activeRun?.conditions || [];
		
		if (evaluationResponse?.conditions) {
			conditionsWithEvaluation = conditionsWithEvaluation.map((condition) => {
				const evalData = evaluationResponse.conditions.find(
					(c) => {
						if (c.conditionID && condition.id && c.conditionID === condition.id) return true;
						if (c.id && condition.id && c.id === condition.id) return true;
						if (c.conditionID && condition.conditionID && c.conditionID === condition.conditionID) return true;
						
						const conditionPersonaStr = typeof condition.persona === 'object'
							? condition.persona?.value
							: condition.persona;
						const evalPersonaStr = typeof c.persona === 'object'
							? c.persona?.value
							: c.persona;
						
						return (
							c.model === condition.model
							&& evalPersonaStr === conditionPersonaStr
							&& c.run_index === condition.run_index
						);
					},
				);
				
				if (evalData && evalData.criteria) {
					return {
						...condition,
						criteria: evalData.criteria,
					};
				}
				return condition;
			});
		}

		conditionsWithEvaluation = conditionsWithEvaluation.map((condition, index) => ({
			...condition,
			trajectoryColor: condition.trajectoryColor || TRAJECTORY_COLOR_PALETTE[index % TRAJECTORY_COLOR_PALETTE.length],
		}));
		
		return {
			conditions: conditionsWithEvaluation,
			raw: activeRun,
		};
	}, [activeRun, evaluationResponse]);

	const criteriaData = useMemo(() => {
		if (!activeRun) return null;
		return activeRun?.criteria || null;
	}, [activeRun]);

	const experimentsMapByAgentId = useMemo(() => {
		if (!activeRunId) return {};
		return mappings[activeRunId] || {};
	}, [activeRunId, mappings]);

	const handleEvaluationResponse = useCallback((response) => {
		if (activeRunId) {
			updateEvaluationResponse(activeRunId, response);
		}
		setEvaluationResponse(response);
	}, [activeRunId, updateEvaluationResponse]);

	const setRunEvaluationLoading = useCallback((runId, isLoading) => {
		if (!runId) {
			return;
		}
		setEvaluationLoadingByRunId((prev) => ({
			...prev,
			[runId]: isLoading,
		}));
	}, []);

	const visibleHistoryEntries = useMemo(() => {
		const counts = {};
		return historyEntries.map((entry) => {
			const entryLabel = typeof entry.label === 'string' && entry.label.trim()
				? entry.label.trim()
				: 'Unknown Task';
			const primaryRun = entry.runs?.[0] || {};
			const taskName = primaryRun.metadata?.task?.name || entryLabel;
			
			if (counts[taskName] === undefined) {
				counts[taskName] = 0;
			}
			counts[taskName]++;
			
			let label = taskName;
			if (counts[taskName] > 1) {
				label = `${taskName} (${counts[taskName] - 1})`;
			}
			
			return {
				...entry,
				label,
			};
		});
	}, [historyEntries]);

	const effectiveActiveRunId = activeRunId || visibleHistoryEntries[0]?.id || null;

	const trajectoryConditionsByRunId = useMemo(() => {
		const next = {};

		visibleHistoryEntries.forEach((entry) => {
			const entryConditions = Array.isArray(entry?.conditions) ? entry.conditions : [];

			next[entry.id] = entryConditions.map((condition, index) => ({
				...condition,
				trajectoryColor: condition.trajectoryColor || TRAJECTORY_COLOR_PALETTE[index % TRAJECTORY_COLOR_PALETTE.length],
			}));
		});

		return next;
	}, [visibleHistoryEntries]);

	return (
		<>
			<section className="visualization-view">
				<div className="visualization-view__tabs-container">
					<HistoryTabs
						items={visibleHistoryEntries}
						activeId={activeRunId}
						onSelect={onSelectRun}
						onClose={onCloseRun}
						closable={true}
					/>
				</div>

				<div className="visualization-view__content">
					<section className={`visualization-view__panel${activeTab !== 'trajectory' ? ' visualization-view__panel--hidden' : ''}`}>
						{visibleHistoryEntries.length > 0 ? (
							visibleHistoryEntries.map((entry) => {
								const isActiveEntry = entry.id === effectiveActiveRunId;
								const showLogsForEntry = shouldShowBackendLogs && isActiveEntry;
								const entryTrajectory = entry?.trajectory || null;
								const entryConditions = trajectoryConditionsByRunId[entry.id] || [];

								return (
									<div
										key={entry.id}
										className={`visualization-view__run-panel${!isActiveEntry ? ' visualization-view__run-panel--hidden' : ''}`}
									>
										{(entryTrajectory || showLogsForEntry) ? (
											<TrajectoryVisualizer
												trajectory={entryTrajectory}
												conditions={entryConditions}
												useImageHashEnabled={effectiveTrajectoryUseImageHash}
												refreshNonce={trajectoryRefreshNonce}
												onNavigateToReasoning={handleTrajectoryNavigateToReasoning}
												onDAGInteraction={onDAGInteraction}
												showBackendLogs={showLogsForEntry}
												backendLogs={showLogsForEntry ? backendLogs : []}
												backendRunStatus={showLogsForEntry ? backendRunStatus : null}
											/>
										) : (
											<div style={{ padding: '20px', color: '#999' }}>
												No trajectory data available
											</div>
										)}
									</div>
								);
							})
						) : (
							<div style={{ padding: '20px', color: '#999' }}>
								No trajectory data available
							</div>
						)}
					</section>
					<section className={`visualization-view__panel${activeTab !== 'reasoning' ? ' visualization-view__panel--hidden' : ''}`}>
						{(criteriaData || shouldShowBackendLogs) ? (
							<ReasoningPanel 
								data={criteriaData}
								conditions={experimentsData?.conditions || []}
								selectedExperimentId={activeRunId}
								experimentsMap={experimentsMapByAgentId}
								evaluationResponse={evaluationResponse}
								evidenceHighlightEnabled={effectiveReasoningEvidenceHighlight}
								navigationRequest={reasoningNavigationRequest}
								showBackendLogs={shouldShowBackendLogs}
								backendLogs={backendLogs}
								backendRunStatus={backendRunStatus}
							/>
						) : (
							<div style={{ padding: '20px', color: '#999' }}>
								No reasoning data available
							</div>
						)}
					</section>
					<section className={`visualization-view__panel${activeTab !== 'evaluation' ? ' visualization-view__panel--hidden' : ''}`}>
						<EvaluationPanel
							criterias={criterias}
							conditions={experimentsData?.conditions || []}
							selectedCriteriaIds={selectedCriteriaIds}
							selectedConditionIds={selectedConditionIds}
							evaluateModel={evaluateModel}
							modelOptions={EVALUATION_MODEL_OPTIONS}
							onEvaluateModelChange={setEvaluateModel}
							onCriteriaSelectionChange={setSelectedCriteriaIds}
							onConditionSelectionChange={setSelectedConditionIds}
							onManageCriteria={onManageCriteria}
							evaluationResponse={evaluationResponse}
							isEvaluating={isEvaluatingCurrentRun}
							onEvaluate={async (config) => {
								const {
									criteria: selectedCriteriaFromPanel,
									conditions: selectedConditionsFromPanel,
									evaluateModel: selectedEvaluateModel,
								} = config;
								const runIdForRequest = activeRunId;
								setRunEvaluationLoading(runIdForRequest, true);
								try {
									const selectedConditions = Array.isArray(selectedConditionsFromPanel)
										? selectedConditionsFromPanel
										: [];

									const selectedCriteria = Array.isArray(selectedCriteriaFromPanel)
										? selectedCriteriaFromPanel
										: [];

									if (selectedConditions.length === 0 || selectedCriteria.length === 0) {
										alert(`Invalid evaluation selection. conditions=${selectedConditions.length}, criteria=${selectedCriteria.length}`);
										return;
									}

									const response = await evaluateExperiment(
										selectedConditions,
										selectedCriteria,
										selectedEvaluateModel || evaluateModel,
									);
									
									if (response.ok) {
										handleEvaluationResponse(response.data);
										alert(`Evaluation completed for ${selectedConditions.length} conditions with ${selectedCriteria.length} criteria.`);
									} else {
										alert(`Evaluation failed: ${response.status}`);
									}
								} catch (error) {
									alert(`Evaluation error: ${error.message}`);
								} finally {
									setRunEvaluationLoading(runIdForRequest, false);
								}
							}}
						/>
					</section>
				</div>
			</section>
			<VerticalTabs
				items={RIGHT_PANEL_TABS}
				activeKey={activeTab}
				onChange={setActiveTab}
				containerClassName="config-vertical-tabs"
			/>
		</>
	);
};

VisualizationView.propTypes = {
	activeRun: PropTypes.object,
	historyEntries: PropTypes.array.isRequired,
	activeRunId: PropTypes.string,
	onSelectRun: PropTypes.func.isRequired,
	onCloseRun: PropTypes.func.isRequired,
	onManageCriteria: PropTypes.func,
	trajectoryUseImageHashEnabled: PropTypes.bool,
	trajectoryRefreshNonce: PropTypes.number,
	reasoningEvidenceHighlightEnabled: PropTypes.bool,
	onDAGInteraction: PropTypes.func,
	showBackendLogs: PropTypes.bool,
	backendLogs: PropTypes.arrayOf(PropTypes.string),
	backendRunStatus: PropTypes.string,
};

VisualizationView.defaultProps = {
	activeRun: null,
	activeRunId: null,
	onManageCriteria: undefined,
	trajectoryUseImageHashEnabled: undefined,
	trajectoryRefreshNonce: 0,
	reasoningEvidenceHighlightEnabled: undefined,
	onDAGInteraction: undefined,
	showBackendLogs: false,
	backendLogs: [],
	backendRunStatus: null,
};

export default VisualizationView;
