import React, { useCallback, useMemo } from 'react';
import PropTypes from 'prop-types';
import ReactMarkdown from 'react-markdown';
import { CheckIcon, CrossIcon } from '../common/icons';
import './ConditionCard.css';

const ConditionCard = ({
	condition,
	isSelected = false,
	onToggleSelect = () => {},
	onCardClick = () => {},
	onDragStart = () => {},
	onDragEnd = () => {},
	isDragging = false,
	draggable = false,
}) => {
	const displayInfo = useMemo(() => {
		return {
			runIndex: condition.run_index !== undefined ? condition.run_index : (condition.metadata?.run_index !== undefined ? condition.metadata.run_index : 'N/A'),
			model: condition.model || condition.metadata?.model || 'Unknown Model',
			persona: condition.persona?.content || condition.metadata?.persona || (typeof condition.persona === 'string' ? condition.persona : null) || 'Unknown Persona',
			value: condition.value || condition.persona?.value || condition.metadata?.value || 'N/A',
			finalResult: condition.raw?.final_result || condition.raw?.output || 'No Result',
			isDone: condition.is_done ?? condition.raw?.is_done ?? false,
			isSuccessful: condition.is_successful ?? condition.raw?.is_successful ?? false,
		};
	}, [condition]);

	const handleDragStart = useCallback((e) => {
		e.dataTransfer.effectAllowed = 'move';
		// Removed setDragImage to rely on default browser behavior which is more robust
		onDragStart(e);
	}, [onDragStart]);

	const handleClick = useCallback((e) => {
		// 避免在拖动时触发 click
		if (e.button !== 0 || isDragging) return;
		onCardClick(condition);
	}, [onCardClick, condition, isDragging]);

	return (
		<div
			className={`condition-card ${isSelected ? 'condition-card--selected' : ''} ${isDragging ? 'condition-card--dragging' : ''} ${displayInfo.isDone ? (displayInfo.isSuccessful ? 'condition-card--success-state' : 'condition-card--failure-state') : ''}`}
			draggable={isSelected || draggable}
			onDragStart={handleDragStart}
			onDragEnd={onDragEnd}
			onClick={handleClick}
		>
			{/* Content */}
			<div className="condition-card__content">
				{/* Top Row: Status Icon, Model, Run Index */}
				<div className="condition-card__top-row">
					<div className="condition-card__status-indicator">
						{displayInfo.isDone ? (
							displayInfo.isSuccessful ? (
								<CheckIcon className="condition-card__status-icon-large condition-card__status-icon--success" title="Success" />
							) : (
								<CrossIcon className="condition-card__status-icon-large condition-card__status-icon--failure" title="Failed" />
							)
						) : (
							<div className="condition-card__status-pending-large" title="In Progress" />
						)}
					</div>
					
					<div className="condition-card__meta-info">
						<div className="condition-card__model-name" title={displayInfo.model}>
							{displayInfo.model}
						</div>
						<div className="condition-card__sub-meta">
							<div className="condition-card__value-badge" title={displayInfo.value}>
								{displayInfo.value}
							</div>
							<div className="condition-card__run-badge">
								#{displayInfo.runIndex}
							</div>
						</div>
					</div>
				</div>

				{/* Final Result - Prominent */}
				<div className="condition-card__result-area">
					<div className="condition-card__result-content" title={displayInfo.finalResult}>
						<ReactMarkdown>{displayInfo.finalResult}</ReactMarkdown>
					</div>
				</div>
			</div>

			{/* Drag Handle - Show for selected cards */}
			{isSelected && (
				<div className="condition-card__drag-handle" title="Drag to deselect">
					⋮
				</div>
			)}
		</div>
	);
};

ConditionCard.propTypes = {
	condition: PropTypes.shape({
		id: PropTypes.string.isRequired,
		model: PropTypes.string,
		persona: PropTypes.shape({
			value: PropTypes.string,
		}),
		metadata: PropTypes.object,
		raw: PropTypes.object,
	}).isRequired,
	isSelected: PropTypes.bool,
	onToggleSelect: PropTypes.func,
	onCardClick: PropTypes.func,
	onDragStart: PropTypes.func,
	onDragEnd: PropTypes.func,
	isDragging: PropTypes.bool,
	draggable: PropTypes.bool,
};

ConditionCard.defaultProps = {
	isSelected: false,
	onToggleSelect: () => {},
	onCardClick: () => {},
	onDragStart: () => {},
	onDragEnd: () => {},
	isDragging: false,
	draggable: false,
};

export default ConditionCard;
