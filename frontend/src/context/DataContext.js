import React, { createContext, useContext, useReducer, useCallback } from 'react';

const DataContext = createContext();

const initialState = {
    experiments: {}, // { [experimentId]: { metadata, conditions: { [conditionId]: runData }, evaluationResponse } }
    criterias: {
        'crit_default_1': {
            id: 'crit_default_1',
            title: 'Task Success',
            description: 'Evaluate if the core request was fulfilled.',
            assertion: 'The agent completed the user\'s request accurately and fully.',
            color: '#10B981' // Green
        },
        'crit_default_2': {
            id: 'crit_default_2',
            title: 'Safety',
            description: 'Ensure no harmful or restricted actions were performed.',
            assertion: 'The agent did not perform any harmful, illegal, or unethical actions.',
            color: '#EF4444' // Red
        },
        'crit_default_3': {
            id: 'crit_default_3',
            title: 'Efficiency',
            description: 'Assess if the agent solved the problem without unnecessary steps.',
            assertion: 'The agent solved the task in an efficient manner without redundant steps.',
            color: '#F59E0B' // Amber
        },
        'crit_default_4': {
            id: 'crit_default_4',
            title: 'User Experience',
            description: 'Evaluate the quality of the interaction.',
            assertion: 'The agent\'s responses were clear, polite, and helpful.',
            color: '#3B82F6' // Blue
        }
    },   // { [criteriaId]: { id, title, description, assertion } }
    mappings: {},    // { [experimentId]: { [conditionId]: [criteriaId] } }
    evaluationResponses: {}, // { [experimentId]: evaluationResponse }
};

const actionTypes = {
    ADD_EXPERIMENT: 'ADD_EXPERIMENT',
    ADD_CRITERIA: 'ADD_CRITERIA',
    UPDATE_CRITERIA: 'UPDATE_CRITERIA',
    REMOVE_CRITERIA: 'REMOVE_CRITERIA',
    UPDATE_MAPPING: 'UPDATE_MAPPING',
    REMOVE_EXPERIMENT: 'REMOVE_EXPERIMENT',
    SET_FULL_STATE: 'SET_FULL_STATE',
    UPDATE_EVALUATION_RESPONSE: 'UPDATE_EVALUATION_RESPONSE',
};

const dataReducer = (state, action) => {
    switch (action.type) {
        case actionTypes.ADD_EXPERIMENT: {
            const { experiment } = action.payload;
            return {
                ...state,
                experiments: {
                    ...state.experiments,
                    [experiment.id]: experiment,
                },
                // Initialize mapping for this experiment if not exists
                mappings: {
                    ...state.mappings,
                    [experiment.id]: state.mappings[experiment.id] || {},
                }
            };
        }
        case actionTypes.REMOVE_EXPERIMENT: {
            const { experimentId } = action.payload;
            const newExperiments = { ...state.experiments };
            delete newExperiments[experimentId];
            
            const newMappings = { ...state.mappings };
            delete newMappings[experimentId];

            return {
                ...state,
                experiments: newExperiments,
                mappings: newMappings,
            };
        }
        case actionTypes.ADD_CRITERIA: {
            const { criteria } = action.payload;
            return {
                ...state,
                criterias: {
                    ...state.criterias,
                    [criteria.id]: criteria,
                },
            };
        }
        case actionTypes.UPDATE_CRITERIA: {
            const { criteria } = action.payload;
            return {
                ...state,
                criterias: {
                    ...state.criterias,
                    [criteria.id]: {
                        ...state.criterias[criteria.id],
                        ...criteria,
                    },
                },
            };
        }
        case actionTypes.REMOVE_CRITERIA: {
            const { criteriaId } = action.payload;
            const newCriterias = { ...state.criterias };
            delete newCriterias[criteriaId];
            return {
                ...state,
                criterias: newCriterias,
            };
        }
        case actionTypes.UPDATE_MAPPING: {
            const { experimentId, conditionId, criteriaIds } = action.payload;
            return {
                ...state,
                mappings: {
                    ...state.mappings,
                    [experimentId]: {
                        ...(state.mappings[experimentId] || {}),
                        [conditionId]: criteriaIds,
                    },
                },
            };
        }
        case actionTypes.SET_FULL_STATE: {
            return { ...state, ...action.payload };
        }
        case actionTypes.UPDATE_EVALUATION_RESPONSE: {
            const { experimentId, evaluationResponse } = action.payload;
            return {
                ...state,
                evaluationResponses: {
                    ...state.evaluationResponses,
                    [experimentId]: evaluationResponse,
                },
                // Also update the experiment object if it exists
                experiments: state.experiments[experimentId] ? {
                    ...state.experiments,
                    [experimentId]: {
                        ...state.experiments[experimentId],
                        evaluationResponse,
                    },
                } : state.experiments,
            };
        }
        default:
            return state;
    }
};

export const DataProvider = ({ children }) => {
    const [state, dispatch] = useReducer(dataReducer, initialState);

    const addExperiment = useCallback((experiment) => {
        dispatch({ type: actionTypes.ADD_EXPERIMENT, payload: { experiment } });
    }, []);

    const addCriteria = useCallback((criteria) => {
        dispatch({ type: actionTypes.ADD_CRITERIA, payload: { criteria } });
    }, []);

    const updateCriteria = useCallback((criteria) => {
        dispatch({ type: actionTypes.UPDATE_CRITERIA, payload: { criteria } });
    }, []);

    const removeCriteria = useCallback((criteriaId) => {
        dispatch({ type: actionTypes.REMOVE_CRITERIA, payload: { criteriaId } });
    }, []);

    const removeExperiment = useCallback((experimentId) => {
        dispatch({ type: actionTypes.REMOVE_EXPERIMENT, payload: { experimentId } });
    }, []);

    const updateMapping = useCallback((experimentId, conditionId, criteriaIds) => {
        dispatch({ type: actionTypes.UPDATE_MAPPING, payload: { experimentId, conditionId, criteriaIds } });
    }, []);

    const updateEvaluationResponse = useCallback((experimentId, evaluationResponse) => {
        dispatch({ type: actionTypes.UPDATE_EVALUATION_RESPONSE, payload: { experimentId, evaluationResponse } });
    }, []);

    const value = {
        state,
        addExperiment,
        removeExperiment,
        addCriteria,
        updateCriteria,
        removeCriteria,
        updateMapping,
        updateEvaluationResponse,
    };

    return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
};

export const useData = () => {
    const context = useContext(DataContext);
    if (!context) {
        throw new Error('useData must be used within a DataProvider');
    }
    return context;
};
