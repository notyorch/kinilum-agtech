import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './ds/tokens.css';
import './ds/components.css';
import './ds/primitives.css';
import { AppShell } from './shell/AppShell';
import { ThemeProvider } from './shell/theme';
import { OfflineProvider } from './offline/OfflineProvider';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <OfflineProvider>
        <AppShell />
      </OfflineProvider>
    </ThemeProvider>
  </StrictMode>,
);
