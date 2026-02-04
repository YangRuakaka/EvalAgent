import React, { useCallback } from 'react';
import PropTypes from 'prop-types';
import './CriteriaCard.css';

const CriteriaCard = ({
	criteria,
	isSelected = false,
	onClick = () => {},
	onDragStart = () => {},
	onDragEnd = () => {},
	isDragging = false,
	draggable = false,
}) => {
	const cardColor = criteria.color || '#3B82F6';

	const handleClick = useCallback(() => {
		onClick(criteria);
	}, [onClick, criteria]);

	const handleDragStart = useCallback((e) => {
		e.dataTransfer.effectAllowed = 'move';
		// Removed setDragImage to rely on default browser behavior which is more robust
		onDragStart(e);
	}, [onDragStart]);

	return (
		<div
			className={`criteria-card ${isSelected ? 'criteria-card--selected' : ''} ${isDragging ? 'criteria-card--dragging' : ''}`}
			style={{ '--criteria-color': cardColor }}
			draggable={isSelected || draggable}
			onDragStart={handleDragStart}
			onDragEnd={onDragEnd}
			onClick={handleClick}
		>
			<div 
				className="criteria-card__color-strip" 
				style={{ backgroundColor: cardColor }} 
			/>
			<div className="criteria-card__content">
				<div className="criteria-card__title">{criteria.title}</div>
				<div className="criteria-card__description">
					{criteria.description || 'No description provided.'}
				</div>
			</div>
			
			{/* Drag Handle - Show for selected cards */}
			{isSelected && (
				<div className="criteria-card__drag-handle" title="Drag to deselect">
					⋮
				</div>
			)}
		</div>
	);
};


CriteriaCard.propTypes = {
	criteria: PropTypes.shape({
		id: PropTypes.string.isRequired,
		title: PropTypes.string,
		description: PropTypes.string,
		assertion: PropTypes.string,
		color: PropTypes.string,
	}).isRequired,
	isSelected: PropTypes.bool,
	onClick: PropTypes.func,
	onDragStart: PropTypes.func,
	onDragEnd: PropTypes.func,
	isDragging: PropTypes.bool,
	draggable: PropTypes.bool,
};

CriteriaCard.defaultProps = {
	isSelected: false,
	onClick: () => {},
	onDragStart: () => {},
	onDragEnd: () => {},
	isDragging: false,
	draggable: false,
};

export default CriteriaCard;
