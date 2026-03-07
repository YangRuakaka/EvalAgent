import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import PropTypes from 'prop-types';
import PanelHeader from '../common/PanelHeader';
import StepTimeline from './StepTimeline';
import EvaluationDetailPanel from './EvaluationDetailPanel';
import CriteriaDetailModal from './CriteriaDetailModal';
import { evaluateStatusMap } from './utils/criteriaInteraction';
import useJudgeReport from '../../hooks/useJudgeReport';
import { useData } from '../../context/DataContext';
import { getCriteriaColorStyles } from '../../utils/colorUtils';
import './ReasoningPanel.css';

/**
 * Convert Base64 screenshot to data URI for img src
 * @param {string} base64Data - Base64 encoded image data
 * @returns {string|null} Data URI or null
 */
const getScreenshotDataUri = (base64Data) => {
	if (!base64Data) return null;
	if (typeof base64Data !== 'string') return null;
	const trimmed = base64Data.trim();
	if (!trimmed) return null;
	
	// If it's already a data URI, return as is
	if (trimmed.startsWith('data:')) {
		return trimmed;
	}

	const normalized = trimmed.replace(/\s+/g, '').replace(/^data:[^,]+,/, '');
	const looksLikeBase64 =
		normalized.length >= 16
		&& normalized.length % 4 === 0
		&& /^[A-Za-z0-9+/=]+$/.test(normalized);

	if (looksLikeBase64) {
		return `data:image/png;base64,${normalized}`;
	}

	// Allow direct URL/path values (for compatibility with older cached logs)
	if (/^(https?:)?\/\//i.test(trimmed)) {
		return trimmed;
	}

	if (/^\/.*\.(png|jpg|jpeg|webp|gif|bmp|svg)(\?.*)?$/i.test(trimmed)) {
		return trimmed;
	}

	// If it looks like file path, do not convert to data URI
	if (/[\\/]/.test(trimmed) || /\.(png|jpg|jpeg|webp)$/i.test(trimmed)) {
		return null;
	}

	return null;
};

/**
 * Helper to normalize action highlight text that might be in Python format
 */
const tryNormalizeActionHighlight = (highlightText, currentAction) => {
	if (!currentAction || !highlightText) return highlightText;
	
	const formattedAction = JSON.stringify(currentAction, null, 2);
	if (highlightText === formattedAction) return highlightText;

	// Helper to check if parsed object matches currentAction or part of it
	const checkMatch = (parsed) => {
		// 1. Check for exact match
		if (JSON.stringify(parsed) === JSON.stringify(currentAction)) {
			return formattedAction;
		}
		
		// 2. If currentAction is array, check if parsed is one of the items
		if (Array.isArray(currentAction)) {
			for (const item of currentAction) {
				if (JSON.stringify(parsed) === JSON.stringify(item)) {
					// Found match in array. Return the item string as it would be represented standalone
					// This matches how we render the individual card JSON in ActionVisualizer
					return JSON.stringify(item, null, 2);
				}
			}
		}
		return null;
	};

	// Try parsing as standard JSON first
	try {
		const parsed = JSON.parse(highlightText);
		const match = checkMatch(parsed);
		if (match) return match;
	} catch (e) {
		// Not valid JSON, continue to Python-like handling
	}

	try {
		// Attempt to convert Python-like string representation to JSON
		// 1. Replace False/True/None
		let jsonStr = highlightText
			.replace(/\bFalse\b/g, 'false')
			.replace(/\bTrue\b/g, 'true')
			.replace(/\bNone\b/g, 'null');
			
		// 2. Replace single quotes with double quotes
		// This is a heuristic and might fail for complex strings containing quotes
		jsonStr = jsonStr.replace(/'/g, '"');
		
		const parsed = JSON.parse(jsonStr);
		
		const match = checkMatch(parsed);
		if (match) return match;
	} catch (e) {
		// Ignore parsing errors
	}
	
	return highlightText;
};

/**
 * Circular progress indicator for confidence score
 */
const ConfidenceCircle = ({ score, color, children, size = 24 }) => {
	const radius = 10;
	const circumference = 2 * Math.PI * radius;
	// Ensure score is between 0 and 1
	const normalizedScore = Math.max(0, Math.min(1, score || 0));
	const strokeDashoffset = circumference - (normalizedScore * circumference);
	
	return (
		<div style={{ position: 'relative', width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
			<svg width={size} height={size} viewBox="0 0 24 24" style={{ transform: 'rotate(-90deg)', position: 'absolute', top: 0, left: 0 }}>
				{/* Background circle */}
				<circle
					cx="12"
					cy="12"
					r={radius}
					fill="none"
					stroke="#e5e7eb"
					strokeWidth="2"
				/>
				{/* Progress circle */}
				<circle
					cx="12"
					cy="12"
					r={radius}
					fill="none"
					stroke={color}
					strokeWidth="2"
					strokeDasharray={circumference}
					strokeDashoffset={strokeDashoffset}
					strokeLinecap="round"
					style={{ transition: 'stroke-dashoffset 0.3s ease' }}
				/>
			</svg>
			<div style={{ position: 'relative', zIndex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', transform: 'scale(0.7)' }}>
				{children}
			</div>
		</div>
	);
};

const ReasoningPanel = ({ 
	data, 
	conditions = [],
	selectedExperimentId = null,
	experimentsMap = {},
	evaluationResponse = null,
	evidenceHighlightEnabled,
	navigationRequest,
	showBackendLogs,
	backendLogs,
	backendRunStatus,
}) => {
	const { state: { criterias } } = useData();
	const [selectedStepIndex, setSelectedStepIndex] = useState(0);
	const [selectedAgentIndex, setSelectedAgentIndex] = useState(0);
	const [showScreenshotModal, setShowScreenshotModal] = useState(false);
	const [showEvaluationPanel, setShowEvaluationPanel] = useState(false);
	const [evaluationFocusType, setEvaluationFocusType] = useState(null); // 'step' or 'cluster'
	const [evaluationFocusIndex, setEvaluationFocusIndex] = useState(null);
	const [evaluatingCriteria, setEvaluatingCriteria] = useState([]);
	const [selectedCriterion, setSelectedCriterion] = useState(null);
	const [hoveredHighlight, setHoveredHighlight] = useState(null);
	const skipNextAgentStepResetRef = useRef(false);
	const lastHandledNavigationNonceRef = useRef(null);

	// Get runId from reasoningDetails (will be computed in memoized value)
	const [runId, setRunId] = useState(null);
	const isEvidenceHighlightEnabled = evidenceHighlightEnabled !== false;
	const normalizedBackendLogs = Array.isArray(backendLogs) ? backendLogs : [];
	const backendStatusLabel = typeof backendRunStatus === 'string' && backendRunStatus.trim()
		? backendRunStatus.trim().toUpperCase()
		: 'RUNNING';
	const backendLogText = normalizedBackendLogs.length > 0
		? normalizedBackendLogs.join('\n')
		: 'Waiting for backend log output...';

	// Get all available agents (value + model + run combinations)
	const agents = useMemo(() => {
		if (!data?.details || data.details.length === 0) {
			return [];
		}

		const normalizedConditions = Array.isArray(conditions) ? conditions : [];
		
		const allAgents = data.details.map((detail, index) => ({
			index,
			id: detail.id,
			model: detail.model || detail.metadata?.model || 'Unknown Model',
			value: detail.value || detail.persona?.value || detail.metadata?.value || 'Unknown Value',
			persona: detail.persona?.content || detail.persona?.value || detail.metadata?.persona || (typeof detail.persona === 'string' ? detail.persona : 'Unknown Persona'),
			run_index: detail.run_index ?? index,
			trajectoryColor: (() => {
				const detailRunIndex = detail.run_index ?? index;
				const detailModel = detail.model || detail.metadata?.model || null;
				const detailValue = detail.value || detail.persona?.value || detail.metadata?.value || null;
				const detailPersona = detail.persona?.content || detail.persona?.value || detail.metadata?.persona || (typeof detail.persona === 'string' ? detail.persona : null);

				const matchedCondition = normalizedConditions.find((condition) => {
					if (!condition) return false;

					if (condition.id && detail.id && condition.id === detail.id) {
						return true;
					}

					if (condition.conditionID && detail.id && condition.conditionID === detail.id) {
						return true;
					}

					const conditionRunIndex = condition.run_index ?? condition.metadata?.run_index;
					const conditionModel = condition.model || condition.metadata?.model || null;
					const conditionValue = condition.value || condition.persona?.value || condition.metadata?.value || (typeof condition.persona === 'string' ? condition.persona : null);
					const conditionPersona = condition.persona?.content || condition.persona?.value || condition.metadata?.persona || (typeof condition.persona === 'string' ? condition.persona : null);

					const runMatches = conditionRunIndex !== undefined
						&& detailRunIndex !== undefined
						&& String(conditionRunIndex) === String(detailRunIndex);
					const modelMatches = conditionModel && detailModel && conditionModel === detailModel;
					const valueMatches = conditionValue && detailValue && conditionValue === detailValue;
					const personaMatches = conditionPersona && detailPersona && conditionPersona === detailPersona;

					return runMatches && modelMatches && (valueMatches || personaMatches);
				});

				return matchedCondition?.trajectoryColor || detail.trajectoryColor || detail.metadata?.trajectoryColor || '#6b7280';
			})(),
			label: detail.label || `Run ${detail.run_index ?? index} - ${detail.model || detail.metadata?.model || 'Unknown Model'} - ${detail.value || detail.persona?.value || detail.metadata?.value || 'Unknown Value'}`,
		}));

		return allAgents;
	}, [data, conditions]);

	const selectedAgent = useMemo(
		() => agents.find((agent) => agent.index === selectedAgentIndex) || null,
		[agents, selectedAgentIndex],
	);

	// Get current condition ID based on selected agent
	const currentConditionId = useMemo(() => {
		if (!agents || agents.length === 0) return null;
		const selectedAgent = agents.find(a => a.index === selectedAgentIndex);
		if (!selectedAgent || !evaluationResponse?.conditions) return null;
		
		const condition = evaluationResponse.conditions.find(c => 
			c.conditionID === selectedAgent.id ||
			(c.run_index === selectedAgent.run_index && 
				c.model === selectedAgent.model && 
				c.persona === selectedAgent.value)
		);
		return condition?.conditionID || null;
	}, [agents, selectedAgentIndex, evaluationResponse]);

	// Ensure selectedAgentIndex is valid for the current agents list
	useEffect(() => {
		if (agents.length > 0) {
			const isSelectedAvailable = agents.some(agent => agent.index === selectedAgentIndex);
			if (!isSelectedAvailable) {
				setSelectedAgentIndex(agents[0].index);
			}
		}
	}, [agents, selectedAgentIndex]);

	useEffect(() => {
		if (!navigationRequest) {
			return;
		}

		if (
			Number.isFinite(navigationRequest.nonce)
			&& lastHandledNavigationNonceRef.current === navigationRequest.nonce
		) {
			return;
		}

		const nextAgentIndex = Number.isFinite(navigationRequest.agentIndex)
			? navigationRequest.agentIndex
			: null;
		const nextStepIndex = Number.isFinite(navigationRequest.stepIndex)
			? navigationRequest.stepIndex
			: null;

		if (nextAgentIndex === null || nextStepIndex === null) {
			return;
		}

		if (Number.isFinite(navigationRequest.nonce)) {
			lastHandledNavigationNonceRef.current = navigationRequest.nonce;
		}

		if (Array.isArray(data?.details) && data.details[nextAgentIndex]) {
			if (nextAgentIndex !== selectedAgentIndex) {
				skipNextAgentStepResetRef.current = true;
				setSelectedAgentIndex(nextAgentIndex);
			}
		}

		const maxStep = Array.isArray(data?.details?.[nextAgentIndex]?.model_outputs)
			? data.details[nextAgentIndex].model_outputs.length - 1
			: null;
		const clampedStepIndex = maxStep !== null
			? Math.max(0, Math.min(nextStepIndex, Math.max(maxStep, 0)))
			: Math.max(0, nextStepIndex);

		setSelectedStepIndex(clampedStepIndex);
		setShowEvaluationPanel(false);
	}, [navigationRequest, data, selectedAgentIndex]);

	// Extract reasoning details based on selected agent
	const reasoningDetails = useMemo(() => {
		if (!data?.details || data.details.length === 0) {
			return null;
		}
		const selected = data.details[selectedAgentIndex];
		
		return selected;
	}, [data, selectedAgentIndex]);

	// Update runId when reasoning details change
	useEffect(() => {
		if (reasoningDetails?.id) {
			setRunId(reasoningDetails.id);
		}
	}, [reasoningDetails?.id]);

	// Parse screenshots and reasoning steps from model outputs
	const steps = useMemo(() => {
		if (!reasoningDetails) {
			return [];
		}

		// Get screenshots from history_payload.screenshots
		const screenshots = reasoningDetails.screenshots || [];
		const modelOutputs = reasoningDetails.model_outputs || [];

		// Build steps array from model_outputs (which contains thinking, next_goal, action, etc.)
		const stepsArray = modelOutputs.map((output, index) => {
			// Create a structured model output with all relevant information
			const modelOutput = {
				thinking: output?.thinking || null,
				next_goal: output?.next_goal || null,
				evaluation_previous_goal: output?.evaluation_previous_goal || null,
				memory: output?.memory || null,
				action: output?.action || null,
			};

			return {
				id: `step-${index}`,
				stepIndex: index,
				screenshot: screenshots[index] || null,
				modelOutput: modelOutput,
			};
		});

		return stepsArray;
	}, [reasoningDetails]);

	// Initialize Judge Report Hook
	const { report, enrichedSteps: hookEnrichedSteps, getStepEvaluationDetails, getClusterEvaluationDetails } = useJudgeReport(runId, steps, evaluationResponse);

	// Create a map of criteria ID/Title to Color from the source of truth (evaluatingCriteria)
	const criteriaColorMap = useMemo(() => {
		const map = {};

		// 1. First populate from global criterias (Source of Truth for colors)
		if (criterias) {
			Object.values(criterias).forEach(c => {
				if (c.color) {
					if (c.id) map[c.id] = c.color;
					if (c.title) map[c.title] = c.color;
				}
			});
		}

		// 2. Then populate from evaluatingCriteria (in case there are experiment-specific overrides or legacy data)
		if (evaluatingCriteria) {
			evaluatingCriteria.forEach(c => {
				// Handle case where c might be just an ID string
				if (typeof c === 'string') return;

				if (c.color) {
					if (c.id) map[c.id] = c.color;
					if (c.title) map[c.title] = c.color;
					if (c.name) map[c.name] = c.color;
					if (c.criterionName) map[c.criterionName] = c.color;
				}
			});
		}
		return map;
	}, [evaluatingCriteria, criterias]);

	// NEW: Process evaluationResponse based on the user's schema
	const processedEvaluationData = useMemo(() => {
		if (!evaluationResponse || !reasoningDetails || !currentConditionId) {
			return null;
		}

		// Find matching condition using currentConditionId
		const conditions = evaluationResponse.conditions || [];
		const currentCondition = conditions.find(c => c.conditionID === currentConditionId);

		if (!currentCondition) return null;

		const stepEvaluations = {};
		const highlights = {};
		const criteriaByStep = {};

		if (currentCondition.criteria) {
			currentCondition.criteria.forEach(criterion => {
				const cTitle = criterion.title || criterion.name || criterion.criterionName;
				const cId = criterion.id;

				const color = criterion.color || 
							  (cId && criteriaColorMap[cId]) || 
							  (cTitle && criteriaColorMap[cTitle]);

				if (criterion.involved_steps) {
					criterion.involved_steps.forEach(involvedStep => {
						const stepIndices = involvedStep.steps || [];
						
						stepIndices.forEach(stepIdx => {
							// 1. Step Evaluations - Contains criterion color info
							if (!stepEvaluations[stepIdx]) stepEvaluations[stepIdx] = [];
							stepEvaluations[stepIdx].push({
								evaluateStatus: involvedStep.evaluateStatus,
								criterion_name: cTitle,
								criterion_id: cId,
								criterion_color: color, // Use found color
								verdict: involvedStep.evaluateStatus, // For compatibility
								confidence_score: involvedStep.confidenceScore,
								reasoning: involvedStep.reasoning
							});

							// 2. Criteria List
							if (!criteriaByStep[stepIdx]) criteriaByStep[stepIdx] = [];
							if (!criteriaByStep[stepIdx].some(c => (c.title || c.name || c.criterionName) === cTitle)) {
								criteriaByStep[stepIdx].push({
									...criterion,
									title: cTitle, // Ensure title exists
									color: color, // Inject color
									evaluateStatus: involvedStep.evaluateStatus,
									reasoning: involvedStep.reasoning,
									confidenceScore: involvedStep.confidenceScore
								});
							}

						// 3. Highlights
						if (involvedStep.highlighted_evidence) {
							if (!highlights[stepIdx]) highlights[stepIdx] = [];
							involvedStep.highlighted_evidence.forEach(ev => {
								if (ev.step_index === stepIdx) {
									highlights[stepIdx].push({
										text: ev.highlighted_text,
										sourceField: ev.source_field,
										verdict: ev.verdict,
										reasoning: ev.reasoning,
										criteriaColor: color
									});
								}
							});
						}
						});
					});
				}
			});
		}

		return { stepEvaluations, highlights, criteriaByStep };
	}, [evaluationResponse, reasoningDetails, currentConditionId, criteriaColorMap]);

	// Merge logic for enrichedSteps
	const enrichedSteps = useMemo(() => {
		if (processedEvaluationData) {
			return steps.map((step, index) => ({
				...step,
				relatedEvaluations: processedEvaluationData.stepEvaluations[index] || []
			}));
		}
		return hookEnrichedSteps;
	}, [processedEvaluationData, steps, hookEnrichedSteps]);
	
	// Handle step click - show evaluation details if available
	const handleStepClick = useCallback((stepIndex) => {
		const evaluations = getStepEvaluationDetails(stepIndex);
		if (evaluations && evaluations.length > 0) {
			setEvaluationFocusType('step');
			setEvaluationFocusIndex(stepIndex);
			setShowEvaluationPanel(true);
		}
	}, [getStepEvaluationDetails]);

	// Handle cluster click - show evaluation details if available
	const handleClusterClick = useCallback((clusterId) => {
		const evaluations = getClusterEvaluationDetails(clusterId);
		if (evaluations && evaluations.length > 0) {
			setEvaluationFocusType('cluster');
			setEvaluationFocusIndex(clusterId);
			setShowEvaluationPanel(true);
		}
	}, [getClusterEvaluationDetails]);

	const handleViewScreenshot = useCallback((stepIndex) => {
		const targetStepIndex = Number.isFinite(stepIndex) ? stepIndex : selectedStepIndex;
		const targetStep = steps[targetStepIndex];

		if (!targetStep?.screenshot) {
			return;
		}

		if (targetStepIndex !== selectedStepIndex) {
			setSelectedStepIndex(targetStepIndex);
		}

		setShowScreenshotModal(true);
	}, [selectedStepIndex, steps]);

	// Reset step index when agent changes
	useEffect(() => {
		if (skipNextAgentStepResetRef.current) {
			skipNextAgentStepResetRef.current = false;
			setShowEvaluationPanel(false);
			setEvaluatingCriteria([]);
			return;
		}

		setSelectedStepIndex(0);
		setShowEvaluationPanel(false);
		setEvaluatingCriteria([]);
	}, [selectedAgentIndex]);

	// When selectedExperimentId changes, get corresponding criteria from experimentsMap
	useEffect(() => {
		if (selectedExperimentId && experimentsMap) {
			const criteria = experimentsMap[selectedExperimentId];
			if (criteria) {
				setEvaluatingCriteria(criteria);
			} else {
				setEvaluatingCriteria([]);
			}
		} else {
			setEvaluatingCriteria([]);
		}
	}, [selectedExperimentId, experimentsMap]);

	// Get current step
	const currentStep = useMemo(() => {
		const step = steps[selectedStepIndex] || null;
		return step;
	}, [steps, selectedStepIndex]);

	// Get current evaluation details based on focus type
	const currentEvaluationDetails = useMemo(() => {
		if (!showEvaluationPanel || !evaluationFocusType) {
			return null;
		}

		if (evaluationFocusType === 'step') {
			return {
				type: 'step',
				step: enrichedSteps[evaluationFocusIndex],
				evaluations: getStepEvaluationDetails(evaluationFocusIndex),
			};
		} else if (evaluationFocusType === 'cluster') {
			const clusters = report?.task_decomposition || [];
			const cluster = clusters.find(c => c.cluster_id === evaluationFocusIndex);
			return {
				type: 'cluster',
				cluster,
				evaluations: getClusterEvaluationDetails(evaluationFocusIndex),
			};
		}

		return null;
	}, [showEvaluationPanel, evaluationFocusType, evaluationFocusIndex, enrichedSteps, report, getStepEvaluationDetails, getClusterEvaluationDetails]);

	// Get current highlights based on enriched steps and criteria colors
	const currentHighlights = useMemo(() => {
		if (!isEvidenceHighlightEnabled) {
			return [];
		}

		const currentAction = enrichedSteps?.[selectedStepIndex]?.modelOutput?.action;

		if (processedEvaluationData) {
			const stepHighlights = processedEvaluationData.highlights[selectedStepIndex] || [];
			return stepHighlights.map(h => {
				const colorInfo = evaluateStatusMap[h.verdict?.toLowerCase()] || evaluateStatusMap['unevaluated'];
				
				let text = h.text;
				if (h.sourceField && h.sourceField.toLowerCase() === 'action') {
					text = tryNormalizeActionHighlight(text, currentAction);
				}

				return {
					text: text,
					color: colorInfo.bg,
					criteriaColor: h.criteriaColor,
					sourceField: h.sourceField,
					reasoning: h.reasoning,
					verdict: h.verdict
				};
			});
		}

		if (!enrichedSteps || !enrichedSteps[selectedStepIndex]) return [];
		const step = enrichedSteps[selectedStepIndex];
		if (!step.relatedEvaluations || step.relatedEvaluations.length === 0) return [];
		
		const highlights = [];
		step.relatedEvaluations.forEach(evalItem => {
			if (evalItem.highlighted_evidence && Array.isArray(evalItem.highlighted_evidence)) {
				const styles = getCriteriaColorStyles(evalItem.criterion_id || evalItem.criterion_name);
				
				evalItem.highlighted_evidence.forEach(evidence => {
					// evidence 可能是对象 {step_index, source_field, highlighted_text, ...} 或字符串
					let text = null;
					let sourceField = null;
					let reasoning = null;
					let verdict = null;
					
					if (typeof evidence === 'object' && evidence !== null) {
						text = evidence.highlighted_text || evidence.text;
						sourceField = evidence.source_field;
						reasoning = evidence.reasoning;
						verdict = evidence.verdict || evalItem.verdict; // Fallback to evalItem verdict
					} else if (typeof evidence === 'string') {
						text = evidence;
						verdict = evalItem.verdict;
					}
					
					if (text) {
						if (sourceField && sourceField.toLowerCase() === 'action') {
							text = tryNormalizeActionHighlight(text, currentAction);
						}

						highlights.push({ 
							text, 
							color: styles.backgroundColor,
							sourceField: sourceField,
							reasoning: reasoning,
							verdict: verdict
						}); 
					}
				});
		}
	});
	
	return highlights;
}, [enrichedSteps, selectedStepIndex, processedEvaluationData, isEvidenceHighlightEnabled]);

	useEffect(() => {
		if (!isEvidenceHighlightEnabled) {
			setHoveredHighlight(null);
		}
	}, [isEvidenceHighlightEnabled]);

	const handleHighlightHover = useCallback((data) => {
		if (!data) {
			setHoveredHighlight(null);
			return;
		}
		const { event, reasoning, verdict } = data;
		const rect = event.target.getBoundingClientRect();
		setHoveredHighlight({
			x: rect.left + rect.width / 2,
			y: rect.top,
			reasoning,
			verdict
		});
	}, []);

	/**
 * Component to render text with highlights
 */
const HighlightText = ({ text, highlights, tagName = 'div', className = '', sourceField = null, markdown = true }) => {
	if (!text) return null;
	
	// Remove <think> tags from start and </think> or </thinking> from end only
	let cleanText = text.replace(/^\s*<think>\s*/i, '');
	cleanText = cleanText.replace(/\s*<\/(?:think|thinking)>\s*$/i, '');
	cleanText = cleanText.trim();

	// Filter highlights to only those matching this sourceField (if specified)
	const relevantHighlights = highlights.filter(h => {
		// If sourceField is specified for the highlight, it must match (case-insensitive)
		if (h.sourceField && sourceField) {
			return h.sourceField.toLowerCase() === sourceField.toLowerCase();
		}
		// If no sourceField specified on highlight, include it for all fields
		return true;
	});
	
	const Tag = tagName;
	
	// Define markdown components to preserve style constraints
	const mdComponents = {
		// Preserve whitespace and font constraints
		p: tagName === 'span' ? 'span' : ({children}) => <p style={{margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word'}}>{children}</p>,
		// Headers mapped to strong to avoid large font changes
		h1: ({children}) => <strong style={{fontSize: 'inherit', display: tagName === 'span' ? 'inline' : 'block'}}>{children}</strong>,
		h2: ({children}) => <strong style={{fontSize: 'inherit', display: tagName === 'span' ? 'inline' : 'block'}}>{children}</strong>,
		h3: ({children}) => <strong style={{fontSize: 'inherit', display: tagName === 'span' ? 'inline' : 'block'}}>{children}</strong>,
		h4: ({children}) => <strong style={{fontSize: 'inherit', display: tagName === 'span' ? 'inline' : 'block'}}>{children}</strong>,
		h5: ({children}) => <strong style={{fontSize: 'inherit', display: tagName === 'span' ? 'inline' : 'block'}}>{children}</strong>,
		h6: ({children}) => <strong style={{fontSize: 'inherit', display: tagName === 'span' ? 'inline' : 'block'}}>{children}</strong>,
		// Ensure links open in new tab if any
		a: ({node, children, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" style={{color: 'inherit', textDecoration: 'underline'}}>{children}</a>
	};

	// Helper to render content (either markdown or plain)
	const renderContent = (content) => {
		if (markdown) {
			return (
				<ReactMarkdown 
					components={mdComponents}
					unwrapDisallowed={tagName === 'span'}
					disallowedElements={tagName === 'span' ? ['p', 'div'] : []}
				>
					{content}
				</ReactMarkdown>
			);
		}
		return content;
	};

	if (!relevantHighlights || relevantHighlights.length === 0) {
		return <Tag className={className}>{renderContent(cleanText)}</Tag>;
	}

	const highlightRanges = [];
	relevantHighlights.forEach((highlight, order) => {
		const phrase = typeof highlight?.text === 'string' ? highlight.text : '';
		if (!phrase) return;

		const escapedPhrase = phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		const regex = new RegExp(escapedPhrase, 'gi');
		let match = regex.exec(cleanText);

		while (match) {
			const matchedText = match[0];
			if (matchedText) {
				highlightRanges.push({
					start: match.index,
					end: match.index + matchedText.length,
					color: highlight.color,
					criteriaColor: highlight.criteriaColor,
					reasoning: highlight.reasoning,
					verdict: highlight.verdict,
					order,
				});
			}

			if (regex.lastIndex === match.index) {
				regex.lastIndex += 1;
			}
			match = regex.exec(cleanText);
		}
	});

	if (highlightRanges.length === 0) {
		return <Tag className={className}>{renderContent(cleanText)}</Tag>;
	}

	const uniqueRanges = [];
	const rangeKeys = new Set();
	highlightRanges.forEach((range) => {
		const key = [
			range.start,
			range.end,
			range.criteriaColor || '',
			range.color || '',
			range.verdict || '',
			range.reasoning || '',
		].join('|');
		if (!rangeKeys.has(key)) {
			rangeKeys.add(key);
			uniqueRanges.push(range);
		}
	});

	const boundaries = new Set([0, cleanText.length]);
	uniqueRanges.forEach((range) => {
		boundaries.add(range.start);
		boundaries.add(range.end);
	});

	const sortedBoundaries = Array.from(boundaries).sort((a, b) => a - b);
	const parts = [];

	for (let i = 0; i < sortedBoundaries.length - 1; i += 1) {
		const start = sortedBoundaries[i];
		const end = sortedBoundaries[i + 1];

		if (start >= end) continue;

		const segmentText = cleanText.slice(start, end);
		const segmentHighlights = uniqueRanges
			.filter((range) => range.start <= start && range.end >= end)
			.sort((a, b) => a.order - b.order);

		if (segmentHighlights.length === 0) {
			parts.push({ text: segmentText, highlight: false });
			continue;
		}

		const seenLayerKeys = new Set();
		const dedupedSegmentHighlights = [];
		segmentHighlights.forEach((segmentHighlight) => {
			const layerKey = [
				segmentHighlight.criteriaColor || segmentHighlight.color || '',
				segmentHighlight.verdict || '',
				segmentHighlight.reasoning || '',
			].join('|');

			if (!seenLayerKeys.has(layerKey)) {
				seenLayerKeys.add(layerKey);
				dedupedSegmentHighlights.push(segmentHighlight);
			}
		});

		parts.push({
			text: segmentText,
			highlight: true,
			highlights: dedupedSegmentHighlights,
		});
	}

	return (
		<Tag className={className}>
			{parts.map((part, i) => (
				part.highlight ? (
					<span key={i} style={{ display: tagName === 'span' ? 'inline' : 'inline-block' }}>
						{part.highlights.reduceRight((child, layer, layerIndex) => {
							const normalizedVerdict = typeof layer.verdict === 'string' ? layer.verdict.toLowerCase() : null;
							const verdictStyle = normalizedVerdict ? evaluateStatusMap[normalizedVerdict] : null;
							const borderColor = layer.criteriaColor || layer.color;
							const isInteractive = Boolean(layer.reasoning);

							return (
								<span
									key={`${i}-${layerIndex}`}
									style={{
										backgroundColor: verdictStyle ? verdictStyle.bg : layer.color,
										border: `1px solid ${borderColor}`,
										padding: '0 2px',
										borderRadius: '2px',
										cursor: isInteractive ? 'help' : 'inherit',
										display: 'inline-block'
									}}
									className={isInteractive ? 'highlight-interactive' : ''}
									onMouseEnter={(e) => {
										if (isInteractive) {
											handleHighlightHover({
												reasoning: layer.reasoning,
												verdict: layer.verdict,
												event: e
											});
										}
									}}
									onMouseLeave={() => {
										if (isInteractive) {
											handleHighlightHover(null);
										}
									}}
								>
									{child}
								</span>
							);
						}, renderContent(part.text))}
					</span>
				) : (
					<span key={i} style={{ display: tagName === 'span' ? 'inline' : undefined }}>
						{renderContent(part.text)}
					</span>
				)
			))}
		</Tag>
	);
};

const ActionVisualizer = ({ action, highlights, onHover }) => {
	const actions = useMemo(() => {
		if (!action) {
			return [];
		}
		return Array.isArray(action) ? action : [action];
	}, [action]);
	const [expandedActionIndexes, setExpandedActionIndexes] = useState({});

	useEffect(() => {
		setExpandedActionIndexes({});
	}, [action]);

	const toggleActionDetails = useCallback((index) => {
		setExpandedActionIndexes((previousState) => ({
			...previousState,
			[index]: !previousState[index],
		}));
	}, []);

	if (actions.length === 0) return null;

	return (
		<div className="action-visualizer">
			{actions.map((act, idx) => {
				const actualAction = act && act.root ? act.root : act;
				const isStructuredAction = Boolean(
					actualAction
					&& typeof actualAction === 'object'
					&& !Array.isArray(actualAction)
					&& Object.keys(actualAction).length > 0
				);
				const type = isStructuredAction
					? Object.keys(actualAction)[0]
					: String(actualAction || 'action');
				const params = isStructuredAction ? actualAction[type] : null;
				const isDone = String(type).toLowerCase() === 'done';
				const isExpanded = Boolean(expandedActionIndexes[idx]);

				const paramEntries = params && typeof params === 'object' && !Array.isArray(params)
					? Object.entries(params)
					: (params !== undefined && params !== null ? [['value', params]] : []);

				const actJson = JSON.stringify(act, null, 2);
				const cardHighlights = (highlights || []).filter(h => 
					h.sourceField && 
					h.sourceField.toLowerCase() === 'action' && 
					h.text === actJson
				);
				const cardHighlight = cardHighlights[0] || null;
				const hoverHighlight = cardHighlights.find(h => h.reasoning) || cardHighlight;

				const extraCardRings = cardHighlights.slice(1).map((highlight, index) => {
					const ringColor = highlight.criteriaColor || highlight.color;
					const ringWidth = (index + 2) * 2;
					return `inset 0 0 0 ${ringWidth}px ${ringColor}`;
				});

				const cardStyle = cardHighlight ? {
					backgroundColor: cardHighlight.verdict && evaluateStatusMap[cardHighlight.verdict.toLowerCase()]
						? evaluateStatusMap[cardHighlight.verdict.toLowerCase()].bg
						: cardHighlight.color,
					border: `1px solid ${cardHighlight.criteriaColor || cardHighlight.color}`,
					...(extraCardRings.length > 0 ? { boxShadow: extraCardRings.join(', ') } : {}),
				} : {};

				return (
					<div 
						key={idx} 
						className={`action-card ${isDone ? 'action-card--done' : ''} ${hoverHighlight ? 'highlight-interactive' : ''}`}
						style={cardStyle}
						onMouseEnter={(e) => {
							if (hoverHighlight && onHover) {
								onHover({
									event: e,
									reasoning: hoverHighlight.reasoning,
									verdict: hoverHighlight.verdict
								});
							}
						}}
						onMouseLeave={() => {
							if (hoverHighlight && onHover) {
								onHover(null);
							}
						}}
					>
						<div className="action-card-header">
							<div className="action-type-badge">{type}</div>
							<button
								type="button"
								className={`action-expand-button ${isExpanded ? 'action-expand-button--expanded' : ''}`}
								aria-label={`${isExpanded ? 'Collapse' : 'Expand'} details for action ${idx + 1}`}
								aria-expanded={isExpanded}
								onClick={(event) => {
									event.stopPropagation();
									toggleActionDetails(idx);
								}}
							>
								▸
							</button>
						</div>

						<div className={`action-details ${isExpanded ? 'action-details--expanded' : ''}`} aria-hidden={!isExpanded}>
							<div className="action-details-inner">
								<div className="action-params-grid">
									{paramEntries.length > 0 ? paramEntries.map(([key, value]) => {
										const isBlockParam = isDone && key === 'text';

										let content = (
											<HighlightText 
												text={typeof value === 'object' ? JSON.stringify(value) : String(value)} 
												highlights={highlights} 
												tagName={isBlockParam ? 'div' : 'span'}
												sourceField="Action" 
												markdown={isBlockParam}
											/>
										);

										if (key === 'url' && typeof value === 'string' && (value.startsWith('http') || value.startsWith('www'))) {
											content = (
												<a 
													href={value} 
													target="_blank" 
													rel="noopener noreferrer" 
													style={{ color: '#2563eb', textDecoration: 'underline' }}
													onClick={(event) => event.stopPropagation()}
												>
													{content}
												</a>
											);
										}

										if (isDone && key === 'success') {
											const isSuccess = String(value).toLowerCase() === 'true';
											content = (
												<span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
													{content}
													{isSuccess 
														? <span style={{ color: '#10b981', fontWeight: 'bold' }}>✓</span> 
														: <span style={{ color: '#ef4444', fontWeight: 'bold' }}>✕</span>
													}
												</span>
											);
										}

										return (
											<div key={key} className={`action-param-item ${isBlockParam ? 'action-param-item--block' : ''}`}>
												<span className="action-param-label">{key}:</span>
												<span className="action-param-value">
													{content}
												</span>
											</div>
										);
									}) : (
										<p className="reasoning-info-empty">No action details available</p>
									)}
								</div>
							</div>
						</div>
					</div>
				);
			})}
		</div>
	);
};

	const displayCriteria = useMemo(() => {
		if (processedEvaluationData) {
			return processedEvaluationData.criteriaByStep[selectedStepIndex] || [];
		}
		// Fallback: use evaluatingCriteria but enrich with colors from map
		if (evaluatingCriteria) {
			return evaluatingCriteria.map(c => {
				// If c is just an ID string
				if (typeof c === 'string') {
					if (criterias && criterias[c]) {
						return criterias[c];
					}
					return { id: c, title: c, color: criteriaColorMap[c] };
				}
				
				return {
					...c,
					color: c.color || criteriaColorMap[c.id] || criteriaColorMap[c.title] || criteriaColorMap[c.name]
				};
			});
		}
		return [];
	}, [processedEvaluationData, selectedStepIndex, evaluatingCriteria, criteriaColorMap, criterias]);

	const hasHighlightsForField = useCallback((fieldName) => {
		if (!Array.isArray(currentHighlights) || currentHighlights.length === 0) {
			return false;
		}

		const normalizedFieldName = String(fieldName || '').toLowerCase();

		return currentHighlights.some((highlight) => {
			const sourceField = typeof highlight?.sourceField === 'string'
				? highlight.sourceField.toLowerCase()
				: null;

			if (!sourceField) {
				return true;
			}

			return sourceField === normalizedFieldName;
		});
	}, [currentHighlights]);

	const currentActions = currentStep?.modelOutput?.action;
	const hasActionContent = Array.isArray(currentActions)
		? currentActions.length > 0
		: Boolean(currentActions);

	if (showBackendLogs) {
		return (
			<div className="reasoning-panel">
				<PanelHeader title="Reasoning" variant="panel">
					<span className="reasoning-log-status" aria-label="Backend run status">{backendStatusLabel}</span>
				</PanelHeader>
				<div className="reasoning-panel__body reasoning-panel__body--logs">
					<div className="reasoning-log-viewer" role="status" aria-live="polite">
						<p className="reasoning-log-viewer__hint">Displaying backend logs while browser agent run is in progress.</p>
						<pre className="reasoning-log-viewer__content">{backendLogText}</pre>
					</div>
				</div>
			</div>
		);
	}

	if (!reasoningDetails) {
		return (
			<div className="reasoning-panel">
				<PanelHeader title="Reasoning" variant="panel" />
				<div className="reasoning-panel__body reasoning-panel__body--empty">
					<p>No reasoning data available</p>
				</div>
			</div>
		);
	}

	return (
		<div className="reasoning-panel">
			<PanelHeader title="Reasoning" variant="panel">
				{/* Agent Selector in Header */}
				{agents.length >= 1 && (
					<div
						className="reasoning-agent-selector-compact"
						style={{ '--agent-color': selectedAgent?.trajectoryColor || '#6b7280' }}
					>
						<span className="reasoning-agent-selector-label">Agent:</span>
						<div className="reasoning-agent-select-wrapper">
							<select
								className="reasoning-agent-select-compact"
								value={selectedAgentIndex}
								onChange={(e) => setSelectedAgentIndex(parseInt(e.target.value, 10))}
								title="Select agent to view reasoning process"
							>
								{agents.map((agent) => {
									const displayLabel = `${agent.value} - ${agent.model} - Run ${agent.run_index}`;
									return (
										<option key={agent.index} value={agent.index} style={{ color: agent.trajectoryColor }}>
											{displayLabel}
										</option>
									);
								})}
							</select>
						</div>
					</div>
				)}
			</PanelHeader>
			<div className="reasoning-panel__body">

				{/* Main content area: Step Info + Criteria on right */}
				<section className="reasoning-content">
					<div className="reasoning-info-section">

						<div className="reasoning-info-content">
							<div className="reasoning-info-column reasoning-info-column--thinking">
								<div className="reasoning-info-block reasoning-info-block--fill">
									<h4 className="reasoning-info-label">Thinking Process</h4>
									<div className={`reasoning-info-text${hasHighlightsForField('Thinking Process') ? ' reasoning-info-text--has-highlight' : ''}`}>
										{currentStep?.modelOutput?.thinking ? (
											<HighlightText text={currentStep.modelOutput.thinking} highlights={currentHighlights} sourceField="Thinking Process" />
										) : (
											<p className="reasoning-info-empty">No thinking process recorded</p>
										)}
									</div>
								</div>
							</div>

							<div className="reasoning-info-column reasoning-info-column--details">
								{currentStep?.modelOutput?.evaluation_previous_goal && (
									<div className="reasoning-info-block">
										<h4 className="reasoning-info-label">Pre-step Evaluation</h4>
										<div className={`reasoning-info-text${hasHighlightsForField('Evaluation') ? ' reasoning-info-text--has-highlight' : ''}`}>
											<HighlightText text={currentStep.modelOutput.evaluation_previous_goal} highlights={currentHighlights} sourceField="Evaluation" />
										</div>
									</div>
								)}

								{currentStep?.modelOutput?.memory && (
									<div className="reasoning-info-block">
										<h4 className="reasoning-info-label">Memory</h4>
										<div className={`reasoning-info-text${hasHighlightsForField('Memory') ? ' reasoning-info-text--has-highlight' : ''}`}>
											<HighlightText text={currentStep.modelOutput.memory} highlights={currentHighlights} sourceField="Memory" />
										</div>
									</div>
								)}

								<div className="reasoning-info-block">
									<h4 className="reasoning-info-label">Next Goal</h4>
									<div className={`reasoning-info-text${hasHighlightsForField('Next Goal') ? ' reasoning-info-text--has-highlight' : ''}`}>
										{currentStep?.modelOutput?.next_goal ? (
											<HighlightText text={currentStep.modelOutput.next_goal} highlights={currentHighlights} sourceField="Next Goal" />
										) : (
											<p className="reasoning-info-empty">No next goal available</p>
										)}
									</div>
								</div>

								{hasActionContent && (
									<div className="reasoning-info-block">
										<h4 className="reasoning-info-label">Action</h4>
										<div className={`reasoning-info-text${hasHighlightsForField('Action') ? ' reasoning-info-text--has-highlight' : ''}`}>
											<ActionVisualizer 
												action={currentActions} 
												highlights={currentHighlights}
												onHover={handleHighlightHover}
											/>
										</div>
									</div>
								)}
							</div>
						</div>
					</div>

					{/* Criteria section - Right side of reasoning-content */}
					<div className="reasoning-criteria-section">
						<div className="reasoning-criteria-header">
							<h3 className="reasoning-criteria-title">
								{displayCriteria.length > 0 
									? `Criteria (${displayCriteria.length})`
									: 'Criteria'
								}
							</h3>
						</div>
						{displayCriteria.length > 0 ? (
							<div className="reasoning-criteria-list">
								{displayCriteria.map((criterion, index) => {
									const criterionKey = criterion.id || criterion.title || criterion.criterionName || criterion.name || `criterion-${index}`;
									const selectedCriterionKey = selectedCriterion?.id || selectedCriterion?.title || selectedCriterion?.criterionName || selectedCriterion?.name;
									const isSelectedCriterion = Boolean(selectedCriterionKey && selectedCriterionKey === criterionKey);
									// Get evaluate status of criterion, default to 'unevaluated'
									const evaluateStatus = criterion.evaluateStatus || 'unevaluated';
									const statusConfig = evaluateStatusMap[evaluateStatus.toLowerCase()] || evaluateStatusMap['unevaluated'];
									
									// Prioritize criterion's own color attribute (defined color), otherwise generate color
									let criteriaBackgroundColor = criterion.color;
									let criteriaTextColor = '#1f2937';
									
									if (!criteriaBackgroundColor) {
										const criteriaId = criterion.id || criterion.title || criterion.name;
										const generatedColors = getCriteriaColorStyles(criteriaId);
										criteriaBackgroundColor = generatedColors.backgroundColor;
										criteriaTextColor = generatedColors.color;
									} else {
										// If color attribute exists, calculate corresponding text color (simple handling: use dark text)
										criteriaTextColor = '#1f2937';
									}
									
									let cardStyle = {};
									let titleColor = criteriaTextColor;
									let verdictIconColor = 'inherit';

									if (evaluateStatus !== 'unevaluated') {
										// When evaluation result exists: background uses verdict color (statusConfig.bg), border uses criteria color
										cardStyle = {
											borderLeftColor: criteriaBackgroundColor,
											backgroundColor: statusConfig.bg,
											border: `1px solid ${criteriaBackgroundColor}`,
											borderLeftWidth: '4px'
										};
										titleColor = criteriaTextColor;
										verdictIconColor = statusConfig.text;
									} else {
										// When no evaluation result: use only criteria color
										cardStyle = {
											borderLeftColor: '#ccc',
											backgroundColor: criteriaBackgroundColor,
										};
										titleColor = criteriaTextColor;
									}
									
									return (
										<div 
											key={criterionKey}
											className={`reasoning-criteria-card${isSelectedCriterion ? ' reasoning-criteria-card--active' : ''}`}
											onClick={() => setSelectedCriterion(criterion)}
											style={{
												...cardStyle,
												cursor: 'pointer',
												borderLeftStyle: 'solid',
												// If cardStyle doesn't have borderLeftWidth, need to add it here, but it's already added above
												borderLeftWidth: cardStyle.borderLeftWidth || '4px',
											}}
										>
											<div className="reasoning-criteria-content">
												<div className="reasoning-criteria-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
													<div 
														className="reasoning-criteria-name"
														style={{ color: titleColor, fontWeight: '600' }}
													>
														{criterion.title || criterion.criterionName || criterion.name || 'Unnamed Criterion'}
													</div>
													{evaluateStatus !== 'unevaluated' && (
														<div title={`${statusConfig.label} (Confidence: ${Math.round((criterion.confidenceScore || 0) * 100)}%)`}>
															<ConfidenceCircle 
																score={criterion.confidenceScore} 
																color={verdictIconColor}
																size={24}
															>
																<span 
																	style={{ 
																		color: verdictIconColor, 
																		fontSize: '1.1em',
																		fontWeight: 'bold',
																		lineHeight: 1,
																		display: 'flex'
																	}}
																>
																	{statusConfig.icon}
																</span>
															</ConfidenceCircle>
														</div>
													)}
												</div>
												{criterion.description && (
													<div className="reasoning-criteria-description">{criterion.description}</div>
												)}
											</div>
										</div>
									);
								})}
							</div>
						) : (
							<div className="reasoning-criteria-empty">
								<p className="reasoning-criteria-placeholder">No criteria added yet</p>
							</div>
						)}
					</div>
				</section>

				{/* Timeline section */}
				<div className="reasoning-timeline-section">
                    <StepTimeline
                        steps={steps}
                        enrichedSteps={enrichedSteps}
                        report={report}
						showEvidenceHighlights={isEvidenceHighlightEnabled}
                        selectedStepIndex={selectedStepIndex}
                        onSelectStep={setSelectedStepIndex}
                        onStepClick={handleStepClick}
						onViewScreenshot={handleViewScreenshot}
                        onClusterClick={handleClusterClick}
                        conditionId={currentConditionId}
                    />
				</div>
			</div>

			{/* Evaluation Detail Panel */}
			{showEvaluationPanel && currentEvaluationDetails && (
				<EvaluationDetailPanel
					step={currentEvaluationDetails.type === 'step' ? currentEvaluationDetails.step : null}
					cluster={currentEvaluationDetails.type === 'cluster' ? currentEvaluationDetails.cluster : null}
					evaluations={currentEvaluationDetails.evaluations || []}
					onClose={() => setShowEvaluationPanel(false)}
				/>
			)}

			{/* Screenshot Modal */}
			{showScreenshotModal && currentStep?.screenshot && (
				<div className="screenshot-modal-overlay" onClick={() => setShowScreenshotModal(false)}>
					<div className="screenshot-modal-content" onClick={(e) => e.stopPropagation()}>
						<div className="screenshot-modal-header">
							<h2 className="screenshot-modal-title">Step {currentStep.stepIndex} Screenshot</h2>
							<button
								className="screenshot-modal-close"
								onClick={() => setShowScreenshotModal(false)}
								title="Close"
							>
								✕
							</button>
						</div>
						<div className="screenshot-modal-body">
							<img
								src={getScreenshotDataUri(currentStep.screenshot)}
								alt={`Step ${currentStep.stepIndex} screenshot`}
								className="screenshot-modal-image"
							/>
						</div>
					</div>
				</div>
			)}

			{/* Criteria Detail Modal */}
			{selectedCriterion && (
				<CriteriaDetailModal
					criterion={selectedCriterion}
					onClose={() => setSelectedCriterion(null)}
				/>
			)}

			{/* Reasoning Tooltip */}
			{hoveredHighlight && (
				<div 
					className="reasoning-tooltip"
					style={{
						left: hoveredHighlight.x,
						top: hoveredHighlight.y
					}}
				>
					<div className="reasoning-tooltip-header">
						<span className={`reasoning-tooltip-verdict ${hoveredHighlight.verdict ? hoveredHighlight.verdict.toLowerCase() : 'unknown'}`}>
							{hoveredHighlight.verdict || 'Unknown'}
						</span>
					</div>
					<div className="reasoning-tooltip-content">
						{hoveredHighlight.reasoning}
					</div>
				</div>
			)}
		</div>
	);
};

ReasoningPanel.propTypes = {
	data: PropTypes.shape({
		details: PropTypes.arrayOf(
			PropTypes.shape({
				id: PropTypes.string,
				model: PropTypes.string,
				persona: PropTypes.object,
				screenshots: PropTypes.array,
				thinking_process: PropTypes.array,
				model_outputs: PropTypes.array,
				metadata: PropTypes.object,
			})
		),
	}),
	conditions: PropTypes.arrayOf(PropTypes.object),
	selectedExperimentId: PropTypes.string,
	experimentsMap: PropTypes.object,
	evaluationResponse: PropTypes.object, // New: evaluation response
	evidenceHighlightEnabled: PropTypes.bool,
	navigationRequest: PropTypes.shape({
		agentIndex: PropTypes.number,
		stepIndex: PropTypes.number,
		nonce: PropTypes.number,
	}),
	showBackendLogs: PropTypes.bool,
	backendLogs: PropTypes.arrayOf(PropTypes.string),
	backendRunStatus: PropTypes.string,
};

ReasoningPanel.defaultProps = {
	data: null,
	conditions: [],
	selectedExperimentId: null,
	experimentsMap: {},
	evaluationResponse: null, // New default value
	evidenceHighlightEnabled: undefined,
	navigationRequest: null,
	showBackendLogs: false,
	backendLogs: [],
	backendRunStatus: null,
};

export default ReasoningPanel;
