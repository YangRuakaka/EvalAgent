import React, { useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';

import PanelHeader from '../common/PanelHeader';
import {
	generatePersona,
	generatePersonaVariation,
	runBrowserAgent,
	stopBrowserAgentRun,
	streamBrowserAgentEvents,
} from '../../services/api';
import EnvironmentSetting from '../configuration/EnvironmentSetting';
import PersonaConfiguration from '../configuration/PersonaConfiguration';

import './ConfigurationView.css';

const EMPTY_FORM = {
	name: '',
	age: '',
	job: '',
	location: '',
	education: '',
	interests: '',
};

const VALUE_VARIATION_OPTIONS = [
	{ value: 'accuracy', label: 'Accuracy', color: '#dbeafe', textColor: '#1d4ed8' },
	{ value: 'empathy', label: 'Empathy', color: '#fce7f3', textColor: '#be185d' },
	{ value: 'efficiency', label: 'Efficiency', color: '#ccfbf1', textColor: '#0f766e' },
	{ value: 'risk_aversion', label: 'Risk Aversion', color: '#ffedd5', textColor: '#c2410c' },
	{ value: 'creativity', label: 'Creativity', color: '#ede9fe', textColor: '#6d28d9' },
	{ value: 'frugal', label: 'Frugality', color: '#fef3c7', textColor: '#b45309' },
	{ value: 'health conscious', label: 'Health Conscious', color: '#e0e7ff', textColor: '#4338ca' },
];

const ENVIRONMENT_TARGET_BASE_URL = 'http://localhost:3000';

// eslint-disable-next-line no-unused-vars
const createEnvironmentTargetOption = (path, label) => ({
	value: `${ENVIRONMENT_TARGET_BASE_URL}${path}`,
	label,
	path,
});

const ENVIRONMENT_MODEL_OPTIONS = [
	{ value: 'deepseek-chat', label: 'DeepSeek Chat' },
	{ value: 'gpt-4o', label: 'OpenAI GPT-4o' },
	{ value: 'claude-3-5-sonnet-20240620', label: 'Anthropic Claude 3.5 Sonnet' },
	{ value: 'gemini-1.5-pro', label: 'Google Gemini 1.5 Pro' },
];

const getPersonaBaseName = (content) => {
	if (!content) {
		return 'Persona';
	}

	const trimmed = content.trim();
	if (!trimmed) {
		return 'Persona';
	}

	const [firstWord] = trimmed.split(/\s+/);
	return firstWord || 'Persona';
};

const assignPersonaNames = (personas) => {
	const counts = {};

	return personas.map((persona) => {
		const baseName = getPersonaBaseName(persona.content);
		const nextCount = (counts[baseName] || 0) + 1;
		counts[baseName] = nextCount;
		const suffix = nextCount === 1 ? '' : String(nextCount - 1).padStart(2, '0');

		return { ...persona, name: `${baseName}${suffix}` };
	});
};

const createDefaultVariationContent = (_personaContent, _valueLabel) => '';

const VALUE_TAG_OPEN_TOKEN = '__VALUE_TAG_OPEN__';
const VALUE_TAG_CLOSE_TOKEN = '__VALUE_TAG_CLOSE__';

const orderVariationEntries = (variationMap) =>
	VALUE_VARIATION_OPTIONS.map((option) => variationMap.get(option.value)).filter(Boolean);

const escapeHtml = (value) => {
	if (value === null || value === undefined) {
		return '';
	}
	return String(value)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;');
};

const formatVariationContent = (content, highlightColor) => {
	const safeColor = highlightColor || '#111111';
	const raw = String(content ?? '');
	// Handle both uppercase and lowercase VALUE tags for robustness
	const withTokens = raw
		.split('<VALUE>').join(VALUE_TAG_OPEN_TOKEN)
		.split('</VALUE>').join(VALUE_TAG_CLOSE_TOKEN)
		.split('<value>').join(VALUE_TAG_OPEN_TOKEN)
		.split('</value>').join(VALUE_TAG_CLOSE_TOKEN);
	const escaped = escapeHtml(withTokens);
	return escaped
		.split(VALUE_TAG_OPEN_TOKEN)
		.join(`<span style="color: ${safeColor}; font-weight: 600;">`)
		.split(VALUE_TAG_CLOSE_TOKEN)
		.join('</span>');
};

const createBrowserAgentRunId = () => {
	if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
		return crypto.randomUUID();
	}
	return `run_${Date.now()}_${Math.random().toString(16).slice(2)}`;
};

const ConfigurationView = ({
	onAddRun,
	activeTab: externalActiveTab,
	onTabChange: externalOnTabChange,
	onGetCacheData,
	isCacheLoading,
	onEnvironmentRunStateChange,
}) => {
	const [activeTab, setActiveTab] = useState('persona'); // 'persona' | 'environment'
	// setActiveTab is reserved for future internal tab switching if external control is not provided
	
	// Use external tab state if provided, otherwise use internal state
	const currentActiveTab = externalActiveTab !== undefined ? externalActiveTab : activeTab;
	const switchConfigTab = (nextTab) => {
		if (typeof externalOnTabChange === 'function') {
			externalOnTabChange(nextTab);
			return;
		}
		setActiveTab(nextTab);
	};
	const [isGeneratingVariation, setIsGeneratingVariation] = useState(false);
	const [hasCompletedVariationGeneration, setHasCompletedVariationGeneration] = useState(false);
	const [formData, setFormData] = useState(EMPTY_FORM);
	const [personaModel, setPersonaModel] = useState(ENVIRONMENT_MODEL_OPTIONS[1].value);
	const [errors, setErrors] = useState({});
	const [isGenerating, setIsGenerating] = useState(false);
	const [personaResult, setPersonaResult] = useState(null);
	const [isEditing, setIsEditing] = useState(false);
	const [editValue, setEditValue] = useState('');
	const [showSavedToast, setShowSavedToast] = useState(false);
	const [personaGallery, setPersonaGallery] = useState([]);
	const [selectedPersonaId, setSelectedPersonaId] = useState('');
	const [variationStateByPersona, setVariationStateByPersona] = useState({});
	const [editingVariationId, setEditingVariationId] = useState(null);
	const [variationEditValue, setVariationEditValue] = useState('');
	const [isValueDropdownOpen, setIsValueDropdownOpen] = useState(false);
	const [variationError, setVariationError] = useState('');
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
	const [regeneratingVariationKey, setRegeneratingVariationKey] = useState(null);
	const dropdownRef = useRef(null);
	const environmentWaitTimerRef = useRef(null);
	const activeEnvironmentRunIdRef = useRef(null);
	const activeEnvironmentAbortRef = useRef(null);

	const emitEnvironmentRunState = (payload) => {
		if (typeof onEnvironmentRunStateChange !== 'function' || !payload || typeof payload !== 'object') {
			return;
		}
		onEnvironmentRunStateChange(payload);
	};

	const selectedPersona = useMemo(
		() => personaGallery.find((persona) => persona.id === selectedPersonaId) || null,
		[personaGallery, selectedPersonaId],
	);

	const currentVariationState = useMemo(() => {
		if (!selectedPersonaId) {
			return { selectedValues: [], variations: [] };
		}
		return (
			variationStateByPersona[selectedPersonaId] || { selectedValues: [], variations: [] }
		);
	}, [selectedPersonaId, variationStateByPersona]);

	const selectedVariationValues = currentVariationState.selectedValues;
	const personaVariations = currentVariationState.variations;

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

	const setCurrentPersonaVariationState = (updater) => {
		if (!selectedPersonaId) {
			return;
		}
		setVariationStateByPersona((prev) => {
			const previous = prev[selectedPersonaId] || { selectedValues: [], variations: [] };
			const nextState = updater(previous);
			return { ...prev, [selectedPersonaId]: nextState };
		});
	};

	useEffect(() => {
		const handleClickOutside = (event) => {
			if (!dropdownRef.current || dropdownRef.current.contains(event.target)) {
				return;
			}
			setIsValueDropdownOpen(false);
		};

		document.addEventListener('mousedown', handleClickOutside);
		return () => {
			document.removeEventListener('mousedown', handleClickOutside);
		};
	}, []);

	useEffect(() => {
		setEditingVariationId(null);
		setVariationEditValue('');
		setHasCompletedVariationGeneration(false);
	}, [selectedPersonaId]);

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

	const extractErrorMessage = (data, fallbackMessage = 'Failed to generate persona. Please try again.') => {
		if (!data) {
			return fallbackMessage;
		}

		if (typeof data === 'string') {
			return data;
		}

		if (data.error_message) {
			return data.error_message;
		}

		if (Array.isArray(data.detail)) {
			const detailMessage = data.detail
				.map((item) => {
					if (!item) {
						return null;
					}
					if (typeof item === 'string') {
						return item;
					}
					if (item.msg) {
						return item.msg;
					}
					return JSON.stringify(item);
				})
				.filter(Boolean)
				.join('; ');

			if (detailMessage) {
				return detailMessage;
			}
		}

		if (typeof data.detail === 'string' && data.detail.trim()) {
			return data.detail;
		}

		if (data.message) {
			return data.message;
		}

		return fallbackMessage;
	};

	const handleInputChange = (event) => {
		const { name, value } = event.target;
		setFormData((prev) => ({ ...prev, [name]: value }));

		if (errors[name]) {
			setErrors((prev) => {
				const nextErrors = { ...prev };
				delete nextErrors[name];
				return nextErrors;
			});
		}
	};

	const handleConfirmPersona = () => {
		if (!personaResult || personaResult.saved) {
			return;
		}

		const personaContent = personaResult.content;
		const newId = `persona-${Date.now()}`;
		const nextGallery = assignPersonaNames([
			...personaGallery,
			{ id: newId, content: personaContent, name: '' },
		]);

		// Add to gallery and select new persona, then hide the generated result
		setPersonaGallery(nextGallery);
		setSelectedPersonaId(newId);
		setIsEditing(false);
		setEditValue('');
		setIsValueDropdownOpen(false);
		setVariationStateByPersona((prev) => ({
			...prev,
			[newId]: prev[newId] || { selectedValues: [], variations: [] },
		}));
		setVariationError('');

		// Hide the generated persona and show a short success toast
		setPersonaResult(null);
		setShowSavedToast(true);
		setTimeout(() => setShowSavedToast(false), 2000);
	};

	const handleEditPersona = () => {
		if (!personaResult) {
			return;
		}

		setIsEditing(true);
		setEditValue(personaResult.content);
	};

	const handleEditChange = (event) => {
		setEditValue(event.target.value);
	};

	const handleSaveEdit = () => {
		if (!personaResult) {
			return;
		}

		const updatedContent = editValue;

		setPersonaResult((prev) => {
			if (!prev) {
				return prev;
			}
			return { ...prev, content: updatedContent };
		});

		if (personaResult.saved && personaResult.id) {
			setPersonaGallery((previousGallery) =>
				assignPersonaNames(
					previousGallery.map((persona) =>
						persona.id === personaResult.id ? { ...persona, content: updatedContent } : persona,
					),
				),
			);
		}

		setIsEditing(false);
		setEditValue('');
	};

	const handleCancelEdit = () => {
		setIsEditing(false);
		setEditValue('');
	};

	const handleDiscardPersona = () => {
		if (!personaResult) {
			return;
		}

		if (personaResult.saved && personaResult.id) {
			setPersonaGallery((previousGallery) =>
				assignPersonaNames(previousGallery.filter((persona) => persona.id !== personaResult.id)),
			);
			setVariationStateByPersona((prev) => {
				if (!prev[personaResult.id]) {
					return prev;
				}
				const next = { ...prev };
				delete next[personaResult.id];
				return next;
			});
			if (selectedPersonaId === personaResult.id) {
				setSelectedPersonaId('');
			}
			if (environmentPersonaId === personaResult.id) {
				setEnvironmentPersonaId('');
				setEnvironmentVariationIds([]);
			}
		}

		setPersonaResult(null);
		setIsEditing(false);
		setEditValue('');
		setEditingVariationId(null);
		setVariationEditValue('');
		setIsValueDropdownOpen(false);
		setVariationError('');
		setHasCompletedVariationGeneration(false);
	};

	const toggleValueDropdown = () => {
		setIsValueDropdownOpen((prev) => !prev);
	};

	const handleValueToggle = (valueKey) => {
		if (!selectedPersonaId) {
			return;
		}

		setVariationError('');
		setHasCompletedVariationGeneration(false);

		setCurrentPersonaVariationState((previousState) => {
			const isActive = previousState.selectedValues.includes(valueKey);
			const tentative = isActive
				? previousState.selectedValues.filter((value) => value !== valueKey)
				: [...previousState.selectedValues, valueKey];
			const orderedOptions = VALUE_VARIATION_OPTIONS.filter((option) =>
				tentative.includes(option.value),
			);
			const nextSelectedValues = orderedOptions.map((option) => option.value);
			const variationMap = new Map(
				previousState.variations.map((variation) => [variation.valueKey, variation]),
			);
			orderedOptions.forEach((option) => {
				const existing = variationMap.get(option.value);
				variationMap.set(option.value, {
					valueKey: option.value,
					label: option.label,
					color: option.color,
					textColor: option.textColor,
					personaId: selectedPersonaId,
					personaContent: selectedPersona?.content ?? '',
					personaName: selectedPersona?.name ?? '',
					content:
						existing?.content
							?? createDefaultVariationContent(selectedPersona?.content ?? '', option.label),
				});
			});

			return {
				selectedValues: nextSelectedValues,
				variations: orderVariationEntries(variationMap),
			};
		});

		if (editingVariationId === valueKey) {
			setEditingVariationId(null);
			setVariationEditValue('');
		}
	};

	const handleStartVariationEdit = (valueKey) => {
		const target = personaVariations.find((variation) => variation.valueKey === valueKey);
		if (!target) {
			return;
		}
		setEditingVariationId(valueKey);
		setVariationEditValue(target.content);
	};

	const handleVariationEditChange = (event) => {
		setVariationEditValue(event.target.value);
	};

	const handleSaveVariationEdit = () => {
		if (!editingVariationId) {
			return;
		}

		setCurrentPersonaVariationState((previousState) => ({
			selectedValues: previousState.selectedValues,
			variations: previousState.variations.map((variation) =>
				variation.valueKey === editingVariationId
					? { ...variation, content: variationEditValue, value: variationEditValue }
					: variation,
				),
		}));

		setEditingVariationId(null);
		setVariationEditValue('');
	};

	const handleCancelVariationEdit = () => {
		setEditingVariationId(null);
		setVariationEditValue('');
	};

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

	const handlePersonaSelect = (event) => {
		const { value } = event.target;
		setSelectedPersonaId(value);
		setHasCompletedVariationGeneration(false);
		setIsEditing(false);
		setEditValue('');
		setEditingVariationId(null);
		setVariationEditValue('');
		setIsValueDropdownOpen(false);

		if (!value) {
			if (personaResult && personaResult.saved) {
				setPersonaResult(null);
			}
			return;
		}

		const selected = personaGallery.find((persona) => persona.id === value);
		if (selected) {
			setPersonaResult({ id: selected.id, content: selected.content, saved: true });
			setVariationStateByPersona((prev) => ({
				...prev,
				[value]: prev[value] || { selectedValues: [], variations: [] },
			}));
		}
	};

	const validateForm = () => {
		const trimmedName = formData.name.trim();
		const trimmedJob = formData.job.trim();
		const ageValue = Number(formData.age);
		const nextErrors = {};

		if (trimmedName.length < 2 || trimmedName.length > 100) {
			nextErrors.name = 'Name must be between 2 and 100 characters.';
		}

		if (!Number.isInteger(ageValue) || ageValue < 18 || ageValue > 100) {
			nextErrors.age = 'Age must be an integer between 18 and 100.';
		}

		if (trimmedJob.length < 2 || trimmedJob.length > 100) {
			nextErrors.job = 'Profession must be between 2 and 100 characters.';
		}

		if (formData.location && formData.location.length > 100) {
			nextErrors.location = 'Location can be up to 100 characters.';
		}

		if (formData.education && formData.education.length > 200) {
			nextErrors.education = 'Education can be up to 200 characters.';
		}

		if (formData.interests && formData.interests.length > 500) {
			nextErrors.interests = 'Interests can be up to 500 characters.';
		}

		return nextErrors;
	};

	const handlePersonaGeneration = async (event) => {
		event.preventDefault();
		const validationErrors = validateForm();

		if (Object.keys(validationErrors).length > 0) {
			setErrors(validationErrors);
			return;
		}

		setIsGenerating(true);
		setErrors((prev) => {
			if (!prev.submit) {
				return prev;
			}
			const nextErrors = { ...prev };
			delete nextErrors.submit;
			return nextErrors;
		});

		try {
			const demographic = {
				name: formData.name.trim(),
				age: Number(formData.age),
				job: formData.job.trim(),
				location: formData.location.trim() || undefined,
				education: formData.education.trim() || undefined,
				interests: formData.interests.trim() || undefined,
			};

			const response = await generatePersona(demographic, personaModel);

			if (!response.ok) {
				const message = extractErrorMessage(response.data);
				setErrors((prev) => ({ ...prev, submit: message }));
				return;
			}

			const payload = response.data;

			if (payload?.success) {
				const personaText =
					typeof payload.persona === 'string'
						? payload.persona
						: payload.persona !== undefined
							? JSON.stringify(payload.persona, null, 2)
							: '';
				setPersonaResult({ id: null, content: personaText ?? '', saved: false });
				setIsEditing(false);
				setEditValue('');
				setEditingVariationId(null);
				setVariationEditValue('');
				setIsValueDropdownOpen(false);
				setHasCompletedVariationGeneration(false);
				setErrors((prev) => {
					if (!prev.submit) {
						return prev;
					}
					const nextErrors = { ...prev };
					delete nextErrors.submit;
					return nextErrors;
				});
				return;
			}

			const message = extractErrorMessage(payload);
			setErrors((prev) => ({ ...prev, submit: message }));
		} catch (error) {
			setErrors((prev) => ({
				...prev,
				submit: error?.message || 'Failed to generate persona. Please try again.',
			}));
		} finally {
			setIsGenerating(false);
		}
	};

	const handleVariationGeneration = async (event) => {
		if (event && typeof event.preventDefault === 'function') {
			event.preventDefault();
		}

		if (!selectedPersonaId || !selectedPersona) {
			setVariationError('Please select a persona before generating variations.');
			return;
		}

		if (selectedVariationValues.length === 0) {
			setVariationError('Please select at least one value to generate variations.');
			return;
		}

		setVariationError('');
		setHasCompletedVariationGeneration(false);
		setIsGeneratingVariation(true);
		try {
			const response = await generatePersonaVariation(
				selectedPersona.content ?? '',
				selectedVariationValues,
				personaModel,
			);

			if (!response.ok) {
				const message = extractErrorMessage(
					response.data,
					'Failed to generate persona variations. Please try again.',
				);
				setVariationError(message);
				return;
			}

			const payload = response.data;
			if (!payload?.success) {
				const message = payload?.error_message
					|| extractErrorMessage(payload, 'Failed to generate persona variations. Please try again.');
				setVariationError(message);
				return;
			}

			const variationsPayload = Array.isArray(payload.variations) ? payload.variations : [];
			const personaContent = selectedPersona.content ?? '';
			const personaName = selectedPersona.name ?? '';
			const variationContentByValue = new Map();
			variationsPayload.forEach((item) => {
				if (!item || !item.value) {
					return;
				}
				variationContentByValue.set(item.value, item.varied_persona ?? '');
			});

			setCurrentPersonaVariationState((previousState) => {
				const orderedOptions = VALUE_VARIATION_OPTIONS.filter((option) =>
					selectedVariationValues.includes(option.value),
				);
				const variationMap = new Map(
					previousState.variations.map((variation) => [variation.valueKey, variation]),
				);
				orderedOptions.forEach((option) => {
					const previous = variationMap.get(option.value);
					const contentFromApi = variationContentByValue.has(option.value)
						? variationContentByValue.get(option.value) ?? ''
						: previous?.content
							?? createDefaultVariationContent(personaContent, option.label);
					variationMap.set(option.value, {
						valueKey: option.value,
						label: option.label,
						color: option.color,
						textColor: option.textColor,
						personaId: selectedPersonaId,
						personaContent,
						personaName,
						content: contentFromApi,
					});
				});
				return {
					selectedValues: orderedOptions.map((option) => option.value),
					variations: orderVariationEntries(variationMap),
				};
			});

			setEditingVariationId(null);
			setVariationEditValue('');
			setIsValueDropdownOpen(false);
			setVariationError('');
			setHasCompletedVariationGeneration(true);
		} catch (error) {
			setVariationError(
				error?.message || 'Failed to generate persona variations. Please try again.',
			);
		} finally {
			setIsGeneratingVariation(false);
		}
	};

	const handleContinueToEnvironment = () => {
		switchConfigTab('environment');
	};

	const handleVariationRegeneration = async (valueKey) => {
		if (!selectedPersonaId || !selectedPersona) {
			setVariationError('Select a persona before regenerating variations.');
			return;
		}

		setVariationError('');
		setRegeneratingVariationKey(valueKey);
		try {
			const response = await generatePersonaVariation(
				selectedPersona.content ?? '',
				[valueKey],
				personaModel,
			);

			if (!response.ok) {
				const message = extractErrorMessage(
					response.data,
					'Failed to regenerate the persona variation. Please try again.',
				);
				setVariationError(message);
				return;
			}

			const payload = response.data;
			if (!payload?.success) {
				const message = payload?.error_message
					|| extractErrorMessage(payload, 'Failed to regenerate the persona variation. Please try again.');
				setVariationError(message);
				return;
			}

			const variationEntry = Array.isArray(payload.variations)
				? payload.variations.find((item) => item?.value === valueKey)
				: null;
			const option = VALUE_VARIATION_OPTIONS.find((item) => item.value === valueKey);
			const personaContent = selectedPersona.content ?? '';
			const personaName = selectedPersona.name ?? '';

			setCurrentPersonaVariationState((previousState) => {
				const variationMap = new Map(
					previousState.variations.map((variation) => [variation.valueKey, variation]),
				);
				const previous = variationMap.get(valueKey);
				variationMap.set(valueKey, {
					valueKey,
					label: option?.label || previous?.label || valueKey,
					color: option?.color || previous?.color || '#e5e7eb',
					textColor: option?.textColor || previous?.textColor || '#1f2937',
					personaId: selectedPersonaId,
					personaContent,
					personaName,
					content:
						variationEntry?.varied_persona
							?? previous?.content
							?? createDefaultVariationContent(personaContent, option?.label || valueKey),
				});
				return {
					selectedValues: previousState.selectedValues,
					variations: orderVariationEntries(variationMap),
				};
			});
		} catch (error) {
			setVariationError(
				error?.message || 'Failed to regenerate the persona variation. Please try again.',
			);
		} finally {
			setRegeneratingVariationKey(null);
		}
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
		const abortController = new AbortController();
		activeEnvironmentRunIdRef.current = runId;
		activeEnvironmentAbortRef.current = abortController;
		emitEnvironmentRunState({
			runId,
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
									onAddRun({ results: runResults });
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
							setEnvironmentRunError(data?.error || 'Browser agent run failed.');
							emitEnvironmentRunState({
								runId,
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
							status: data?.status || 'completed',
							isRunning: false,
							logs: Array.isArray(data?.logs) ? data.logs : undefined,
							error: data?.error || null,
						});

						if (settled) {
							return;
						}

						if (data?.status === 'failed' || data?.status === 'cancelled') {
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
							status: 'failed',
							isRunning: false,
							error: streamError?.message || 'Browser agent event stream failed.',
						});
						settled = true;
						stream.close();
						reject(streamError);
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
					status: 'cancelled',
					isRunning: false,
					error: 'Browser agent run was stopped.',
				});
				return;
			}
			emitEnvironmentRunState({
				runId,
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
				isRunning: false,
			});
		}
	};

	return (
		<div className="configuration-panel">
			<PanelHeader title="Configuration" />
			<div className="config-container">
				{/* Content area */}
				<div className="panel__body config-content">
					<section className="config-section">
							{currentActiveTab === 'persona' && (
								<form id="persona-form" className="config-form" onSubmit={handlePersonaGeneration} noValidate>
									<PersonaConfiguration
										formData={formData}
										personaModel={personaModel}
										onModelChange={setPersonaModel}
										modelOptions={ENVIRONMENT_MODEL_OPTIONS}
										errors={errors}
										onInputChange={handleInputChange}
										personaGallery={personaGallery}
										selectedPersonaId={selectedPersonaId}
										handlePersonaSelect={handlePersonaSelect}
										selectedVariationValues={selectedVariationValues}
										isValueDropdownOpen={isValueDropdownOpen}
										toggleValueDropdown={toggleValueDropdown}
										handleValueToggle={handleValueToggle}
										valueOptions={VALUE_VARIATION_OPTIONS}
										dropdownRef={dropdownRef}
										variationError={variationError}
										personaVariations={personaVariations}
										editingVariationId={editingVariationId}
										variationEditValue={variationEditValue}
										handleStartVariationEdit={handleStartVariationEdit}
										handleVariationEditChange={handleVariationEditChange}
										handleSaveVariationEdit={handleSaveVariationEdit}
										handleCancelVariationEdit={handleCancelVariationEdit}
										handleVariationGeneration={handleVariationGeneration}
										handleVariationRegeneration={handleVariationRegeneration}
										isGenerating={isGenerating}
										isGeneratingVariation={isGeneratingVariation}
										regeneratingVariationKey={regeneratingVariationKey}
										formatVariationContent={formatVariationContent}
										selectedPersona={selectedPersona}
										personaResult={personaResult}
										isEditing={isEditing}
										editValue={editValue}
										handleConfirmPersona={handleConfirmPersona}
										handleEditPersona={handleEditPersona}
										handleEditChange={handleEditChange}
										handleSaveEdit={handleSaveEdit}
										handleCancelEdit={handleCancelEdit}
										handleDiscardPersona={handleDiscardPersona}
										showSavedToast={showSavedToast}
										hasCompletedVariationGeneration={hasCompletedVariationGeneration}
										onContinueToEnvironment={handleContinueToEnvironment}
									/>
									{errors.submit && <p className="config-form__error config-form__error--global">{errors.submit}</p>}
								</form>
							)}

							{currentActiveTab === 'environment' && (
								<EnvironmentSetting
									personaGallery={personaGallery}
									environmentPersonaId={environmentPersonaId}
									handleEnvironmentPersonaChange={handleEnvironmentPersonaChange}
									environmentErrors={environmentErrors}
									environmentPersona={environmentPersona}
									environmentPersonaVariations={environmentPersonaVariations}
									environmentVariationIds={environmentVariationIds}
									handleEnvironmentVariationToggle={handleEnvironmentVariationToggle}
									handleEnvironmentVariationUpdate={handleEnvironmentVariationUpdate}
									VALUE_VARIATION_OPTIONS={VALUE_VARIATION_OPTIONS}
									formatVariationContent={formatVariationContent}
									environmentTasks={[]}
									environmentTaskName={environmentTaskName}
									environmentTaskUrl={environmentTaskUrl}
									onEnvironmentTaskNameChange={setEnvironmentTaskName}
									onEnvironmentTaskUrlChange={setEnvironmentTaskUrl}
									environmentRunTimes={environmentRunTimes}
									handleEnvironmentRunTimesChange={handleEnvironmentRunTimesChange}
									ENVIRONMENT_MODEL_OPTIONS={ENVIRONMENT_MODEL_OPTIONS}
									environmentModels={environmentModels}
									handleEnvironmentModelToggle={handleEnvironmentModelToggle}
									environmentRunError={environmentRunError}
									environmentRunResult={environmentRunResult}
									handleEnvironmentRun={handleEnvironmentRun}
									isRunningEnvironment={isRunningEnvironment}
									environmentWaitSeconds={environmentWaitSeconds}
									isCacheLoading={isCacheLoading}
								/>
							)}
						</section>
					</div>
				</div>
			</div>
		);
	};

ConfigurationView.propTypes = {
	onAddRun: PropTypes.func,
	activeTab: PropTypes.oneOf(['persona', 'environment']),
	onTabChange: PropTypes.func,
	onGetCacheData: PropTypes.func,
	isCacheLoading: PropTypes.bool,
	onEnvironmentRunStateChange: PropTypes.func,
};

ConfigurationView.defaultProps = {
	onAddRun: undefined,
	activeTab: undefined,
	onTabChange: undefined,
	onGetCacheData: undefined,
	isCacheLoading: false,
	onEnvironmentRunStateChange: undefined,
};

export default ConfigurationView;
