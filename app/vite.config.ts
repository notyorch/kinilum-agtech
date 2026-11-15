import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Base relativa: la app funciona igual en la raíz de un dominio o en /<repo>/.
export default defineConfig({
  base: './',
  plugins: [react()],
});
