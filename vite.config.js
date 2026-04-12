import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    base: './', // Important for Electron
    server: {
        port: 5173,
        hmr: false, // Disable HMR to force full page reloads
        proxy: {
            '/study': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            }
        }
    }
})
