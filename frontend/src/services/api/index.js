import { createApiClient } from './client';
import { API_ENDPOINTS } from './endpoints';

const defaultClient = createApiClient();

export const generatePersona = (demographic, client = defaultClient) => {
	console.log('[API] generatePersona - Request:', { demographic });
	return client.post(API_ENDPOINTS.persona.generate, { demographic }).then(response => {
		console.log('[API] generatePersona - Response:', response);
		return response;
	});
};

export const generatePersonaVariation = (personaContent, values, client = defaultClient) => {
	const payload = {
		persona: personaContent,
		values,
	};
	console.log('[API] generatePersonaVariation - Request:', { personaContent, values });
	return client.post(API_ENDPOINTS.personaVariation.generate, payload).then(response => {
		console.log('[API] generatePersonaVariation - Response:', response);
		return response;
	});
};

export const fetchHistoryLogs = (client = defaultClient) => {
	console.log('[API] fetchHistoryLogs - Request');
	return client.get(API_ENDPOINTS.historyLogs.root).then(response => {
		console.log('[API] fetchHistoryLogs - Response:', response);
		return response;
	});
};

export const runBrowserAgent = (payload, client = defaultClient) => {
	console.log('[API] runBrowserAgent - Request:', payload);
	return client.post(API_ENDPOINTS.browserAgent.run, payload).then(response => {
		console.log('[API] runBrowserAgent - Response:', response);
		return response;
	});
};

export const generateCriteria = (taskName, taskUrl, personas, models, client = defaultClient) => {
	const payload = {
		task_name: taskName,
		task_url: taskUrl,
		personas,
		models,
	};
	console.log('[API] generateCriteria - Request:', { taskName, taskUrl, personas, models });
	return client.post(API_ENDPOINTS.criteria.generate, payload).then(response => {
		console.log('[API] generateCriteria - Response:', response);
		return response;
	});
};

export const evaluateExperiment = (conditionIds, criteria, client = defaultClient) => {
	const payload = {
		conditions: conditionIds.map(c => {
			const conditionId = typeof c === 'object' ? (c.id || c.conditionID) : c;
			return { conditionID: conditionId };
		}),
		criteria: criteria.map(c => ({
			title: c.title || c.id || c.name || '',
			assertion: c.assertion || '',
			description: c.description || '',
		})),
	};

	console.log('[API] evaluateExperiment - Request:', { payload });
	return client.post(API_ENDPOINTS.judge.evaluateExperiment, payload).then(response => {
		console.log('[API] evaluateExperiment - Response:', response);
		return response;
	}).catch(error => {
		console.error('[API] evaluateExperiment - Error:', error);
		throw error;
	});
};

export const analyzeGranularity = (criterion, taskName, taskUrl, client = defaultClient) => {
	const payload = {
		criterion,
		task_name: taskName,
		task_url: taskUrl,
	};
	console.log('[API] analyzeGranularity - Request:', { criterion, taskName, taskUrl });
	return client.post(API_ENDPOINTS.judge.analyzeGranularity, payload).then(response => {
		console.log('[API] analyzeGranularity - Response:', response);
		return response;
	});
};



export { createApiClient, API_ENDPOINTS };
