import React, { useEffect, useMemo, useState } from 'react';
import { useLanguage } from '../contexts/LanguageContext';

const KNOWN_MOOD_KEYS = new Set([
  'neutral',
  'excited',
  'happy',
  'calm',
  'angry',
  'intensely_protective',
  'protective',
  'sad',
  'tired',
]);

const KNOWN_WEATHER_KEYS = new Set([
  'clear',
  'mostly_clear',
  'partly_cloudy',
  'cloudy',
  'fog',
  'drizzle',
  'rain',
  'snow',
  'storm',
]);

const WEATHER_CODE_TO_KEY = [
  [[0], 'clear'],
  [[1], 'mostly_clear'],
  [[2], 'partly_cloudy'],
  [[3], 'cloudy'],
  [[45, 48], 'fog'],
  [[51, 52, 53, 54, 55, 56, 57], 'drizzle'],
  [[61, 62, 63, 64, 65, 66, 67, 80, 81, 82], 'rain'],
  [[71, 72, 73, 74, 75, 76, 77, 85, 86], 'snow'],
  [[95, 96, 99], 'storm'],
];

const padTime = (value) => String(value).padStart(2, '0');

const formatDate = (date, language) => (
  new Intl.DateTimeFormat(language || 'en', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date)
);

const timeOfDayKey = (hour) => {
  if (hour >= 5 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 17) return 'afternoon';
  if (hour >= 17 && hour < 21) return 'evening';
  return 'night';
};

const normalizeKey = (value) => String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');

const weatherKeyFromCode = (code) => {
  const numericCode = Number(code);
  const match = WEATHER_CODE_TO_KEY.find(([codes]) => codes.includes(numericCode));
  return match ? match[1] : '';
};

const weatherLabel = (weather, t) => {
  if (!weather) return '';

  if (typeof weather === 'string') {
    const key = normalizeKey(weather);
    return KNOWN_WEATHER_KEYS.has(key) ? t(`mas_clock.weather.${key}`) : weather.trim();
  }

  const key = normalizeKey(weather.condition || weather.weather || weather.description)
    || weatherKeyFromCode(weather.code);
  if (KNOWN_WEATHER_KEYS.has(key)) {
    return t(`mas_clock.weather.${key}`);
  }
  return '';
};

const moodLabel = (mood, t) => {
  const key = normalizeKey(mood || 'neutral');
  if (KNOWN_MOOD_KEYS.has(key)) {
    return t(`mas_clock.mood.${key}`);
  }
  return key.replace(/_/g, ' ');
};

const MASClock = ({ personalityState = {} }) => {
  const { t, language } = useLanguage();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 10000);
    return () => window.clearInterval(timer);
  }, []);

  const display = useMemo(() => {
    const hour = now.getHours();
    const minutes = now.getMinutes();
    const time = `${padTime(hour)}:${padTime(minutes)}`;
    const weather = weatherLabel(personalityState.weather, t);
    const details = [
      formatDate(now, language),
      weather,
      time,
    ].filter(Boolean);

    return {
      mood: moodLabel(personalityState.mood, t),
      timeOfDay: t(`mas_clock.time_of_day.${timeOfDayKey(hour)}`),
      details: details.join(' · '),
    };
  }, [now, personalityState, t, language]);

  return (
    <div className="mas-clock" aria-label={`${display.mood} ${display.timeOfDay}, ${display.details}`}>
      <div className="mas-clock__content">
        <div className="mas-clock__mood">{display.mood} {display.timeOfDay}</div>
        <div className="mas-clock__details">{display.details}</div>
      </div>
    </div>
  );
};

export default React.memo(MASClock);
