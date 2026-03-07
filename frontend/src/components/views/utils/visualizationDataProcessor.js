const toArray = (value) => {
	if (value === undefined || value === null) {
		return [];
	}

	return Array.isArray(value) ? value : [value];
};

const toObject = (value) => {
	if (value && typeof value === 'object' && !Array.isArray(value)) {
		return value;
	}
	return {};
};

const extractRuns = (payload) => {
	if (Array.isArray(payload)) {
		return payload;
	}

	if (!payload || typeof payload !== 'object') {
		return [];
	}

	if (Array.isArray(payload.results)) {
		return payload.results;
	}

	if (Array.isArray(payload.data)) {
		return payload.data;
	}

	if (payload.data && Array.isArray(payload.data.results)) {
		return payload.data.results;
	}

	if (payload.metadata || payload.history_payload || payload.details || payload.summary) {
		return [payload];
	}

	return [];
};

const normalizeHistoryPayload = (run) => {
	if (run.history_payload && typeof run.history_payload === 'object') {
		return run.history_payload;
	}

	const details = toObject(run.details);
	if (Object.keys(details).length > 0) {
		return {
			screenshots: toArray(details.screenshots),
			screenshot_paths: toArray(details.screenshot_paths),
			screenshot_hashes: toArray(details.screenshot_hashes),
			step_descriptions: toArray(details.step_descriptions),
			model_outputs: details.model_outputs || null,
			last_action: details.last_action || null,
			trajectory: details.trajectory || null,
		};
	}

	return {};
};

const normalizeRun = (run) => {
	const metadata = toObject(run.metadata);
	const summary = toObject(run.summary);
	const historyPayload = normalizeHistoryPayload(run);

	return {
		...run,
		metadata,
		history_payload: historyPayload,
		model: run.model || metadata.model || '',
		run_index: run.run_index !== undefined ? run.run_index : (metadata.run_index !== undefined ? metadata.run_index : undefined),
		is_done: run.is_done !== undefined ? run.is_done : summary.is_done,
		is_successful: run.is_successful !== undefined ? run.is_successful : summary.is_successful,
		has_errors: run.has_errors !== undefined ? run.has_errors : summary.has_errors,
		number_of_steps: run.number_of_steps !== undefined ? run.number_of_steps : summary.number_of_steps,
		total_duration_seconds: run.total_duration_seconds !== undefined ? run.total_duration_seconds : summary.total_duration_seconds,
		final_result: run.final_result !== undefined ? run.final_result : summary.final_result,
		history_path: run.history_path || run.filename || '',
	};
};

const getRunLabel = (run, index) => {
	if (run.label) return run.label;
	const personaData = run.metadata?.persona || run.persona;
	const persona = typeof personaData === 'object' ? personaData.value : personaData;
	const model = run.model;
	if (persona && model) {
		return `${persona} (${model})`;
	}
	return `Condition ${index + 1}`;
};

const getRunId = (run, index) => run.metadata?.id || run.id || run.history_path || run.filename || `condition-${index}`;

export const processVisualizationData = (payload) => {
	// Basic information
	const createdAt = Date.now();
	const uniqueSuffix = Math.random().toString(36).substr(2, 9); 
	const runs = extractRuns(payload).map(normalizeRun);

	const primaryRun = runs[0];
	const taskName = primaryRun?.metadata?.task?.name || 'Unknown Task';
	
	const runId = `${createdAt}-${uniqueSuffix}`;

	// Create a unified processed run object strictly
	const processedRuns = runs.map((run, index) => {
		const id = getRunId(run, index);
		const label = getRunLabel(run, index);
		
		// Extract heavy data
		const screenshots = run.history_payload?.screenshots || run.screenshots || run.details?.screenshots || [];
		const screenshot_hashes = run.history_payload?.screenshot_hashes || run.screenshot_hashes || run.details?.screenshot_hashes || [];
		const model_outputs = run.history_payload?.model_outputs || run.model_outputs || run.details?.model_outputs || [];
		const trajectory = run.trajectory || run.history_payload?.trajectory || run.details?.trajectory || null;

		// Create a clean object with only necessary data, avoiding redundant nesting if possible
		// We keep ...run but we might want to strip history_payload if we extracted everything
		const cleanRun = {
			...run,
			id,
			label,
			screenshots,
			screenshot_hashes,
			model_outputs,
			trajectory
		};
		
		return cleanRun;
	});

	const normalizedConditions = processedRuns.map((run, index) => ({
		id: run.id,
		model: run.model,
		persona: run.metadata?.persona || run.persona,
		run_index: run.run_index !== undefined ? run.run_index : index,
		metadata: run.metadata,
		// raw: run, // Avoiding full raw duplication if not strictly needed, or point to processedRun
		// If raw is needed by some components that expect exact backend structure:
		raw: run, 
		label: run.label,
	}));

	const finalResult = {
		label: taskName+createdAt,
		createdAt,
		conditions: normalizedConditions,
		runs: processedRuns,
		id: runId,
		originalId: primaryRun?.metadata?.id,
		trajectory: {
			details: processedRuns.map((run) => {
				// We already processed trajectory info in processedRuns
				if (run.trajectory || (run.screenshots && run.screenshots.length > 0)) {
					return run; // Just return the processed run which has unified structure
				}
				return null;
			}).filter(Boolean),
		},
		criteria: {
			details: processedRuns, // Reuse the same reference
		},
	};

	return finalResult;
};

export default processVisualizationData;
