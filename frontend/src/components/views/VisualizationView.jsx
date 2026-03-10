import React, { useState, useMemo, useCallback } from 'react';
import PropTypes from 'prop-types';
import VerticalTabs from '../common/VerticalTabs';
import HistoryTabs from '../common/HistoryTabs';
import TrajectoryVisualizer from '../trajectory/TrajectoryVisualizer';
import ReasoningPanel from '../reasoning/ReasoningPanel';
import EvaluationPanel from '../evaluation/evaluationPanel';
import { TrajectoryIcon, ReasoningIcon, EvaluationIcon } from '../common/icons';
import { useExperimentEvaluation } from '../../hooks/useExperimentEvaluation';
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
	const [activeTab, setActiveTab] = useState('trajectory');
	const [reasoningNavigationRequest, setReasoningNavigationRequest] = useState(null);

    const evaluationState = useExperimentEvaluation(activeRunId);

	const effectiveTrajectoryUseImageHash = trajectoryUseImageHashEnabled !== false;
	const effectiveReasoningEvidenceHighlight = reasoningEvidenceHighlightEnabled !== false;
	const shouldShowBackendLogs = showBackendLogs === true;

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

	const experimentsData = useMemo(() => {
		if (!activeRun) return null;
		
		let conditionsWithEvaluation = activeRun?.conditions || [];
		
		if (evaluationState.evaluationResponse?.conditions) {
			conditionsWithEvaluation = conditionsWithEvaluation.map((condition) => {
				const evalData = evaluationState.evaluationResponse.conditions.find(
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
	}, [activeRun, evaluationState.evaluationResponse]);

	const criteriaData = useMemo(() => {
		if (!activeRun) return null;
		return activeRun?.criteria || null;
	}, [activeRun]);

	const experimentsMapByAgentId = useMemo(() => {
		if (!activeRunId) return {};
		return evaluationState.mappings[activeRunId] || {};
	}, [activeRunId, evaluationState.mappings]);


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
	const activeTrajectoryEntry = useMemo(
		() => visibleHistoryEntries.find((entry) => entry.id === effectiveActiveRunId) || null,
		[visibleHistoryEntries, effectiveActiveRunId],
	);

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

	const activeTrajectoryConditions = useMemo(() => {
		if (!activeTrajectoryEntry) {
			return [];
		}

		return trajectoryConditionsByRunId[activeTrajectoryEntry.id] || [];
	}, [activeTrajectoryEntry, trajectoryConditionsByRunId]);
	const hasActiveTrajectoryContent = Boolean(activeTrajectoryEntry?.trajectory || shouldShowBackendLogs);

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
						{activeTrajectoryEntry ? (
							hasActiveTrajectoryContent ? (
								<div key={activeTrajectoryEntry.id} className="visualization-view__run-panel">
									<TrajectoryVisualizer
										runId={activeTrajectoryEntry.id}
										trajectory={activeTrajectoryEntry?.trajectory || null}
										conditions={activeTrajectoryConditions}
										useImageHashEnabled={effectiveTrajectoryUseImageHash}
										refreshNonce={trajectoryRefreshNonce}
										onNavigateToReasoning={handleTrajectoryNavigateToReasoning}
										onDAGInteraction={onDAGInteraction}
										showBackendLogs={shouldShowBackendLogs}
										backendLogs={shouldShowBackendLogs ? backendLogs : []}
										backendRunStatus={shouldShowBackendLogs ? backendRunStatus : null}
									/>
								</div>
							) : (
								<div style={{ padding: '20px', color: '#999' }}>
									No trajectory data available
								</div>
							)
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
								evaluationResponse={evaluationState.evaluationResponse}
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
							criterias={evaluationState.criterias}
							conditions={experimentsData?.conditions || []}
							selectedCriteriaIds={evaluationState.selectedCriteriaIds}
							selectedConditionIds={evaluationState.selectedConditionIds}
							evaluateModel={evaluationState.evaluateModel}
							modelOptions={EVALUATION_MODEL_OPTIONS}
							onEvaluateModelChange={evaluationState.setEvaluateModel}
							onCriteriaSelectionChange={evaluationState.setSelectedCriteriaIds}
							onConditionSelectionChange={evaluationState.setSelectedConditionIds}
							onManageCriteria={onManageCriteria}
							evaluationResponse={evaluationState.evaluationResponse}
							isEvaluating={evaluationState.isEvaluatingCurrentRun}
							onEvaluate={evaluationState.handleEvaluate}
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