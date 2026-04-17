/**
 * Meal System Utilities
 * 
 * Functions for meal detection, "Eat Together" mode management, and meal selection
 */

import {
  MEAL_KEYWORDS,
  FINISHED_MEAL_KEYWORDS,
  START_EAT_TOGETHER_KEYWORDS,
  STOP_EAT_TOGETHER_KEYWORDS,
  MONIKA_MEAL_ASSETS,
} from './mealConstants';

/**
 * Detects if text contains a meal mention and returns the meal type
 * @param raw - Raw text to analyze
 * @returns Meal key (e.g., "pasta", "pizza") or null if no meal detected
 */
export const detectMealKey = (raw: string): string | null => {
  const text = String(raw || "").toLowerCase();
  if (!text) return null;

  for (const entry of MEAL_KEYWORDS) {
    if (entry.re.test(text)) {
      return entry.key;
    }
  }

  return null;
};

/**
 * Detects if text indicates meal completion
 * @param raw - Raw text to analyze
 * @returns true if meal is finished, false otherwise
 */
export const detectFinishedMeal = (raw: string): boolean => {
  const text = String(raw || "").toLowerCase();
  if (!text) return false;
  return FINISHED_MEAL_KEYWORDS.some((re) => re.test(text));
};

/**
 * Detects if text contains request to start "Eat Together" mode
 * @param raw - Raw text to analyze
 * @returns true if user wants to start eating together, false otherwise
 */
export const shouldStartEatTogether = (raw: string): boolean => {
  const text = String(raw || "").toLowerCase();
  if (!text) return false;
  return START_EAT_TOGETHER_KEYWORDS.some((keyword) => text.includes(keyword));
};

/**
 * Detects if text contains request to stop "Eat Together" mode
 * @param raw - Raw text to analyze
 * @returns true if user wants to stop eating together, false otherwise
 */
export const shouldStopEatTogether = (raw: string): boolean => {
  const text = String(raw || "").toLowerCase();
  if (!text) return false;
  return STOP_EAT_TOGETHER_KEYWORDS.some((keyword) => text.includes(keyword));
};

/**
 * Randomly selects a meal from Monika's available choices
 * @returns Random meal key from MONIKA_MEAL_ASSETS, or null if no meals available
 */
export const pickRandomMonikaMeal = (): string | null => {
  const keys = Object.keys(MONIKA_MEAL_ASSETS || {});
  if (!keys.length) return null;
  return keys[Math.floor(Math.random() * keys.length)];
};

/**
 * Validates if a meal type exists in Monika's available meals
 * @param mealKey - Meal key to validate
 * @returns true if meal exists in MONIKA_MEAL_ASSETS, false otherwise
 */
export const isValidMonikaMeal = (mealKey: string): boolean => {
  return mealKey in MONIKA_MEAL_ASSETS;
};
