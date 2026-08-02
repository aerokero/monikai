/**
 * Shared panel primitives.
 * One canonical Card / Badge / form-field / section-label implementation
 * so every rail panel is built from the same pieces instead of each
 * hand-rolling its own variant of the same idea.
 */

import React from 'react';
import { ChevronDown, ChevronRight, Check } from '../icons';

// Uppercase tracked-wide label that introduces a block of content.
export const SectionLabel = ({ children, action = null, className = '' }) => (
  <div className={`mb-2 flex items-center justify-between gap-3 ${className}`}>
    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8c7769]">
      {children}
    </div>
    {action}
  </div>
);

// Bordered surface used for list items, tiles, and grouped content blocks.
export const Card = React.forwardRef(({
  as: Tag = 'div',
  interactive = false,
  selected = false,
  className = '',
  children,
  ...rest
}, ref) => (
  <Tag
    ref={ref}
    className={`rounded-xl border transition-colors ${
      selected
        ? 'border-[#de9d50]/60 bg-[#de9d50]/[0.08]'
        : 'border-[#2c1e15] bg-[#140d08]/40'
    } ${interactive ? 'text-left hover:border-[#3c2e26] hover:bg-[#140d08]/60' : ''} ${className}`}
    {...rest}
  >
    {children}
  </Tag>
));

// A single bordered container that holds a list of ListRow children,
// dividing them with hairlines instead of boxing each row individually —
// this is the "one card, many rows" shape Settings/menu lists actually use.
export const ListContainer = ({ children, className = '' }) => (
  <div className={`divide-y divide-[#2c1e15] overflow-hidden rounded-xl border border-[#2c1e15] bg-[#140d08]/30 ${className}`}>
    {children}
  </div>
);

// One flat row inside a ListContainer (or standalone): plain icon, title,
// optional description, optional trailing content. No per-row box, no
// icon badge — the thing ChatGPT/Claude/Gemini menus actually look like.
export const ListRow = ({
  as,
  icon: Icon,
  leading = null,
  title,
  description,
  trailing = null,
  showChevron = false,
  className = '',
  ...rest
}) => {
  const Tag = as || (rest.onClick ? 'button' : 'div');
  return (
    <Tag
      type={Tag === 'button' ? 'button' : undefined}
      className={`flex w-full items-center gap-3 px-4 py-3 text-left transition-colors ${
        rest.onClick ? 'cursor-pointer hover:bg-white/[0.03]' : ''
      } ${className}`}
      {...rest}
    >
      {leading ?? (Icon ? <Icon size={16} className="shrink-0 text-[#8c7769]" /> : null)}
      <div className="min-w-0 flex-1">
        <div className="text-sm text-[#f5e6d3]">{title}</div>
        {description ? <div className="mt-0.5 text-xs leading-relaxed text-[#8c7769]">{description}</div> : null}
      </div>
      {trailing}
      {showChevron ? <ChevronRight size={15} className="shrink-0 text-[#8c7769]/60" /> : null}
    </Tag>
  );
};

const BADGE_TONES = {
  amber: 'border-[rgba(222,157,80,0.3)] bg-[rgba(222,157,80,0.12)] text-[#efc78f]',
  green: 'border-[rgba(146,174,126,0.38)] bg-[rgba(126,166,104,0.15)] text-[#a8c896]',
  red: 'border-[rgba(202,104,85,0.34)] bg-[rgba(166,72,58,0.14)] text-[#df8978]',
  neutral: 'border-[#3c2e26] bg-white/[0.04] text-[#8c7769]',
};

// Small status pill — "Active", "current", "trusted", etc.
export const Badge = ({ tone = 'amber', children, className = '' }) => (
  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] ${BADGE_TONES[tone]} ${className}`}>
    {children}
  </span>
);

// Pill segmented control — view switchers and tab bars.
export const SegmentedTabs = ({ options, value, onChange, className = '' }) => (
  <div className={`flex gap-1 rounded-full border border-[#3c2e26] bg-[#1e1612] p-1 ${className}`}>
    {options.map((opt) => {
      const Icon = opt.icon;
      return (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-full py-1.5 px-2 text-xs font-semibold transition-colors ${
            value === opt.value ? 'bg-[#de9d50] text-[#16100d]' : 'text-[#8c7769] hover:text-[#f5e6d3]'
          }`}
        >
          {Icon ? <Icon size={13} /> : null}
          {opt.label}
        </button>
      );
    })}
  </div>
);

export const FieldLabel = ({ children }) => (
  <label className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8c7769]">{children}</label>
);

// Field sizing is a closed set of variants (not a className you append) —
// Tailwind utility precedence depends on generated CSS order, not on where
// a class sits in the string, so "px-3 ... px-2" is not a safe override.
const FIELD_BASE = 'rounded-lg border border-[#3c2e26] bg-[#1e1612] text-[#f5e6d3] placeholder-[#8c7769]/50 outline-none transition-colors focus:border-[#de9d50]';
const FIELD_SIZES = {
  md: 'w-full px-3 py-2 text-sm',
  sm: 'w-full px-2.5 py-1.5 text-xs',
};
const SELECT_SIZES = {
  md: 'w-full px-3 py-2 pr-8 text-sm',
  sm: 'w-full px-2.5 py-1.5 pr-7 text-xs',
};

export const TextField = React.forwardRef(({ label, size = 'md', className = '', wrapperClassName = '', ...rest }, ref) => (
  <div className={`flex flex-col gap-1.5 ${wrapperClassName}`}>
    {label ? <FieldLabel>{label}</FieldLabel> : null}
    <input ref={ref} className={`${FIELD_BASE} ${FIELD_SIZES[size]} ${className}`} {...rest} />
  </div>
));

export const TextAreaField = React.forwardRef(({ label, size = 'md', className = '', wrapperClassName = '', ...rest }, ref) => (
  <div className={`flex flex-col gap-1.5 ${wrapperClassName}`}>
    {label ? <FieldLabel>{label}</FieldLabel> : null}
    <textarea ref={ref} className={`${FIELD_BASE} ${FIELD_SIZES[size]} resize-none ${className}`} {...rest} />
  </div>
));

export const SelectField = ({ label, options, size = 'md', className = '', wrapperClassName = '', ...rest }) => (
  <div className={`flex flex-col gap-1.5 ${wrapperClassName}`}>
    {label ? <FieldLabel>{label}</FieldLabel> : null}
    <div className="relative">
      <select
        className={`appearance-none ${FIELD_BASE} ${SELECT_SIZES[size]} ${className}`}
        {...rest}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      <ChevronDown size={size === 'sm' ? 11 : 13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8c7769]" />
    </div>
  </div>
);

// On/off switch — one implementation shared by Settings, Profile, Calendar.
export const Toggle = ({ checked, onChange, disabled = false }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={`relative h-6 w-11 shrink-0 rounded-full transition-colors focus:outline-none disabled:opacity-40 ${
      checked ? 'bg-[#de9d50]' : 'bg-[#251c17]'
    }`}
  >
    <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition-transform ${checked ? 'translate-x-[22px]' : 'translate-x-1'}`} />
  </button>
);

// Checkbox — square variant of Toggle, for the same on/off idea when a
// switch would be too heavy (inline form options, "install globally", etc).
export const Checkbox = ({ checked, onChange, label, disabled = false, className = '' }) => (
  <label className={`flex items-center gap-2 text-xs text-[#8c7769] ${disabled ? 'opacity-50' : 'cursor-pointer select-none'} ${className}`}>
    <span className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border transition-colors ${
      checked ? 'border-[#de9d50] bg-[#de9d50]' : 'border-[#3c2e26] bg-[#1e1612]'
    }`}>
      {checked ? <Check size={10} className="text-[#16100d]" /> : null}
    </span>
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      disabled={disabled}
      className="hidden"
    />
    {label}
  </label>
);

// Centered muted placeholder for empty lists/results.
export const EmptyState = ({ children, className = '' }) => (
  <div className={`rounded-xl border border-dashed border-[#2c1e15] px-4 py-8 text-center text-xs leading-relaxed text-[#8c7769]/80 ${className}`}>
    {children}
  </div>
);

// A settings/profile-style row: label + description on the left, control on the right.
export const FieldRow = ({ title, description, children }) => (
  <div className="flex items-center justify-between gap-4 border-b border-[#2c1e15] py-3.5 last:border-0">
    <div className="flex min-w-0 flex-1 flex-col">
      <span className="text-[13px] font-semibold text-[#f5e6d3]">{title}</span>
      {description ? <span className="mt-0.5 text-[11px] leading-relaxed text-[#8c7769]">{description}</span> : null}
    </div>
    <div className="flex shrink-0 items-center justify-end">{children}</div>
  </div>
);

// A read-only label/value pair — used by profile-style summary views.
export const SummaryField = ({ label, value }) => (
  <div className="flex items-baseline justify-between gap-4 border-b border-[#2c1e15] py-2.5 last:border-0">
    <span className="shrink-0 text-xs text-[#8c7769]">{label}</span>
    <span className="text-right text-sm text-[#f5e6d3]">{value}</span>
  </div>
);
