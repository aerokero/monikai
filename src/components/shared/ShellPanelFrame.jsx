import React from 'react';
import { X } from '../icons';
import { useMonika } from '../../contexts/MonikaContext';
import { useLanguage } from '../../contexts/LanguageContext';

const ShellPanelFrame = ({
  icon: Icon = null,
  title,
  subtitle = '',
  titleClassName = 'font-serif text-[28px] text-[#f5e6d3] font-normal tracking-wide py-1',
  headerClassName = 'flex items-start justify-between gap-4 border-b border-[#2c1e15] bg-transparent px-6 pt-6 pb-4',
  actions = null,
  children,
  className = '',
  bodyClassName = 'flex flex-col h-full overflow-hidden',
}) => {
  const { setActiveContext } = useMonika();
  const { t } = useLanguage();

  return (
    <section
      className={`flex h-full min-h-0 flex-col overflow-hidden rounded-none border-0 bg-[linear-gradient(180deg,rgba(28,18,12,0.96),rgba(10,7,4,0.98))] backdrop-blur-xl ${className}`}
    >
      <div className={headerClassName}>
        <div className="min-w-0">
          {Icon ? (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#3c2e26] bg-[#1e1612] text-[#de9d50]">
                <Icon size={15} />
              </div>
              <div className="min-w-0">
                <div className={titleClassName}>{title}</div>
                {subtitle ? <div className="mt-0.5 text-xs text-[#8c7769]">{subtitle}</div> : null}
              </div>
            </div>
          ) : (
            <div className="min-w-0">
              <div className={titleClassName}>{title}</div>
              {subtitle ? <div className="mt-0.5 text-xs text-[#8c7769]">{subtitle}</div> : null}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {actions}
          <button
            type="button"
            onClick={() => setActiveContext('chat')}
            title={t('navigation.close_panel')}
            aria-label={t('navigation.close_panel')}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#3c2e26] bg-[#1e1612] text-[#8c7769] transition hover:border-[#4c3a2e] hover:bg-[#2a1f18] hover:text-[#f5e6d3]"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
};

export default ShellPanelFrame;
