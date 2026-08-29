import React from 'react';
import { X } from '../icons';
import { useMonika } from '../../contexts/MonikaContext';
import { useLanguage } from '../../contexts/LanguageContext';

const ShellPanelFrame = ({
  icon: Icon = null,
  title,
  subtitle = '',
  titleClassName = 'text-xl font-semibold text-white/95 tracking-tight',
  headerClassName = 'flex items-center justify-between gap-4 border-b border-white/10 bg-black/30 px-6 py-4 backdrop-blur-md shrink-0',
  actions = null,
  children,
  className = '',
  bodyClassName = 'flex flex-col h-full overflow-hidden min-h-0',
}) => {
  const { setActiveContext } = useMonika();
  const { t } = useLanguage();

  return (
    <section
      className={`flex h-full min-h-0 flex-col overflow-hidden rounded-2xl bg-transparent ${className}`}
    >
      <div className={headerClassName}>
        <div className="min-w-0 flex items-center gap-3">
          {Icon && (
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-pink-500/30 bg-pink-950/40 text-pink-300 shadow-md">
              <Icon className="w-4 h-4" />
            </div>
          )}
          <div className="min-w-0">
            <div className={titleClassName}>{title}</div>
            {subtitle ? <div className="text-xs text-white/40 mt-0.5">{subtitle}</div> : null}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {actions}
          <button
            type="button"
            onClick={() => setActiveContext('chat')}
            title={t('navigation.close_panel')}
            aria-label={t('navigation.close_panel')}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-white/60 transition hover:border-pink-500/40 hover:bg-pink-950/30 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
};

export default ShellPanelFrame;
