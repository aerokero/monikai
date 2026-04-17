/**
 * VN Background & Scene Constants
 * 
 * Manages all Monika's location visuals and scene configurations
 */

// Base scene backgrounds (used as fallbacks)
export const VN_BACKGROUNDS = {
  room: "/vn/location/bg_room.png",
  kitchen: "/vn/location/bg_kitchen.png",
  outside: "/vn/location/bg_outside.png",
  school: "/vn/location/bg_school.png",
  restaurant: "/vn/location/bg_restaurant.png",
};

// Room backgrounds (day/night variants)
export const ROOM_DAY_BG = "/vn/location/bg_room.png";
export const ROOM_NIGHT_BG = "/vn/location/bg_room_night.png";

// Outside backgrounds (multiple variants for variety)
export const OUTSIDE_DAY_VARIANTS = [
  "/vn/location/bg_outside.png",
  "/vn/location/bg_outside_2.png",
];

export const OUTSIDE_NIGHT_VARIANTS = [
  "/vn/location/bg_outside_night.png",
  "/vn/location/bg_outside_2_night.png",
];

// Scene configuration - determines Monika's location based on time
export const SCENE_SCHEDULE = {
  // 6:00-10:00 → Kitchen
  KITCHEN_START: 6,
  KITCHEN_END: 10,
  // 10:00-16:00 → School
  SCHOOL_START: 10,
  SCHOOL_END: 16,
  // 16:00-22:00 → Room
  ROOM_EVENING_START: 16,
  ROOM_EVENING_END: 22,
  // 22:00-6:00 → Room (Night)
  NIGHT_START: 22,
  NIGHT_END: 6,
};

// Night hours (for determining day/night background variants)
export const NIGHT_HOUR_START = 22;
export const NIGHT_HOUR_END = 6;
