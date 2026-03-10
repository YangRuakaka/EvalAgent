import { useState, useRef, useMemo, useEffect } from 'react';
import { runBrowserAgent, stopBrowserAgentRun, streamBrowserAgentEvents } from '../services/api';
import { createBrowserAgentRunId, extractErrorMessage } from '../utils/runUtils';

export const useEnvironmentConfiguration = (
    variationStateByPersona, 
    setVariationStateByPersona, 
    personaGallery, 
    onAddRun,
    onEnvironmentRunStateChange,
    isCacheLoading
) => {
    const [environmentPersonaId, setEnvironmentPersonaId] = useState('');
    const [environmentVariationIds, setEnvironmentVariationIds] = useState([]);
    const [environmentTaskName, setEnvironmentTaskName] = useState('');
    const [environmentTaskUrl, setEnvironmentTaskUrl] = useState('');
    const [environmentModels, setEnvironmentModels] = useState([]);
    const [environmentRunTimes, setEnvironmentRunTimes] = useState('1');
    const [environmentErrors, setEnvironmentErrors] = useState({});
    const [environmentRunError, setEnvironmentRunError] = useState('');
    const [environmentRunResult, setEnvironmentRunResult] = useState(null);
    const [isRunningEnvironment, setIsRunningEnvironment] = useState(false);
    const [environmentWaitSeconds, setEnvironmentWaitSeconds] = useState(0);
    const environmentWaitTimerRef = useRef(null);
    const activeEnvironmentRunIdRef = useRef(null);
    const activeEnvironmentAbortRef = useRef(null);

    const emitEnvironmentRunState = (payload) => {
		if (typeof onEnvironmentRunStateChange !== 'function' || !payload || typeof payload !== 'object') {
			return;
		}
		onEnvironmentRunStateChange(payload);
	};

    const environmentPersona = useMemo(
		() => personaGallery.find((persona) => persona.id === environmentPersonaId) || null,
		[personaGallery, environmentPersonaId],
	);

	const environmentPersonaVariations = useMemo(() => {
		if (!environmentPersonaId) {
			return [];
		}
		const state = variationStateByPersona[environmentPersonaId];
		return state?.variations || [];
	}, [environmentPersonaId, variationStateByPersona]);

    useEffect(() => {
		if (!environmentPersonaId) {
			if (environmentVariationIds.length > 0) {
				setEnvironmentVariationIds([]);
			}
			return;
		}
		const state = variationStateByPersona[environmentPersonaId];
		const validKeys = (state?.variations || []).map((variation) => variation.valueKey);
		if (environmentVariationIds.some((value) => !validKeys.includes(value))) {
			setEnvironmentVariationIds((prev) => prev.filter((value) => validKeys.includes(value)));
		}
	}, [environmentPersonaId, environmentVariationIds, variationStateByPersona]);

	useEffect(() => () => {
		if (environmentWaitTimerRef.current) {
			window.clearInterval(environmentWaitTimerRef.current);
			environmentWaitTimerRef.current = null;
		}

		if (activeEnvironmentAbortRef.current) {
			activeEnvironmentAbortRef.current.abort();
			activeEnvironmentAbortRef.current = null;
		}

		const activeRunId = activeEnvironmentRunIdRef.current;
		if (activeRunId) {
			stopBrowserAgentRun(activeRunId).catch((error) => {
				console.warn('[browser-agent/stop] Cleanup stop request failed:', error);
			});
			activeEnvironmentRunIdRef.current = null;
		}
	}, []);

    const clearEnvironmentError = (field) => {
		setEnvironmentErrors((prev) => {
			if (!prev[field]) {
				return prev;
			}
			const next = { ...prev };
			delete next[field];
			return next;
		});
	};

	const handleEnvironmentPersonaChange = (event) => {
		const { value } = event.target;
		setEnvironmentPersonaId(value);
		setEnvironmentVariationIds([]);
		clearEnvironmentError('persona');
		clearEnvironmentError('variations');
		setEnvironmentRunError('');
		setEnvironmentRunResult(null);
	};

	const handleEnvironmentVariationToggle = (valueKey) => {
		setEnvironmentVariationIds((prev) => {
			const isSelected = prev.includes(valueKey);
			const next = isSelected ? prev.filter((value) => value !== valueKey) : [...prev, valueKey];
			return next;
		});
		clearEnvironmentError('variations');
		setEnvironmentRunError('');
		setEnvironmentRunResult(null);
	};

	const handleEnvironmentVariationUpdate = (variationId, updates) => {
		// updates expected shape: { value: 'new content' }
		setVariationStateByPersona((prev) => {
			const next = { ...prev };
			let changed = false;
			
			// Helper function to process variations for a persona
			const processPersonaVariations = (personaId) => {
				const state = next[personaId];
				if (!state || !Array.isArray(state.variations)) return false;
				
				const newVariations = state.variations.map((v) => {
					if (v.valueKey === variationId) {
						// update both `value` and `content` to keep different consumers in sync
						return { ...v, value: updates.value, content: updates.value };
					}
					return v;
				});
				
				const hasChanged = newVariations.some((v, idx) => v !== state.variations[idx]);
				if (hasChanged) {
					next[personaId] = { ...state, variations: newVariations };
				}
				return hasChanged;
			};
			
			// Find and update the matching variation
			for (const personaId of Object.keys(next)) {
				if (processPersonaVariations(personaId)) {
					changed = true;
					break; // stop after updating the matching variation
				}
			}
			
			// if no matching variation found, return prev unchanged
			return changed ? next : prev;
		});
	};

	const handleEnvironmentModelToggle = (value) => {
		setEnvironmentModels((prev) => {
			const isSelected = prev.includes(value);
			if (isSelected) {
				return prev.filter((item) => item !== value);
			}
			return [...prev, value];
		});
		clearEnvironmentError('model');
		setEnvironmentRunError('');
		setEnvironmentRunResult(null);
	};

	const handleEnvironmentRunTimesChange = (event) => {
		setEnvironmentRunTimes(event.target.value);
		clearEnvironmentError('run_times');
		setEnvironmentRunError('');
		setEnvironmentRunResult(null);
	};

    const handleEnvironmentRun = async () => {
		if (isCacheLoading) {
			return;
		}

		if (isRunningEnvironment) {
			const activeRunId = activeEnvironmentRunIdRef.current;

			if (environmentWaitTimerRef.current) {
				window.clearInterval(environmentWaitTimerRef.current);
				environmentWaitTimerRef.current = null;
			}

			if (activeEnvironmentAbortRef.current) {
				activeEnvironmentAbortRef.current.abort();
				activeEnvironmentAbortRef.current = null;
			}

			if (activeRunId) {
				try {
					await stopBrowserAgentRun(activeRunId);
				} catch (error) {
					console.warn('[browser-agent/stop] stop request failed:', error);
				}
			}

			activeEnvironmentRunIdRef.current = null;
			setIsRunningEnvironment(false);
			setEnvironmentRunError('Browser agent run was stopped.');
			emitEnvironmentRunState({
				runId: activeRunId,
				status: 'cancelled',
				isRunning: false,
				error: 'Browser agent run was stopped.',
			});
			return;
		}

		const nextErrors = {};
		if (!environmentPersonaId) {
			nextErrors.persona = 'Select a persona to run the environment.';
		}
		if (environmentVariationIds.length === 0) {
			nextErrors.variations = 'Select at least one variation to include.';
		}
		if (!environmentTaskName.trim() || !environmentTaskUrl.trim()) {
			nextErrors.tasks = 'Task name and target URL are required.';
		}
		if (environmentModels.length === 0) {
			nextErrors.model = 'Select at least one model to run.';
		}
		const parsedRunTimes = Number(environmentRunTimes);
		if (
			!Number.isInteger(parsedRunTimes)
			|| parsedRunTimes < 1
			|| parsedRunTimes > 10
		) {
			nextErrors.run_times = 'Run times must be an integer between 1 and 10.';
		}

		if (Object.keys(nextErrors).length > 0) {
			setEnvironmentErrors(nextErrors);
			return;
		}

		setEnvironmentErrors({});
		setEnvironmentRunError('');
		setEnvironmentRunResult(null);
		setIsRunningEnvironment(true);
		setEnvironmentWaitSeconds(0);
		const runId = createBrowserAgentRunId();
		const taskNameForRun = environmentTaskName.trim();
		const abortController = new AbortController();
		activeEnvironmentRunIdRef.current = runId;
		activeEnvironmentAbortRef.current = abortController;
		emitEnvironmentRunState({
			runId,
			taskName: taskNameForRun,
			status: 'queued',
			isRunning: true,
			logs: [],
			error: null,
		});

		if (environmentWaitTimerRef.current) {
			window.clearInterval(environmentWaitTimerRef.current);
		}
		environmentWaitTimerRef.current = window.setInterval(() => {
			setEnvironmentWaitSeconds((prev) => prev + 1);
		}, 1000);
		try {
			const personaState = variationStateByPersona[environmentPersonaId] || {
				variations: [],
			};
			const selectedVariations = personaState.variations.filter((variation) =>
				environmentVariationIds.includes(variation.valueKey),
			);
			const personaPayload = selectedVariations.map((variation) => ({
				value: variation.valueKey,
				content: variation.content,
			}));
			const modelPayload = environmentModels;

			const requestBody = {
				task: {
					name: environmentTaskName.trim(),
					url: environmentTaskUrl.trim(),
				},
				persona: personaPayload,
				model: modelPayload,
				run_times: parsedRunTimes,
				run_id: runId,
			};

			// Step 1: Start the run (returns immediately)
			const response = await runBrowserAgent(requestBody, {
				retryOnNetworkError: false,
				signal: abortController.signal,
				headers: {
					'X-Browser-Agent-Run-Id': runId,
				},
			});
			console.info('[browser-agent/run] Start response:', response.data);

			if (!response.ok) {
				const message = response.status === 409
					? 'Another browser agent run is already in progress. Please wait or stop it first.'
					: extractErrorMessage(
						response.data,
						`Failed to start the browser agent for task "${environmentTaskName}".`,
					);
				setEnvironmentRunError(message);
				emitEnvironmentRunState({
					runId,
					taskName: taskNameForRun,
					status: 'failed',
					isRunning: false,
					error: message,
				});
				return;
			}

			await new Promise((resolve, reject) => {
				let settled = false;

				const stream = streamBrowserAgentEvents(runId, {
					onStatus: (data) => {
						console.info('[browser-agent/events] Status:', data?.status);

						emitEnvironmentRunState({
							runId,
							taskName: taskNameForRun,
							status: data?.status || 'running',
							isRunning: data?.status === 'queued' || data?.status === 'running',
							logs: Array.isArray(data?.logs) ? data.logs : undefined,
							error: data?.error || null,
						});

						if (data?.status === 'completed') {
							const runResults = Array.isArray(data.results) ? data.results : [];
							if (!runResults.length) {
								setEnvironmentRunError('The browser agent did not return any results.');
								setEnvironmentRunResult([]);
							} else {
								setEnvironmentRunResult(runResults);
								if (typeof onAddRun === 'function') {
									onAddRun({ results: runResults }, { activate: false });
								}
							}

							if (!settled) {
								settled = true;
								stream.close();
								resolve();
							}
							return;
						}

						if (data?.status === 'failed' || data?.status === 'cancelled') {
							const runResults = Array.isArray(data?.results) ? data.results : [];
							if (runResults.length) {
								setEnvironmentRunResult(runResults);
								if (typeof onAddRun === 'function') {
									onAddRun({ results: runResults }, { activate: false });
								}
							}
							setEnvironmentRunError(data?.error || 'Browser agent run failed.');
							emitEnvironmentRunState({
								runId,
								taskName: taskNameForRun,
								status: data?.status,
								isRunning: false,
								logs: Array.isArray(data?.logs) ? data.logs : undefined,
								error: data?.error || 'Browser agent run failed.',
							});
							if (!settled) {
								settled = true;
								stream.close();
								resolve();
							}
						}
					},
					onEnd: (data) => {
						emitEnvironmentRunState({
							runId,
							taskName: taskNameForRun,
							status: data?.status || 'completed',
							isRunning: false,
							logs: Array.isArray(data?.logs) ? data.logs : undefined,
							error: data?.error || null,
						});

						if (settled) {
							return;
						}

						if (data?.status === 'failed' || data?.status === 'cancelled') {
							const runResults = Array.isArray(data?.results) ? data.results : [];
							if (runResults.length) {
								setEnvironmentRunResult(runResults);
								if (typeof onAddRun === 'function') {
									onAddRun({ results: runResults }, { activate: false });
								}
							}
							setEnvironmentRunError(data?.error || 'Browser agent run failed.');
						}

						settled = true;
						stream.close();
						resolve();
					},
					onError: (streamError) => {
						if (settled) {
							return;
						}

						if (abortController.signal.aborted) {
							emitEnvironmentRunState({
								runId,
								taskName: taskNameForRun,
								status: 'cancelled',
								isRunning: false,
								error: 'Browser agent run was stopped.',
							});
							settled = true;
							stream.close();
							resolve();
							return;
						}

						emitEnvironmentRunState({
							runId,
							taskName: taskNameForRun,
							status: 'failed',
							isRunning: false,
							error: streamError?.message || 'Browser agent event stream failed.',
						});
						settled = true;
						stream.close();
						reject(streamError);
					},
					onLog: (line) => {
						if (settled || typeof line !== 'string' || !line.trim()) {
							return;
						}

						emitEnvironmentRunState({
							runId,
							taskName: taskNameForRun,
							status: 'running',
							isRunning: true,
							appendLogs: [line],
							error: null,
						});
					},
				});

				abortController.signal.addEventListener(
					'abort',
					() => {
						if (settled) {
							return;
						}
						settled = true;
						stream.close();
						resolve();
					},
					{ once: true },
				);
			});
		} catch (error) {
			if (error?.name === 'AbortError') {
				setEnvironmentRunError('Browser agent run was stopped.');
				emitEnvironmentRunState({
					runId,
					taskName: taskNameForRun,
					status: 'cancelled',
					isRunning: false,
					error: 'Browser agent run was stopped.',
				});
				return;
			}
			emitEnvironmentRunState({
				runId,
				taskName: taskNameForRun,
				status: 'failed',
				isRunning: false,
				error: error?.message || 'Failed to run the browser agent. Please try again later.',
			});
			setEnvironmentRunError(
				error?.message || 'Failed to run the browser agent. Please try again later.',
			);
		} finally {
			if (environmentWaitTimerRef.current) {
				window.clearInterval(environmentWaitTimerRef.current);
				environmentWaitTimerRef.current = null;
			}
			activeEnvironmentAbortRef.current = null;
			activeEnvironmentRunIdRef.current = null;
			setIsRunningEnvironment(false);
			emitEnvironmentRunState({
				runId,
				taskName: taskNameForRun,
				isRunning: false,
			});
		}
	};

    return {
        environmentPersonaId, setEnvironmentPersonaId,
        environmentVariationIds, setEnvironmentVariationIds,
        environmentTaskName, setEnvironmentTaskName,
        environmentTaskUrl, setEnvironmentTaskUrl,
        environmentModels, setEnvironmentModels,
        environmentRunTimes, setEnvironmentRunTimes,
        environmentErrors, setEnvironmentErrors,
        environmentRunError, setEnvironmentRunError,
        environmentRunResult, setEnvironmentRunResult,
        isRunningEnvironment, setIsRunningEnvironment,
        environmentWaitSeconds, setEnvironmentWaitSeconds,
        environmentPersona,
        environmentPersonaVariations,
        handleEnvironmentPersonaChange,
        handleEnvironmentVariationToggle,
        handleEnvironmentVariationUpdate,
        handleEnvironmentModelToggle,
        handleEnvironmentRunTimesChange,
        handleEnvironmentRun
    };
};
