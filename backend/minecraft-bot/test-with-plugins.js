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

console.log('=== Minecraft Connection Test WITH PLUGINS ===');
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
try {
  bot.loadPlugin(Pathfinder);
  console.log('[INIT] Pathfinder loaded');
  bot.loadPlugin(ArmorManager);
  console.log('[INIT] ArmorManager loaded');
  bot.loadPlugin(autoEat);
  console.log('[INIT] AutoEat loaded');
  bot.loadPlugin(toolPlugin);
  console.log('[INIT] Tool plugin loaded');
  bot.loadPlugin(collectBlock);
  console.log('[INIT] CollectBlock loaded');
  bot.loadPlugin(pvp);
  console.log('[INIT] PVP loaded');
} catch(e) {
  console.log('[INIT ERROR]', e.message);
}

bot.once('login', () => {
  console.log('[LOGIN] Successfully logged in!');
});

bot.once('spawn', () => {
  console.log('[SPAWN] Bot spawned!');
  console.log('[SPAWN] Position:', bot.entity.position);
  bot.quit('Test complete');
});

bot.on('end', (reason) => {
  console.log('[END] Connection ended:', reason);
  process.exit(0);
});

bot.on('error', (error) => {
  console.log('[ERROR] Error occurred:');
  console.log('  Message:', error.message);
  console.log('  Code:', error.code);
  console.log('  Stack:', error.stack?.split('\n').slice(0, 3).join('\n'));
});

setTimeout(() => {
  console.log('[TIMEOUT] No spawn after 10 seconds');
  process.exit(1);
}, 10000);
