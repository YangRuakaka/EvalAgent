import { useState, useCallback, useEffect, useRef } from 'react';
import { evaluateExperiment } from '../services/api';

/**
 * Helper hook to manage Agent Judge evaluation reports
 * Responsible for:
 * 1. Loading existing evaluation report
 * 2. Submitting evaluation request
 * 3. Merging steps and evaluation data
 * 4. Providing query methods
 */
export function useJudgeReport(runId, initialSteps = [], evaluationResponse = null) {
  // Evaluation report (from backend)
  const [report, setReport] = useState(null);
  
  // Loading status
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Locally computed aggregated data (Step + Report merge)
  const [enrichedSteps, setEnrichedSteps] = useState([]);
  
  // Cached analyzed granularity (criterion → required_granularity)
  const [granularityCache, setGranularityCache] = useState({});

  // Use ref to store latest initialSteps, avoiding infinite loops from dependency changes
  const stepsRef = useRef(initialSteps);
  useEffect(() => {
    stepsRef.current = initialSteps;
  }, [initialSteps]);

  // When evaluationResponse is passed from outside, update report and enrichedSteps
  useEffect(() => {
    if (!evaluationResponse) {
      // If no evaluationResponse, but initialSteps updated, we need to reset enrichedSteps
      setEnrichedSteps(initialSteps);
      return;
    }

    setReport(evaluationResponse);
    
    // Process new response data directly
    if (evaluationResponse.experiments && evaluationResponse.experiments.length > 0) {
      // If runId not provided, use run_id from the first experiment in evaluationResponse
      let targetRunId = runId;
      if (!targetRunId && evaluationResponse.experiments[0]) {
        targetRunId = evaluationResponse.experiments[0].run_id || evaluationResponse.experiments[0].condition_id;
      }

      let experiment = evaluationResponse.experiments.find(e => e.run_id === targetRunId || e.condition_id === targetRunId);

      // Fallback: if not found and there is only one experiment, use it
      if (!experiment && evaluationResponse.experiments.length === 1) {
        experiment = evaluationResponse.experiments[0];
      }

      if (experiment) {
        const stepEvaluations = {}; // stepIndex -> array of evaluations

        experiment.criteria.forEach(criterion => {
          if (!criterion.involved_steps) return;
          
          criterion.involved_steps.forEach(involvedStep => {
            if (!involvedStep.steps || !Array.isArray(involvedStep.steps)) return;

            involvedStep.steps.forEach(stepIdx => {
              if (!stepEvaluations[stepIdx]) {
                stepEvaluations[stepIdx] = [];
              }
              
              // Handle highlighted_evidence - can be array or single object
              let evidenceList = [];
              if (involvedStep.highlighted_evidence) {
                if (Array.isArray(involvedStep.highlighted_evidence)) {
                  evidenceList = involvedStep.highlighted_evidence;
                } else {
                  evidenceList = [involvedStep.highlighted_evidence];
                }
              }
              
              stepEvaluations[stepIdx].push({
                criterion_name: criterion.title,
                criterion_id: criterion.id || criterion.title, // If no id, use title
                verdict: involvedStep.evaluateStatus ? involvedStep.evaluateStatus.toUpperCase() : 'UNKNOWN',
                evaluateStatus: involvedStep.evaluateStatus, // Keep original status for icon mapping
                reasoning: involvedStep.reasoning,
                confidence_score: involvedStep.confidenceScore,
                highlighted_evidence: evidenceList, // Ensure it is an array
                granularity: involvedStep.granularity,
                isStepLevelEval: involvedStep.granularity === 'step_level'
              });
            });
          });
        });

        const enriched = initialSteps.map((step, idx) => {
          return {
            ...step,
            relatedEvaluations: stepEvaluations[idx] || []
          };
        });
        
        setEnrichedSteps(enriched);
      } else {
        console.warn('[useJudgeReport] No matching experiment found for runId:', targetRunId);
        setEnrichedSteps(initialSteps);
      }
    }
  }, [evaluationResponse, runId, initialSteps]);

  /**
   * Internal method: merge steps and report data
   */
  const enrichStepsWithEvaluations = useCallback((steps, judgeReport) => {
    if (!judgeReport) {
      setEnrichedSteps(steps);
      return;
    }

    // Handle new response format (experiments array)
    if (judgeReport.experiments) {
      const experiment = judgeReport.experiments.find(e => e.run_id === runId || e.condition_id === runId);
      if (!experiment) {
        setEnrichedSteps(steps);
        return;
      }

      const stepEvaluations = {}; // stepIndex -> array of evaluations

      experiment.criteria.forEach(criterion => {
        if (!criterion.involved_steps) return;
        
        criterion.involved_steps.forEach(involvedStep => {
          involvedStep.steps.forEach(stepIdx => {
            if (!stepEvaluations[stepIdx]) {
              stepEvaluations[stepIdx] = [];
            }
            
            let evidenceList = [];
            if (involvedStep.highlighted_evidence) {
              if (Array.isArray(involvedStep.highlighted_evidence)) {
                evidenceList = involvedStep.highlighted_evidence;
              } else {
                evidenceList = [involvedStep.highlighted_evidence];
              }
            }
            
            stepEvaluations[stepIdx].push({
              criterion_name: criterion.title,
              criterion_id: criterion.id || criterion.title,
              verdict: involvedStep.evaluateStatus ? involvedStep.evaluateStatus.toUpperCase() : 'UNKNOWN',
              evaluateStatus: involvedStep.evaluateStatus, 
              reasoning: involvedStep.reasoning,
              confidence_score: involvedStep.confidenceScore,
              highlighted_evidence: evidenceList, 
              granularity: involvedStep.granularity,
              isStepLevelEval: involvedStep.granularity === 'step_level'
            });
          });
        });
      });

      const enriched = steps.map((step, idx) => {
        return {
          ...step,
          relatedEvaluations: stepEvaluations[idx] || []
        };
      });
      
      setEnrichedSteps(enriched);
      return;
    }
    
    const clusterMap = {};
    judgeReport.clusters?.forEach(cluster => {
      cluster.step_indices.forEach(stepIdx => {
        clusterMap[stepIdx] = {
          cluster_id: cluster.cluster_id,
          semantic_label: cluster.semantic_label,
        };
      });
    });
    
    const enriched = steps.map((step, idx) => {
      const relatedEvals = judgeReport.evaluations
        .filter(evaluation => evaluation.relevant_steps.includes(idx))
        .map(evaluation => ({
          criterion_name: evaluation.criterion_name,
          verdict: evaluation.verdict,
          confidence_score: evaluation.confidence_score,
          isStepLevelEval: evaluation.required_granularity === 'STEP_LEVEL',
        }));
      
      return {
        ...step,
        clusterId: clusterMap[idx]?.cluster_id || null,
        clusterLabel: clusterMap[idx]?.semantic_label || null,
        relatedEvaluations: relatedEvals,
      };
    });
    
    setEnrichedSteps(enriched);
    
    const granularityDict = {};
    judgeReport.evaluations?.forEach(evaluation => {
      granularityDict[evaluation.criterion_name] = evaluation.required_granularity;
    });
    setGranularityCache(granularityDict);
  }, [runId]);

  
  const submitEvaluation = useCallback(async (criteriaList) => {
    if (!runId) throw new Error('runId (conditionId) is required');
    
    setIsLoading(true);
    setError(null);
    
    try {
      const result = await evaluateExperiment([runId], criteriaList);
      
      if (result.ok && result.data) {
        setReport(result.data);
        enrichStepsWithEvaluations(stepsRef.current, result.data);
      } else {
        throw new Error(result.error || 'Evaluation failed');
      }
      
      return result;
    } catch (err) {
      console.error('Evaluation error:', err);
      setError(err.message || 'Failed to submit evaluation');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [runId, enrichStepsWithEvaluations]);
  
  const getGranularityForCriterion = useCallback((criterionId) => {
    return granularityCache[criterionId] || 'STEP_LEVEL';
  }, [granularityCache]);
  
  const getStepEvaluationDetails = useCallback((stepIndex) => {
    // Prefer using enrichedSteps which handles both formats
    if (enrichedSteps[stepIndex] && enrichedSteps[stepIndex].relatedEvaluations) {
      return enrichedSteps[stepIndex].relatedEvaluations;
    }

    if (!report || !report.evaluations) return [];
    
    return report.evaluations
      .filter(evaluation => evaluation.relevant_steps.includes(stepIndex))
      .map(evaluation => ({
        ...evaluation,
        affectsThisStep: true,
      }));
  }, [report, enrichedSteps]);
  
  const getClusterEvaluationDetails = useCallback((clusterId) => {
    if (!report || !report.evaluations) return [];
    
    const cluster = report.clusters?.find(c => c.cluster_id === clusterId);
    if (!cluster) return [];
    
    return report.evaluations
      .filter(evaluation => {
        if (evaluation.required_granularity === 'SUBTASK_CLUSTER') {
          return evaluation.relevant_steps.some(idx => cluster.step_indices.includes(idx));
        }
        return evaluation.relevant_steps.some(idx => cluster.step_indices.includes(idx));
      })
      .map(evaluation => ({
        ...evaluation,
        affectsThisCluster: true,
      }));
  }, [report]);
  
  useEffect(() => {
    enrichStepsWithEvaluations(stepsRef.current, null);
  }, [enrichStepsWithEvaluations]);
  
  return {
    report,
    isLoading,
    error,
    
    enrichedSteps,
    
    submitEvaluation,
    getGranularityForCriterion,
    getStepEvaluationDetails,
    getClusterEvaluationDetails,
  };
}

export default useJudgeReport;
