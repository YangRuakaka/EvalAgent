import React, { useCallback } from 'react';
import PropTypes from 'prop-types';
import { CrossIcon } from '../common/icons';
import './CriteriaDetailModal.css';

/**
 * CriteriaDetailModal 组件
 * 
 * 显示 Criteria 的详细信息
 * 包括 title, description, assertion 等
 */
const CriteriaDetailModal = ({
	criteria,
	comparison = null,
	conditions = [],
	onClose = () => {},
	isSelected = false,
	onToggleSelect,
}) => {
	const handleBackdropClick = useCallback((e) => {
		if (e.target === e.currentTarget) {
			onClose();
		}
	}, [onClose]);

	const handleCloseClick = useCallback(() => {
		onClose();
	}, [onClose]);

	return (
		<div className="criteria-detail-modal__backdrop" onClick={handleBackdropClick}>
			<div className="criteria-detail-modal">
				{/* Header */}
				<div className="criteria-detail-modal__header">
					<h2 className="criteria-detail-modal__title">{criteria.title || 'Criteria Details'}</h2>
					<button
						className="criteria-detail-modal__close-btn"
						onClick={handleCloseClick}
						aria-label="Close modal"
					>
						<CrossIcon />
					</button>
				</div>

				{/* Body */}
				<div className="criteria-detail-modal__body">
					{/* Description Section */}
					{criteria.description && (
						<div className="criteria-detail-modal__section">
							<h3 className="criteria-detail-modal__section-title">Description</h3>
							<p className="criteria-detail-modal__text">{criteria.description}</p>
						</div>
					)}

					{/* Assertion Section */}
					{criteria.assertion && (
						<div className="criteria-detail-modal__section">
							<h3 className="criteria-detail-modal__section-title">Assertion</h3>
							<p 
								className="criteria-detail-modal__text criteria-detail-modal__assertion"
								style={{ borderLeftColor: criteria.color }}
							>
								{criteria.assertion}
							</p>
						</div>
					)}

					{/* Comparison Section */}
					{comparison && comparison.condition_comparison && (
						<div className="criteria-detail-modal__section">
							<h3 className="criteria-detail-modal__section-title">Multi-Condition Assessment</h3>

							{comparison.condition_comparison.ranking && (
								<div className="criteria-detail-modal__ranking-list">
									{comparison.condition_comparison.ranking.map((rankItem, index) => (
										<div key={index} className="criteria-detail-modal__ranking-item">
											<div className="criteria-detail-modal__rank-badge">#{rankItem.rank}</div>
											<div className="criteria-detail-modal__rank-content">
												<div className="criteria-detail-modal__rank-header">
													<span className="criteria-detail-modal__rank-id">
														{rankItem.model} - {rankItem.value || rankItem.persona} (Run {rankItem.run_index})
													</span>
													<span className={`criteria-detail-modal__rank-status criteria-detail-modal__rank-status--${rankItem.overall_assessment}`}>
														{rankItem.overall_assessment}
													</span>
												</div>
												<div className="criteria-detail-modal__rank-details">
													<span>Confidence: {rankItem.confidence}</span>
												</div>
											</div>
										</div>
									))}
								</div>
							)}
                            
                            {comparison.condition_comparison.ranking_reasoning && (
                                <div className="criteria-detail-modal__ranking-reasoning">
                                    <strong>Reasoning: </strong>
                                    {comparison.condition_comparison.ranking_reasoning}
                                </div>
                            )}
						</div>
					)}

					{/* Additional Info - ID removed */}
				</div>

				{/* Footer */}
				<div className="criteria-detail-modal__footer">
					{onToggleSelect && (
						<button
							className={`criteria-detail-modal__btn ${isSelected ? 'criteria-detail-modal__btn--danger' : 'criteria-detail-modal__btn--success'}`}
							onClick={() => {
								onToggleSelect();
								// Keep modal open to allow user to see status change, or close it?
								// Usually selecting implies "I'm done with this one", but maybe not.
								// Let's keep it open.
							}}
							style={{ marginRight: 'auto' }}
						>
							{isSelected ? 'Remove from Selection' : 'Add to Selection'}
						</button>
					)}
					<button
						className="criteria-detail-modal__btn criteria-detail-modal__btn--primary"
						onClick={handleCloseClick}
					>
						Close
					</button>
				</div>
			</div>
		</div>
	);
};

CriteriaDetailModal.propTypes = {
	criteria: PropTypes.shape({
		id: PropTypes.string.isRequired,
		title: PropTypes.string,
		description: PropTypes.string,
		assertion: PropTypes.string,
	}).isRequired,
	comparison: PropTypes.object,
	conditions: PropTypes.array,
	onClose: PropTypes.func,
	isSelected: PropTypes.bool,
	onToggleSelect: PropTypes.func,
};

CriteriaDetailModal.defaultProps = {
	onClose: () => {},
	isSelected: false,
};

export default CriteriaDetailModal;
