import React from 'react';
import PropTypes from 'prop-types';

import './PanelHeader.css';

/**
 * PanelHeader renders a consistent heading element for primary layout panels.
 * NOTE: Use ActionButton component separately for action buttons to avoid style pollution.
 */
const PanelHeader = ({
  title,
  className,
  icon,
  variant,
  onGetCacheData,
  onManageCriteria,
  onCleanupServer,
  onRestartBackend,
  isCacheLoading,
  isCleanupLoading,
  isRestartLoading,
  children,
}) => {
  const variantClass = variant && variant !== 'panel' ? `panel__header--${variant}` : null;
  const headerClassName = ['panel__header', variantClass, className]
    .filter(Boolean)
    .join(' ');
  const canRequestCache = typeof onGetCacheData === 'function';
  const canManageCriteria = typeof onManageCriteria === 'function';
  const canCleanupServer = typeof onCleanupServer === 'function';
  const canRestartBackend = typeof onRestartBackend === 'function';
  const hasRightContent = Boolean(children) || canRequestCache || canManageCriteria || canCleanupServer || canRestartBackend;

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
          {canCleanupServer && (
            <button
              type="button"
              className="panel__action"
              onClick={onCleanupServer}
              disabled={isCleanupLoading}
            >
              {isCleanupLoading ? 'Cleaning…' : 'Cleanup Server Files'}
            </button>
          )}
          {canRestartBackend && (
            <button
              type="button"
              className="panel__action"
              onClick={onRestartBackend}
              disabled={isRestartLoading}
            >
              {isRestartLoading ? 'Restarting…' : 'Restart Backend'}
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
  onCleanupServer: PropTypes.func,
  onRestartBackend: PropTypes.func,
  isCacheLoading: PropTypes.bool,
  isCleanupLoading: PropTypes.bool,
  isRestartLoading: PropTypes.bool,
  children: PropTypes.node,
};

PanelHeader.defaultProps = {
  className: undefined,
  icon: undefined,
  variant: 'panel',
  onGetCacheData: undefined,
  onManageCriteria: undefined,
  onCleanupServer: undefined,
  onRestartBackend: undefined,
  isCacheLoading: false,
  isCleanupLoading: false,
  isRestartLoading: false,
  children: null,
};

export default PanelHeader;
