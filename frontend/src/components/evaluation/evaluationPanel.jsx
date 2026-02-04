import React, { useState, useMemo, useCallback } from 'react';
import PropTypes from 'prop-types';
import PanelHeader from '../common/PanelHeader';
import ActionButton from '../common/ActionButton';
import CriteriaCard from './CriteriaCard';
import ConditionCard from './ConditionCard';
import CriteriaDetailModal from './CriteriaDetailModal';
import ConditionDetailModal from './ConditionDetailModal';
import './evaluationPanel.css';

const EvaluationPanel = ({
	criterias = {},
	conditions = [],
	selectedCriteriaIds = [],
	selectedConditionIds = [],
	onCriteriaSelectionChange = () => {},
	onConditionSelectionChange = () => {},
	onEvaluate = () => {},
	evaluationResponse = null,
}) => {
	const [showCriteriaModal, setShowCriteriaModal] = useState(false);
	const [selectedCriteriaIdForModal, setSelectedCriteriaIdForModal] = useState(null);
	const [showConditionModal, setShowConditionModal] = useState(false);
	const [selectedConditionIdForModal, setSelectedConditionIdForModal] = useState(null);
	const [criteriaFilterMeta] = useState({ personas: null, models: null });
	const [draggedItem, setDraggedItem] = useState(null);
	const [isEvaluating, setIsEvaluating] = useState(false);

	const criteriaList = useMemo(() => {
		return Object.values(criterias || {});
	}, [criterias]);

	// Derive the currently selected criteria object for the modal from the latest criteriaList
	const selectedCriteriaForModal = useMemo(() => {
		return selectedCriteriaIdForModal ? criteriaList.find(c => c.id === selectedCriteriaIdForModal) : null;
	}, [selectedCriteriaIdForModal, criteriaList]);

	const filteredConditions = useMemo(() => {
		let filtered = conditions;
		if (criteriaFilterMeta.personas) {
			filtered = filtered.filter(d => d.persona?.value === criteriaFilterMeta.personas);
		}
		if (criteriaFilterMeta.models) {
			filtered = filtered.filter(d => d.model === criteriaFilterMeta.models);
		}
		
		// Normalize condition object, ensure id field exists
		return filtered.map(cond => ({
			...cond,
			id: cond.id || cond.conditionID,
		}));
	}, [conditions, criteriaFilterMeta]);

	// Derive the currently selected condition object for the modal from the latest filteredConditions (which comes from props)
	const selectedConditionForModal = useMemo(() => {
		return selectedConditionIdForModal ? filteredConditions.find(c => c.id === selectedConditionIdForModal) : null;
	}, [selectedConditionIdForModal, filteredConditions]);

	const selectedConditions = useMemo(() => {
		return filteredConditions.filter(d => selectedConditionIds.includes(d.id));
	}, [filteredConditions, selectedConditionIds]);

	const unselectedConditions = useMemo(() => {
		return filteredConditions.filter(d => !selectedConditionIds.includes(d.id));
	}, [filteredConditions, selectedConditionIds]);

	const selectedCriteriaList = useMemo(() => {
		return criteriaList.filter(c => selectedCriteriaIds.includes(c.id));
	}, [criteriaList, selectedCriteriaIds]);

	const unselectedCriteriaList = useMemo(() => {
		return criteriaList.filter(c => !selectedCriteriaIds.includes(c.id));
	}, [criteriaList, selectedCriteriaIds]);

	const selectedCriteriaComparison = useMemo(() => {
		if (!selectedCriteriaForModal || !evaluationResponse?.multi_condition_assessment?.criteria_comparisons) {
			return null;
		}
		return evaluationResponse.multi_condition_assessment.criteria_comparisons.find(
			c => {
				// Try to match by ID if available in comparison data (it might not be based on user snippet)
				if (c.id && selectedCriteriaForModal.id) return c.id === selectedCriteriaForModal.id;
				// Fallback to title and assertion
				return c.title === selectedCriteriaForModal.title && c.assertion === selectedCriteriaForModal.assertion;
			}
		);
	}, [selectedCriteriaForModal, evaluationResponse]);

	const handleCriteriaCardClick = useCallback((criteria) => {
		setSelectedCriteriaIdForModal(criteria.id);
		setShowCriteriaModal(true);
	}, []);

	const handleConditionCardClick = useCallback((condition) => {
		setSelectedConditionIdForModal(condition.id);
		setShowConditionModal(true);
	}, []);

	const handleConditionToggle = useCallback((conditionId) => {
		const newSelection = selectedConditionIds.includes(conditionId)
			? selectedConditionIds.filter(id => id !== conditionId)
			: [...selectedConditionIds, conditionId];
		onConditionSelectionChange(newSelection);
	}, [selectedConditionIds, onConditionSelectionChange]);

	const handleCriteriaDragStart = useCallback((e, criteria) => {
		e.dataTransfer.effectAllowed = 'move';
		const dragData = {
			type: 'criteria',
			id: criteria.id,
		};
		e.dataTransfer.setData('text/plain', JSON.stringify(dragData));
		setDraggedItem(dragData);
	}, []);

	const handleCriteriaDropToSelected = useCallback((e) => {
		e.preventDefault();
		try {
			const data = JSON.parse(e.dataTransfer.getData('text/plain'));
			if (data.type === 'criteria' && (data.id || data.id === 0)) {
				const isAlreadySelected = selectedCriteriaIds.includes(data.id);
				if (!isAlreadySelected) {
					const newSelection = [...selectedCriteriaIds, data.id];
					onCriteriaSelectionChange(newSelection);
				} else {
				}
			}
		} catch (error) {
		}
		setDraggedItem(null);
	}, [selectedCriteriaIds, onCriteriaSelectionChange]);

	const handleCriteriaDropToUnselected = useCallback((e) => {
		e.preventDefault();
		try {
			const data = JSON.parse(e.dataTransfer.getData('text/plain'));
			if (data.type === 'criteria' && (data.id || data.id === 0)) {
				// 直接计算新的选择状态，而不依赖 selectedCriteriaIds
				if (selectedCriteriaIds.includes(data.id)) {
					const newSelection = selectedCriteriaIds.filter(id => id !== data.id);
					onCriteriaSelectionChange(newSelection);
				}
			}
		} catch (error) {
		}
		setDraggedItem(null);
	}, [selectedCriteriaIds, onCriteriaSelectionChange]);

	const handleDragStart = useCallback((e, condition) => {
		e.dataTransfer.effectAllowed = 'move';
		const dragData = {
			type: 'condition',
			id: condition.id,
		};
		e.dataTransfer.setData('text/plain', JSON.stringify(dragData));
		setDraggedItem(dragData);
	}, []);

	const handleDragEnd = useCallback(() => {
		setDraggedItem(null);
	}, []);

	const handleDropToSelected = useCallback((e) => {
		e.preventDefault();
		try {
			const data = JSON.parse(e.dataTransfer.getData('text/plain'));
			if (data.type === 'condition' && (data.id || data.id === 0)) {
				if (!selectedConditionIds.includes(data.id)) {
					handleConditionToggle(data.id);
				} else {
				}
			}
		} catch (error) {
		}
		setDraggedItem(null);
	}, [handleConditionToggle, selectedConditionIds]);

	const handleDropToUnselected = useCallback((e) => {
		e.preventDefault();
		try {
			const data = JSON.parse(e.dataTransfer.getData('text/plain'));
			if (data.type === 'condition' && (data.id || data.id === 0)) {
				// If it's currently selected, toggle it (deselect)
				if (selectedConditionIds.includes(data.id)) {
					handleConditionToggle(data.id);
				}
			}
		} catch (error) {
		}
		setDraggedItem(null);
	}, [selectedConditionIds, handleConditionToggle]);

	const handleDragOver = useCallback((e) => {
		e.preventDefault();
		e.dataTransfer.dropEffect = 'move';
	}, []);

	const handleEvaluate = useCallback(async () => {
		if (selectedCriteriaIds.length === 0 || selectedConditionIds.length === 0) {
			alert('Please select at least one criteria and one condition before evaluating.');
			return;
		}
		try {
			setIsEvaluating(true);
			// Get the actual condition data for selected conditions
			const selectedConditionData = filteredConditions.filter(c => selectedConditionIds.includes(c.id));
			const selectedCriteriaData = criteriaList.filter(c => selectedCriteriaIds.includes(c.id));
			
			await onEvaluate({
				criteriaIds: selectedCriteriaIds,
				conditionIds: selectedConditionIds,
				conditions: selectedConditionData,
				criteria: selectedCriteriaData,
			});
		} finally {
			setIsEvaluating(false);
		}
	}, [selectedCriteriaIds, selectedConditionIds, filteredConditions, criteriaList, onEvaluate]);

	const hasSelections = selectedCriteriaIds.length > 0 && selectedConditionIds.length > 0;

	return (
		<div className="evaluation-panel">
			<PanelHeader title="Evaluation">
				<ActionButton
					label={isEvaluating ? 'Evaluating...' : 'Evaluate'}
					onClick={handleEvaluate}
					disabled={!hasSelections || isEvaluating}
					isLoading={isEvaluating}
					variant="primary"
				/>
			</PanelHeader>

			<div className="evaluation-panel__content">
				{/* Criteria Section */}
				<section className="evaluation-panel__section evaluation-panel__section--criteria">
					<div className="evaluation-panel__section-title">
						<span>Criteria</span>
						<span className="evaluation-panel__count">
							{selectedCriteriaIds.length}/{criteriaList.length}
						</span>
					</div>
					
					<div className="evaluation-panel__criteria-wrapper">
						{/* Selected Criteria */}
						<div
							className="evaluation-panel__criteria-area evaluation-panel__criteria-area--selected"
							onDragOver={handleDragOver}
							onDrop={handleCriteriaDropToSelected}
						>
							<div className="evaluation-panel__criteria-label">
								Selected ({selectedCriteriaList.length})
							</div>
							<div className="evaluation-panel__cards-container evaluation-panel__cards-container--criteria">
								{selectedCriteriaList.length > 0 ? (
									selectedCriteriaList.map(criteria => (
										<CriteriaCard
											key={criteria.id}
											criteria={criteria}
											isSelected={true}
											onClick={() => handleCriteriaCardClick(criteria)}
											onDragStart={(e) => handleCriteriaDragStart(e, criteria)}
											onDragEnd={handleDragEnd}
											isDragging={draggedItem?.id === criteria.id}
											draggable
										/>
									))
								) : (
									<div className="evaluation-panel__empty-state">
										<p>No selected criteria</p>
										<p className="evaluation-panel__empty-state-hint">
											Drag from right to select
										</p>
									</div>
								)}
							</div>
						</div>

						{/* Available Criteria */}
						<div
							className="evaluation-panel__criteria-area evaluation-panel__criteria-area--unselected"
							onDragOver={handleDragOver}
							onDrop={handleCriteriaDropToUnselected}
						>
							<div className="evaluation-panel__criteria-label">
								Available ({unselectedCriteriaList.length})
							</div>
							<div className="evaluation-panel__cards-container evaluation-panel__cards-container--criteria">
								{unselectedCriteriaList.length > 0 ? (
									unselectedCriteriaList.map(criteria => (
										<CriteriaCard
											key={criteria.id}
											criteria={criteria}
											isSelected={false}
											onClick={() => handleCriteriaCardClick(criteria)}
											onDragStart={(e) => handleCriteriaDragStart(e, criteria)}
											onDragEnd={handleDragEnd}
											isDragging={draggedItem?.id === criteria.id}
											draggable
										/>
									))
								) : (
									<div className="evaluation-panel__empty-state">
										<p>No available criteria</p>
										<p className="evaluation-panel__empty-state-hint">
											All criteria selected
										</p>
									</div>
								)}
							</div>
						</div>
					</div>
				</section>

				{/* Conditions Section */}
				<section className="evaluation-panel__section evaluation-panel__section--conditions">
					<div className="evaluation-panel__section-title">
						<span>Conditions</span>
						<span className="evaluation-panel__count">
							{selectedConditionIds.length}/{conditions.length}
						</span>
					</div>
					
					<div className="evaluation-panel__conditions-wrapper">
						{/* Selected Conditions */}
						<div
							className="evaluation-panel__conditions-area evaluation-panel__conditions-area--selected"
							onDragOver={handleDragOver}
							onDrop={handleDropToSelected}
						>
							<div className="evaluation-panel__conditions-label">
								Selected ({selectedConditions.length})
							</div>
							<div className="evaluation-panel__cards-container evaluation-panel__cards-container--conditions">
								{selectedConditions.length > 0 ? (
									selectedConditions.map(condition => (
										<ConditionCard
											key={condition.id}
											condition={condition}
											isSelected={true}
											onToggleSelect={() => handleConditionToggle(condition.id)}
											onCardClick={handleConditionCardClick}
											onDragStart={(e) => handleDragStart(e, condition)}
											onDragEnd={handleDragEnd}
											isDragging={draggedItem?.id === condition.id}
											draggable
										/>
									))
								) : (
									<div className="evaluation-panel__empty-state">
										<p>No selected conditions</p>
										<p className="evaluation-panel__empty-state-hint">
											Drag from right to select
										</p>
									</div>
								)}
							</div>
						</div>

						{/* Unselected Conditions */}
						<div
							className="evaluation-panel__conditions-area evaluation-panel__conditions-area--unselected"
							onDragOver={handleDragOver}
							onDrop={handleDropToUnselected}
						>
							{/* Trash Overlay - Shows when dragging a selected item */}
							{draggedItem && selectedConditionIds.includes(draggedItem.id) && (
								<div className="evaluation-panel__trash-overlay">
									<div className="evaluation-panel__trash-overlay-icon">🗑️</div>
									<div className="evaluation-panel__trash-overlay-text">Drop to Remove</div>
								</div>
							)}

							<div className="evaluation-panel__conditions-label">
								Available ({unselectedConditions.length})
							</div>
							<div className="evaluation-panel__cards-container evaluation-panel__cards-container--conditions">
								{unselectedConditions.length > 0 ? (
									unselectedConditions.map(condition => (
										<ConditionCard
											key={condition.id}
											condition={condition}
											isSelected={false}
											onToggleSelect={() => handleConditionToggle(condition.id)}
											onCardClick={handleConditionCardClick}
											onDragStart={(e) => handleDragStart(e, condition)}
											onDragEnd={handleDragEnd}
											isDragging={draggedItem?.id === condition.id}
											draggable
										/>
									))
								) : (
									<div className="evaluation-panel__empty-state">
										<p>No available conditions</p>
										<p className="evaluation-panel__empty-state-hint">
											All conditions selected
										</p>
									</div>
								)}
							</div>
						</div>
					</div>

					{/* Delete Zone Removed */}
				</section>
			</div>

			{/* Criteria Detail Modal */}
			{showCriteriaModal && selectedCriteriaForModal && (
				<CriteriaDetailModal
					criteria={selectedCriteriaForModal}
					comparison={selectedCriteriaComparison}
					conditions={conditions}
					onClose={() => {
						setShowCriteriaModal(false);
						setSelectedCriteriaIdForModal(null);
					}}
					isSelected={selectedCriteriaIds.includes(selectedCriteriaForModal.id)}
					onToggleSelect={() => {
						const isSelected = selectedCriteriaIds.includes(selectedCriteriaForModal.id);
						const newSelection = isSelected
							? selectedCriteriaIds.filter(id => id !== selectedCriteriaForModal.id)
							: [...selectedCriteriaIds, selectedCriteriaForModal.id];
						onCriteriaSelectionChange(newSelection);
					}}
				/>
			)}

			{/* Condition Detail Modal */}
			{showConditionModal && selectedConditionForModal && (
				<ConditionDetailModal
					condition={selectedConditionForModal}
					onClose={() => {
						setShowConditionModal(false);
						setSelectedConditionIdForModal(null);
					}}
				/>
			)}
		</div>
	);
};

EvaluationPanel.propTypes = {
	criterias: PropTypes.object,
	conditions: PropTypes.array,
	selectedCriteriaIds: PropTypes.array,
	selectedConditionIds: PropTypes.array,
	onCriteriaSelectionChange: PropTypes.func,
	onConditionSelectionChange: PropTypes.func,
	onEvaluate: PropTypes.func,
};

EvaluationPanel.defaultProps = {
	criterias: {},
	conditions: [],
	selectedCriteriaIds: [],
	selectedConditionIds: [],
	onCriteriaSelectionChange: () => {},
	onConditionSelectionChange: () => {},
	onEvaluate: () => {},
};

export default EvaluationPanel;
