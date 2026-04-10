import React from 'react';

const AdaptiveCommandRail = ({ items = [], title = 'Command Rail' }) => {
  return (
    <nav className="adaptive-command-rail" aria-label={title}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={item.onClick}
          className={`adaptive-command-rail__button ${item.active ? 'is-active' : ''}`}
          title={item.title || item.label}
          aria-pressed={item.active ? 'true' : 'false'}
        >
          <span className="adaptive-command-rail__icon">{item.icon}</span>
          <span className="adaptive-command-rail__label">{item.label}</span>
        </button>
      ))}
    </nav>
  );
};

export default AdaptiveCommandRail;
