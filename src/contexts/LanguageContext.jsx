import React, { createContext, useContext, useState, useEffect } from 'react';

const LanguageContext = createContext();

const defaultTranslations = {
  en: {
    system: {
      window_reset: "Window '{windowId}' position reset.",
      connecting: "Connecting...",
      connected: "Connected",
      disconnected: "Disconnected",
      monikai_started: "MonikAI Started",
      monikai_stopped: "MonikAI Stopped",
      model_connected: "Model Connected",
      camera_error: "Camera error",
      reading_memory: "Reading memory file...",
      memory_empty: "Memory file is empty.",
      memory_error: "Error reading memory file.",
    },
    chat: {
      you: "You",
      attachments: "Attachments",
      sent_attachments: "Sent attachments",
      monika_thought: "Monika (thought)",
    },
    companion: {
      title: "Companion Hub",
      subtitle: "The cozy place for shared routines, sessions, and study",
      kicker: "Companion Center",
      open_goals: "Open Mission Log",
      tabs: {
        session: "Session",
        activities: "Activities",
        study: "Study",
      },
      overview: {
        mood: "Mood",
        energy: "Energy",
        affection: "Affinity",
        goals: "Goals / Unlocks",
        neutral: "neutral",
      },
      activities: {
        eat: "Eat Together",
        eat_desc: "Start a low-pressure shared meal mode and hang out for a bit.",
        headpat: "Headpat",
        headpat_desc: "A tiny affectionate interaction. Short, silly, effective.",
        gift: "Give a Gift",
        gift_desc: "Send a small symbolic gift and let the moment land naturally.",
        gift_prompt: "What gift do you want to give?",
      },
      study: {
        japanese_together: "Study Japanese Together",
        title: "Study Companion",
        desc: "Open the current study setup and continue from the selected page.",
        folder: "Folder",
        file: "File",
      },
      session: {
        title: "Guided Session",
        desc: "Use this when you want a more focused, reflective mode instead of normal chat.",
        start: "Start Session",
        end: "End Session",
        start_desc: "Switch into a slower, more intentional session flow.",
        end_desc: "Return to normal conversation and close the focused mode.",
      },
    },
    goals: {
      title: "Progress",
      subtitle: "Achievement tree, daily tasks, and long-term progression",
      kicker: "Progress Matrix",
      relationship: "Relationship Track",
      level: "Level",
      closeness: "Closeness",
      current_xp: "{value}/{total} XP in this level",
      total_xp: "{value} total XP",
      active_missions: "Active Missions",
      empty: "No active missions right now.",
      quest_fallback: "Mission",
      completed_recent: "Recently Completed",
      skill_tree: "Growth Tree",
      unlocks: "Unlocked Paths",
      unlocks_empty: "Nothing unlocked yet.",
      next_unlocks: "Next Thresholds",
      reach_level: "Reach level {value}",
      reward_xp: "+{value} XP",
      tree: {
        title: "Achievement Tree",
        hint: "Hover a node to inspect it. On touch screens, you can tap it instead.",
        summary: "Unlocked {unlocked} of {total} achievements",
        selected: "Selected Achievement",
        status_unlocked: "Unlocked",
        status_locked: "Locked",
        requirement: "Requirement",
        reward: "Reward / Unlock",
        bond_status: "Trust {value}",
        nodes: {
          first_bond: { title: "First Contact", desc: "Start the shared route and unlock the bond core.", reward: "Bond core", req: "Available from the start" },
          bond_lvl_2: { title: "First Real Spark", desc: "Reach bond level 2.", reward: "New personal topics", req: "Reach bond level 2" },
          trust_40: { title: "Trust Fall", desc: "Build enough trust for deeper conversation.", reward: "Softer reflective replies", req: "Reach 40 trust" },
          playful_35: { title: "Bit Mode", desc: "Keep the tone playful enough for natural banter.", reward: "More playful banter", req: "Reach 35 playfulness" },
          reflection_25: { title: "Quiet Depth", desc: "Raise reflection to unlock deeper branches.", reward: "New introspective prompts", req: "Reach 25 reflection" },
          streak_3: { title: "See You Tomorrow", desc: "Maintain a 3-day streak.", reward: "Daily check-in feel", req: "Keep a 3-day streak" },
          unlocks_3: { title: "Pathfinder", desc: "Unlock multiple progression routes.", reward: "New relationship routes", req: "Unlock 3 paths" },
          quests_2: { title: "Quest Clear", desc: "Complete visible missions together.", reward: "Bonus quest flavor", req: "Complete 2 missions" },
          bond_lvl_4: { title: "Inner Circle", desc: "Reach bond level 4.", reward: "Rarer options and topics", req: "Reach bond level 4" },
        },
      },
      daily: {
        title: "Daily Quests",
        empty: "There are no daily quests yet today.",
      },
      lifetime: {
        title: "Lifetime Quests",
        items: {
          bond3: { title: "Stable Bond", desc: "Reach bond level 3." },
          trust40: { title: "Deeper Trust", desc: "Reach 40 trust." },
          quests5: { title: "Mission Runner", desc: "Complete 5 missions in total." },
          growth30: { title: "Long-Term Growth", desc: "Raise average growth to 30." },
        },
      },
      stats: {
        reflection: "Reflection",
        communication: "Communication",
        curiosity: "Curiosity",
        consistency: "Consistency",
      },
      category: {
        bond: "Bond",
        reflection: "Reflection",
        curiosity: "Curiosity",
        consistency: "Consistency",
        reward: "Reward",
      },
      unlock_type: {
        topic: "Topic",
        activity: "Activity",
        reward: "Reward",
      },
    },
    session: {
      notes_title: "Session Notes",
    },
    personality: {
      state: "Monika's State",
      affection: "Affection",
      mood: "Mood",
      energy: "Energy",
      cycle: "Biological Cycle",
      day: "Day",
      quests: "Active Quests",
      quest: "Quest",
      no_quests: "No active quests right now.",
    },
  },
  pl: {
    system: {
      window_reset: "Zresetowano pozycję okna '{windowId}'.",
      connecting: "Łączenie...",
      connected: "Połączono",
      disconnected: "Rozłączono",
      monikai_started: "MonikAI Uruchomiona",
      monikai_stopped: "MonikAI Zatrzymana",
      model_connected: "Model Połączony",
      camera_error: "Błąd kamery",
      reading_memory: "Wczytywanie pliku pamięci...",
      memory_empty: "Plik pamięci jest pusty.",
      memory_error: "Błąd odczytu pliku pamięci.",
    },
    chat: {
      you: "Ty",
      attachments: "Załączniki",
      sent_attachments: "Wysłano załączniki",
      monika_thought: "Myśli Moniki",
    },
    companion: {
      title: "Centrum Towarzysza",
      subtitle: "Wspólne rytuały, sesje i nauka w jednym miejscu",
      kicker: "Centrum Towarzysza",
      open_goals: "Otwórz dziennik misji",
      tabs: {
        session: "Sesja",
        activities: "Aktywności",
        study: "Nauka",
      },
      overview: {
        mood: "Nastrój",
        energy: "Energia",
        affection: "Bliskość",
        goals: "Cele / Odblokowania",
        neutral: "neutralny",
      },
      activities: {
        eat: "Zjedzmy razem",
        eat_desc: "Uruchom spokojny tryb wspólnego posiłku i pobądźmy chwilę razem.",
        headpat: "Głaskanie",
        headpat_desc: "Mała czuła interakcja. Krótka, głupio urocza i skuteczna.",
        gift: "Daj prezent",
        gift_desc: "Podaruj drobny symboliczny prezent i zróbmy z tego miły moment.",
        gift_prompt: "Jaki prezent chcesz dać?",
      },
      study: {
        japanese_together: "Uczmy się japońskiego razem",
        title: "Towarzysz nauki",
        desc: "Otwórz aktualny zestaw nauki i wróć do wybranej strony.",
        folder: "Folder",
        file: "Plik",
      },
      session: {
        title: "Prowadzona sesja",
        desc: "Włącz to, jeśli chcesz wolniejszego, bardziej skupionego trybu zamiast zwykłego czatu.",
        start: "Rozpocznij sesję",
        end: "Zakończ sesję",
        start_desc: "Przejdź do spokojniejszego, bardziej intencjonalnego trybu rozmowy.",
        end_desc: "Wróć do normalnej rozmowy i zamknij skupiony tryb.",
      },
    },
    goals: {
      title: "Postępy",
      subtitle: "Drzewko osiągnięć, codzienne zadania i długofalowy progres",
      kicker: "Macierz Postępu",
      relationship: "Tor relacji",
      level: "Poziom",
      closeness: "Bliskość",
      current_xp: "{value}/{total} XP na tym poziomie",
      total_xp: "{value} XP łącznie",
      active_missions: "Aktywne misje",
      empty: "Na razie nie ma aktywnych misji.",
      quest_fallback: "Misja",
      completed_recent: "Ostatnio ukończone",
      skill_tree: "Drzewko rozwoju",
      unlocks: "Odblokowane ścieżki",
      unlocks_empty: "Jeszcze nic tu nie odblokowano.",
      next_unlocks: "Kolejne progi",
      reach_level: "Osiągnij poziom {value}",
      reward_xp: "+{value} XP",
      tree: {
        title: "Drzewko osiągnięć",
        hint: "Najedź na węzeł, żeby zobaczyć szczegóły. Na dotyku możesz też kliknąć.",
        summary: "Zdobyto {unlocked} z {total} osiągnięć",
        selected: "Wybrane osiągnięcie",
        status_unlocked: "Zdobyte",
        status_locked: "Zablokowane",
        requirement: "Wymaganie",
        reward: "Nagroda / odblokowanie",
        bond_status: "Zaufanie {value}",
        nodes: {
          first_bond: { title: "Pierwszy kontakt", desc: "Rozpocznij wspólną ścieżkę i odblokuj rdzeń więzi.", reward: "Rdzeń więzi", req: "Dostępne od początku" },
          bond_lvl_2: { title: "Pierwsza iskra", desc: "Wejdź na 2 poziom więzi.", reward: "Nowe osobiste wątki", req: "Osiągnij poziom więzi 2" },
          trust_40: { title: "Skok zaufania", desc: "Zbuduj zaufanie dla głębszych rozmów.", reward: "Bardziej refleksyjny ton", req: "Osiągnij 40 zaufania" },
          playful_35: { title: "Tryb bitu", desc: "Utrzymaj dość playful klimat na naturalny banter.", reward: "Więcej drobnego banteru", req: "Osiągnij 35 playful" },
          reflection_25: { title: "Cicha głębia", desc: "Rozwiń refleksję i odblokuj głębsze ścieżki.", reward: "Nowe pytania introspekcyjne", req: "Osiągnij 25 refleksji" },
          streak_3: { title: "Do jutra", desc: "Utrzymaj streak przez 3 dni.", reward: "Daily check-in vibe", req: "Utrzymaj streak 3 dni" },
          unlocks_3: { title: "Pathfinder", desc: "Odblokuj kilka ścieżek progresji.", reward: "Nowe ścieżki relacji", req: "Odblokuj 3 ścieżki" },
          quests_2: { title: "Quest clear", desc: "Ukończ widoczne misje razem.", reward: "Bonusowy flavor misji", req: "Ukończ 2 misje" },
          bond_lvl_4: { title: "Inner circle", desc: "Wejdź na poziom więzi 4.", reward: "Rzadsze opcje i tematy", req: "Osiągnij poziom więzi 4" },
        },
      },
      daily: {
        title: "Daily quests",
        empty: "Dzisiaj nie ma jeszcze żadnych daily questów.",
      },
      lifetime: {
        title: "Lifetime quests",
        items: {
          bond3: { title: "Stabilna więź", desc: "Wejdź na 3 poziom więzi." },
          trust40: { title: "Pełniejsze zaufanie", desc: "Osiągnij 40 punktów zaufania." },
          quests5: { title: "Mission runner", desc: "Ukończ 5 misji łącznie." },
          growth30: { title: "Długofalowy rozwój", desc: "Podnieś średni rozwój do 30." },
        },
      },
      stats: {
        reflection: "Refleksja",
        communication: "Komunikacja",
        curiosity: "Ciekawość",
        consistency: "Regularność",
      },
      category: {
        bond: "Więź",
        reflection: "Refleksja",
        curiosity: "Ciekawość",
        consistency: "Regularność",
        reward: "Nagroda",
      },
      unlock_type: {
        topic: "Wątek",
        activity: "Aktywność",
        reward: "Nagroda",
      },
    },
    session: {
      notes_title: "Notatki sesji",
    },
    personality: {
      state: "Stan Moniki",
      affection: "Sympatia",
      mood: "Nastrój",
      energy: "Energia",
      cycle: "Cykl biologiczny",
      day: "Dzień",
      quests: "Aktywne cele",
      quest: "Cel",
      no_quests: "Brak aktywnych celów.",
    },
  }
};

export const LanguageProvider = ({ children }) => {
  const [language, setLanguage] = useState('pl');
  const [translations, setTranslations] = useState(defaultTranslations);

  useEffect(() => {
    const loadTranslations = () => {
      try {
        if (window.require) {
          const fs = window.require('fs');
          const path = window.require('path');
          const localePath = path.join(process.cwd(), 'data', 'locales', `${language}.json`);
          
          if (fs.existsSync(localePath)) {
            const content = fs.readFileSync(localePath, 'utf-8');
            const json = JSON.parse(content);
            setTranslations(prev => ({ ...prev, [language]: json }));
          }
        }
      } catch (err) {
        console.error("Failed to load translations:", err);
      }
    };
    loadTranslations();
  }, [language]);

  const t = (key, params = {}) => {
    const keys = key.split('.');
    
    // Helper to safely access nested objects
    const getTranslation = (langObj, keyPath) => {
      let val = langObj;
      for (const k of keyPath) {
        if (val && val[k]) val = val[k];
        else return null;
      }
      return val;
    };

    // Try current language, fallback to English
    let value = getTranslation(translations[language], keys);
    if (!value && language !== 'en') {
      value = getTranslation(translations['en'], keys);
    }

    if (typeof value !== 'string') return key;

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
