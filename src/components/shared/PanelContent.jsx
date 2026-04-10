/**
 * PanelContent Component
 * Reusable scrollable content container for all panels
 * Handles overflow, padding, and responsive sizing
 */

import React from 'react';

const PanelContent = ({
  children,
  className = '',
  scrollable = true,
  padded = true,
  gap = true
}) => {
  return (
    <div className={`
      panel-content
      ${scrollable ? 'overflow-y-auto' : 'overflow-hidden'}
      ${padded ? 'px-4 py-3' : ''}
      ${gap ? 'space-y-4' : ''}
      flex-1
      ${className}
    `}>
      {children}
    </div>
  );
};

export default PanelContent;
