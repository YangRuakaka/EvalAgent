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

const VisualizationView = ({ activeRun, historyEntries, activeRunId, onSelectRun, onCloseRun }) => {
	const { state: { mappings, criterias, evaluationResponses }, updateEvaluationResponse } = useData();
	const [activeTab, setActiveTab] = useState('trajectory');
	
	// Store state for each experiment (runId = experimentId): { [experimentId]: { selectedCriteriaIds, selectedConditionIds } }
	const [experimentStates, setExperimentStates] = useState({});

	// Get current experiment state or default values
	const currentExperimentState = useMemo(() => experimentStates[activeRunId] || {
		selectedCriteriaIds: [],
		selectedConditionIds: []
	}, [experimentStates, activeRunId]);

	const { selectedCriteriaIds, selectedConditionIds } = currentExperimentState;

	// State updaters for current experiment
	const setSelectedCriteriaIds = useCallback((ids) => {
		if (!activeRunId) {
			return;
		}
		setExperimentStates(prev => ({
			...prev,
			[activeRunId]: {
				...(prev[activeRunId] || { selectedConditionIds: [], selectedCriteriaIds: [] }),
				selectedCriteriaIds: ids
			}
		}));
	}, [activeRunId]);

	const setSelectedConditionIds = useCallback((ids) => {
		if (!activeRunId) return;
		setExperimentStates(prev => ({
			...prev,
			[activeRunId]: {
				...(prev[activeRunId] || { selectedCriteriaIds: [], selectedConditionIds: [] }),
				selectedConditionIds: ids
			}
		}));
	}, [activeRunId]);

	const [evaluationResponse, setEvaluationResponse] = useState(null);

	// When activeRunId changes, load evaluation response from DataContext if available
	useEffect(() => {
		if (activeRunId && evaluationResponses && evaluationResponses[activeRunId]) {
			setEvaluationResponse(evaluationResponses[activeRunId]);
		} else {
			setEvaluationResponse(null);
		}
	}, [activeRunId, evaluationResponses]);

	const rightPanelTabs = [
		{ key: 'trajectory', label: 'Trajectory', icon: TrajectoryIcon, title: 'Trajectory' },
		{ key: 'reasoning', label: 'Reasoning', icon: ReasoningIcon, title: 'Reasoning Process' },
		{ key: 'evaluation', label: 'Evaluation', icon: EvaluationIcon, title: 'Evaluation' },
	];

	const trajectoryData = useMemo(() => {
		if (!activeRun) return null;
		return activeRun?.trajectory || null;
	}, [activeRun]);

	const experimentsData = useMemo(() => {
		if (!activeRun) return null;
		
		let conditionsWithEvaluation = activeRun?.conditions || [];
		
		if (evaluationResponse?.conditions) {
			conditionsWithEvaluation = conditionsWithEvaluation.map(condition => {
				const evalData = evaluationResponse.conditions.find(
					c => {
						if (c.conditionID && condition.id && c.conditionID === condition.id) return true;
						if (c.id && condition.id && c.id === condition.id) return true;
						if (c.conditionID && condition.conditionID && c.conditionID === condition.conditionID) return true;
						
						const conditionPersonaStr = typeof condition.persona === 'object' 
							? condition.persona?.value 
							: condition.persona;
						const evalPersonaStr = typeof c.persona === 'object' 
							? c.persona?.value 
							: c.persona;
						
						return (c.model === condition.model && 
							evalPersonaStr === conditionPersonaStr && 
							c.run_index === condition.run_index);
					}
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

	const visibleHistoryEntries = useMemo(() => {
		const counts = {};
		return historyEntries.map(entry => {
			const primaryRun = entry.runs?.[0] || {};
			const taskName = primaryRun.metadata?.task?.name || 'Unknown Task';
			
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
				label
			};
		});
	}, [historyEntries]);

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
					{activeTab === 'trajectory' && (
						<section className="visualization-view__panel">
							{trajectoryData ? (
								<TrajectoryVisualizer 
									trajectory={trajectoryData}
									conditions={experimentsData?.conditions || []}
								/>
							) : (
								<div style={{ padding: '20px', color: '#999' }}>
									No trajectory data available
								</div>
							)}
						</section>
					)}
					{activeTab === 'reasoning' && (
						<section className="visualization-view__panel">
							{criteriaData ? (
								<ReasoningPanel 
									data={criteriaData}
									selectedExperimentId={activeRunId}
									experimentsMap={experimentsMapByAgentId}
									evaluationResponse={evaluationResponse}
								/>
							) : (
								<div style={{ padding: '20px', color: '#999' }}>
									No reasoning data available
								</div>
							)}
						</section>
					)}
					{activeTab === 'evaluation' && (
						<section className="visualization-view__panel">
							<EvaluationPanel
								criterias={criterias}
								conditions={experimentsData?.conditions || []}
								selectedCriteriaIds={selectedCriteriaIds}
								selectedConditionIds={selectedConditionIds}
								onCriteriaSelectionChange={setSelectedCriteriaIds}
								onConditionSelectionChange={setSelectedConditionIds}
								evaluationResponse={evaluationResponse}
								onEvaluate={async (config) => {
							const { criteriaIds, conditionIds } = config;								try {
									// Get selected conditions data
									const selectedConditions = experimentsData?.conditions
										?.filter(cond => conditionIds.includes(cond.id))
										|| [];
									
									// Get selected criteria data
									const selectedCriteria = Object.values(criterias || {})
										.filter(crit => criteriaIds.includes(crit.id))
										|| [];
									
									let experimentIdToUse = activeRun?.originalId;
									
									if (!experimentIdToUse && activeRunId) {
										// Fallback: try to extract from ID if it matches the pattern generated by visualizationDataProcessor
										// Pattern: originalId-timestamp-suffix
										// timestamp is usually 13 digits (Date.now())
										// suffix is usually 9 chars (Math.random().toString(36).substr(2, 9))
										const match = activeRunId.match(/^(.*)-(\d{13})-([a-z0-9]{9})$/);
									if (match) {
										experimentIdToUse = match[1];
									} else {
											experimentIdToUse = activeRunId;
										}
								}

								// Call API to evaluate experiment
									const response = await evaluateExperiment(
										selectedConditions,
										selectedCriteria
									);
									
								if (response.ok) {
									// response.data 已经是评估结果对象，包含 { run_id, conditions: [...] }
									handleEvaluationResponse(response.data);
									alert(`Evaluation completed for ${selectedConditions.length} conditions with ${selectedCriteria.length} criteria.`);
								} else {
									alert(`Evaluation failed: ${response.status}`);
								}
							} catch (error) {
								alert(`Evaluation error: ${error.message}`);
							}
							}}
							/>
						</section>
					)}
				</div>
			</section>
			<VerticalTabs
				items={rightPanelTabs}
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
};

VisualizationView.defaultProps = {
	activeRun: null,
	activeRunId: null,
};

export default VisualizationView;
