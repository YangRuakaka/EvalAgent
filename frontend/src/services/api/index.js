import { createApiClient } from './client';
import { API_ENDPOINTS } from './endpoints';

const defaultClient = createApiClient();

const sanitizeBaseUrl = (value) => {
	if (!value) {
		return '';
	}
	return value.endsWith('/') ? value.slice(0, -1) : value;
};

const buildEventStreamUrl = (path) => {
	const baseUrl = sanitizeBaseUrl(
		process.env.REACT_APP_API_BASE_URL
			|| 'https://eval-agent-backend-588077581214.us-central1.run.app/api/v1/',
	);
	return path.startsWith('/') ? `${baseUrl}${path}` : `${baseUrl}/${path}`;
};

export const generatePersona = (demographic, model, client = defaultClient) => {
	console.log('[API] generatePersona - Request:', { demographic, model });
	return client.post(API_ENDPOINTS.persona.generate, { demographic, model }).then(response => {
		console.log('[API] generatePersona - Response:', response);
		return response;
	});
};

export const generatePersonaVariation = (personaContent, values, model, client = defaultClient) => {
	const payload = {
		persona: personaContent,
		values,
		model,
	};
	console.log('[API] generatePersonaVariation - Request:', { personaContent, values, model });
	return client.post(API_ENDPOINTS.personaVariation.generate, payload).then(response => {
		console.log('[API] generatePersonaVariation - Response:', response);
		return response;
	});
};

export const fetchHistoryLogs = (optionsOrClient = {}, maybeClient) => {
	let options = {};
	let client = defaultClient;

	if (optionsOrClient && typeof optionsOrClient.get === 'function') {
		client = optionsOrClient;
	} else {
		options = optionsOrClient || {};
		if (maybeClient && typeof maybeClient.get === 'function') {
			client = maybeClient;
		}
	}

	const dataSource = typeof options?.dataSource === 'string'
		? options.dataSource.trim().toLowerCase()
		: '';

	const query = dataSource ? `?data_source=${encodeURIComponent(dataSource)}` : '';
	const path = `${API_ENDPOINTS.historyLogs.root}${query}`;

	console.log('[API] fetchHistoryLogs - Request:', { dataSource: dataSource || null });
	return client.get(path).then(response => {
		console.log('[API] fetchHistoryLogs - Response:', response);
		return response;
	});
};

export const runBrowserAgent = (payload, optionsOrClient, maybeClient) => {
	let requestOptions = {};
	let client = defaultClient;

	if (optionsOrClient && typeof optionsOrClient.post === 'function') {
		client = optionsOrClient;
	} else {
		requestOptions = optionsOrClient || {};
		if (maybeClient && typeof maybeClient.post === 'function') {
			client = maybeClient;
		}
	}

	console.log('[API] runBrowserAgent - Request:', payload);
	return client.post(API_ENDPOINTS.browserAgent.run, payload, {
		retryOnNetworkError:	true,
		maxRetries:		2,
		retryDelayMs:		1000,
		signal: requestOptions.signal,
		...(requestOptions.headers ? { headers: requestOptions.headers } : {}),
	}).then(response => {
		console.log('[API] runBrowserAgent - Response:', response);
		return response;
	});
};

export const stopBrowserAgentRun = (runId, client = defaultClient) => {
	console.log('[API] stopBrowserAgentRun - Request:', { runId });
	return client.post(API_ENDPOINTS.browserAgent.stop, { run_id: runId }, {
		retryOnNetworkError: false,
		maxRetries: 0,
	}).then(response => {
		console.log('[API] stopBrowserAgentRun - Response:', response);
		return response;
	});
};

export const getBrowserAgentStatus = (runId, client = defaultClient) => {
	return client.get(`${API_ENDPOINTS.browserAgent.status}/${runId}`, {
		retryOnNetworkError: false,
		maxRetries: 0,
	}).then(response => {
		return response;
	});
};

export const streamBrowserAgentEvents = (
	runId,
	{ onStatus, onError, onEnd, onLog } = {},
) => {
	const url = buildEventStreamUrl(
		`${API_ENDPOINTS.browserAgent.events}/${encodeURIComponent(runId)}`,
	);
	const source = new EventSource(url);

	const parseEventData = (event) => {
		const raw = event?.data;
		if (typeof raw !== 'string') {
			return {};
		}

		try {
			return JSON.parse(raw || '{}');
		} catch {
			return { raw };
		}
	};

	source.addEventListener('status', (event) => {
		try {
			const payload = parseEventData(event);
			if (typeof onStatus === 'function') {
				onStatus(payload);
			}
		} catch (error) {
			if (typeof onError === 'function') {
				onError(error);
			}
		}
	});

	source.addEventListener('end', (event) => {
		try {
			const payload = parseEventData(event);
			if (typeof onEnd === 'function') {
				onEnd(payload);
			}
		} catch (error) {
			if (typeof onError === 'function') {
				onError(error);
			}
		}
	});

	source.addEventListener('log', (event) => {
		if (typeof onLog !== 'function') {
			return;
		}

		try {
			const payload = parseEventData(event);
			if (typeof payload === 'string') {
				onLog(payload);
				return;
			}

			const line = typeof payload?.line === 'string'
				? payload.line
				: (typeof payload?.log === 'string'
					? payload.log
					: (typeof payload?.message === 'string' ? payload.message : payload?.raw));

			if (typeof line === 'string' && line.trim()) {
				onLog(line);
			}
		} catch (error) {
			if (typeof onError === 'function') {
				onError(error);
			}
		}
	});

	source.onmessage = (event) => {
		if (typeof onLog !== 'function') {
			return;
		}

		const payload = parseEventData(event);
		const line = typeof payload === 'string'
			? payload
			: (typeof payload?.line === 'string'
				? payload.line
				: (typeof payload?.log === 'string'
					? payload.log
					: (typeof payload?.message === 'string' ? payload.message : payload?.raw)));

		if (typeof line === 'string' && line.trim()) {
			onLog(line);
		}
	};

	source.onerror = (error) => {
		if (source.readyState === EventSource.CLOSED && typeof onError === 'function') {
			onError(error);
		}
	};

	return {
		close: () => source.close(),
	};
};

export const cleanupServerFiles = (client = defaultClient) => {
	console.log('[API] cleanupServerFiles - Request');
	return client.post(API_ENDPOINTS.maintenance.cleanupFiles, {}).then(response => {
		console.log('[API] cleanupServerFiles - Response:', response);
		return response;
	});
};

export const restartBackendService = (client = defaultClient) => {
	console.log('[API] restartBackendService - Request');
	return client.post(API_ENDPOINTS.maintenance.restartService, {}).then(response => {
		console.log('[API] restartBackendService - Response:', response);
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

export const evaluateExperiment = (conditionIds, criteria, judgeModel = null, client = defaultClient) => {
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

	if (judgeModel) {
		payload.judge_model = judgeModel;
	}

	console.log('[API] evaluateExperiment - Request:', { payload, judgeModel });
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
