import React, { useLayoutEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';

import './HistoryTabs.css';

const HistoryTabs = ({ items, activeId, onSelect, onClose, closable, fullWidth }) => {
  const tabRefs = useRef(new Map());
  const [closingTabs, setClosingTabs] = useState({});

  useLayoutEffect(() => {
    setClosingTabs((prev) => {
      const next = { ...prev };

      Object.keys(next).forEach((id) => {
        if (!items.some((item) => item.id === id)) {
          delete next[id];
        }
      });

      return next;
    });
  }, [items]);

  if (!items.length) {
    return null;
  }

  const requestClose = (id) => {
    if (closingTabs[id]) {
      return;
    }

    const node = tabRefs.current.get(id);

    if (!node) {
      onClose(id);
      return;
    }

    const width = node.getBoundingClientRect().width;

    setClosingTabs((prev) => ({
      ...prev,
      [id]: { width, closing: false },
    }));

    requestAnimationFrame(() => {
      setClosingTabs((prev) => {
        const current = prev[id];

        if (!current) {
          return prev;
        }

        return {
          ...prev,
          [id]: { ...current, closing: true },
        };
      });
    });
  };

  const handleTransitionEnd = (event, id) => {
    if (event.propertyName !== 'width') {
      return;
    }

    if (!closingTabs[id]) {
      return;
    }

    setClosingTabs((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });

    onClose(id);
  };

  const setTabRef = (id) => (node) => {
    if (node) {
      tabRefs.current.set(id, node);
    } else {
      tabRefs.current.delete(id);
    }
  };

  const navClassName = [
    'history-tabs',
    fullWidth && 'history-tabs--full',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <nav className={navClassName} aria-label="Experiment and trajectory history">
      <ul className="history-tabs__list">
        {items.map((item) => {
          const isActive = item.id === activeId;
          const closingInfo = closingTabs[item.id];
          const itemStyle = closingInfo
            ? {
                width: `${closingInfo.closing ? 0 : closingInfo.width}px`,
                opacity: closingInfo.closing ? 0 : 1,
                transition: 'width 220ms cubic-bezier(0.4, 0, 0.2, 1), opacity 160ms ease',
              }
            : undefined;

          return (
            <li
              key={item.id}
              className={[
                'history-tabs__item',
                closingInfo && 'history-tabs__item--closing',
              ]
                .filter(Boolean)
                .join(' ')}
              ref={setTabRef(item.id)}
              style={itemStyle}
              onTransitionEnd={(event) => handleTransitionEnd(event, item.id)}
            >
              <button
                type="button"
                className={[
                  'history-tabs__button',
                  isActive && 'history-tabs__button--active',
                  closingInfo && 'history-tabs__button--closing',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => {
                  if (closingInfo) {
                    return;
                  }

                  onSelect(item.id);
                }}
              >
                <span className="history-tabs__label">{item.label}</span>
                {item.description && (
                  <span className="history-tabs__description">{item.description}</span>
                )}
                {closable && (
                  <span
                    role="button"
                    tabIndex={0}
                    className="history-tabs__close"
                    aria-label={`Close ${item.label}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      requestClose(item.id);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        event.stopPropagation();
                        requestClose(item.id);
                      }
                    }}
                  >
                    ×
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};

HistoryTabs.propTypes = {
  items: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      description: PropTypes.string,
    }),
  ),
  activeId: PropTypes.string,
  onSelect: PropTypes.func,
  onClose: PropTypes.func,
  closable: PropTypes.bool,
  fullWidth: PropTypes.bool,
};

HistoryTabs.defaultProps = {
  items: [],
  activeId: undefined,
  onSelect: () => {},
  onClose: () => {},
  closable: true,
  fullWidth: false,
};

export default HistoryTabs;
