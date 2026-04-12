/**
 * PanelHeader Component
 * Reusable header for all panel components
 * Displays panel title and control buttons (close, collapse, etc.)
 */

import React from 'react';
import { X, ChevronDown, ChevronUp } from 'lucide-react';

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
      border-b border-white/10
      bg-white/5
      ${className}
    `}>
      {/* Title Section */}
      <div className="flex items-center gap-3 flex-1 min-w-0">
        {Icon && (
          <Icon size={18} className="text-monika-accent-primary flex-shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-white/90 truncate">
            {title}
          </h3>
          {subtitle && (
            <p className="text-xs text-white/50 truncate">
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
              p-1.5 rounded hover:bg-white/10 transition-colors
              text-white/60 hover:text-white/90
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
              p-1.5 rounded hover:bg-white/10 transition-colors
              text-white/60 hover:text-white/90
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
