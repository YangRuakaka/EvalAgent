import React from 'react';
import PropTypes from 'prop-types';
import { verdictToColor, granularityLabels } from './utils/criteriaInteraction';
import './EvaluationDetailPanel.css';


const EvaluationDetailPanel = ({ 
  step,                
  cluster,               
  evaluations,           
  onClose,
}) => {
  if (!evaluations || evaluations.length === 0) {
    return null;
  }
  
  const isClusterView = !!cluster;
  const title = isClusterView 
    ? `Cluster "${cluster.semantic_label}" Evaluations`
    : `Step ${step?.stepIndex} Evaluations`;
  
  return (
    <div className="evaluation-detail-panel">
      <div className="evaluation-detail-header">
        <h3 className="evaluation-detail-title">{title}</h3>
        <button className="evaluation-detail-close" onClick={onClose}>✕</button>
      </div>
      
      <div className="evaluation-detail-summary">
        {isClusterView ? (
          <p className="cluster-summary">{cluster.cluster_summary}</p>
        ) : (
          <p className="step-summary">
            {step?.modelOutput?.thinking || 'No thinking recorded'}
          </p>
        )}
      </div>
      
      <div className="evaluation-detail-content">
        {evaluations.map((evaluation) => {
          const colorScheme = verdictToColor[evaluation.verdict];
          
          return (
            <div
              key={evaluation.criterion_name}
              className="evaluation-detail-card"
              style={{ borderLeftColor: colorScheme.border }}
            >
              {/* Header: Criteria and Verdict */}
              <div className="evaluation-detail-header-row">
                <span className="evaluation-detail-criterion">
                  {evaluation.criterion_name}
                </span>
                <span
                  className="evaluation-detail-verdict"
                  style={{
                    backgroundColor: colorScheme.bg,
                    color: colorScheme.text,
                    borderColor: colorScheme.border,
                  }}
                >
                  {evaluation.verdict}
                </span>
              </div>
              
              {/* Granularity and Confidence */}
              <div className="evaluation-detail-metadata">
                <span className="granularity-badge">
                  {granularityLabels[evaluation.required_granularity]}
                </span>
                <span className="confidence-badge">
                  Confidence: {(evaluation.confidence_score * 100).toFixed(0)}%
                </span>
              </div>
              
              {/* Reasoning Process */}
              <div className="evaluation-detail-reasoning">
                <h5>Reasoning:</h5>
                <p>{evaluation.reasoning}</p>
              </div>
              
              {/* Aggregated Step Summary */}
              <div className="evaluation-detail-aggregated">
                <h5>Aggregated Steps:</h5>
                <pre className="aggregated-summary">
                  {evaluation.aggregated_step_summary}
                </pre>
              </div>
              
              {/* Relevant Steps */}
              {evaluation.relevant_steps && evaluation.relevant_steps.length > 0 && (
                <div className="evaluation-detail-steps">
                  <h5>Relevant Steps: </h5>
                  <div className="step-indices">
                    {evaluation.relevant_steps.map(idx => (
                      <span key={idx} className="step-index-badge">{idx}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

EvaluationDetailPanel.propTypes = {
  step: PropTypes.shape({
    stepIndex: PropTypes.number,
    modelOutput: PropTypes.object,
  }),
  cluster: PropTypes.shape({
    cluster_id: PropTypes.string,
    semantic_label: PropTypes.string,
    cluster_summary: PropTypes.string,
  }),
  evaluations: PropTypes.arrayOf(PropTypes.shape({
    criterion_name: PropTypes.string,
    verdict: PropTypes.string,
    reasoning: PropTypes.string,
    confidence_score: PropTypes.number,
    aggregated_step_summary: PropTypes.string,
    relevant_steps: PropTypes.arrayOf(PropTypes.number),
    required_granularity: PropTypes.string,
  })),
  onClose: PropTypes.func,
};

EvaluationDetailPanel.defaultProps = {
  step: null,
  cluster: null,
  evaluations: [],
  onClose: () => {},
};

export default EvaluationDetailPanel;
