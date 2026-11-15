import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './ds/tokens.css';
import { AppShell } from './shell/AppShell';
import { ThemeProvider } from './shell/theme';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <AppShell />
    </ThemeProvider>
  </StrictMode>,
);
