import React from 'react';

const ShellPanelFrame = ({
  icon: Icon = null,
  title,
  subtitle = '',
  actions = null,
  children,
  className = '',
  bodyClassName = '',
}) => {
  return (
    <section
      className={`flex h-full min-h-0 flex-col overflow-hidden rounded-[10px] border border-[rgba(232,178,102,0.14)] bg-[linear-gradient(180deg,rgba(35,25,17,0.72),rgba(14,10,7,0.88))] shadow-[0_18px_55px_rgba(13,9,6,0.32)] backdrop-blur-xl ${className}`}
    >
      <div className="flex items-start justify-between gap-4 border-b border-[rgba(232,178,102,0.12)] bg-[rgba(255,238,212,0.04)] px-4 py-3.5">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            {Icon ? (
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[rgba(232,178,102,0.16)] bg-[rgba(232,178,102,0.08)] text-[rgba(255,246,233,0.9)]">
                <Icon size={16} />
              </div>
            ) : null}
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold tracking-wide text-white/92">{title}</div>
              {subtitle ? <div className="mt-0.5 text-[11px] text-white/48">{subtitle}</div> : null}
            </div>
          </div>
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>

      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
};

export default ShellPanelFrame;
