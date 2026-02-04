import React from 'react';
import PropTypes from 'prop-types';
import './ActionButton.css';

/**
 * ActionButton is a reusable button component for action triggers.
 * Used independently of PanelHeader to avoid style pollution.
 */
const ActionButton = ({
	label,
	onClick,
	disabled = false,
	isLoading = false,
	variant = 'default',
	className = '',
}) => {
	const classNames = [
		'action-button',
		`action-button--${variant}`,
		isLoading && 'action-button--loading',
		className,
	]
		.filter(Boolean)
		.join(' ');

	return (
		<button
			type="button"
			className={classNames}
			onClick={onClick}
			disabled={disabled || isLoading}
			aria-busy={isLoading}
		>
			{isLoading && <span className="action-button__spinner"></span>}
			{label}
		</button>
	);
};

ActionButton.propTypes = {
	label: PropTypes.string.isRequired,
	onClick: PropTypes.func.isRequired,
	disabled: PropTypes.bool,
	isLoading: PropTypes.bool,
	variant: PropTypes.oneOf(['default', 'primary', 'secondary']),
	className: PropTypes.string,
};

export default ActionButton;
