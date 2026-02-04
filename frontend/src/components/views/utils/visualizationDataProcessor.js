const toArray = (value) => {
	if (value === undefined || value === null) {
		return [];
	}

	return Array.isArray(value) ? value : [value];
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

const getRunId = (run, index) => run.metadata?.id || run.id || `condition-${index}`;

export const processVisualizationData = (payload) => {
	// Basic information
	const createdAt = Date.now();
	const uniqueSuffix = Math.random().toString(36).substr(2, 9); 
	const runs = toArray(payload.results);

	const primaryRun = runs[0];
	const taskName = primaryRun?.metadata?.task?.name || 'Unknown Task';
	
	const runId = `${createdAt}-${uniqueSuffix}`;

	// Create a unified processed run object strictly
	const processedRuns = runs.map((run, index) => {
		const id = getRunId(run, index);
		const label = getRunLabel(run, index);
		
		// Extract heavy data
		const screenshots = run.history_payload?.screenshots || run.screenshots || [];
		const model_outputs = run.history_payload?.model_outputs || run.model_outputs || [];
		const trajectory = run.trajectory || run.history_payload?.trajectory || null;

		// Create a clean object with only necessary data, avoiding redundant nesting if possible
		// We keep ...run but we might want to strip history_payload if we extracted everything
		const cleanRun = {
			...run,
			id,
			label,
			screenshots,
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
