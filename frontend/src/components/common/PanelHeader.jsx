import React from 'react';
import PropTypes from 'prop-types';

import './PanelHeader.css';

/**
 * PanelHeader renders a consistent heading element for primary layout panels.
 * NOTE: Use ActionButton component separately for action buttons to avoid style pollution.
 */
const PanelHeader = ({ title, className, icon, variant, onGetCacheData, onManageCriteria, isCacheLoading, children }) => {
  const variantClass = variant && variant !== 'panel' ? `panel__header--${variant}` : null;
  const headerClassName = ['panel__header', variantClass, className]
    .filter(Boolean)
    .join(' ');
  const canRequestCache = typeof onGetCacheData === 'function';
  const canManageCriteria = typeof onManageCriteria === 'function';
  const hasRightContent = Boolean(children) || canRequestCache || canManageCriteria;

  return (
    <header className={headerClassName}>
      {icon && (
        <span className="panel__icon" aria-hidden>
          {icon}
        </span>
      )}
      <h2 className="panel__title">{title}</h2>
      {hasRightContent && (
        <div className="panel__controls">
          {children}
          {canManageCriteria && (
            <button
              type="button"
              className="panel__action"
              onClick={onManageCriteria}
            >
              Manage Criteria
            </button>
          )}
          {canRequestCache && (
            <button
              type="button"
              className="panel__action"
              onClick={onGetCacheData}
              disabled={isCacheLoading}
            >
              {isCacheLoading ? 'Loading…' : 'Get Cache Data'}
            </button>
          )}
        </div>
      )}
    </header>
  );
};

PanelHeader.propTypes = {
  title: PropTypes.string.isRequired,
  className: PropTypes.string,
  icon: PropTypes.node,
  variant: PropTypes.oneOf(['page', 'panel']),
  onGetCacheData: PropTypes.func,
  onManageCriteria: PropTypes.func,
  isCacheLoading: PropTypes.bool,
  children: PropTypes.node,
};

PanelHeader.defaultProps = {
  className: undefined,
  icon: undefined,
  variant: 'panel',
  onGetCacheData: undefined,
  onManageCriteria: undefined,
  isCacheLoading: false,
  children: null,
};

export default PanelHeader;
