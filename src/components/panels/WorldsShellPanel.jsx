import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronUp,
  Globe,
  RefreshCw,
  Upload,
} from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import { useLanguage } from '../../contexts/LanguageContext';

const MODES = [
  ['grounded', 'Rzeczywistość', 'Fakty realne mają pierwszeństwo.'],
  ['crossover', 'Crossover', 'Aktywne światy mogą się przenikać.'],
  ['roleplay', 'Roleplay', 'Scenariusz i fikcja prowadzą scenę.'],
  ['ambiguous', 'Niejednoznaczny', 'Monika zachowuje kilka interpretacji.'],
];

const CandidateCard = ({ candidate, lorebooks, busy, onReview }) => {
  const [title, setTitle] = useState(candidate.title);
  const [content, setContent] = useState(candidate.content);
  const [targetBook, setTargetBook] = useState(candidate.target_lorebook_id || '');
  const [resolution, setResolution] = useState('');
  const conflicts = candidate.conflicts_with || [];
  const needsWorld = candidate.target_type !== 'personal_memory';

  return (
    <div className="rounded-xl border border-[#493426] bg-black/15 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide">
        <span className="rounded-full border border-[#5b412d] px-2 py-0.5 text-[#d6a66f]">
          {candidate.target_type}
        </span>
        <span className="text-[#8f7b6d]">
          pewność {Math.round(candidate.confidence * 100)}%
        </span>
        {conflicts.length ? (
          <span className="text-[#d98570]">konflikt: {conflicts.length}</span>
        ) : null}
      </div>
      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        className="w-full rounded-md border border-[#3b2a20] bg-black/25 px-2.5 py-2 text-sm font-semibold text-[#f5e6d3] outline-none focus:border-[#8e643d]"
      />
      <textarea
        value={content}
        onChange={(event) => setContent(event.target.value)}
        rows={3}
        className="mt-2 w-full resize-y rounded-md border border-[#3b2a20] bg-black/25 px-2.5 py-2 text-xs leading-relaxed text-[#d7c1ae] outline-none focus:border-[#8e643d]"
      />
      <div className="mt-2 text-[11px] leading-relaxed text-[#806f63]">
        Źródło: {candidate.source_excerpt || 'brak fragmentu'}
      </div>
      {candidate.rationale ? (
        <div className="mt-1 text-[11px] leading-relaxed text-[#806f63]">
          Powód: {candidate.rationale}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {needsWorld ? (
          <select
            value={targetBook}
            onChange={(event) => setTargetBook(event.target.value)}
            className="min-w-36 rounded-md border border-[#3b2a20] bg-[#17100c] px-2 py-1.5 text-xs text-[#d7c1ae]"
          >
            {candidate.target_type === 'world_lore' ? (
              <option value="reality">Rzeczywistość</option>
            ) : lorebooks
              .filter((book) => ['imported_fiction', 'scenario', 'custom'].includes(book.kind))
              .map((book) => (
                <option key={book.id} value={book.id}>{book.name}</option>
              ))}
          </select>
        ) : null}
        {conflicts.length ? (
          <select
            value={resolution}
            onChange={(event) => setResolution(event.target.value)}
            className="min-w-44 rounded-md border border-[#754536] bg-[#21130f] px-2 py-1.5 text-xs text-[#dfaa98]"
          >
            <option value="">Rozwiąż konflikt…</option>
            {conflicts.map((uid) => (
              <option key={uid} value={uid}>Zastąp {uid}</option>
            ))}
            <option value="keep_both">Zachowaj oba fakty</option>
          </select>
        ) : null}
        <div className="flex-1" />
        <button
          type="button"
          disabled={busy}
          onClick={() => onReview(candidate.id, false)}
          className="rounded-md border border-[#59372e] px-3 py-1.5 text-xs text-[#cb8b7c] hover:bg-[#4a2922]/40 disabled:opacity-50"
        >
          Odrzuć
        </button>
        <button
          type="button"
          disabled={busy || !title.trim() || !content.trim() || (conflicts.length > 0 && !resolution)}
          onClick={() => onReview(candidate.id, true, {
            edits: {
              title: title.trim(),
              content: content.trim(),
              target_lorebook_id: targetBook || undefined,
            },
            supersedes_uid: resolution && resolution !== 'keep_both' ? resolution : undefined,
            keep_conflicts: resolution === 'keep_both',
          })}
          className="rounded-md border border-[#627c4e] bg-[#526942]/30 px-3 py-1.5 text-xs font-medium text-[#bad39f] hover:bg-[#526942]/45 disabled:opacity-40"
        >
          Zaakceptuj
        </button>
      </div>
    </div>
  );
};

const WorldsShellPanel = ({ socket }) => {
  const { t } = useLanguage();
  const fileRef = useRef(null);
  const [state, setState] = useState({
    conversation_id: '',
    lorebooks: [],
    world_stack: {
      reality_mode: 'grounded',
      lorebook_ids: [],
      pinned_entries: [],
      token_budget: null,
    },
    diagnostics: [],
    candidates: [],
  });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!socket) return undefined;
    const onState = (payload) => {
      if (payload) setState(payload);
      setBusy(false);
    };
    const onImported = (payload) => {
      const warnings = payload?.warnings?.length
        ? ` ${payload.warnings.join(' ')}`
        : '';
      setNotice(
        payload?.ok
          ? `Zaimportowano ${payload.entry_count} wpisów.${warnings}`
          : 'Import nie powiódł się.',
      );
      setBusy(false);
    };
    const onDiagnostics = (payload) => {
      setState((current) => ({
        ...current,
        diagnostics: payload?.items || [],
      }));
    };
    const onError = (payload) => {
      setNotice(payload?.error || 'Operacja lorebooka nie powiodła się.');
      setBusy(false);
    };
    const refresh = () => socket.emit('lore_state_get', {});

    socket.on('lore_state', onState);
    socket.on('lore_imported', onImported);
    socket.on('lore_diagnostics', onDiagnostics);
    socket.on('lore_error', onError);
    socket.on('connect', refresh);
    refresh();
    const poll = window.setInterval(refresh, 10000);
    return () => {
      window.clearInterval(poll);
      socket.off('lore_state', onState);
      socket.off('lore_imported', onImported);
      socket.off('lore_diagnostics', onDiagnostics);
      socket.off('lore_error', onError);
      socket.off('connect', refresh);
    };
  }, [socket]);

  const activeIds = state.world_stack?.lorebook_ids || [];
  const activeSet = useMemo(() => new Set(activeIds), [activeIds]);

  const saveStack = (patch) => {
    if (!socket || busy) return;
    setBusy(true);
    setNotice('');
    socket.emit(
      'lore_world_stack_set',
      {
        reality_mode: state.world_stack?.reality_mode || 'grounded',
        lorebook_ids: activeIds,
        pinned_entries: state.world_stack?.pinned_entries || [],
        token_budget: state.world_stack?.token_budget ?? null,
        ...patch,
      },
      (response) => {
        if (response?.ok === false) {
          setNotice(response.error || 'Nie udało się zapisać World Stacka.');
          setBusy(false);
        }
      },
    );
  };

  const toggleBook = (bookId) => {
    const next = activeSet.has(bookId)
      ? activeIds.filter((id) => id !== bookId)
      : [...activeIds, bookId];
    saveStack({ lorebook_ids: next });
  };

  const moveBook = (bookId, direction) => {
    const index = activeIds.indexOf(bookId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= activeIds.length) return;
    const next = [...activeIds];
    [next[index], next[target]] = [next[target], next[index]];
    saveStack({ lorebook_ids: next });
  };

  const importFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !socket) return;
    if (file.size > 10 * 1024 * 1024) {
      setNotice('Plik jest większy niż 10 MiB.');
      return;
    }
    setBusy(true);
    setNotice('');
    try {
      const content = await file.text();
      socket.emit(
        'lore_import',
        {
          file_name: file.name,
          format_hint: file.name.split('.').pop(),
          content,
        },
        (response) => {
          if (response?.ok === false) {
            setNotice(response.error || 'Import nie powiódł się.');
            setBusy(false);
          }
        },
      );
    } catch (error) {
      setNotice(String(error));
      setBusy(false);
    }
  };

  const exportBook = (bookId) => {
    if (!socket) return;
    socket.emit(
      'lore_export',
      { book_id: bookId, format: 'json' },
      (response) => {
        if (!response?.ok) {
          setNotice(response?.error || 'Eksport nie powiódł się.');
          return;
        }
        const blob = new Blob([response.content], {
          type: 'application/json;charset=utf-8',
        });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = response.filename;
        anchor.click();
        URL.revokeObjectURL(url);
      },
    );
  };

  const refreshDiagnostics = () => {
    if (socket) socket.emit('lore_diagnostics_get', { limit: 50 });
  };

  const reviewCandidate = (candidateId, accept, options = {}) => {
    if (!socket || busy) return;
    setBusy(true);
    setNotice('');
    socket.emit(
      'lore_candidate_review',
      {
        candidate_id: candidateId,
        accept,
        ...options,
      },
      (response) => {
        if (response?.ok === false) {
          setNotice(response.error || 'Nie udało się ocenić propozycji.');
          setBusy(false);
        }
      },
    );
  };

  return (
    <ShellPanelFrame
      icon={Globe}
      title={t('worlds.title')}
      subtitle={state.conversation_id ? `Rozmowa: ${state.conversation_id}` : ''}
      actions={(
        <>
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            accept=".json,.yaml,.yml,.md,.markdown"
            onChange={importFile}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="flex items-center gap-2 rounded-lg border border-[#5b412d] bg-[#2b1d14] px-3 py-2 text-xs font-medium text-[#efc78f] transition hover:bg-[#3a271a] disabled:opacity-50"
          >
            <Upload size={14} />
            {t('worlds.import')}
          </button>
        </>
      )}
      bodyClassName="overflow-y-auto px-5 py-4"
    >
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
        {notice ? (
          <div className="rounded-lg border border-[#5b412d] bg-[#2b1d14]/80 px-3 py-2 text-xs leading-relaxed text-[#efc78f]">
            {notice}
          </div>
        ) : null}

        <section>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#9f8878]">
            {t('worlds.mode')}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {MODES.map(([id, label, description]) => {
              const selected = state.world_stack?.reality_mode === id;
              return (
                <button
                  type="button"
                  key={id}
                  disabled={busy}
                  onClick={() => saveStack({ reality_mode: id })}
                  className={`rounded-xl border p-3 text-left transition ${
                    selected
                      ? 'border-[#d69b58] bg-[#d69b58]/10'
                      : 'border-[#3b2a20] bg-black/15 hover:border-[#5b412d]'
                  }`}
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-[#f5e6d3]">
                    <span className={`flex h-5 w-5 items-center justify-center rounded-full border ${
                      selected ? 'border-[#d69b58] bg-[#d69b58] text-[#20160f]' : 'border-[#5a4638]'
                    }`}>
                      {selected ? <Check size={12} /> : null}
                    </span>
                    {label}
                  </div>
                  <div className="mt-1 pl-7 text-xs leading-relaxed text-[#9f8878]">
                    {description}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#9f8878]">
            Propozycje Moniki
          </div>
          <div className="space-y-2">
            {state.candidates?.length ? state.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                lorebooks={state.lorebooks || []}
                busy={busy}
                onReview={reviewCandidate}
              />
            )) : (
              <div className="rounded-xl border border-dashed border-[#3b2a20] p-4 text-center text-xs text-[#77675c]">
                Brak faktów oczekujących na ocenę.
              </div>
            )}
          </div>
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#9f8878]">
                {t('worlds.books')}
              </div>
              <div className="mt-1 text-xs text-[#77675c]">
                Import nie aktywuje świata automatycznie.
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-[#9f8878]">
              Budżet
              <input
                key={state.world_stack?.token_budget ?? 'auto'}
                type="number"
                min="100"
                max="12000"
                step="100"
                defaultValue={state.world_stack?.token_budget || ''}
                placeholder="auto"
                onBlur={(event) => saveStack({
                  token_budget: event.target.value || null,
                })}
                className="w-24 rounded-md border border-[#3b2a20] bg-black/25 px-2 py-1.5 text-[#e8d6c4] outline-none focus:border-[#8e643d]"
              />
            </label>
          </div>

          <div className="space-y-2">
            {state.lorebooks?.length ? state.lorebooks.map((book) => {
              const active = activeSet.has(book.id);
              return (
                <div
                  key={book.id}
                  className={`flex items-center gap-3 rounded-xl border p-3 ${
                    active
                      ? 'border-[#765333] bg-[#d69b58]/[0.07]'
                      : 'border-[#33251d] bg-black/15'
                  }`}
                >
                  <button
                    type="button"
                    disabled={busy || !book.enabled}
                    onClick={() => toggleBook(book.id)}
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border ${
                      active
                        ? 'border-[#d69b58] bg-[#d69b58] text-[#20160f]'
                        : 'border-[#5a4638] text-transparent'
                    }`}
                    aria-label={`${active ? 'Dezaktywuj' : 'Aktywuj'} ${book.name}`}
                  >
                    <Check size={14} />
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-semibold text-[#f5e6d3]">{book.name}</span>
                      <span className="rounded-full border border-[#49362a] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[#a98f7d]">
                        {book.kind}
                      </span>
                      {book.trusted ? (
                        <span className="text-[10px] uppercase tracking-wide text-[#91b878]">trusted</span>
                      ) : null}
                    </div>
                    <div className="mt-1 text-xs text-[#8f7b6d]">
                      {book.entry_count} wpisów · ID: {book.id}
                    </div>
                  </div>
                  {active ? (
                    <div className="flex flex-col">
                      <button
                        type="button"
                        disabled={busy || activeIds.indexOf(book.id) === 0}
                        onClick={() => moveBook(book.id, -1)}
                        className="rounded p-0.5 text-[#8f7b6d] hover:text-[#efd4b5] disabled:opacity-20"
                        aria-label={`Przesuń ${book.name} wyżej`}
                      >
                        <ChevronUp size={14} />
                      </button>
                      <button
                        type="button"
                        disabled={busy || activeIds.indexOf(book.id) === activeIds.length - 1}
                        onClick={() => moveBook(book.id, 1)}
                        className="rounded p-0.5 text-[#8f7b6d] hover:text-[#efd4b5] disabled:opacity-20"
                        aria-label={`Przesuń ${book.name} niżej`}
                      >
                        <ChevronDown size={14} />
                      </button>
                    </div>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => exportBook(book.id)}
                    className="rounded-md border border-[#3b2a20] px-2.5 py-1.5 text-xs text-[#bca18d] hover:border-[#6a4b34] hover:text-[#efd4b5]"
                  >
                    JSON
                  </button>
                </div>
              );
            }) : (
              <div className="rounded-xl border border-dashed border-[#3b2a20] p-6 text-center text-sm text-[#8f7b6d]">
                {t('worlds.empty')}
              </div>
            )}
          </div>
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#9f8878]">
              {t('worlds.diagnostics')}
            </div>
            <button
              type="button"
              onClick={refreshDiagnostics}
              className="flex items-center gap-1.5 text-xs text-[#aa8d77] hover:text-[#efd4b5]"
            >
              <RefreshCw size={13} />
              Odśwież
            </button>
          </div>
          <div className="overflow-hidden rounded-xl border border-[#33251d]">
            {state.diagnostics?.length ? state.diagnostics.map((item, index) => (
              <div
                key={`${item.created_at}-${item.entry_uid}-${index}`}
                className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-3 border-b border-[#2c2019] px-3 py-2 text-xs last:border-b-0"
              >
                <div className="truncate text-[#d7c1ae]">{item.entry_uid}</div>
                <div className="text-[#927a69]">{item.reason}</div>
                <div className={item.included ? 'text-[#91b878]' : 'text-[#c77d6d]'}>
                  {item.included ? 'użyty' : 'pominięty'} · {item.score.toFixed(1)}
                </div>
              </div>
            )) : (
              <div className="p-5 text-center text-xs text-[#77675c]">
                Brak aktywacji w tej rozmowie.
              </div>
            )}
          </div>
        </section>
      </div>
    </ShellPanelFrame>
  );
};

export default WorldsShellPanel;
