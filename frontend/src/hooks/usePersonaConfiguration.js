import { useState, useRef, useMemo, useEffect } from 'react';
import { generatePersona, generatePersonaVariation } from '../services/api';
import { 
    assignPersonaNames, 
    createDefaultVariationContent, 
    orderVariationEntries, 
    formatVariationContent 
} from '../utils/personaUtils';
import { extractErrorMessage } from '../utils/runUtils';
import { ENVIRONMENT_MODEL_OPTIONS, VALUE_VARIATION_OPTIONS } from '../config/constants';

const EMPTY_FORM = {
	name: '',
	age: '',
	job: '',
	location: '',
	education: '',
	interests: '',
};

export const usePersonaConfiguration = () => {
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
    const [isGeneratingVariation, setIsGeneratingVariation] = useState(false);
    const [hasCompletedVariationGeneration, setHasCompletedVariationGeneration] = useState(false);
    const [regeneratingVariationKey, setRegeneratingVariationKey] = useState(null);
    const dropdownRef = useRef(null);

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
		const inputName = typeof formData.name === 'string' ? formData.name.trim() : '';
		const safeOriginalName = inputName.length > 0 ? inputName : 'Persona';
		
		const nextGallery = assignPersonaNames([
			...personaGallery,
			{ 
				id: newId, 
				content: personaContent, 
				name: safeOriginalName, // Temporary name before assignment
				originalName: safeOriginalName 
			},
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

	const handleDiscardPersona = (environmentPersonaId, setEnvironmentPersonaId, setEnvironmentVariationIds) => {
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

    return {
        formData, setFormData,
        personaModel, setPersonaModel,
        errors, setErrors,
        isGenerating,
        personaResult, setPersonaResult,
        isEditing, setIsEditing,
        editValue, setEditValue,
        showSavedToast, setShowSavedToast,
        personaGallery, setPersonaGallery,
        selectedPersonaId, setSelectedPersonaId,
        variationStateByPersona, setVariationStateByPersona,
        editingVariationId, setEditingVariationId,
        variationEditValue, setVariationEditValue,
        isValueDropdownOpen, setIsValueDropdownOpen,
        variationError, setVariationError,
        isGeneratingVariation, setIsGeneratingVariation,
        hasCompletedVariationGeneration, setHasCompletedVariationGeneration,
        regeneratingVariationKey, setRegeneratingVariationKey,
        dropdownRef,
        selectedPersona,
        selectedVariationValues,
        personaVariations,
        setCurrentPersonaVariationState,
        handleInputChange,
        handleConfirmPersona,
        handleEditPersona,
        handleEditChange,
        handleSaveEdit,
        handleCancelEdit,
        handleDiscardPersona,
        toggleValueDropdown,
        handleValueToggle,
        handleStartVariationEdit,
        handleVariationEditChange,
        handleSaveVariationEdit,
        handleCancelVariationEdit,
        handlePersonaSelect,
        handlePersonaGeneration,
        handleVariationGeneration,
        handleVariationRegeneration,
        formatVariationContent
    };
};
