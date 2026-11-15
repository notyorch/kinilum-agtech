import { Badge, Button, Callout } from '../ds/components';
import { t } from '../i18n/es';
import { Card } from '../screens/parts';
import { useOffline } from './OfflineProvider';
import type { OfflineReadiness } from './readiness.ts';
import './offline.css';

/** Con señal en verde y sin señal en rojo, con palabra e ícono (el color solo no basta). */
function SignalPill({ online }: { online: boolean }) {
  return (
    <Badge tone={online ? 'positive' : 'risk'} className={online ? undefined : 'kn-badge-offline'}>
      {online ? t.offline.online : t.offline.offline}
    </Badge>
  );
}

/** «Con señal / Sin señal», siempre a la vista. */
export function SignalBadge() {
  const { online } = useOffline();
  return (
    <span role="status" className="kn-signal">
      <SignalPill online={online} />
    </span>
  );
}

/** Avisos de versión nueva de los datos y de la app. Ninguno cambia nada sin que el usuario acepte. */
export function UpdateNotices() {
  const { newData, newApp, useNewData, updateApp } = useOffline();
  if (!newData && !newApp) return null;
  return (
    <div className="kn-notices">
      {newData && (
        <Callout tone="info" title={t.offline.newData}>
          {t.offline.newDataText}
          <div className="kn-notices__action">
            <Button size="sm" onClick={useNewData}>
              {t.offline.useNewData}
            </Button>
          </div>
        </Callout>
      )}
      {newApp && (
        <Callout tone="info" title={t.offline.newApp}>
          {t.offline.newAppText}
          <div className="kn-notices__action">
            <Button size="sm" onClick={updateApp}>
              {t.offline.update}
            </Button>
          </div>
        </Callout>
      )}
    </div>
  );
}

const copy = (): Record<OfflineReadiness, { title: string; text: string; tone: 'positive' | 'info' | 'unknown' | 'risk' }> => ({
  ready: { title: t.offline.ready, text: t.offline.readyText, tone: 'positive' },
  saving: { title: t.offline.saving, text: t.offline.savingText, tone: 'info' },
  'needs-signal': { title: t.offline.needsSignal, text: t.offline.needsSignalText, tone: 'info' },
  'shell-missing': { title: t.offline.shellMissing, text: t.offline.shellMissingText, tone: 'unknown' },
  unsupported: { title: t.offline.unsupported, text: t.offline.unsupportedText, tone: 'risk' },
  failed: { title: t.offline.failed, text: t.offline.failedText, tone: 'risk' },
  dev: { title: t.offline.dev, text: t.offline.devText, tone: 'unknown' },
});

/** En Ajustes: el estado completo. «Listo» solo aparece cuando datos y aplicación quedaron guardados y releídos. */
export function OfflineCard() {
  const { readiness, dataDate, online } = useOffline();
  const c = copy()[readiness];
  return (
    <Card title={t.offline.title}>
      <div className="kn-offline__row">
        <Badge tone={c.tone}>{c.title}</Badge>
        <SignalPill online={online} />
      </div>
      <p className="kn-card__text">{c.text}</p>
      {dataDate && readiness !== 'dev' && <p className="kn-meta">{`${t.offline.dataFrom} ${dataDate}`}</p>}
    </Card>
  );
}
