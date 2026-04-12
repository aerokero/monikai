import React, { createContext, useContext, useState, useMemo } from 'react';
import enLocale from '../../data/locales/en.json';
import plLocale from '../../data/locales/pl.json';
import zhLocale from '../../data/locales/zh.json';
import jaLocale from '../../data/locales/ja.json';

const LanguageContext = createContext();

/**
 * Deep merge objects, combining translations
 */
const mergeDeep = (target, source) => {
  const result = { ...target };
  for (const key in source) {
    if (source.hasOwnProperty(key)) {
      if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
        result[key] = mergeDeep(target[key] || {}, source[key]);
      } else {
        result[key] = source[key];
      }
    }
  }
  return result;
};

// Build complete translation dictionary by merging loaded locales
const fullTranslations = {
  en: mergeDeep({}, enLocale),
  pl: mergeDeep({}, plLocale),
  zh: mergeDeep({}, zhLocale),
  ja: mergeDeep({}, jaLocale),
};

export const LanguageProvider = ({ children }) => {
  const [language, setLanguage] = useState('pl');

  // Use fullTranslations which includes all imported locales
  const translations = useMemo(() => fullTranslations, []);

  const t = (key, params = {}) => {
    const keys = key.split('.');
    
    // Helper to safely access nested objects
    const getTranslation = (langObj, keyPath) => {
      let val = langObj;
      for (const k of keyPath) {
        if (val && typeof val === 'object' && k in val) {
          val = val[k];
        } else {
          return null;
        }
      }
      return val;
    };

    // Try current language, fallback to English
    let value = getTranslation(translations[language], keys);
    if (!value && language !== 'en') {
      value = getTranslation(translations['en'], keys);
    }

    if (typeof value !== 'string') {
      console.warn(`Missing translation key: ${key}`);
      return key;
    }

    // Replace parameters in translation string
    return value.replace(/{(\w+)}/g, (_, match) => {
      return params[match] !== undefined ? params[match] : `{${match}}`;
    });
  };

  return (
    <LanguageContext.Provider value={{ t, language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => useContext(LanguageContext);
