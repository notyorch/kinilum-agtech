import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './ds/tokens.css';
import './ds/components.css';
import './ds/primitives.css';
import { AppShell } from './shell/AppShell';
import { ThemeProvider } from './shell/theme';
import { OfflineProvider } from './offline/OfflineProvider';
import { LangProvider } from './i18n/lang';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LangProvider>
      <ThemeProvider>
        <OfflineProvider>
          <AppShell />
        </OfflineProvider>
      </ThemeProvider>
    </LangProvider>
  </StrictMode>,
);
