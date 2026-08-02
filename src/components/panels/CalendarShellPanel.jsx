import React, { useMemo, useState } from 'react';
import { Calendar, Plus, RefreshCw, Trash2, Edit2, ChevronLeft, ChevronRight, Users } from '../icons';
import { useLanguage } from '../../contexts/LanguageContext';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';
import { SegmentedTabs, Card, TextField, Checkbox, EmptyState, ListContainer, ListRow } from '../shared/panelPrimitives';

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
    endDate: new Date().toISOString().split('T')[0],
    time: new Date().toTimeString().slice(0, 5),
    duration: 60,
    speak: true,
    alert: true,
    allDay: false,
  });

  const getLocalDayStart = (date) => {
    const d = new Date(date);
    d.setHours(0, 0, 0, 0);
    return d;
  };

  const addDays = (date, days) => {
    const d = new Date(date);
    d.setDate(d.getDate() + days);
    return d;
  };

  const getDateInputAsLocalDay = (value) => new Date(`${value}T00:00:00`);

  const itemOverlapsDate = (item, date) => {
    const dayStart = getLocalDayStart(date);
    const dayEnd = addDays(dayStart, 1);
    const itemStart = item.time;
    const itemEnd = item.endTime && !Number.isNaN(item.endTime.getTime()) ? item.endTime : itemStart;
    if (item.type === 'event') {
      return itemStart < dayEnd && itemEnd > dayStart;
    }
    return itemStart.toDateString() === dayStart.toDateString();
  };

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
    const mappedEvents = events.map((e) => {
      const start = new Date(e.start_iso);
      const end = new Date(e.end_iso);
      const durationMs = end.getTime() - start.getTime();
      const looksLikeFullDayRange = durationMs >= 24 * 60 * 60 * 1000
        && durationMs % (24 * 60 * 60 * 1000) === 0
        && /T00:00:00/.test(String(e.start_iso || ''));
      return {
        type: 'event',
        id: e.id,
        title: e.summary,
        description: e.description || '',
        time: start,
        endTime: end,
        allDay: !!e.all_day || looksLikeFullDayRange,
      };
    });
    const mappedBirthdays = birthdays.map((b, idx) => {
      const date = new Date(b.date);
      return {
        type: 'birthday',
        id: `birthday-${idx}-${b.date}`,
        title: b.label || t('schedule.birthday'),
        time: Number.isNaN(date.getTime()) ? new Date() : date,
      };
    });
    return [...mappedReminders, ...mappedEvents, ...mappedBirthdays]
      .filter(item => (item.endTime && !Number.isNaN(item.endTime.getTime()) ? item.endTime > today : item.time >= today))
      .sort((a, b) => a.time - b.time);
  }, [birthdays, events, reminders, t]);

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
    if (description === 'Holiday') return forceTextEmojiPresentation(t('schedule.holiday'));
    if (description === 'Happy Birthday!' || itemType === 'birthday') return forceTextEmojiPresentation(t('schedule.happy_birthday'));
    return forceTextEmojiPresentation(description);
  };

  const getDisplayTime = (item) => {
    if (item.type === 'event' && item.allDay) {
      const startText = item.time.toLocaleDateString(locale);
      const lastDay = addDays(getLocalDayStart(item.endTime), -1);
      const endText = lastDay.toLocaleDateString(locale);
      return startText === endText
        ? `${startText} · ${t('schedule.all_day')}`
        : `${startText} - ${endText} · ${t('schedule.all_day')}`;
    }
    return item.time.toLocaleString(locale);
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
        start = getDateInputAsLocalDay(formData.date);
        const inclusiveEndDate = formData.endDate && formData.endDate >= formData.date ? formData.endDate : formData.date;
        end = addDays(getDateInputAsLocalDay(inclusiveEndDate), 1);
      } else {
        start = new Date(`${formData.date} ${formData.time}`);
        end = new Date(start.getTime() + formData.duration * 60000);
      }
      socket.emit('create_event', {
        summary: formData.message,
        start_iso: start.toISOString(),
        end_iso: end.toISOString(),
        description: '',
        all_day: formData.allDay,
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
    <ShellPanelFrame icon={Calendar} title={t('panels.calendar') || 'Calendar'}>
      <div ref={panelRef} className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar text-sm pb-10">
        <div className="flex flex-col gap-4">
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-[#8c7769] text-sm">
              {t('schedule.loading')}
            </div>
          )}

          {!isLoading && !socket && (
            <div className="flex items-center justify-center py-12 text-[#8c7769]/50 text-sm">
              {t('system.disconnected')}
            </div>
          )}

          {!isLoading && socket && (
            <>
              <div className="flex gap-2">
                <SegmentedTabs
                  className="flex-1"
                  value={activeTab}
                  onChange={setActiveTab}
                  options={[
                    { value: 'list', label: t('schedule.list_view') },
                    { value: 'month', label: t('schedule.month_view') },
                  ]}
                />
                <button
                  onClick={refreshData}
                  className="px-3 rounded-full bg-[#1e1612] border border-[#3c2e26] text-[#f5e6d3] hover:border-[#de9d50] hover:text-[#de9d50] transition-colors"
                  title={t('schedule.refresh')}
                >
                  <RefreshCw size={12} />
                </button>
                <button
                  onClick={() => setIsCreating((v) => !v)}
                  className={`px-3 rounded-full border transition-all ${isCreating ? 'bg-[#de9d50] border-[#de9d50] text-[#16100d]' : 'bg-[#1e1612] border-[#3c2e26] text-[#f5e6d3] hover:border-[#de9d50] hover:text-[#de9d50]'}`}
                  title={t('schedule.create')}
                >
                  <Plus size={12} className={isCreating ? 'rotate-45 transition-transform' : 'transition-transform'} />
                </button>
              </div>

              {isCreating && (
                <Card className="space-y-3.5 p-4">
                  <SegmentedTabs
                    value={createType}
                    onChange={setCreateType}
                    options={[
                      { value: 'reminder', label: t('schedule.reminder') },
                      { value: 'event', label: t('schedule.event') },
                    ]}
                  />
                  <TextField
                    type="text"
                    value={formData.message}
                    onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                    placeholder={t('schedule.description')}
                  />
                  <div className="flex gap-2">
                    <TextField
                      type="date"
                      value={formData.date}
                      size="sm"
                      wrapperClassName="flex-1"
                      onChange={(e) => {
                        const nextDate = e.target.value;
                        setFormData((prev) => ({
                          ...prev,
                          date: nextDate,
                          endDate: prev.endDate < nextDate ? nextDate : prev.endDate,
                        }));
                      }}
                    />
                    {!(createType === 'event' && formData.allDay) && (
                      <TextField
                        type="time"
                        value={formData.time}
                        size="sm"
                        wrapperClassName="w-24"
                        onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                      />
                    )}
                    {createType === 'event' && formData.allDay && (
                      <TextField
                        type="date"
                        value={formData.endDate}
                        min={formData.date}
                        size="sm"
                        wrapperClassName="flex-1"
                        onChange={(e) => setFormData({ ...formData, endDate: e.target.value })}
                      />
                    )}
                  </div>
                  {createType === 'event' && (
                    <div className="flex items-center justify-between text-xs text-[#8c7769]">
                      <Checkbox
                        checked={formData.allDay}
                        onChange={(checked) => setFormData({ ...formData, allDay: checked })}
                        label={t('schedule.all_day')}
                      />
                      {!formData.allDay && (
                        <div className="flex items-center gap-2">
                          <span>{t('schedule.duration')}</span>
                          <input
                            type="number"
                            value={formData.duration}
                            onChange={(e) => setFormData({ ...formData, duration: parseInt(e.target.value, 10) || 0 })}
                            className="w-16 bg-[#1e1612] border border-[#3c2e26] rounded px-2 py-1 text-[#f5e6d3] text-center focus:outline-none focus:border-[#de9d50]"
                          />
                          <span>{t('schedule.minutes')}</span>
                        </div>
                      )}
                    </div>
                  )}
                  <button
                    onClick={handleCreate}
                    className="w-full py-2.5 rounded-full bg-[#de9d50] hover:brightness-110 text-[#16100d] text-xs font-bold transition-all"
                  >
                    {t('schedule.create')}
                  </button>
                </Card>
              )}

              {activeTab === 'list' ? (
                mergedItems.length === 0 ? (
                  <EmptyState>{t('schedule.no_items')}</EmptyState>
                ) : (
                  <ListContainer>
                    {mergedItems.slice(0, 50).map((item) => (
                      <ListRow
                        key={`${item.type}-${item.id}`}
                        className="group items-start"
                        title={(
                          <>
                            <div className="text-xs text-[#8c7769] mb-0.5">{getDisplayTime(item)}</div>
                            {editingItem?.id === item.id ? (
                              <input
                                autoFocus
                                type="text"
                                value={editingItem.text}
                                onChange={(e) => setEditingItem({ ...editingItem, text: e.target.value })}
                                onBlur={() => handleUpdate(item, editingItem.text)}
                                onKeyDown={(e) => e.key === 'Enter' && handleUpdate(item, editingItem.text)}
                                className="w-full bg-[#1e1612] border border-[#3c2e26] rounded px-2 py-1 text-sm text-[#f5e6d3] focus:outline-none focus:border-[#de9d50]"
                              />
                            ) : (
                              <span className="font-semibold truncate emoji-text">{getDisplayTitle(item.title)}</span>
                            )}
                          </>
                        )}
                        description={!!item.description ? (
                          <span className="truncate emoji-text">{getDisplayDescription(item.description, item.type)}</span>
                        ) : null}
                        trailing={(
                          <div className="flex shrink-0 items-center gap-1">
                            {item.type !== 'birthday' && (
                              <button onClick={() => setEditingItem({ id: item.id, text: getDisplayTitle(item.title) })} className="opacity-0 group-hover:opacity-100 p-1.5 text-[#8c7769] hover:text-[#f5e6d3] transition-colors">
                                <Edit2 size={12} />
                              </button>
                            )}
                            {item.type !== 'birthday' && (
                              <button onClick={() => handleDelete(item)} className="opacity-0 group-hover:opacity-100 p-1.5 text-[#8c7769] hover:text-red-400 transition-colors">
                                <Trash2 size={12} />
                              </button>
                            )}
                            {item.type === 'birthday' && <Users size={12} className="text-[#de9d50]" />}
                          </div>
                        )}
                      />
                    ))}
                  </ListContainer>
                )
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <button onClick={() => setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))} className="p-1.5 rounded-full border border-[#3c2e26] bg-[#1e1612] text-[#f5e6d3] hover:border-[#de9d50] hover:text-[#de9d50] transition-colors">
                      <ChevronLeft size={14} />
                    </button>
                    <span className="text-lg font-serif text-[#f5e6d3] font-normal tracking-wide">{currentDate.toLocaleDateString(locale, { month: 'long', year: 'numeric' })}</span>
                    <button onClick={() => setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))} className="p-1.5 rounded-full border border-[#3c2e26] bg-[#1e1612] text-[#f5e6d3] hover:border-[#de9d50] hover:text-[#de9d50] transition-colors">
                      <ChevronRight size={14} />
                    </button>
                  </div>

                  <div className="grid gap-2 text-center text-sm" style={{ gridTemplateColumns: 'repeat(7,minmax(0,1fr))' }}>
                    {weekdayLabels.map((d, index) => (
                      <div key={`${d}-${index}`} className="text-[#8c7769] py-1.5 font-bold text-xs uppercase tracking-wider">{d}</div>
                    ))}
                    {getMonthCells(currentDate).map((day, i) => {
                      if (!day) return <div key={i} className="rounded-lg h-8" />;
                      const cellDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), day);
                      const isToday = new Date().toDateString() === cellDate.toDateString();
                      const isSelected = selectedDate.toDateString() === cellDate.toDateString();
                      const hasItems = mergedItems.some((it) => itemOverlapsDate(it, cellDate));
                      return (
                        <button
                          key={i}
                          onClick={() => setSelectedDate(cellDate)}
                          className={`h-12 rounded-xl flex flex-col items-center justify-center transition-colors ${isSelected ? 'bg-[#de9d50] text-[#16100d] font-bold' : isToday ? 'bg-[#1e1612] border border-[#de9d50] text-[#de9d50]' : 'text-[#f5e6d3] hover:bg-[#1e1612]/60 hover:text-[#de9d50]'}`}
                        >
                          <span className="text-base leading-none">{day}</span>
                          {hasItems && <span className={`w-1.5 h-1.5 rounded-full mt-1 ${isSelected ? 'bg-[#16100d]' : 'bg-[#de9d50]'}`} />}
                        </button>
                      );
                    })}
                  </div>

                  <div className="pt-4 border-t border-[#2c1e15] space-y-2.5">
                    <div className="text-xs font-bold text-[#8c7769] uppercase tracking-[0.15em] font-sans">{selectedDate.toLocaleDateString(locale, { month: 'long', day: 'numeric' })}</div>
                    {mergedItems.filter((it) => itemOverlapsDate(it, selectedDate)).slice(0, 6).map((it) => (
                      <div key={`${it.type}-${it.id}-selected`} className="text-sm text-[#f5e6d3] truncate emoji-text font-medium">• {getDisplayTitle(it.title)}</div>
                    ))}
                    {mergedItems.filter((it) => itemOverlapsDate(it, selectedDate)).length === 0 && (
                      <div className="text-sm text-[#8c7769]/60 italic">{t('schedule.no_items_day')}</div>
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
