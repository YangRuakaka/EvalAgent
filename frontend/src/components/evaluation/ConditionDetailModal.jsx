import React, { useCallback } from 'react';
import PropTypes from 'prop-types';
import ReactMarkdown from 'react-markdown';
import { useData } from '../../context/DataContext';
import { CrossIcon } from '../common/icons';
import './ConditionDetailModal.css';

const ConditionDetailModal = ({
	condition,
	onClose = () => {},
}) => {
	const { state: { criterias } } = useData();

	const handleBackdropClick = useCallback((e) => {
		if (e.target === e.currentTarget) {
			onClose();
		}
	}, [onClose]);

	const handleCloseClick = useCallback(() => {
		onClose();
	}, [onClose]);

	const getAssessmentStyle = (assessment) => {
		const normalizedAssessment = assessment?.toLowerCase() || 'unknown';
		switch (normalizedAssessment) {
			case 'pass':
				return '#10b981'; // green
			case 'fail':
				return '#ef4444'; // red
			case 'partial':
				return '#f59e0b'; // orange
			default:
				return '#6b7280'; // gray
		}
	};

	const getCriteriaColor = (criterion) => {
		// Try to find the criteria in the context to get the correct color
		const criteriaList = Object.values(criterias || {});
		const title = criterion.title || criterion.name;
		const id = criterion.id || criterion.criteria_id;

		let matchedCriteria = null;
		if (id && criterias[id]) {
			matchedCriteria = criterias[id];
		} else if (title) {
			matchedCriteria = criteriaList.find(c => c.title === title);
		}

		if (matchedCriteria && matchedCriteria.color) {
			return matchedCriteria.color;
		}

		if (criterion.color) {
			return criterion.color;
		}
		return getAssessmentStyle(criterion.overall_assessment);
	};

	const displayInfo = {
		runIndex: condition.run_index !== undefined ? condition.run_index : (condition.metadata?.run_index !== undefined ? condition.metadata.run_index : 'N/A'),
		model: condition.model || condition.metadata?.model || 'Unknown Model',
		persona: condition.value || condition.metadata?.value || condition.persona?.value || condition.persona || condition.metadata?.persona || 'Unknown Persona',
		finalResult: condition.raw?.final_result || condition.raw?.output || 'No Result',
		conditionId: condition.id || condition.conditionID || 'Unknown',
	};

	let criteriaArray = [];
	if (condition.criteria && Array.isArray(condition.criteria)) {
		criteriaArray = condition.criteria;
	}
	
	const actualPersona = condition.metadata?.persona || condition.persona;

	return (
		<div className="condition-detail-modal__backdrop" onClick={handleBackdropClick}>
			<div className="condition-detail-modal">
				{/* Header */}
				<div className="condition-detail-modal__header">
					<h2 className="condition-detail-modal__title">
						Condition Details
					</h2>
					<button
						className="condition-detail-modal__close-btn"
						onClick={handleCloseClick}
						aria-label="Close modal"
					>
						<CrossIcon />
					</button>
				</div>

			{/* Body */}
			<div className="condition-detail-modal__body">
			{/* Criteria Evaluations Section */}
			{criteriaArray && criteriaArray.length > 0 && (
				<div className="condition-detail-modal__section">
					<h3 className="condition-detail-modal__section-title">Criteria Evaluations</h3>
					<div className="condition-detail-modal__criteria-list">
						{criteriaArray.map((criterion, idx) => {
							if (!criterion) {
								console.warn('[ConditionDetailModal] Null criterion at index:', idx);
								return null;
							}
							
							return (
								<div key={idx} className="condition-detail-modal__criteria-item">
									<div className="condition-detail-modal__criteria-header">
										<div className="condition-detail-modal__criteria-color-indicator" style={{
											backgroundColor: getCriteriaColor(criterion),
										}} />
										<h4 className="condition-detail-modal__criteria-title">
											{criterion.title || criterion.name || 'Unknown Criterion'}
										</h4>
										{criterion.overall_assessment && (
											<span
												className="condition-detail-modal__assessment-badge"
												style={{
													backgroundColor: getAssessmentStyle(criterion.overall_assessment),
												}}
											>
												{criterion.overall_assessment.toUpperCase()}
											</span>
										)}
									</div>
									
									{criterion.overall_reasoning && criterion.overall_reasoning.trim().length > 0 && (
										<div className="condition-detail-modal__criteria-reasoning">
											<p className="condition-detail-modal__text">
												{criterion.overall_reasoning}
											</p>
										</div>
									)}
									
									{criterion.confidence !== undefined && criterion.confidence !== null && (
										<div className="condition-detail-modal__criteria-meta">
											<span className="condition-detail-modal__meta-label">Confidence:</span>
											<span className="condition-detail-modal__meta-value">
												{typeof criterion.confidence === 'number' 
													? (criterion.confidence * 100).toFixed(0)
													: criterion.confidence
												}%
											</span>
										</div>
									)}
								</div>
							);
						})}
					</div>
				</div>
			)}

				{/* Run Index, Model - All in one row */}
				<div className="condition-detail-modal__info-row">
					<div className="condition-detail-modal__info-item">
						<h3 className="condition-detail-modal__section-title">Run Index</h3>
						<p className="condition-detail-modal__text">{displayInfo.runIndex}</p>
					</div>
					<div className="condition-detail-modal__info-item">
						<h3 className="condition-detail-modal__section-title">Model</h3>
						<p className="condition-detail-modal__text">{displayInfo.model}</p>
					</div>
				</div>

				{/* Persona Section - Detailed */}
				<div className="condition-detail-modal__section">
					<h3 className="condition-detail-modal__section-title">Persona Details</h3>
					<div className="condition-detail-modal__persona-details">
						{actualPersona && typeof actualPersona === 'object' ? (
							<div className="condition-detail-modal__key-value-list">
								{Object.entries(actualPersona).map(([key, value]) => (
									<div key={key} className="condition-detail-modal__kv-item">
										{key !== 'content' && <span className="condition-detail-modal__kv-key">{key}:</span>}
										<span className="condition-detail-modal__kv-value">
											{typeof value === 'object' ? JSON.stringify(value) : String(value)}
										</span>
									</div>
								))}
							</div>
						) : (
							<p className="condition-detail-modal__text">
								{typeof actualPersona === 'string' ? actualPersona : displayInfo.persona}
							</p>
						)}
					</div>
				</div>

				{/* Final Result Section */}
				<div className="condition-detail-modal__section">
					<h3 className="condition-detail-modal__section-title">Result</h3>
					<div className="condition-detail-modal__result-box">
						<div className="condition-detail-modal__text condition-detail-modal__result-text">
							<ReactMarkdown>
								{displayInfo.finalResult}
							</ReactMarkdown>
						</div>
					</div>
				</div>
				</div>

				{/* Footer */}
				<div className="condition-detail-modal__footer">
					<button
						className="condition-detail-modal__btn condition-detail-modal__btn--primary"
						onClick={handleCloseClick}
					>
						Close
					</button>
				</div>
			</div>
		</div>
	);
};

ConditionDetailModal.propTypes = {
	condition: PropTypes.shape({
		id: PropTypes.string,
		conditionID: PropTypes.string,
		model: PropTypes.string,
		persona: PropTypes.oneOfType([
			PropTypes.string,
			PropTypes.shape({
				value: PropTypes.string,
			}),
		]),
		metadata: PropTypes.object,
		raw: PropTypes.object,
		criteria: PropTypes.arrayOf(
			PropTypes.shape({
				title: PropTypes.string,
				name: PropTypes.string,
				overall_assessment: PropTypes.string,
				overall_reasoning: PropTypes.string,
				confidence: PropTypes.number,
				color: PropTypes.string,
			})
		),
	}).isRequired,
	onClose: PropTypes.func,
};

ConditionDetailModal.defaultProps = {
	onClose: () => {},
};

export default ConditionDetailModal;
