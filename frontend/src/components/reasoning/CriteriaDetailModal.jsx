import React from 'react';
import PropTypes from 'prop-types';
import { evaluateStatusMap } from './utils/criteriaInteraction';
import './CriteriaDetailModal.css';

const CriteriaDetailModal = ({ 
  criterion,
  onClose,
}) => {
  if (!criterion) {
    return null;
  }

  const evaluateStatus = criterion.evaluateStatus || 'unevaluated';
  const statusConfig = evaluateStatusMap[evaluateStatus] || evaluateStatusMap['unevaluated'];

  return (
    <div className="reasoning-criteria-detail-modal__backdrop" onClick={onClose}>
      <div className="reasoning-criteria-detail-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="reasoning-criteria-detail-modal__header">
          <div className="reasoning-criteria-detail-modal__title-section">
            <h2 className="reasoning-criteria-detail-modal__title">
              {criterion.title || criterion.criterionName || criterion.name || 'Unnamed Criterion'}
            </h2>
            <div 
              className="reasoning-criteria-detail-modal__status-badge"
              style={{
                backgroundColor: statusConfig.bg,
                borderColor: statusConfig.border,
                color: statusConfig.text,
              }}
            >
              <span className="reasoning-criteria-detail-modal__status-icon">{statusConfig.icon}</span>
              <span className="reasoning-criteria-detail-modal__status-label">{statusConfig.label}</span>
            </div>
          </div>
          <button
            className="reasoning-criteria-detail-modal__close"
            onClick={onClose}
            title="Close"
          >
            ✕
          </button>
        </div>

        {/* Content Area */}
        <div className="reasoning-criteria-detail-modal__body">
          {/* Description */}
          {criterion.description && (
            <div className="reasoning-criteria-detail-modal__section">
              <h4 className="reasoning-criteria-detail-modal__section-title">Description</h4>
              <p className="reasoning-criteria-detail-modal__section-content">
                {criterion.description}
              </p>
            </div>
          )}

          {/* Assertion */}
          {criterion.assertion && (
            <div className="reasoning-criteria-detail-modal__section">
              <h4 className="reasoning-criteria-detail-modal__section-title">Assertion</h4>
              <p className="reasoning-criteria-detail-modal__section-content">
                {criterion.assertion}
              </p>
            </div>
          )}

          {/* Evaluation Reasoning */}
          {criterion.reasoning && (
            <div className="reasoning-criteria-detail-modal__section">
              <h4 className="reasoning-criteria-detail-modal__section-title">Reasoning</h4>
              <p className="reasoning-criteria-detail-modal__section-content">
                {criterion.reasoning}
              </p>
            </div>
          )}

          {/* Confidence */}
          {criterion.confidenceScore !== undefined && (
            <div className="reasoning-criteria-detail-modal__section">
              <h4 className="reasoning-criteria-detail-modal__section-title">Confidence Score</h4>
              <div className="reasoning-criteria-detail-modal__confidence">
                <div className="reasoning-criteria-detail-modal__confidence-bar-container">
                  <div 
                    className="reasoning-criteria-detail-modal__confidence-bar"
                    style={{
                      width: `${Math.round(criterion.confidenceScore * 100)}%`,
                      backgroundColor: statusConfig.border,
                    }}
                  />
                </div>
                <span className="reasoning-criteria-detail-modal__confidence-text">
                  {Math.round(criterion.confidenceScore * 100)}%
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

CriteriaDetailModal.propTypes = {
  criterion: PropTypes.shape({
    title: PropTypes.string,
    criterionName: PropTypes.string,
    name: PropTypes.string,
    description: PropTypes.string,
    assertion: PropTypes.string,
    reasoning: PropTypes.string,
    evaluateStatus: PropTypes.oneOf(['pass', 'fail', 'partial', 'unevaluated']),
    confidenceScore: PropTypes.number,
  }),
  onClose: PropTypes.func.isRequired,
};

CriteriaDetailModal.defaultProps = {
  criterion: null,
};

export default CriteriaDetailModal;
