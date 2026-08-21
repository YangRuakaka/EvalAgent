import { useCallback, useMemo } from 'react';

import { createApiClient } from '../services/api/client';
import { API_ENDPOINTS } from '../services/api/endpoints';
import { debugLog } from '../utils/logger';

/**
 * React hook that provides action creators for interacting with the shared application state.
 * Handles all data fetching, CRUD operations, and state dispatch.
 * Creates a new API client instance per hook invocation for better testability and flexibility.
 */
export const useAppActions = (dispatch) => {
  // Create API client instance for this hook (enables testing, dynamic config, etc.)
  const apiClient = useMemo(() => createApiClient(), []);

  // ============ Configuration & Criteria Fetching ============
  const createFetchAction = useCallback((endpoint, actionType) => async () => {
    try {
      dispatch({ type: `${actionType}/loading` });
      debugLog(`[API] ${actionType} - Request from endpoint:`, endpoint);
      const response = await apiClient.get(endpoint);
      debugLog(`[API] ${actionType} - Response:`, response);
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
      debugLog('[API] createCriteria - Request:', criteriaData);
      const response = await apiClient.post(API_ENDPOINTS.criteria.create, criteriaData);
      debugLog('[API] createCriteria - Response:', response);
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
  }, [apiClient, dispatch]);

  const updateCriteria = useCallback(async (criteriaId, criteriaData) => {
    try {
      dispatch({ type: 'criteria/updating' });
      debugLog('[API] updateCriteria - Request:', { criteriaId, criteriaData });
      const response = await apiClient.put(
        API_ENDPOINTS.criteria.update(criteriaId),
        criteriaData,
      );
      debugLog('[API] updateCriteria - Response:', response);
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
  }, [apiClient, dispatch]);

  const deleteCriteria = useCallback(async (criteriaId) => {
    try {
      dispatch({ type: 'criteria/deleting' });
      debugLog('[API] deleteCriteria - Request:', { criteriaId });
      const response = await apiClient.delete(API_ENDPOINTS.criteria.delete(criteriaId));
      debugLog('[API] deleteCriteria - Response:', response);
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
  }, [apiClient, dispatch]);

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
