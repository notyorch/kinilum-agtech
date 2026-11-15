// Textos de la interfaz. Nada de cadenas sueltas en componentes:
// cuando llegue el inglés, va en un en.ts con la misma forma.
export const es = {
  app: {
    name: 'kinilum',
    nav: 'Secciones',
    illustrative: 'Caso ilustrativo',
    pending: 'Sin datos todavía',
    closing: 'La decisión es suya. Revísela con su técnico local.',
  },
  tabs: {
    parcela: 'Mi parcela',
    comparar: 'Comparar',
    simular: 'Simular',
    evidencia: 'Evidencia',
    ajustes: 'Ajustes',
  },
  parcela: {
    title: 'Mi parcela',
    intro: 'Aquí verá su parcela, el clima de su zona y su suelo.',
    gridCaption: 'Vista de ejemplo. Cada celda es un cuadro de la grilla común.',
    measured: 'Medido',
    noData: 'Sin dato',
    cards: [
      { title: 'Clima en su zona', text: 'Lluvia y calor de las últimas temporadas.' },
      { title: 'Suelo', text: 'Tipo de suelo y profundidad hasta la roca.' },
      { title: 'Agua disponible', text: 'Temporal o riego, según lo que usted indique.' },
    ],
  },
  comparar: {
    title: 'Comparar rotaciones',
    intro: 'Cuatro caminos para su parcela, lado a lado.',
    notComputed: 'Sin calcular',
    strategies: [
      { name: 'Maíz de temporal', note: 'Lo que hace hoy: suelo desnudo en secas.' },
      { name: 'Maíz → mucuna → maíz', note: 'Cobertura de leguminosa en relevo.' },
      { name: 'Maíz → frijol → maíz', note: 'Frijol regional entre ciclos.' },
      { name: 'Maíz → sorgo → maíz', note: 'Sorgo en la temporada seca.' },
    ],
  },
  simular: {
    title: '¿Qué pasa si…?',
    intro: 'Mueva la lluvia o el calor y vea qué tan estable es cada sugerencia.',
    controls: [
      { title: 'Ajustar lluvia', text: 'De un año seco a un año lluvioso.' },
      { title: 'Ajustar calor', text: 'Días con más de 35 °C en la temporada.' },
      { title: 'Cambiar prioridad', text: 'Ahorrar agua, mejorar el suelo o ingreso.' },
    ],
  },
  evidencia: {
    title: 'Ver evidencia',
    intro: 'De dónde sale cada dato y qué tan fino es.',
    notConnected: 'Sin conectar',
    sources: [
      { name: 'POWER', res: '0.5°', text: 'Clima modelado de su zona.' },
      { name: 'GPM', res: '0.1°', text: 'Lluvia estimada por satélite.' },
      { name: 'HLS', res: '30 m', text: 'Verdor de la vegetación.' },
      { name: 'MODIS', res: '250 m', text: 'Vegetación y temperatura del suelo.' },
      { name: 'ECOSTRESS', res: '70 m', text: 'Estrés por calor en las plantas.' },
      { name: 'SMAP', res: '9 km', text: 'Humedad del suelo en su zona.' },
      { name: 'SRTM', res: '30 m', text: 'Relieve y pendiente.' },
    ],
  },
  ajustes: {
    title: 'Ajustes',
    theme: 'Tema',
    themes: { system: 'Dispositivo', light: 'Claro', dark: 'Oscuro' },
    about: 'Acerca de kinilum',
    aboutText: 'kinilum compara rotaciones de cultivo con datos satelitales de la NASA. Apoya; no decide.',
    version: 'Versión 0.0.0',
  },
} as const;

export type Strings = typeof es;
export const t = es;
