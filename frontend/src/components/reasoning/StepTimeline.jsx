import React from 'react';
import PropTypes from 'prop-types';
import { verdictToColor } from './utils/criteriaInteraction';
import { getCriteriaColorStyles } from '../../utils/colorUtils';
import { CheckIcon, CrossIcon, ExclamationIcon, QuestionIcon } from '../common/icons';
import './StepTimeline.css';

/**
 * Convert Base64 screenshot to data URI for img src
 * @param {string} base64Data - Base64 encoded image data
 * @returns {string|null} Data URI or null
 */
const getScreenshotDataUri = (base64Data) => {
	if (!base64Data) return null;
	
	// If it's already a data URI, return as is
	if (base64Data.startsWith('data:')) {
		return base64Data;
	}
	
	// Otherwise, assume it's PNG base64 and convert to data URI
	return `data:image/png;base64,${base64Data}`;
};

const StepTimeline = ({ 
	steps, 
	selectedStepIndex, 
	onSelectStep,
	enrichedSteps = [],        // 融合了evaluation信息的steps
	report,                     // JudgeEvaluationReport
	onStepClick,                // step被点击时的callback
	onClusterClick,             // cluster被点击时的callback
	conditionId = null,         // 当前condition的ID，用于过滤evaluation结果
}) => {

	if (!steps || steps.length === 0) {
		return (
			<div className="step-timeline">
				<p className="step-timeline-empty">No steps available</p>
			</div>
		);
	}

	/**
	 * 构建cluster visuals - 在timeline中展示cluster边界和标签
	 */
	const renderClusterLabels = () => {
		if (!report?.task_decomposition || report.task_decomposition.length === 0) return null;
		
		return (
			<div className="step-timeline-clusters">
				{report.task_decomposition.map(cluster => {
					const startIdx = Math.min(...cluster.step_indices);
					const endIdx = Math.max(...cluster.step_indices);
					
					// 计算在timeline中的位置（百分比）
					const startPercent = (startIdx / (steps.length - 1)) * 100;
					const endPercent = (endIdx / (steps.length - 1)) * 100;
					const width = endPercent - startPercent;
					
					const handleClusterClick = () => {
						if (onClusterClick) {
							onClusterClick(cluster.cluster_id);
						}
					};
					
					return (
						<div
							key={cluster.cluster_id}
							className="cluster-indicator"
							style={{
								left: `${startPercent}%`,
								width: `${width}%`,
							}}
							title={`${cluster.semantic_label || 'Cluster'}\nClick to view evaluation details`}
							onClick={handleClusterClick}
							role="button"
							tabIndex={0}
							onKeyDown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									handleClusterClick();
								}
							}}
						>
							<span className="cluster-label">{cluster.semantic_label || 'Cluster'}</span>
						</div>
					);
				})}
			</div>
		);
	};

	/**
	 * 渲染单个step的evaluation指示器
	 */
	const renderEvaluationIndicators = (step, stepIndex) => {
		const enrichedStep = enrichedSteps[stepIndex];
		
		if (!enrichedStep?.relatedEvaluations) {
			return null;
		}
		
		const evals = enrichedStep.relatedEvaluations;
		if (evals.length === 0) {
			return null;
		}
		
		return (
			<div className="step-evaluation-indicators">
				{evals.map((evaluation, idx) => {
					const status = (evaluation.evaluateStatus || evaluation.verdict || 'unable_to_evaluate').toLowerCase();
					
					let verdictKey = 'UNABLE_TO_EVALUATE';
					let IconComponent = QuestionIcon;
					
					if (status === 'pass') {
						verdictKey = 'PASS';
						IconComponent = CheckIcon;
					} else if (status === 'fail') {
						verdictKey = 'FAIL';
						IconComponent = CrossIcon;
					} else if (status === 'partial') {
						verdictKey = 'PARTIAL';
						IconComponent = ExclamationIcon;
					}
					
					const criteriaId = evaluation.criterion_id || evaluation.criterion_name;
					let criteriaColor = evaluation.criterion_color;
					
					if (!criteriaColor) {
						const criteriaBaseColor = getCriteriaColorStyles(criteriaId);
						criteriaColor = criteriaBaseColor.backgroundColor;
					}
					
					const verdictConfig = verdictToColor[verdictKey] || verdictToColor['UNABLE_TO_EVALUATE'];
					
					const confidencePercent = evaluation.confidence_score ? (evaluation.confidence_score * 100).toFixed(0) : 'N/A';

					return (
						<div
							key={idx}
							className="evaluation-indicator-icon"
							style={{
								backgroundColor: verdictConfig.border,
								borderColor: criteriaColor,
								color: '#ffffff',
								borderWidth: '2px',
								borderStyle: 'solid',
							}}
							title={`${evaluation.criterion_name}\nStatus: ${status.toUpperCase()}\nConfidence: ${confidencePercent}%`}
						>
							<IconComponent width={10} height={10} strokeWidth={3} />
						</div>
					);
				})}
			</div>
		);
	};

	return (
		<div className="step-timeline">
			{/* Cluster层 */}
			{renderClusterLabels()}

			<div className="step-timeline-container">
				{/* Horizontal connector line */}
				<div className="step-timeline-line" />

				{/* Step nodes */}
				<div className="step-timeline-nodes">
					{steps.map((step, index) => {
						const isSelected = index === selectedStepIndex;
						const hasEvaluations = enrichedSteps[index]?.relatedEvaluations?.length > 0;
						
						return (
							<div
								key={step.id}
								className={`step-timeline-node-wrapper ${hasEvaluations ? 'has-evaluations' : ''}`}
							>
								<button
									className={`step-timeline-node ${
										isSelected ? 'step-timeline-node--active' : ''
									}`}
									onClick={() => {
										onSelectStep(index);
										onStepClick?.(step, index);
									}}
									title={`Step ${step.stepIndex}`}
									type="button"
								>
									{step.screenshot ? (
										<img
											src={getScreenshotDataUri(step.screenshot)}
											alt={`Step ${step.stepIndex} thumbnail`}
											className="step-timeline-screenshot"
										/>
									) : (
										<div className="step-timeline-placeholder">
											Step {step.stepIndex}
										</div>
									)}
								</button>
								
								{/* Evaluation指示器 */}
								{renderEvaluationIndicators(step, index)}
							</div>
						);
					})}
				</div>
			</div>

			{/* Step counter */}
			<div className="step-timeline-info">
				<span className="step-timeline-counter">
					Step {selectedStepIndex + 1} of {steps.length}
				</span>
			</div>
		</div>
	);
};

StepTimeline.propTypes = {
	steps: PropTypes.arrayOf(
		PropTypes.shape({
			id: PropTypes.string.isRequired,
			stepIndex: PropTypes.number.isRequired,
			screenshot: PropTypes.string,
		})
	).isRequired,
	selectedStepIndex: PropTypes.number.isRequired,
	onSelectStep: PropTypes.func.isRequired,
	enrichedSteps: PropTypes.array,
	report: PropTypes.shape({
		task_decomposition: PropTypes.arrayOf(PropTypes.shape({
			cluster_id: PropTypes.string,
			semantic_label: PropTypes.string,
			step_indices: PropTypes.arrayOf(PropTypes.number),
		})),
	}),
	onStepClick: PropTypes.func,
	onClusterClick: PropTypes.func,
	conditionId: PropTypes.string,
};

StepTimeline.defaultProps = {
	enrichedSteps: [],
	report: null,
	onStepClick: null,
	onClusterClick: null,
	conditionId: null,
};

export default StepTimeline;
