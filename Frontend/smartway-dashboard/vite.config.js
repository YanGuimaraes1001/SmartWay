import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
    server: {
    host: true,      // aceita conexões externas (equivalente a 0.0.0.0)
    port: 5174,      // opcional, se quiser garantir a porta
    // hmr: { host: 'SEU_IP' } // ver nota sobre HMR abaixo, se precisar
  }
})
