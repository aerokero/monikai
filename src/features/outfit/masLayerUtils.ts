import {
  OUTFITS_WITHOUT_ARM_OVERLAYS,
  OUTFITS_WITHOUT_CROSSED_ARM_10,
  OUTFITS_WITHOUT_LEANING_RIGHT_ARM_10,
} from './outfitConstants';

type VisualState = {
  clothesFolder: string;
  hairStyle: string;
  headAccessories: string[];
  ahogeAccessory: string | null;
  deskAccessories: string[];
};

export const buildMasLayers = ({
  personalityMood,
  personalityEnergy,
  visualState,
  headpatActive,
  showStudyWindow,
  currentHour,
  currentMinute,
  randomPose,
  vnScene,
  isBlinking,
  randomGlance,
  eatTogetherActive,
  eatTogetherMeal,
  monikaMeal,
  monikaMealAssets,
  eatMealAssets,
}: {
  personalityMood: string;
  personalityEnergy: number;
  visualState: VisualState;
  headpatActive: boolean;
  showStudyWindow: boolean;
  currentHour: number;
  currentMinute: number;
  randomPose: string | null;
  vnScene: string;
  isBlinking: boolean;
  randomGlance: string | null;
  eatTogetherActive: boolean;
  eatTogetherMeal: string | null;
  monikaMeal: string;
  monikaMealAssets: Record<string, string>;
  eatMealAssets: Record<string, string>;
}) => {
  const baseMood = (personalityMood || 'neutral').toLowerCase();
  const mood = headpatActive ? `${baseMood} happy` : baseMood;
  const { clothesFolder, hairStyle, headAccessories, ahogeAccessory, deskAccessories } = visualState;
  const isTowelOutfit = clothesFolder === 'bath_towel_white';
  const hasOutfitArmOverlays = !OUTFITS_WITHOUT_ARM_OVERLAYS.has(clothesFolder);
  const hasCrossedArm10 = !OUTFITS_WITHOUT_CROSSED_ARM_10.has(clothesFolder);
  const hasLeaningRightArm10 = !OUTFITS_WITHOUT_LEANING_RIGHT_ARM_10.has(clothesFolder);
  const isStudyMode = showStudyWindow;
  const forceClosedEyes = headpatActive;
  const forceHappy = headpatActive;

  const energy = Number(personalityEnergy ?? 0.8);
  const leanChance =
    energy < 0.1 ? 1.0 :
    energy < 0.25 ? 0.7 :
    energy < 0.35 ? 0.45 :
    energy < 0.5 ? 0.2 : 0.0;
  const leanBucket = Math.floor((currentHour * 60 + currentMinute) / 10);
  const leanRoll = Math.abs(Math.sin(leanBucket * 9301 + 49297) * 10000) % 1;
  const energyLean = leanRoll < leanChance;

  const isLeaning = !isStudyMode && (
    energyLean ||
    mood.includes('leaning') ||
    mood.includes('mysterious') ||
    mood.includes('foggy') ||
    mood.includes('dream') ||
    mood.includes('love') ||
    mood.includes('enchanted')
  );

  let armStyle = 'def';
  if (!isLeaning) {
    if (mood.includes('angry') || mood.includes('annoyed') || mood.includes('bored')) {
      armStyle = 'crossed';
    } else if (mood.includes('thinking') || mood.includes('focus')) {
      armStyle = 'steepling';
    } else if (mood.includes('explaining') || mood.includes('teaching')) {
      armStyle = 'point';
    } else if (randomPose) {
      armStyle = randomPose;
    }
  }
  if (isStudyMode) {
    armStyle = 'def';
  }
  if (isTowelOutfit) {
    armStyle = 'def';
  }
  if (!isLeaning && !hasOutfitArmOverlays && armStyle === 'def') {
    armStyle = 'restpoint';
  }

  if (vnScene === 'outside') {
    let sprite = 'ai_normal.png';

    if (headpatActive) {
      sprite = 'ai_closed_eyes.png';
    } else if (isLeaning) {
      sprite = 'ai_leaning.png';
    } else if (isBlinking) {
      sprite = 'ai_closed_eyes.png';
    } else if (armStyle === 'point') {
      sprite = (mood.includes('happy') || mood.includes('excited'))
        ? 'ai_arm_point_happy.png'
        : 'ai_arm_point_open.png';
    } else if (mood.includes('angry') || mood.includes('annoyed')) {
      sprite = 'ai_annoyed.png';
    } else if (mood.includes('worried') || mood.includes('sad') || mood.includes('anxious') || mood.includes('depressed')) {
      sprite = 'ai_worried.png';
    } else if (mood.includes('embarrassed')) {
      sprite = 'ai_embarrassed.png';
    } else if (mood.includes('shy') || mood.includes('love')) {
      sprite = 'ai_shy.png';
    } else if (mood.includes('happy') || mood.includes('excited')) {
      sprite = 'ai_happy.png';
    } else if (mood.includes('neutral')) {
      sprite = 'ai_neutral.png';
    }
    return [`/vn/monika/s/${sprite}`];
  }

  const facePrefix = isLeaning ? '/vn/monika/f/face-leaning-def-' : '/vn/monika/f/face-';

  let eyes = 'eyes-normal.png';
  let eyebrows = 'eyebrows-mid.png';
  let mouth = 'mouth-smile.png';
  let nose = 'nose-def.png';
  let blush: string | null = null;

  if (mood.includes('happy') || mood.includes('excited') || mood.includes('joy')) {
    mouth = 'mouth-smile.png';
  } else if (mood.includes('sad') || mood.includes('lonely') || mood.includes('depressed')) {
    eyebrows = 'eyebrows-knit.png';
  } else if (mood.includes('angry') || mood.includes('annoyed')) {
    eyebrows = 'eyebrows-furrowed.png';
    mouth = 'mouth-angry.png';
  } else if (mood.includes('love') || mood.includes('shy')) {
    eyes = 'eyes-soft.png';
    mouth = 'mouth-smile.png';
    blush = 'blush-shade.png';
  } else if (mood.includes('surprised') || mood.includes('shocked')) {
    eyes = 'eyes-wide.png';
    mouth = 'mouth-gasp.png';
    eyebrows = 'eyebrows-up.png';
  } else if (mood.includes('thinking')) {
    eyebrows = 'eyebrows-think.png';
    eyes = 'eyes-left.png';
  }

  if (randomGlance && !isBlinking && !forceClosedEyes) {
    if (!eyes.includes('closed')) {
      if (randomGlance === 'left') eyes = 'eyes-left.png';
      else if (randomGlance === 'right') eyes = 'eyes-right.png';
    }
  }

  if (forceClosedEyes) {
    eyes = 'eyes-closedhappy.png';
  } else if (isBlinking) {
    if (mood.includes('angry') || mood.includes('annoyed')) {
      eyes = 'eyes-closedangry.png';
    } else {
      eyes = 'eyes-closedhappy.png';
    }
  }
  if (forceHappy) {
    mouth = 'mouth-smile.png';
  }

  const hairBack = isLeaning ? `/vn/monika/h/${hairStyle}/def-0.png` : `/vn/monika/h/${hairStyle}/0.png`;
  const hairFront = isLeaning ? `/vn/monika/h/${hairStyle}/def-10.png` : `/vn/monika/h/${hairStyle}/10.png`;
  const accFrame = isLeaning ? '5' : '0';
  const headAccessoryBackLayers: string[] = [];
  const headAccessoryFrontLayers: string[] = [];
  if (Array.isArray(headAccessories) && headAccessories.length) {
    headAccessories.forEach((acc) => {
      const layer = `/vn/monika/a/${acc}/${accFrame}.png`;
      if (isLeaning && String(acc).startsWith('ribbon_')) {
        headAccessoryBackLayers.push(layer);
      } else {
        headAccessoryFrontLayers.push(layer);
      }
    });
  }

  const layers = [
    '/vn/monika/t/chair-def.png',
    hairBack,
    ...headAccessoryBackLayers,
  ];

  const armLayers: string[] = [];
  let headBase: string | null = null;

  let leaningTopOverlay: string | null = null;
  if (isLeaning) {
    layers.push(
      '/vn/monika/b/body-leaning-def-0.png',
      `/vn/monika/c/${clothesFolder}/body-leaning-def-0.png`,
      '/vn/monika/b/body-leaning-def-1.png',
      ...(isTowelOutfit ? [] : [`/vn/monika/c/${clothesFolder}/body-leaning-def-1.png`])
    );
    if (isTowelOutfit) {
      leaningTopOverlay = `/vn/monika/c/${clothesFolder}/body-leaning-def-1.png`;
    }
    headBase = '/vn/monika/b/body-leaning-def-head.png';

    armLayers.push(
      '/vn/monika/b/arms-leaning-def-left-def-10.png',
      '/vn/monika/b/arms-leaning-def-right-def-5.png',
      '/vn/monika/b/arms-leaning-def-right-def-10.png'
    );
    if (!isTowelOutfit && hasOutfitArmOverlays) {
      armLayers.push(
        `/vn/monika/c/${clothesFolder}/arms-leaning-def-left-def-10.png`,
        `/vn/monika/c/${clothesFolder}/arms-leaning-def-right-def-5.png`
      );
      if (hasLeaningRightArm10) {
        armLayers.push(`/vn/monika/c/${clothesFolder}/arms-leaning-def-right-def-10.png`);
      }
    }
  } else {
    layers.push(
      '/vn/monika/b/body-def-0.png',
      `/vn/monika/c/${clothesFolder}/body-def-0.png`,
      '/vn/monika/b/body-def-1.png',
      `/vn/monika/c/${clothesFolder}/body-def-1.png`
    );
    headBase = '/vn/monika/b/body-def-head.png';

    if (armStyle === 'crossed') {
      armLayers.push('/vn/monika/b/arms-crossed-5.png', '/vn/monika/b/arms-crossed-10.png');
      if (!isTowelOutfit && hasOutfitArmOverlays) {
        armLayers.push(`/vn/monika/c/${clothesFolder}/arms-crossed-5.png`);
        if (hasCrossedArm10) {
          armLayers.push(`/vn/monika/c/${clothesFolder}/arms-crossed-10.png`);
        }
      }
    } else if (armStyle === 'steepling') {
      armLayers.push('/vn/monika/b/arms-steepling-10.png');
      if (!isTowelOutfit && hasOutfitArmOverlays) armLayers.push(`/vn/monika/c/${clothesFolder}/arms-steepling-10.png`);
    } else if (armStyle === 'point') {
      armLayers.push('/vn/monika/b/arms-left-down-0.png', '/vn/monika/b/arms-right-point-0.png');
      if (!isTowelOutfit && hasOutfitArmOverlays) {
        armLayers.push(
          `/vn/monika/c/${clothesFolder}/arms-left-down-0.png`,
          `/vn/monika/c/${clothesFolder}/arms-right-point-0.png`
        );
      }
    } else if (armStyle === 'restpoint') {
      armLayers.push('/vn/monika/b/arms-left-rest-10.png', '/vn/monika/b/arms-right-restpoint-10.png');
      if (!isTowelOutfit && hasOutfitArmOverlays) {
        armLayers.push(
          `/vn/monika/c/${clothesFolder}/arms-left-rest-10.png`,
          `/vn/monika/c/${clothesFolder}/arms-right-restpoint-10.png`
        );
      }
    } else {
      armLayers.push('/vn/monika/b/arms-left-down-0.png', '/vn/monika/b/arms-right-down-0.png');
      if (!isTowelOutfit && hasOutfitArmOverlays) {
        armLayers.push(
          `/vn/monika/c/${clothesFolder}/arms-left-down-0.png`,
          `/vn/monika/c/${clothesFolder}/arms-right-down-0.png`
        );
      }
    }
  }

  const eatLayers: string[] = [];
  if (eatTogetherActive) {
    const monikaLayer = monikaMealAssets[monikaMeal] || monikaMealAssets.pasta;
    if (monikaLayer) eatLayers.push(monikaLayer);
    const userLayer = eatTogetherMeal ? eatMealAssets[eatTogetherMeal] : null;
    if (userLayer) eatLayers.push(userLayer);
  }

  layers.push('/vn/monika/t/table-def.png');
  if (Array.isArray(deskAccessories) && deskAccessories.length) {
    deskAccessories.forEach((acc) => {
      layers.push(`/vn/monika/a/${acc}/0.png`);
    });
  }
  layers.push('/vn/monika/t/table-def-s.png');

  layers.push(...armLayers);
  if (leaningTopOverlay) layers.push(leaningTopOverlay);

  if (headBase) layers.push(headBase);

  const faceParts = [facePrefix + nose];
  if (clothesFolder === 'bath_towel_white') {
    faceParts.push(facePrefix + nose);
  }
  faceParts.push(facePrefix + mouth, facePrefix + eyes, facePrefix + eyebrows);
  layers.push(...faceParts);

  if (blush) layers.push(facePrefix + blush);

  layers.push(hairFront);

  if (ahogeAccessory) {
    layers.push(`/vn/monika/a/${ahogeAccessory}/${accFrame}.png`);
  }

  if (headAccessoryFrontLayers.length) layers.push(...headAccessoryFrontLayers);

  if (eatLayers.length) layers.push(...eatLayers);

  return layers;
};
