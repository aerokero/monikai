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
      className={`flex h-full min-h-0 flex-col overflow-hidden rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,rgba(30,18,36,0.72),rgba(12,10,16,0.88))] shadow-[0_18px_55px_rgba(0,0,0,0.28)] backdrop-blur-xl ${className}`}
    >
      <div className="flex items-start justify-between gap-4 border-b border-white/10 bg-white/[0.04] px-4 py-3.5">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            {Icon ? (
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/12 bg-white/[0.08] text-white/90">
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
