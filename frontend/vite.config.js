import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        router: (req) => {
          const host = req.headers.host || 'localhost:5173';
          const backendHost = host.replace('5173', '8002');
          return `http://${backendHost}`;
        },
        changeOrigin: true,
      },
    },
  },
})
