import React from 'react';
import PropTypes from 'prop-types';
import './VerticalTabs.css';

// Generic vertical tabs component. It renders a nav with the given
// containerClassName so existing styles like `config-vertical-tabs`
// continue to work. If no containerClassName is provided it falls back
// to `vertical-tabs` which is styled by VerticalTabs.css.
const VerticalTabs = ({
  items,
  activeKey,
  onChange,
  containerClassName = 'vertical-tabs',
}) => {
  const container = containerClassName || 'vertical-tabs';

  return (
    <nav className={container}>
      {items.map((it) => {
        const Icon = it.icon;
        return (
          <button
            key={it.key}
            type="button"
            className={`${container}__item ${activeKey === it.key ? `${container}__item--active` : ''}`}
            onClick={() => onChange(it.key)}
            title={it.title || it.label}
          >
            {Icon ? <Icon /> : null}
            <span className={`${container}__label`}>{it.label}</span>
          </button>
        );
      })}
    </nav>
  );
};

VerticalTabs.propTypes = {
  items: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      icon: PropTypes.oneOfType([PropTypes.func, PropTypes.object]),
      title: PropTypes.string,
    }),
  ).isRequired,
  activeKey: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  containerClassName: PropTypes.string,
};

VerticalTabs.defaultProps = {
  activeKey: undefined,
  containerClassName: 'vertical-tabs',
};

export default VerticalTabs;



