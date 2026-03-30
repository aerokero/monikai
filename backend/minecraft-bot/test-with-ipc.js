import mineflayer from 'mineflayer';
import pathfinderPkg from 'mineflayer-pathfinder';
import ArmorManager from 'mineflayer-armor-manager';
import autoEat from 'mineflayer-auto-eat';
import pvpPkg from 'mineflayer-pvp';
import toolPkg from 'mineflayer-tool';
import collectBlockPkg from 'mineflayer-collectblock';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '.env') });

const { pathfinder: Pathfinder } = pathfinderPkg;
const { plugin: pvp } = pvpPkg;
const { plugin: collectBlock } = collectBlockPkg;
const toolPlugin = toolPkg.plugin;

const config = {
  host: process.env.MC_HOST || 'localhost',
  port: parseInt(process.env.MC_PORT || '25565'),
  username: process.env.MC_USERNAME || 'strawberryglass',
  auth: process.env.MC_AUTH || 'offline',
  version: process.env.MC_VERSION || '1.20.4'
};

console.log('=== Minecraft Connection Test WITH IPC ===');
console.log('Config:', config);
console.log('Starting bot creation...\n');

const bot = mineflayer.createBot({
  host: config.host,
  port: config.port,
  username: config.username,
  auth: config.auth,
  version: config.version
});

console.log('[INIT] Loading plugins...');
bot.loadPlugin(Pathfinder);
bot.loadPlugin(ArmorManager);
bot.loadPlugin(autoEat);
bot.loadPlugin(toolPlugin);
bot.loadPlugin(collectBlock);
bot.loadPlugin(pvp);
console.log('[INIT] All plugins loaded');

// Setup status updates
let statusInterval = null;

bot.once('spawn', () => {
  console.log('[SPAWN] Bot spawned!');
  console.log('[SPAWN] Position:', bot.entity.position);
  
  // Start status updates
  statusInterval = setInterval(() => {
    const position = bot.entity.position;
    const health = bot.health;
    const hunger = bot.food;
    const dimension = bot.game.dimension;
    console.log('[STATUS] health:', health, 'hunger:', hunger, 'pos:', position);
  }, 1000);
});

// Setup stdin action handler
console.log('[INIT] Setting up stdin handler...');
process.stdin.setEncoding('utf-8');
process.stdin.on('data', async (data) => {
  const line = data.trim();
  if (!line) return;
  console.log('[ACTION] Received:', line);
});

bot.on('end', (reason) => {
  console.log('[END] Connection ended:', reason);
  if (statusInterval) clearInterval(statusInterval);
  process.exit(0);
});

bot.on('error', (error) => {
  console.log('[ERROR] Error occurred:');
  console.log('  Message:', error.message);
  console.log('  Code:', error.code);
});

bot.once('login', () => {
  console.log('[LOGIN] Successfully logged in!');
});

setTimeout(() => {
  console.log('[TIMEOUT] No spawn after 10 seconds');
  process.exit(1);
}, 10000);
