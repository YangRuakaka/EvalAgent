import React, { useState, useMemo, useEffect, useCallback } from 'react';
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
	
	// If it's already a data URI, return as is
	if (base64Data.startsWith('data:')) {
		return base64Data;
	}
	
	// Otherwise, assume it's PNG base64 and convert to data URI
	return `data:image/png;base64,${base64Data}`;
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
	selectedExperimentId = null,
	experimentsMap = {},
	evaluationResponse = null,
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

	// Get runId from reasoningDetails (will be computed in memoized value)
	const [runId, setRunId] = useState(null);

	// Get all available agents (model + persona combinations)
	const agents = useMemo(() => {
		if (!data?.details || data.details.length === 0) {
			return [];
		}
		
		const allAgents = data.details.map((detail, index) => ({
			index,
			id: detail.id,
			model: detail.model,
			value: detail.value || detail.persona?.value || detail.metadata?.value || 'Unknown Value',
			run_index: detail.run_index || index,
			label: detail.label || `Run ${detail.run_index || index} - ${detail.model} - ${detail.value || detail.persona?.value || detail.metadata?.value || 'Unknown'}`,
		}));

		return allAgents;
	}, [data]);

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

	// Reset step index when agent changes
	useEffect(() => {
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
}, [enrichedSteps, selectedStepIndex, processedEvaluationData]);	const handleHighlightHover = useCallback((data) => {
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

	let parts = [{ text: cleanText, highlight: false }];

	relevantHighlights.forEach(h => {
		const phrase = h.text;
		const color = h.color;
		const criteriaColor = h.criteriaColor;
		const reasoning = h.reasoning;
		const verdict = h.verdict;

		if (!phrase) return;

		const newParts = [];
		parts.forEach(part => {
			if (part.highlight) {
				newParts.push(part);
			} else {
				// Escape special regex characters in phrase
				const escapedPhrase = phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
				const regex = new RegExp(`(${escapedPhrase})`, 'gi');
				const split = part.text.split(regex);
				
				split.forEach(segment => {
				if (segment.toLowerCase() === phrase.toLowerCase()) {
					newParts.push({ text: segment, highlight: true, color: color, criteriaColor: criteriaColor, reasoning: reasoning, verdict: verdict });
				} else if (segment) {
					newParts.push({ text: segment, highlight: false });
				}
				});
			}
		});
		parts = newParts;
	});

	return (
		<Tag className={className}>
			{parts.map((part, i) => (
				part.highlight ? (
					<span 
						key={i} 
						style={{ 
							backgroundColor: part.verdict && evaluateStatusMap[part.verdict.toLowerCase()] 
								? evaluateStatusMap[part.verdict.toLowerCase()].bg 
								: part.color,
							border: `1px solid ${part.criteriaColor || part.color}`,
							padding: '0 2px', 
							borderRadius: '2px', 
							cursor: part.reasoning ? 'help' : 'inherit',
							display: 'inline-block' // Ensure transforms/box-model work well
						}}
						className={part.reasoning ? "highlight-interactive" : ""}
						onMouseEnter={(e) => {
							if (part.reasoning) {
								handleHighlightHover({
									reasoning: part.reasoning,
									verdict: part.verdict,
									event: e
								});
							}
						}}
						onMouseLeave={() => {
							if (part.reasoning) {
								handleHighlightHover(null);
							}
						}}
					>
						{renderContent(part.text)}
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
    if (!action) return null;
    const actions = Array.isArray(action) ? action : [action];

    return (
        <div className="action-visualizer">
            {actions.map((act, idx) => {
                // If action is wrapped in a "root" property, extract it
                const actualAction = act.root ? act.root : act;
                const type = Object.keys(actualAction)[0];
                const params = actualAction[type];
                const isDone = type === 'done';

                // Check for card-level highlight
                // We compare the formatted JSON of the action item with highlight text
                const actJson = JSON.stringify(act, null, 2);
                const cardHighlight = highlights?.find(h => 
                    h.sourceField && 
                    h.sourceField.toLowerCase() === 'action' && 
                    h.text === actJson
                );

                const cardStyle = cardHighlight ? {
                    borderColor: cardHighlight.criteriaColor || cardHighlight.color,
                    boxShadow: `0 0 0 2px ${cardHighlight.color}1A`, // Subtle glow
                    backgroundColor: `${cardHighlight.color}0D`, // Very light tint (approx 5% opacity)
                    borderLeft: `4px solid ${cardHighlight.criteriaColor || cardHighlight.color}`, // Consistent with criteria cards
                } : {};

                return (
                    <div 
                        key={idx} 
                        className={`action-card ${isDone ? 'action-card--done' : ''} ${cardHighlight ? 'highlight-interactive' : ''}`}
                        style={cardStyle}
                        onMouseEnter={(e) => {
                            if (cardHighlight && onHover) {
                                onHover({
                                    event: e,
                                    reasoning: cardHighlight.reasoning,
                                    verdict: cardHighlight.verdict
                                });
                            }
                        }}
                        onMouseLeave={() => {
                            if (cardHighlight && onHover) {
                                onHover(null);
                            }
                        }}
                    >
                        <div className="action-type-badge">{type}</div>
                        <div className="action-params-grid">
                            {Object.entries(params).map(([key, value]) => {
                                // For 'done' action, display 'text' in a block layout
                                const isBlockParam = isDone && key === 'text';
                                
                                let content = (
                                    <HighlightText 
                                        text={typeof value === 'object' ? JSON.stringify(value) : String(value)} 
                                        highlights={highlights} 
                                        tagName={isBlockParam ? "div" : "span"}
                                        sourceField="Action" 
                                        markdown={isBlockParam}
                                    />
                                );

                                // Special handling for URL -> clickable link
                                if (key === 'url' && typeof value === 'string' && (value.startsWith('http') || value.startsWith('www'))) {
                                    content = (
                                        <a 
                                            href={value} 
                                            target="_blank" 
                                            rel="noopener noreferrer" 
                                            style={{ color: '#2563eb', textDecoration: 'underline' }}
                                            onClick={(e) => e.stopPropagation()}
                                        >
                                            {content}
                                        </a>
                                    );
                                }

                                // Special handling for done.success -> add check/cross icon
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
                            })}
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
					<div className="reasoning-agent-selector-compact">
						<select
							className="reasoning-agent-select-compact"
							value={selectedAgentIndex}
							onChange={(e) => setSelectedAgentIndex(parseInt(e.target.value, 10))}
							title="Select agent to view reasoning process"
						>
						{agents.map((agent) => {
							const displayLabel = `Run ${agent.run_index} - ${agent.model} - ${agent.value}`;
							return (
								<option key={agent.index} value={agent.index}>
									{displayLabel}
								</option>
							);
						})}
						</select>
					</div>
				)}
                <button
                    className="reasoning-screenshot-btn"
                    onClick={() => setShowScreenshotModal(true)}
                    title="View screenshot"
                >
                    📷 View Screenshot
                </button>
			</PanelHeader>
			<div className="reasoning-panel__body">

				{/* Main content area: Step Info + Criteria on right */}
				<section className="reasoning-content">
					<div className="reasoning-info-section">

						<div className="reasoning-info-content">
						{/* Thinking Process - Middle column, spans both rows */}
						<div className="reasoning-info-block" data-position="middle">
							<h4 className="reasoning-info-label">Thinking Process</h4>
							<div className="reasoning-info-text">
								{currentStep?.modelOutput?.thinking ? (
									<HighlightText text={currentStep.modelOutput.thinking} highlights={currentHighlights} sourceField="Thinking Process" />
								) : (
									<p className="reasoning-info-empty">No thinking process recorded</p>
								)}
							</div>
						</div>							{/* Next Goal - Right column, top */}
							<div className="reasoning-info-block" data-position="right-top">
								<h4 className="reasoning-info-label">Next Goal</h4>
								<div className="reasoning-info-text">
									{currentStep?.modelOutput?.next_goal ? (
										<HighlightText text={currentStep.modelOutput.next_goal} highlights={currentHighlights} sourceField="Next Goal" />
									) : (
										<p className="reasoning-info-empty">No next goal available</p>
									)}
								</div>
							</div>

							{/* Evaluation of Previous Goal - Left column, top */}
							{currentStep?.modelOutput?.evaluation_previous_goal && (
								<div className="reasoning-info-block" data-position="left-top">
									<h4 className="reasoning-info-label">Evaluation</h4>
									<div className="reasoning-info-text">
										<HighlightText text={currentStep.modelOutput.evaluation_previous_goal} highlights={currentHighlights} sourceField="Evaluation" />
									</div>
								</div>
							)}

							{/* Memory - Left column, bottom */}
							{currentStep?.modelOutput?.memory && (
								<div className="reasoning-info-block" data-position="left-bottom">
									<h4 className="reasoning-info-label">Memory</h4>
									<div className="reasoning-info-text">
										<HighlightText text={currentStep.modelOutput.memory} highlights={currentHighlights} sourceField="Memory" />
									</div>
								</div>
							)}

							{/* Actions - Right column, bottom */}
							{currentStep?.modelOutput?.action && currentStep.modelOutput.action.length > 0 && (
								<div className="reasoning-info-block" data-position="right-bottom">
									<h4 className="reasoning-info-label">Action</h4>
									<div className="reasoning-info-text">
										<ActionVisualizer 
											action={currentStep.modelOutput.action} 
											highlights={currentHighlights}
											onHover={handleHighlightHover}
										/>
									</div>
								</div>
							)}
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
											key={index} 
											className="reasoning-criteria-card reasoning-criteria-card--active"
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
                        selectedStepIndex={selectedStepIndex}
                        onSelectStep={setSelectedStepIndex}
                        onStepClick={handleStepClick}
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
	selectedExperimentId: PropTypes.string,
	experimentsMap: PropTypes.object,
	evaluationResponse: PropTypes.object, // New: evaluation response
};

ReasoningPanel.defaultProps = {
	data: null,
	selectedExperimentId: null,
	experimentsMap: {},
	evaluationResponse: null, // New default value
};

export default ReasoningPanel;
