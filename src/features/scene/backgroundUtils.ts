/**
 * VN Background & Scene Utilities
 * 
 * Functions for managing scene transitions, time-based visuals, and background logic
 */

import {
  VN_BACKGROUNDS,
  ROOM_DAY_BG,
  ROOM_NIGHT_BG,
  OUTSIDE_DAY_VARIANTS,
  OUTSIDE_NIGHT_VARIANTS,
  SCENE_SCHEDULE,
  NIGHT_HOUR_START,
  NIGHT_HOUR_END,
} from './backgroundConstants';

/**
 * Determines if the given hour is night time
 * Night: 22:00 - 06:00
 */
export const isNightHour = (date: Date): boolean => {
  const h = date.getHours();
  return h >= NIGHT_HOUR_START || h < NIGHT_HOUR_END;
};

/**
 * Resolves the appropriate background image for a given scene and time
 * Handles day/night variants for rooms and outside scenes
 */
export const resolveVnBackground = (scene: string, date: Date = new Date()): string => {
  if (scene === 'room') {
    return isNightHour(date) ? ROOM_NIGHT_BG : ROOM_DAY_BG;
  }

  if (scene === 'outside') {
    const idx = date.getDate() % OUTSIDE_DAY_VARIANTS.length;
    return isNightHour(date) ? OUTSIDE_NIGHT_VARIANTS[idx] : OUTSIDE_DAY_VARIANTS[idx];
  }

  return VN_BACKGROUNDS[scene as keyof typeof VN_BACKGROUNDS] || VN_BACKGROUNDS.room;
};

/**
 * Picks the default scene based on time of day
 * Default schedule keeps Monika indoors; outside only when explicitly triggered
 * 
 * Schedule:
 * - 06:00-10:00 → Kitchen
 * - 10:00-16:00 → School  
 * - 16:00-22:00 → Room
 * - 22:00-06:00 → Room (Night)
 */
export const pickVnScene = (date: Date): string => {
  const h = date.getHours();

  if (h >= SCENE_SCHEDULE.KITCHEN_START && h < SCENE_SCHEDULE.KITCHEN_END) {
    return 'kitchen';
  }

  if (h >= SCENE_SCHEDULE.SCHOOL_START && h < SCENE_SCHEDULE.SCHOOL_END) {
    return 'school';
  }

  if (h >= SCENE_SCHEDULE.ROOM_EVENING_START && h < SCENE_SCHEDULE.ROOM_EVENING_END) {
    return 'room';
  }

  // Default: room (night or any other time)
  return 'room';
};

/**
 * Checks if a scene is valid (exists in VN_BACKGROUNDS)
 */
export const isValidScene = (scene: string): boolean => {
  return scene in VN_BACKGROUNDS;
};
