import React, { useState, useEffect } from 'react';
import { Search, Play, FileText, CheckCircle2, AlertCircle, Clock, ExternalLink, RefreshCw, Layers } from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import { Badge } from '../shared/panelPrimitives';

const ResearchShellPanel = ({ socket }) => {
  const [topic, setTopic] = useState('');
  const [depth, setDepth] = useState('standard');
  const [activeTask, setActiveTask] = useState(null);
  const [tasksList, setTasksList] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    // Fetch initial list of research tasks
    fetch('/api/v1/research/list')
      .then(res => res.json())
      .then(data => {
        if (data.tasks) setTasksList(data.tasks);
      })
      .catch(() => {});

    if (!socket) return;

    const handleProgress = (data) => {
      setActiveTask(prev => {
        if (!prev || prev.task_id === data.task_id) {
          return { ...prev, ...data };
        }
        return prev;
      });
      if (data.status === 'completed') {
        setIsSubmitting(false);
        // Refresh tasks list
        fetch('/api/v1/research/list')
          .then(res => res.json())
          .then(d => { if (d.tasks) setTasksList(d.tasks); });
      }
    };

    socket.on('research_progress', handleProgress);
    return () => {
      socket.off('research_progress', handleProgress);
    };
  }, [socket]);

  const handleStartResearch = async () => {
    if (!topic.trim() || isSubmitting) return;
    setIsSubmitting(true);
    setSelectedReport(null);

    try {
      if (socket) {
        socket.emit('research_start', { topic: topic.trim(), depth });
      } else {
        const res = await fetch('/api/v1/research/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic: topic.trim(), depth }),
        });
        const data = await res.json();
      }
    } catch (e) {
      console.error(e);
      setIsSubmitting(false);
    }
  };

  const handleLoadReport = async (taskId) => {
    try {
      const res = await fetch(`/api/v1/research/report/${taskId}`);
      const data = await res.json();
      if (data.ok) {
        setSelectedReport(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <ShellPanelFrame icon={Search} title="Deep Research (Odysseus)">
      <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar text-sm pb-10">
        {/* Research Input Form */}
        <div className="p-4 rounded-xl bg-black/30 border border-white/10 space-y-4">
          <div className="text-base font-semibold text-white/90">Nowe Wieloetapowe Badanie</div>
          <div className="flex gap-2">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Wpisz temat, pytanie lub tezę badawczą..."
              className="flex-1 px-4 py-2.5 rounded-lg bg-black/40 border border-white/15 text-white placeholder:text-white/40 focus:outline-none focus:border-pink-500/50"
              onKeyDown={(e) => e.key === 'Enter' && handleStartResearch()}
            />
            <button
              onClick={handleStartResearch}
              disabled={isSubmitting || !topic.trim()}
              className="px-5 py-2.5 rounded-lg bg-gradient-to-r from-pink-600 to-purple-600 text-white font-medium hover:opacity-90 disabled:opacity-50 transition flex items-center gap-2"
            >
              {isSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              <span>{isSubmitting ? 'Badanie w toku...' : 'Uruchom'}</span>
            </button>
          </div>

          <div className="flex items-center gap-4 text-xs text-white/70">
            <span>Głębokość analizy:</span>
            {['quick', 'standard', 'deep'].map((d) => (
              <label key={d} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="depth"
                  value={d}
                  checked={depth === d}
                  onChange={(e) => setDepth(e.target.value)}
                  className="accent-pink-500"
                />
                <span className="capitalize">{d === 'quick' ? 'Szybkie (3 zapytania)' : (d === 'standard' ? 'Standardowe (5 zapytań)' : 'Głębokie (8 zapytań)')}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Live Progress Card */}
        {activeTask && activeTask.status === 'running' && (
          <div className="mt-6 p-4 rounded-xl bg-pink-950/20 border border-pink-500/30 space-y-3 animate-pulse">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-pink-300 flex items-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Trwa analiza: {activeTask.topic}</span>
              </div>
              <Badge tone="amber">{Math.round((activeTask.progress || 0) * 100)}%</Badge>
            </div>

            <div className="w-full bg-black/40 rounded-full h-2 overflow-hidden border border-white/10">
              <div
                className="bg-gradient-to-r from-pink-500 to-purple-500 h-full transition-all duration-300"
                style={{ width: `${Math.max(5, (activeTask.progress || 0) * 100)}%` }}
              />
            </div>

            <div className="text-xs text-white/70 flex items-center justify-between">
              <span>{activeTask.current_step}</span>
              {activeTask.cost && (
                <span className="text-white/50">
                  Tokeny: {activeTask.cost.total_tokens} | Koszt: ${activeTask.cost.estimated_cost_usd?.toFixed(4) || '0.0000'}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Selected or Finished Report Reader */}
        {(selectedReport || (activeTask && activeTask.status === 'completed' && activeTask.report_markdown)) && (
          <div className="mt-6 p-6 rounded-xl bg-black/40 border border-white/15 space-y-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="text-lg font-bold text-white/95 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <span>{selectedReport?.topic || activeTask?.topic}</span>
              </div>
              <Badge tone="green">Gotowy</Badge>
            </div>

            <div className="prose prose-invert max-w-none text-white/90 whitespace-pre-wrap font-sans text-sm leading-relaxed">
              {selectedReport?.report_markdown || activeTask?.report_markdown}
            </div>
          </div>
        )}

        {/* Previous Tasks History */}
        {tasksList.length > 0 && (
          <div className="mt-8 space-y-3">
            <div className="text-sm font-semibold text-white/80 flex items-center gap-2">
              <Clock className="w-4 h-4" />
              <span>Historia Badań ({tasksList.length})</span>
            </div>

            <div className="space-y-2">
              {tasksList.map((t) => (
                <div
                  key={t.task_id}
                  onClick={() => handleLoadReport(t.task_id)}
                  className="p-3 rounded-lg bg-black/25 hover:bg-white/5 border border-white/10 cursor-pointer transition flex items-center justify-between"
                >
                  <div>
                    <div className="font-medium text-white/90">{t.topic}</div>
                    <div className="text-xs text-white/40 mt-0.5">
                      Głębokość: {t.depth} • Czas: {t.duration_s}s • {t.created_at?.slice(0, 19).replace('T', ' ')}
                    </div>
                  </div>
                  <Badge tone={t.status === 'completed' ? 'green' : (t.status === 'failed' ? 'red' : 'amber')}>
                    {t.status}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </ShellPanelFrame>
  );
};

export default ResearchShellPanel;
