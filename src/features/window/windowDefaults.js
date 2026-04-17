export const getDefaultPositions = () => ({
  video: { x: window.innerWidth - 230, y: window.innerHeight - 210 },
  screen: { x: window.innerWidth - 230, y: window.innerHeight - 210 },
  chat: { x: window.innerWidth / 2, y: window.innerHeight / 2 + 100 },
  browser: { x: 320, y: window.innerHeight - 315 },
  study: { x: Math.max(420, Math.round(window.innerWidth * 0.32)), y: window.innerHeight / 2 },
  minecraft: { x: window.innerWidth - 320, y: 360 },
});

export const getDefaultElementSizes = () => ({
  chat: { w: 980, h: 320 },
  browser: { w: 600, h: 450 },
  video: { w: 360, h: 240 },
  screen: { w: 360, h: 240 },
  study: { w: 1120, h: 760 },
  minecraft: { w: 384, h: 520 },
});
