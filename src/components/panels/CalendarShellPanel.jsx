import React, { useMemo, useState } from 'react';
import { Calendar, Plus, RefreshCw, Trash2, Edit2, ChevronLeft, ChevronRight, Check, Users } from 'lucide-react';
import { useLanguage } from '../../contexts/LanguageContext';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';

const DAYS_IN_WEEK = 7;
const CALENDAR_WEEKS = 6;
const LANGUAGE_LOCALES = {
  en: 'en-US',
  pl: 'pl-PL',
  ja: 'ja-JP',
  zh: 'zh-CN',
};

const EMOJI_TEXT_PRESENTATION_RE = /([\u2600-\u27BF\u{1F000}-\u{1FAFF}])(?!\uFE0E)/gu;

const forceTextEmojiPresentation = (value) => {
  const normalized = String(value || '').replace(/\uFE0F/gu, '\uFE0E');
  return normalized.replace(EMOJI_TEXT_PRESENTATION_RE, '$1\uFE0E');
};

const CalendarShellPanel = ({ socket = null }) => {
  const { t, language } = useLanguage();
  const [panelRef] = useElementSize();
  const [events, setEvents] = useState([]);
  const [birthdays, setBirthdays] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('list');
  const [isCreating, setIsCreating] = useState(false);
  const [createType, setCreateType] = useState('reminder');
  const [editingItem, setEditingItem] = useState(null);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [formData, setFormData] = useState({
    message: '',
    date: new Date().toISOString().split('T')[0],
    time: new Date().toTimeString().slice(0, 5),
    duration: 60,
    speak: true,
    alert: true,
    allDay: false,
  });

  const emitWithAckTimeout = React.useCallback((eventName, payload = {}, fallbackData = {}, timeoutMs = 4000) => {
    if (!socket) return Promise.resolve(fallbackData);
    return new Promise((resolve) => {
      let settled = false;
      const timeout = setTimeout(() => {
        if (!settled) {
          settled = true;
          resolve(fallbackData);
        }
      }, timeoutMs);

      socket.emit(eventName, payload, (response) => {
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          resolve(response || fallbackData);
        }
      });
    });
  }, [socket]);

  const refreshData = React.useCallback(async () => {
    if (!socket) {
      setIsLoading(false);
      return;
    }
    const [eventsResponse, birthdaysResponse, remindersResponse] = await Promise.all([
      emitWithAckTimeout('calendar_get_events', {}, { events: [] }),
      emitWithAckTimeout('calendar_get_birthdays', {}, { birthdays: [] }),
      emitWithAckTimeout('list_reminders', {}, { reminders: [] }),
    ]);
    setEvents(Array.isArray(eventsResponse?.events) ? eventsResponse.events : []);
    setBirthdays(Array.isArray(birthdaysResponse?.birthdays) ? birthdaysResponse.birthdays : []);
    setReminders(Array.isArray(remindersResponse?.reminders) ? remindersResponse.reminders : []);
    setIsLoading(false);
  }, [emitWithAckTimeout, socket]);

  React.useEffect(() => {
    let isMounted = true;

    if (!socket) {
      setIsLoading(false);
      return;
    }

    const onRemindersList = (data) => {
      if (!isMounted) return;
      setReminders(Array.isArray(data?.reminders) ? data.reminders : []);
    };
    const onCalendarData = (data) => {
      if (!isMounted) return;
      setEvents(Array.isArray(data) ? data : []);
    };

    socket.on('reminders_list', onRemindersList);
    socket.on('calendar_data', onCalendarData);

    refreshData();

    return () => {
      isMounted = false;
      socket.off('reminders_list', onRemindersList);
      socket.off('calendar_data', onCalendarData);
    };
  }, [refreshData, socket]);

  const mergedItems = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const mappedReminders = reminders.map((r) => ({
      type: 'reminder',
      id: r.id,
      title: r.message,
      time: new Date(r.when_iso),
    }));
    const mappedEvents = events.map((e) => ({
      type: 'event',
      id: e.id,
      title: e.summary,
      description: e.description || '',
      time: new Date(e.start_iso),
      endTime: new Date(e.end_iso),
    }));
    const mappedBirthdays = birthdays.map((b, idx) => {
      const date = new Date(b.date);
      return {
        type: 'birthday',
        id: `birthday-${idx}-${b.date}`,
        title: b.label || 'Birthday',
        time: Number.isNaN(date.getTime()) ? new Date() : date,
      };
    });
    return [...mappedReminders, ...mappedEvents, ...mappedBirthdays]
      .filter(item => item.time >= today)
      .sort((a, b) => a.time - b.time);
  }, [birthdays, events, reminders]);

  // Helper to translate holiday and special event titles
  const getDisplayTitle = (title) => {
    if (title && typeof title === 'string' && title.startsWith('holidays.')) {
      return forceTextEmojiPresentation(t(title));
    }
    return forceTextEmojiPresentation(title);
  };

  // Helper to translate event descriptions
  const getDisplayDescription = (description, itemType) => {
    if (!description) return '';
    // Translate backend's hardcoded descriptions
    if (description === 'Holiday') return forceTextEmojiPresentation('Holiday');
    if (description === 'Happy Birthday!' || itemType === 'birthday') return forceTextEmojiPresentation('Happy Birthday!');
    return forceTextEmojiPresentation(description);
  };

  const handleDelete = (item) => {
    if (!socket || item.type === 'birthday') return;
    if (item.type === 'reminder') {
      socket.emit('cancel_reminder', { id: item.id });
    } else if (item.type === 'event') {
      socket.emit('delete_event', { id: item.id });
    }
  };

  const handleUpdate = (item, newText) => {
    if (!socket || !newText.trim()) return;
    if (item.type === 'reminder') {
      socket.emit('update_reminder', { id: item.id, message: newText });
    } else if (item.type === 'event') {
      socket.emit('update_event', { id: item.id, summary: newText });
    }
    setEditingItem(null);
  };

  const handleCreate = () => {
    if (!socket || !formData.message.trim()) return;

    if (createType === 'reminder') {
      socket.emit('create_reminder', {
        message: formData.message,
        at: `${formData.date} ${formData.time}`,
        speak: formData.speak,
        alert: formData.alert,
      });
    } else {
      let start;
      let end;
      if (formData.allDay) {
        start = new Date(`${formData.date}T00:00:00`);
        end = new Date(`${formData.date}T23:59:59`);
      } else {
        start = new Date(`${formData.date} ${formData.time}`);
        end = new Date(start.getTime() + formData.duration * 60000);
      }
      socket.emit('create_event', {
        summary: formData.message,
        start_iso: start.toISOString(),
        end_iso: end.toISOString(),
        description: '',
      });
    }

    setFormData((prev) => ({ ...prev, message: '' }));
    setIsCreating(false);
  };

  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const days = new Date(year, month + 1, 0).getDate();
    const firstDay = new Date(year, month, 1).getDay();
    return { days, firstDay };
  };

  const getMonthCells = (date) => {
    const { days, firstDay } = getDaysInMonth(date);
    const leadingBlanks = Array(firstDay).fill(null);
    const dayNumbers = Array.from({ length: days }, (_, i) => i + 1);
    const trailingBlanks = Array(Math.max(0, CALENDAR_WEEKS * DAYS_IN_WEEK - leadingBlanks.length - dayNumbers.length)).fill(null);
    return [...leadingBlanks, ...dayNumbers, ...trailingBlanks];
  };

  const locale = LANGUAGE_LOCALES[language] || LANGUAGE_LOCALES.en;
  const weekdayLabels = useMemo(() => {
    const baseDate = new Date(Date.UTC(2026, 0, 4));
    return Array.from({ length: DAYS_IN_WEEK }, (_, index) =>
      new Intl.DateTimeFormat(locale, { weekday: 'narrow' }).format(
        new Date(baseDate.getTime() + index * 24 * 60 * 60 * 1000),
      ),
    );
  }, [locale]);

  return (
    <ShellPanelFrame icon={Calendar} title={t('panels.calendar')} bodyClassName="min-h-0">
      <div ref={panelRef} className="h-full min-h-0 p-3 overflow-y-auto">
        <div className="flex flex-col gap-4">
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-white/60 text-sm">
              {t('schedule.loading')}
            </div>
          )}

          {!isLoading && !socket && (
            <div className="flex items-center justify-center py-12 text-white/40 text-sm">
              {t('system.disconnected')}
            </div>
          )}

          {!isLoading && socket && (
            <>
              <div className="flex gap-2">
                <div className="flex-1 bg-white/5 p-1 rounded-lg flex gap-1">
                  <button
                    onClick={() => setActiveTab('list')}
                    className={`flex-1 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'list' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'}`}
                  >
                    {t('schedule.list_view')}
                  </button>
                  <button
                    onClick={() => setActiveTab('month')}
                    className={`flex-1 py-2 rounded-md text-sm font-medium transition-all ${activeTab === 'month' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'}`}
                  >
                    {t('schedule.month_view')}
                  </button>
                </div>
                <button
                  onClick={refreshData}
                  className="px-3 rounded-lg bg-white/5 border border-white/10 text-white/70 hover:bg-white/10"
                  title={t('schedule.refresh')}
                >
                  <RefreshCw size={14} />
                </button>
                <button
                  onClick={() => setIsCreating((v) => !v)}
                  className={`px-3 rounded-lg border text-white transition-all ${isCreating ? 'bg-white/20 border-white/40' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}
                  title={t('schedule.create')}
                >
                  <Plus size={14} className={isCreating ? 'rotate-45 transition-transform' : 'transition-transform'} />
                </button>
              </div>

              {isCreating && (
                <div className="rounded-lg border border-white/10 bg-black/20 p-3 space-y-3">
                  <div className="flex gap-2">
                    {['reminder', 'event'].map((type) => (
                      <button
                        key={type}
                        onClick={() => setCreateType(type)}
                        className={`flex-1 text-xs py-1.5 rounded border transition-colors ${createType === type ? 'bg-white/20 border-white/40 text-white' : 'border-transparent text-white/40 hover:bg-white/5'}`}
                      >
                        {type === 'reminder' ? t('schedule.reminder') : t('schedule.event')}
                      </button>
                    ))}
                  </div>
                  <input
                    type="text"
                    value={formData.message}
                    onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                    placeholder={t('schedule.description')}
                    className="w-full bg-black/50 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-white/30"
                  />
                  <div className="flex gap-2">
                    <input
                      type="date"
                      value={formData.date}
                      onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                      className="flex-1 bg-black/50 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white"
                    />
                    {!formData.allDay && (
                      <input
                        type="time"
                        value={formData.time}
                        onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                        className="w-24 bg-black/50 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white"
                      />
                    )}
                  </div>
                  {createType === 'event' && (
                    <div className="flex items-center justify-between text-xs text-white/60">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <span className={`w-3 h-3 border rounded flex items-center justify-center ${formData.allDay ? 'bg-white border-white' : 'border-white/30'}`}>
                          {formData.allDay && <Check size={10} className="text-black" />}
                        </span>
                        <input
                          type="checkbox"
                          checked={formData.allDay}
                          onChange={(e) => setFormData({ ...formData, allDay: e.target.checked })}
                          className="hidden"
                        />
                        {t('schedule.all_day')}
                      </label>
                      {!formData.allDay && (
                        <div className="flex items-center gap-2">
                          <span>{t('schedule.duration')}</span>
                          <input
                            type="number"
                            value={formData.duration}
                            onChange={(e) => setFormData({ ...formData, duration: parseInt(e.target.value, 10) || 0 })}
                            className="w-16 bg-black/50 border border-white/10 rounded px-2 py-1 text-white"
                          />
                          <span>{t('schedule.minutes')}</span>
                        </div>
                      )}
                    </div>
                  )}
                  <button
                    onClick={handleCreate}
                    className="w-full py-2 rounded-lg bg-white/20 hover:bg-white/30 text-white text-xs font-medium"
                  >
                    {t('schedule.create')}
                  </button>
                </div>
              )}

              {activeTab === 'list' ? (
                <div className="space-y-2">
                  {mergedItems.length === 0 ? (
                    <div className="flex items-center justify-center py-10 text-white/40 text-sm">{t('schedule.no_items')}</div>
                  ) : (
                    mergedItems.slice(0, 50).map((item) => (
                      <div key={`${item.type}-${item.id}`} className="rounded-lg border border-white/5 bg-black/20 p-3 group">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="text-xs text-white/50">{item.time.toLocaleString(locale)}</div>
                            {editingItem?.id === item.id ? (
                              <input
                                autoFocus
                                type="text"
                                value={editingItem.text}
                                onChange={(e) => setEditingItem({ ...editingItem, text: e.target.value })}
                                onBlur={() => handleUpdate(item, editingItem.text)}
                                onKeyDown={(e) => e.key === 'Enter' && handleUpdate(item, editingItem.text)}
                                className="w-full mt-1 bg-black/50 border border-white/40 rounded px-2 py-1 text-sm text-white"
                              />
                            ) : (
                              <div className="text-sm text-white truncate emoji-text">{getDisplayTitle(item.title)}</div>
                            )}
                            {!!item.description && <div className="text-xs text-white/40 mt-1 truncate emoji-text">{getDisplayDescription(item.description, item.type)}</div>}
                          </div>
                          <div className="flex items-center gap-1">
                            {item.type !== 'birthday' && (
                              <button onClick={() => setEditingItem({ id: item.id, text: getDisplayTitle(item.title) })} className="opacity-0 group-hover:opacity-100 p-1.5 text-white/40 hover:text-white transition-all">
                                <Edit2 size={14} />
                              </button>
                            )}
                            {item.type !== 'birthday' && (
                              <button onClick={() => handleDelete(item)} className="opacity-0 group-hover:opacity-100 p-1.5 text-white/40 hover:text-red-400 transition-all">
                                <Trash2 size={14} />
                              </button>
                            )}
                            {item.type === 'birthday' && <Users size={14} className="text-cyan-300" />}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <button onClick={() => setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))} className="p-1 rounded text-white/60 hover:bg-white/10 hover:text-white">
                      <ChevronLeft size={16} />
                    </button>
                    <span className="text-lg font-semibold text-white/90">{currentDate.toLocaleDateString(locale, { month: 'long', year: 'numeric' })}</span>
                    <button onClick={() => setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))} className="p-1 rounded text-white/60 hover:bg-white/10 hover:text-white">
                      <ChevronRight size={16} />
                    </button>
                  </div>

                  <div className="grid gap-2 text-center text-sm" style={{ gridTemplateColumns: 'repeat(7,minmax(0,1fr))' }}>
                    {weekdayLabels.map((d, index) => (
                      <div key={`${d}-${index}`} className="text-white/50 py-1.5 font-medium">{d}</div>
                    ))}
                    {getMonthCells(currentDate).map((day, i) => {
                      if (!day) return <div key={i} className="rounded-lg h-8" />;
                      const cellDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), day);
                      const isToday = new Date().toDateString() === cellDate.toDateString();
                      const isSelected = selectedDate.toDateString() === cellDate.toDateString();
                      const hasItems = mergedItems.some((it) => it.time.toDateString() === cellDate.toDateString());
                      return (
                        <button
                          key={i}
                          onClick={() => setSelectedDate(cellDate)}
                          className={`h-12 rounded-xl flex flex-col items-center justify-center transition-colors ${isSelected ? 'bg-white text-black' : isToday ? 'bg-white/20 text-white border border-white/30' : 'text-white/80 hover:bg-white/10'}`}
                        >
                          <span className="text-base leading-none">{day}</span>
                          {hasItems && <span className={`w-1.5 h-1.5 rounded-full mt-1 ${isSelected ? 'bg-black' : 'bg-white'}`} />}
                        </button>
                      );
                    })}
                  </div>

                  <div className="pt-3 border-t border-white/10 space-y-2">
                    <div className="text-sm text-white/55 uppercase tracking-wider">{selectedDate.toLocaleDateString(locale, { month: 'long', day: 'numeric' })}</div>
                    {mergedItems.filter((it) => it.time.toDateString() === selectedDate.toDateString()).slice(0, 6).map((it) => (
                      <div key={`${it.type}-${it.id}-selected`} className="text-sm text-white/85 truncate emoji-text">• {getDisplayTitle(it.title)}</div>
                    ))}
                    {mergedItems.filter((it) => it.time.toDateString() === selectedDate.toDateString()).length === 0 && (
                      <div className="text-sm text-white/35 italic">{t('schedule.no_items_day')}</div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </ShellPanelFrame>
  );
};

export default CalendarShellPanel;
