/**
 * PanelHeader Component
 * Reusable header for all panel components
 * Displays panel title and control buttons (close, collapse, etc.)
 */

import React from 'react';
import { X, ChevronDown, ChevronUp } from '../icons';

const PanelHeader = ({
  title,
  subtitle = null,
  onClose = null,
  onCollapse = null,
  isCollapsed = false,
  collapsible = true,
  icon: Icon = null,
  className = ''
}) => {
  return (
    <div className={`
      panel-header
      flex items-center justify-between
      px-4 py-3
      border-b border-[rgba(232,178,102,0.12)]
      bg-[rgba(255,238,212,0.045)]
      ${className}
    `}>
      {/* Title Section */}
      <div className="flex items-center gap-3 flex-1 min-w-0">
        {Icon && (
          <Icon size={18} className="text-monika-accent-primary flex-shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-[rgba(255,246,233,0.94)] truncate">
            {title}
          </h3>
          {subtitle && (
            <p className="text-xs text-[rgba(255,224,190,0.5)] truncate">
              {subtitle}
            </p>
          )}
        </div>
      </div>

      {/* Control Buttons */}
      <div className="flex items-center gap-1 flex-shrink-0 ml-2">
        {/* Collapse Button */}
        {collapsible && onCollapse && (
          <button
            onClick={onCollapse}
            className="
              p-1.5 rounded hover:bg-[rgba(232,178,102,0.1)] transition-colors
              text-[rgba(255,240,218,0.62)] hover:text-[rgba(255,246,233,0.94)]
              flex-shrink-0
            "
            aria-label={isCollapsed ? 'Expand panel' : 'Collapse panel'}
            title={isCollapsed ? 'Expand' : 'Collapse'}
          >
            {isCollapsed ? (
              <ChevronUp size={16} />
            ) : (
              <ChevronDown size={16} />
            )}
          </button>
        )}

        {/* Close Button */}
        {onClose && (
          <button
            onClick={onClose}
            className="
              p-1.5 rounded hover:bg-[rgba(232,178,102,0.1)] transition-colors
              text-[rgba(255,240,218,0.62)] hover:text-[rgba(255,246,233,0.94)]
              flex-shrink-0
            "
            aria-label="Close panel"
            title="Close"
          >
            <X size={16} />
          </button>
        )}
      </div>
    </div>
  );
};

export default PanelHeader;
