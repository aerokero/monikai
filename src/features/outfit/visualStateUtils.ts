import { AHOGE_ACCESSORIES } from './outfitConstants';

const WEATHER_CODE_TO_KEY: Array<[number[], string]> = [
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

const weatherKeyFromCode = (code: unknown) => {
  const numericCode = Number(code);
  if (Number.isNaN(numericCode)) return '';

  const match = WEATHER_CODE_TO_KEY.find(([codes]) => codes.includes(numericCode));
  return match ? match[1] : '';
};

const weatherText = (weather: unknown) => {
  if (!weather) return '';

  if (typeof weather === 'string') return weather;

  if (typeof weather === 'object') {
    const record = weather as Record<string, unknown>;
    const condition = record.condition ?? record.weather ?? record.description;

    if (typeof condition === 'string' && condition.trim()) {
      return condition;
    }

    const codeKey = weatherKeyFromCode(record.code);
    if (codeKey) return codeKey;

    if (condition != null) return String(condition);
  }

  return String(weather);
};

export const buildVisualState = ({
  mood,
  affection,
  weather,
  currentHour,
  currentMinute,
  currentMonth,
  currentDay,
  currentYear,
  vnScene,
  eatTogetherActive,
  sessionModeActive,
  showStudyWindow,
}: {
  mood: string;
  affection: number;
  weather: string;
  currentHour: number;
  currentMinute: number;
  currentMonth: number;
  currentDay: number;
  currentYear: number;
  vnScene: string;
  eatTogetherActive: boolean;
  sessionModeActive: boolean;
  showStudyWindow: boolean;
}) => {
  const normalizedMood = (mood || 'neutral').toLowerCase();
  const normalizedWeather = weatherText(weather).toLowerCase();
  const isHalloween = currentMonth === 9 && currentDay === 31;
  const isChristmas = currentMonth === 11 && currentDay >= 24 && currentDay <= 26;
  const isValentines = currentMonth === 1 && currentDay === 14;
  const tempMatch = normalizedWeather.match(/(-?\d+(?:\.\d+)?)\s*°c/i);
  const tempC = tempMatch ? parseFloat(tempMatch[1]) : null;
  const isCold = tempC !== null ? tempC <= 6 : normalizedWeather.includes('snowy');
  const isRainy = normalizedWeather.includes('rainy') || normalizedWeather.includes('thunderstorm');

  let hairStyle = 'def';
  const isNight = currentHour >= 20 || currentHour < 7;
  const isLateNight = currentHour >= 22 || currentHour < 6;
  const isShowerTime =
    (currentHour === 6 && currentMinute < 30) ||
    (currentHour === 19 && currentMinute < 30);

  if (isNight) {
    hairStyle = 'down';
  }

  let clothesFolder = 'def';
  let outfitName = 'School Uniform';
  let headAccessories = ['ribbon_def'];
  let ahogeAccessory: string | null = null;
  let deskAccessories: string[] = [];

  const addHeadAccessory = (acc: string) => {
    if (!acc) return;
    if (!headAccessories.includes(acc)) headAccessories.push(acc);
  };
  const addDeskAccessory = (acc: string) => {
    if (!acc) return;
    if (!deskAccessories.includes(acc)) deskAccessories.push(acc);
  };

  if (AHOGE_ACCESSORIES.length) {
    const daySeed = currentYear * 10000 + (currentMonth + 1) * 100 + currentDay;
    ahogeAccessory = AHOGE_ACCESSORIES[daySeed % AHOGE_ACCESSORIES.length];
  }

  if ((currentMonth === 11 && currentDay === 31) || (currentMonth === 0 && currentDay === 1)) {
    clothesFolder = 'new_years_dress';
    outfitName = "New Year's Dress";
  } else if (currentMonth === 1 && currentDay === 14) {
    clothesFolder = isNight ? 'vday_lingerie' : 'blackpinkdress';
    outfitName = isNight ? "Valentine's Lingerie" : 'Blackpink Dress';
  } else if (isHalloween) {
    clothesFolder = isNight ? 'spider_lingerie' : 'marisa';
    outfitName = isNight ? 'Spider Lingerie' : 'Witch Cosplay (Marisa)';
  } else if (isChristmas) {
    clothesFolder = isNight ? 'santa_lingerie' : 'santa';
    outfitName = isNight ? 'Santa Lingerie' : 'Santa Costume';
  } else {
    if (isNight && affection > 50 && (normalizedMood.includes('flirty') || normalizedMood.includes('love') || normalizedMood.includes('romantic'))) {
      clothesFolder = 'vday_lingerie';
      outfitName = "Valentine's Lingerie";
    } else if (isLateNight) {
      clothesFolder = 'bath_towel_white';
      outfitName = 'White Bath Towel';
      headAccessories = [];
    } else if (isShowerTime) {
      clothesFolder = 'bath_towel_white';
      hairStyle = 'wet';
      outfitName = 'White Bath Towel';
      headAccessories = [];
    } else if (!isNight && (normalizedWeather.includes('sunny') || normalizedWeather.includes('clear'))) {
      clothesFolder = 'sundress_white';
      outfitName = 'White Sundress';
    } else if (!isNight && (showStudyWindow || sessionModeActive || normalizedMood.includes('focus') || normalizedMood.includes('thinking') || normalizedMood.includes('learning') || normalizedMood.includes('studying'))) {
      clothesFolder = 'blazerless';
      outfitName = 'School Uniform (Blazerless)';
    } else if (isNight) {
      outfitName = 'School Uniform';
    }
  }

  if (eatTogetherActive) {
    clothesFolder = 'blackdress';
    outfitName = 'Black Dress';
    headAccessories = ['ribbon_black'];
  }

  if (vnScene === 'outside') {
    clothesFolder = 'def';
    outfitName = 'School Uniform';
  }

  if (showStudyWindow) {
    clothesFolder = 'def';
    outfitName = 'School Uniform';
    hairStyle = 'def';
  }

  if (isChristmas) addHeadAccessory('holly_hairclip');
  if (isRainy) addHeadAccessory('water_drops');
  if (clothesFolder === 'marisa') {
    headAccessories = ['marisa_witchhat', 'marisa_strandbow'];
  }
  if (clothesFolder === 'bath_towel_white') {
    headAccessories = [];
  }

  if (isChristmas) {
    addDeskAccessory('candycane');
    addDeskAccessory('christmas_cookies');
  }
  if (isValentines) {
    addDeskAccessory('roses');
    addDeskAccessory('heartchoc');
  }
  if (isHalloween) {
    addDeskAccessory('desk_candy_jack_half');
    addDeskAccessory(isNight ? 'desk_lantern_lit' : 'desk_lantern_unlit');
  }
  if (isCold) addDeskAccessory('thermos_mug');
  if (!isCold && !isHalloween && !isChristmas && !isValentines && !eatTogetherActive) {
    const drinkSeed = currentYear * 1000000 + (currentMonth + 1) * 10000 + currentDay * 100 + currentHour;
    if (drinkSeed % 3 === 0) addDeskAccessory('mug');
  }

  return { clothesFolder, hairStyle, outfitName, headAccessories, ahogeAccessory, deskAccessories };
};
