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
import { SectionLabel, Card, Badge, TextField, TextAreaField, SelectField, EmptyState, ListContainer, ListRow } from '../shared/panelPrimitives';

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

  const bookOptions = candidate.target_type === 'world_lore'
    ? [{ value: 'reality', label: 'Rzeczywistość' }]
    : lorebooks
      .filter((book) => ['imported_fiction', 'scenario', 'custom'].includes(book.kind))
      .map((book) => ({ value: book.id, label: book.name }));

  const conflictOptions = [
    { value: '', label: 'Rozwiąż konflikt…' },
    ...conflicts.map((uid) => ({ value: uid, label: `Zastąp ${uid}` })),
    { value: 'keep_both', label: 'Zachowaj oba fakty' },
  ];

  return (
    <Card className="p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge tone="amber">{candidate.target_type}</Badge>
        <span className="text-[11px] text-[#8c7769]">
          pewność {Math.round(candidate.confidence * 100)}%
        </span>
        {conflicts.length ? (
          <Badge tone="red">konflikt: {conflicts.length}</Badge>
        ) : null}
      </div>
      <TextField value={title} onChange={(event) => setTitle(event.target.value)} className="font-semibold" />
      <TextAreaField
        value={content}
        onChange={(event) => setContent(event.target.value)}
        rows={3}
        size="sm"
        className="leading-relaxed"
        wrapperClassName="mt-2"
      />
      <div className="mt-2 text-[11px] leading-relaxed text-[#8c7769]">
        Źródło: {candidate.source_excerpt || 'brak fragmentu'}
      </div>
      {candidate.rationale ? (
        <div className="mt-1 text-[11px] leading-relaxed text-[#8c7769]">
          Powód: {candidate.rationale}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {needsWorld ? (
          <SelectField
            value={targetBook}
            onChange={(event) => setTargetBook(event.target.value)}
            options={bookOptions}
            size="sm"
            wrapperClassName="min-w-36"
          />
        ) : null}
        {conflicts.length ? (
          <SelectField
            value={resolution}
            onChange={(event) => setResolution(event.target.value)}
            options={conflictOptions}
            size="sm"
            wrapperClassName="min-w-44"
          />
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
    </Card>
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
          <SectionLabel>{t('worlds.mode')}</SectionLabel>
          <ListContainer>
            {MODES.map(([id, label, description]) => {
              const selected = state.world_stack?.reality_mode === id;
              return (
                <ListRow
                  key={id}
                  disabled={busy}
                  onClick={() => saveStack({ reality_mode: id })}
                  className={selected ? 'bg-[#de9d50]/[0.06]' : ''}
                  title={label}
                  description={description}
                  trailing={(
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                      selected ? 'border-[#d69b58] bg-[#d69b58] text-[#20160f]' : 'border-[#5a4638]'
                    }`}>
                      {selected ? <Check size={12} /> : null}
                    </span>
                  )}
                />
              );
            })}
          </ListContainer>
        </section>

        <section>
          <SectionLabel>Propozycje Moniki</SectionLabel>
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
              <EmptyState>Brak faktów oczekujących na ocenę.</EmptyState>
            )}
          </div>
        </section>

        <section>
          <SectionLabel
            action={(
              <label className="flex items-center gap-2 text-xs text-[#8c7769]">
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
                  className="w-24 rounded-md border border-[#3c2e26] bg-[#1e1612] px-2 py-1.5 text-[#f5e6d3] outline-none focus:border-[#de9d50]"
                />
              </label>
            )}
          >
            {t('worlds.books')}
          </SectionLabel>
          <div className="mb-2 text-xs text-[#8c7769]">
            Import nie aktywuje świata automatycznie.
          </div>

          {state.lorebooks?.length ? (
            <ListContainer>
              {state.lorebooks.map((book) => {
                const active = activeSet.has(book.id);
                return (
                  <ListRow
                    key={book.id}
                    leading={(
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
                    )}
                    title={(
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="truncate font-semibold">{book.name}</span>
                        <Badge tone="neutral">{book.kind}</Badge>
                        {book.trusted ? <Badge tone="green">trusted</Badge> : null}
                      </span>
                    )}
                    description={`${book.entry_count} wpisów · ID: ${book.id}`}
                    trailing={(
                      <div className="flex shrink-0 items-center gap-1">
                        {active ? (
                          <div className="flex flex-col">
                            <button
                              type="button"
                              disabled={busy || activeIds.indexOf(book.id) === 0}
                              onClick={() => moveBook(book.id, -1)}
                              className="rounded p-0.5 text-[#8c7769] hover:text-[#efd4b5] disabled:opacity-20"
                              aria-label={`Przesuń ${book.name} wyżej`}
                            >
                              <ChevronUp size={14} />
                            </button>
                            <button
                              type="button"
                              disabled={busy || activeIds.indexOf(book.id) === activeIds.length - 1}
                              onClick={() => moveBook(book.id, 1)}
                              className="rounded p-0.5 text-[#8c7769] hover:text-[#efd4b5] disabled:opacity-20"
                              aria-label={`Przesuń ${book.name} niżej`}
                            >
                              <ChevronDown size={14} />
                            </button>
                          </div>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => exportBook(book.id)}
                          className="rounded-md border border-[#3c2e26] px-2.5 py-1.5 text-xs text-[#8c7769] hover:border-[#5b412d] hover:text-[#efd4b5]"
                        >
                          JSON
                        </button>
                      </div>
                    )}
                  />
                );
              })}
            </ListContainer>
          ) : (
            <EmptyState>{t('worlds.empty')}</EmptyState>
          )}
        </section>

        <section>
          <SectionLabel
            action={(
              <button
                type="button"
                onClick={refreshDiagnostics}
                className="flex items-center gap-1.5 text-xs text-[#8c7769] hover:text-[#efd4b5]"
              >
                <RefreshCw size={13} />
                Odśwież
              </button>
            )}
          >
            {t('worlds.diagnostics')}
          </SectionLabel>
          <ListContainer>
            {state.diagnostics?.length ? state.diagnostics.map((item, index) => (
              <div
                key={`${item.created_at}-${item.entry_uid}-${index}`}
                className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-3 px-4 py-2.5 text-xs"
              >
                <div className="truncate text-[#8c7769]">{item.entry_uid}</div>
                <div className="text-[#8c7769]">{item.reason}</div>
                <div className={item.included ? 'text-[#a8c896]' : 'text-[#df8978]'}>
                  {item.included ? 'użyty' : 'pominięty'} · {item.score.toFixed(1)}
                </div>
              </div>
            )) : (
              <div className="p-5 text-center text-xs text-[#8c7769]/70">
                Brak aktywacji w tej rozmowie.
              </div>
            )}
          </ListContainer>
        </section>
      </div>
    </ShellPanelFrame>
  );
};

export default WorldsShellPanel;
