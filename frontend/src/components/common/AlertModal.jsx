import React from 'react';
import PropTypes from 'prop-types';

import './AlertModal.css';

/**
 * Alert Modal Component for displaying error or info messages
 * @component
 * @param {Object} props
 * @param {boolean} props.open - Whether the modal is open
 * @param {string} props.title - Modal title
 * @param {string} props.message - Modal message
 * @param {string} props.type - 'error' | 'info' | 'warning' (default: 'error')
 * @param {Function} props.onClose - Callback when closing the modal
 * @returns {React.ReactElement}
 */
const AlertModal = ({ open, title, message, type = 'error', onClose }) => {
	if (!open) return null;

	return (
		<div className="alert-modal-overlay" role="alertdialog" aria-modal="true">
			<div className={`alert-modal alert-modal--${type}`}>
				<div className="alert-modal__header">
					<h3 className="alert-modal__title">{title}</h3>
				</div>
				<div className="alert-modal__body">
					<p className="alert-modal__message">{message}</p>
				</div>
				<div className="alert-modal__actions">
					<button
						type="button"
						className="alert-modal__btn"
						onClick={onClose}
					>
						OK
					</button>
				</div>
			</div>
		</div>
	);
};

AlertModal.propTypes = {
	open: PropTypes.bool.isRequired,
	title: PropTypes.string.isRequired,
	message: PropTypes.string.isRequired,
	type: PropTypes.oneOf(['error', 'info', 'warning']),
	onClose: PropTypes.func.isRequired,
};

AlertModal.defaultProps = {
	type: 'error',
};

export default AlertModal;
