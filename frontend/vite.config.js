import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
 
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://167.172.137.169',
      '/ui':  'http://167.172.137.169',
      '/shows': 'http://167.172.137.169',
      '/bin': 'http://167.172.137.169',
      '/vouchers': 'http://167.172.137.169',
      '/trade': 'http://167.172.137.169',
      '/inventory': 'http://167.172.137.169',
      '/claims': 'http://167.172.137.169',
      '/users': 'http://167.172.137.169',
      '/media': 'http://167.172.137.169',
      '/health': 'http://167.172.137.169',
    }
  }
})