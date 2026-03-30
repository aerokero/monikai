import mineflayer from 'mineflayer';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '.env') });

const config = {
  host: process.env.MC_HOST || 'localhost',
  port: parseInt(process.env.MC_PORT || '25565'),
  username: process.env.MC_USERNAME || 'strawberryglass',
  auth: process.env.MC_AUTH || 'offline',
  version: process.env.MC_VERSION || '1.20.4'
};

console.log('=== Minecraft Connection Test ===');
console.log('Config:', config);
console.log('Starting bot creation...\n');

const bot = mineflayer.createBot({
  host: config.host,
  port: config.port,
  username: config.username,
  auth: config.auth,
  version: config.version
});

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
  console.log('  Full Error:', error);
  console.log('  Stack:', error.stack);
});

setTimeout(() => {
  console.log('[TIMEOUT] No connection after 10 seconds');
  process.exit(1);
}, 10000);
