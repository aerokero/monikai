import React, { useState, useEffect } from 'react';
import { FileText, Sparkles, Check, X, Plus, RefreshCw, Layers, Clock, ArrowRight } from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import { Badge } from '../shared/panelPrimitives';

const DocsShellPanel = ({ socket }) => {
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [currentDoc, setCurrentDoc] = useState(null);
  const [docContent, setDocContent] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [aiInstruction, setAiInstruction] = useState('');
  const [isAiEditing, setIsAiEditing] = useState(false);
  const [activeDiff, setActiveDiff] = useState(null);
  const [saving, setSaving] = useState(false);

  const fetchDocs = async () => {
    try {
      const res = await fetch('/api/v1/docs/list');
      const data = await res.json();
      if (data.documents) {
        setDocuments(data.documents);
        if (!selectedDocId && data.documents.length > 0) {
          loadDoc(data.documents[0].id);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchDocs();
  }, []);

  const loadDoc = async (id) => {
    setSelectedDocId(id);
    setActiveDiff(null);
    try {
      const res = await fetch(`/api/v1/docs/get/${id}`);
      const data = await res.json();
      if (data.ok) {
        setCurrentDoc(data.document);
        setDocContent(data.document.content);
        if (data.document.pending_diff) {
          setActiveDiff(data.document.pending_diff);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateDoc = async () => {
    if (!newTitle.trim()) return;
    try {
      const res = await fetch('/api/v1/docs/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim(), content: `# ${newTitle.trim()}\n\nRozpocznij pisanie...` }),
      });
      const data = await res.json();
      if (data.ok) {
        setNewTitle('');
        setIsCreating(false);
        await fetchDocs();
        loadDoc(data.document.id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSaveDoc = async () => {
    if (!selectedDocId) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/docs/update/${selectedDocId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: docContent, commit_message: 'Ręczna edycja' }),
      });
      const data = await res.json();
      if (data.ok) {
        setCurrentDoc(data.document);
        fetchDocs();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const handleAiEdit = async () => {
    if (!selectedDocId || !aiInstruction.trim() || isAiEditing) return;
    setIsAiEditing(true);
    try {
      const res = await fetch(`/api/v1/docs/ai_edit/${selectedDocId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: aiInstruction.trim() }),
      });
      const data = await res.json();
      if (data.ok && data.diff) {
        setActiveDiff(data.diff);
        setAiInstruction('');
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsAiEditing(false);
    }
  };

  const handleAcceptDiff = async () => {
    if (!selectedDocId) return;
    try {
      const res = await fetch(`/api/v1/docs/accept_diff/${selectedDocId}`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        setCurrentDoc(data.document);
        setDocContent(data.document.content);
        setActiveDiff(null);
        fetchDocs();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleRejectDiff = async () => {
    if (!selectedDocId) return;
    try {
      await fetch(`/api/v1/docs/reject_diff/${selectedDocId}`, { method: 'POST' });
      setActiveDiff(null);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <ShellPanelFrame icon={FileText} title="Dokumenty AI (Odysseus Docs)">
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar: Document List */}
        <div className="w-64 border-r border-white/10 p-4 flex flex-col bg-black/20">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold uppercase text-white/50 tracking-wider">Dokumenty</span>
            <button
              onClick={() => setIsCreating(true)}
              className="p-1.5 rounded-lg bg-pink-600/30 hover:bg-pink-600/50 text-pink-300 transition"
              title="Nowy dokument"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          {isCreating && (
            <div className="mb-3 p-2 rounded-lg bg-black/40 border border-pink-500/30 space-y-2">
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Tytuł dokumentu..."
                className="w-full px-2 py-1 text-xs bg-black/50 border border-white/10 rounded text-white focus:outline-none focus:border-pink-500"
                autoFocus
              />
              <div className="flex justify-end gap-1">
                <button onClick={() => setIsCreating(false)} className="px-2 py-0.5 text-xs text-white/60 hover:text-white">Anuluj</button>
                <button onClick={handleCreateDoc} className="px-2 py-0.5 text-xs bg-pink-600 text-white rounded hover:bg-pink-500">Stwórz</button>
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto space-y-1.5 custom-scrollbar">
            {documents.map((d) => (
              <div
                key={d.id}
                onClick={() => loadDoc(d.id)}
                className={`p-2.5 rounded-lg cursor-pointer transition text-xs ${
                  selectedDocId === d.id ? 'bg-pink-600/20 border border-pink-500/40 text-white font-medium' : 'hover:bg-white/5 text-white/70 border border-transparent'
                }`}
              >
                <div className="truncate">{d.title}</div>
                <div className="text-[10px] text-white/40 mt-1 flex items-center justify-between">
                  <span>{d.char_count} znaków</span>
                  {d.has_pending_diff && <Badge tone="amber">Diff</Badge>}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Area: Document Editor & Diff View */}
        <div className="flex-1 flex flex-col overflow-hidden bg-black/10">
          {currentDoc ? (
            <>
              {/* Header */}
              <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/20">
                <div>
                  <div className="text-base font-semibold text-white/95">{currentDoc.title}</div>
                  <div className="text-xs text-white/40 mt-0.5">
                    Rewizja v{currentDoc.revisions?.length || 1} • Ostatnia zmiana: {currentDoc.updated_at?.slice(0, 19).replace('T', ' ')}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSaveDoc}
                    disabled={saving}
                    className="px-3.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-white text-xs font-medium transition"
                  >
                    {saving ? 'Zapisywanie...' : 'Zapisz'}
                  </button>
                </div>
              </div>

              {/* AI Instruction Bar */}
              <div className="p-3 border-b border-white/10 bg-pink-950/10 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-pink-400 shrink-0" />
                <input
                  type="text"
                  value={aiInstruction}
                  onChange={(e) => setAiInstruction(e.target.value)}
                  placeholder="Poproś Monikę o edycję (np. 'Rozbuduj sekcję wniosków', 'Popraw styl i błędy')..."
                  className="flex-1 px-3 py-1.5 text-xs bg-black/40 border border-white/10 rounded-lg text-white placeholder:text-white/40 focus:outline-none focus:border-pink-500/50"
                  onKeyDown={(e) => e.key === 'Enter' && handleAiEdit()}
                />
                <button
                  onClick={handleAiEdit}
                  disabled={isAiEditing || !aiInstruction.trim()}
                  className="px-3 py-1.5 rounded-lg bg-gradient-to-r from-pink-600 to-purple-600 text-white text-xs font-medium hover:opacity-90 disabled:opacity-50 transition flex items-center gap-1.5"
                >
                  {isAiEditing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  <span>Zaproponuj Diff</span>
                </button>
              </div>

              {/* Main Content Area: Diff Reviewer or Textarea */}
              <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                {activeDiff ? (
                  <div className="space-y-4">
                    {/* Diff Header / Action Banner */}
                    <div className="p-4 rounded-xl bg-purple-950/30 border border-purple-500/40 flex items-center justify-between">
                      <div>
                        <div className="font-semibold text-purple-200 text-sm flex items-center gap-2">
                          <Sparkles className="w-4 h-4 text-pink-400" />
                          <span>Propozycja zmian AI (+{activeDiff.additions} / -{activeDiff.deletions})</span>
                        </div>
                        <div className="text-xs text-white/70 mt-1">{activeDiff.explanation}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleRejectDiff}
                          className="px-3 py-1.5 rounded-lg bg-red-600/30 hover:bg-red-600/50 text-red-300 text-xs font-medium transition flex items-center gap-1"
                        >
                          <X className="w-3.5 h-3.5" />
                          <span>Odrzuć</span>
                        </button>
                        <button
                          onClick={handleAcceptDiff}
                          className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition flex items-center gap-1"
                        >
                          <Check className="w-3.5 h-3.5" />
                          <span>Zatwierdź i Zastosuj</span>
                        </button>
                      </div>
                    </div>

                    {/* Unified Diff View */}
                    <div className="p-4 rounded-xl bg-black/60 border border-white/10 font-mono text-xs overflow-x-auto space-y-0.5">
                      {activeDiff.unified_diff.split('\n').map((line, idx) => {
                        let bg = 'text-white/80';
                        if (line.startsWith('+') && !line.startsWith('+++')) bg = 'bg-emerald-950/60 text-emerald-300 px-1 rounded';
                        else if (line.startsWith('-') && !line.startsWith('---')) bg = 'bg-red-950/60 text-red-300 px-1 rounded';
                        else if (line.startsWith('@')) bg = 'text-purple-400 font-bold';
                        return (
                          <div key={idx} className={bg}>
                            {line || '\u00A0'}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <textarea
                    value={docContent}
                    onChange={(e) => setDocContent(e.target.value)}
                    className="w-full h-full min-h-[400px] p-4 bg-transparent border-0 text-white font-mono text-sm leading-relaxed focus:outline-none resize-none custom-scrollbar"
                    placeholder="Wpisz treść dokumentu..."
                  />
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-white/40 text-sm">
              Wybierz lub utwórz dokument z listy po lewej stronie.
            </div>
          )}
        </div>
      </div>
    </ShellPanelFrame>
  );
};

export default DocsShellPanel;
