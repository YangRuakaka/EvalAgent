import { useCallback, useMemo } from 'react';

import { createApiClient } from '../services/api/client';
import { API_ENDPOINTS } from '../services/api/endpoints';

/**
 * React hook that provides action creators for interacting with the shared application state.
 * Handles all data fetching, CRUD operations, and state dispatch.
 * Creates a new API client instance per hook invocation for better testability and flexibility.
 */
export const useAppActions = (dispatch) => {
  // Create API client instance for this hook (enables testing, dynamic config, etc.)
  const apiClient = createApiClient();

  // ============ Configuration & Criteria Fetching ============
  const createFetchAction = useCallback((endpoint, actionType) => async () => {
    try {
      dispatch({ type: `${actionType}/loading` });
      console.log(`[API] ${actionType} - Request from endpoint:`, endpoint);
      const response = await apiClient.get(endpoint);
      console.log(`[API] ${actionType} - Response:`, response);
      if (response.ok) {
        dispatch({ type: `${actionType}/loaded`, payload: response.data });
      } else {
        dispatch({ type: `${actionType}/error`, payload: response.status });
      }
    } catch (error) {
      console.error(`[API] ${actionType} - Error:`, error);
      dispatch({ type: `${actionType}/error`, payload: error.message });
    }
  }, [apiClient, dispatch]);

  const fetchConfiguration = useMemo(() => 
    createFetchAction(API_ENDPOINTS.configuration.root, 'configuration'),
    [createFetchAction]
  );

  const fetchCriteria = useMemo(() => 
    createFetchAction(API_ENDPOINTS.criteria.root, 'criteria'),
    [createFetchAction]
  );

  const fetchExperiments = useMemo(() => 
    createFetchAction(API_ENDPOINTS.experiments.root, 'experiments'),
    [createFetchAction]
  );

  const fetchTrajectory = useMemo(() => 
    createFetchAction(API_ENDPOINTS.trajectory.root, 'trajectory'),
    [createFetchAction]
  );

  // ============ Criteria CRUD Operations ============
  const createCriteria = useCallback(async (criteriaData) => {
    try {
      dispatch({ type: 'criteria/creating' });
      console.log('[API] createCriteria - Request:', criteriaData);
      const response = await apiClient.post(API_ENDPOINTS.criteria.create, criteriaData);
      console.log('[API] createCriteria - Response:', response);
      if (response.ok) {
        dispatch({ type: 'criteria/created', payload: response.data });
        return response.data;
      } else {
        dispatch({ type: 'criteria/error', payload: response.status });
        return null;
      }
    } catch (error) {
      console.error('[API] createCriteria - Error:', error);
      dispatch({ type: 'criteria/error', payload: error.message });
      return null;
    }
  }, [dispatch]);

  const updateCriteria = useCallback(async (criteriaId, criteriaData) => {
    try {
      dispatch({ type: 'criteria/updating' });
      console.log('[API] updateCriteria - Request:', { criteriaId, criteriaData });
      const response = await apiClient.put(
        API_ENDPOINTS.criteria.update(criteriaId),
        criteriaData,
      );
      console.log('[API] updateCriteria - Response:', response);
      if (response.ok) {
        dispatch({ type: 'criteria/updated', payload: response.data });
        return response.data;
      } else {
        dispatch({ type: 'criteria/error', payload: response.status });
        return null;
      }
    } catch (error) {
      console.error('[API] updateCriteria - Error:', error);
      dispatch({ type: 'criteria/error', payload: error.message });
      return null;
    }
  }, [dispatch]);

  const deleteCriteria = useCallback(async (criteriaId) => {
    try {
      dispatch({ type: 'criteria/deleting' });
      console.log('[API] deleteCriteria - Request:', { criteriaId });
      const response = await apiClient.delete(API_ENDPOINTS.criteria.delete(criteriaId));
      console.log('[API] deleteCriteria - Response:', response);
      if (response.ok) {
        dispatch({ type: 'criteria/deleted', payload: criteriaId });
        return true;
      } else {
        dispatch({ type: 'criteria/error', payload: response.status });
        return false;
      }
    } catch (error) {
      console.error('[API] deleteCriteria - Error:', error);
      dispatch({ type: 'criteria/error', payload: error.message });
      return false;
    }
  }, [dispatch]);

  // ============ Other Actions ============
  const selectExperiment = useCallback((experimentId) => {
    dispatch({ type: 'experiments/select', payload: experimentId });
  }, [dispatch]);

  // Return actions directly (not wrapped in a function)
  return {
    fetchConfiguration,
    fetchCriteria,
    fetchExperiments,
    fetchTrajectory,
    createCriteria,
    updateCriteria,
    deleteCriteria,
    selectExperiment,
  };
};
