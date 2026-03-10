import { useState, useCallback, useMemo, useEffect } from 'react';
import { useData } from '../context/DataContext';
import { evaluateExperiment } from '../services/api';

const createDefaultExperimentState = () => ({
	selectedCriteriaIds: [],
	selectedConditionIds: [],
});

export const useExperimentEvaluation = (activeRunId) => {
    const { state: { mappings, criterias, evaluationResponses }, updateEvaluationResponse } = useData();
    const [evaluateModel, setEvaluateModel] = useState('gpt-4o-mini');
    const [evaluationLoadingByRunId, setEvaluationLoadingByRunId] = useState({});
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

    useEffect(() => {
		if (activeRunId && evaluationResponses && evaluationResponses[activeRunId]) {
			setEvaluationResponse(evaluationResponses[activeRunId]);
		} else {
			setEvaluationResponse(null);
		}
	}, [activeRunId, evaluationResponses]);

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

    const handleEvaluate = async (config) => {
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
    };

    return {
        evaluateModel, setEvaluateModel,
        evaluationResponse,
        selectedCriteriaIds, setSelectedCriteriaIds,
        selectedConditionIds, setSelectedConditionIds,
        isEvaluatingCurrentRun,
        handleEvaluate,
        criterias, // pass through
        mappings, // pass through
    };
};
