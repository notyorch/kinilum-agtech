/* eslint-disable */
/*
 * GENERADO por scripts/gen-schema-types.mjs desde shared/schema/. NO lo edite a mano:
 * cambie el esquema (requiere la aprobación de Jorge) y corra `npm run gen:schema`.
 */

/**
 * Identificador opaco de la parcela. Es el único acceso (sin login): largo y no adivinable en producción.
 */
export type ParcelId = string;
export type IsoDate = string;
/**
 * Dónde aplica el dato. zone y region son contexto («en su zona»), nunca color dentro del polígono.
 */
export type SupportLevel = 'parcel' | 'surroundings' | 'zone' | 'region';
/**
 * Cómo se obtuvo. Solo measured es sólido; el resto se dibuja punteado.
 */
export type Method = 'measured' | 'interpolated' | 'modeled' | 'assumed';
export type Quality = 'high' | 'medium' | 'low' | 'none';
export type Assumption =
  'innerBuffer' | 'greenNotStubble' | 'modeledClimate' | 'karstDepth' | 'teamAssumption' | 'contextOnly';
/**
 * Cultivo de rotación del catálogo (pipeline/rules/crops.<versión>.yaml).
 */
export type RotationCrop = 'frijol' | 'garbanzo' | 'sorgo' | 'trigo';

/**
 * Paquete de una parcela: el único archivo que viaja del pipeline a la app (public/packages/<parcela>.<fecha>.json). Pesa menos de 500 KB (objetivo ≈ 260 KB). NO lleva el polígono exacto ni nombres: solo un punto redondeado a 2 decimales y las hectáreas (ARQUITECTURA-DEV §5.3). Los cambios a este archivo requieren la aprobación de Jorge.
 */
export interface ParcelPackage {
  /**
   * Comentario libre para quien lea el archivo. La app lo ignora.
   */
  _nota?: string;
  /**
   * Versión del formato. Se cambia aquí y en la app a la vez; un cambio incompatible sube el número.
   */
  package_format: 'kinilum-package/2';
  parcel_id: ParcelId;
  generated_at: IsoDate;
  /**
   * true = caso ilustrativo: datos de ejemplo, no una parcela real. La app lo rotula «Caso ilustrativo» en todas las pantallas.
   */
  illustrative: boolean;
  /**
   * Superficie en hectáreas.
   */
  area_ha: number;
  /**
   * Región (clave de es.json: regions.*).
   */
  region_key: 'northSinaloa';
  /**
   * Opcional. [longitud, latitud] REDONDEADA a dos decimales (≈ 1 km): ubica la zona, no la parcela. Si la ubicación tampoco puede mostrarse, se omite.
   *
   * @minItems 2
   * @maxItems 2
   */
  reference_point?: number[];
  /**
   * Cuadros de 30 m limpios dentro de la parcela, sin la orilla (búfer interno de 30 m).
   */
  clean_pixels: number;
  /**
   * Lo que sabemos de la parcela: los seis valores de «Lo que sabemos» y Ver evidencia.
   */
  values: {
    rain: ContractValue;
    bare: ContractValue;
    heat: ContractValue;
    soil: ContractValue;
    moisture: ContractValue;
    slope: ContractValue;
  };
  /**
   * Lluvia acumulada de esta temporada (mm, por mes desde enero) y lo que se espera con su margen.
   */
  rain_this_season: {
    /**
     * @maxItems 12
     */
    observed: number[];
    /**
     * @maxItems 12
     */
    projected: {
      y: number;
      lo: number;
      hi: number;
    }[];
  };
  /**
   * Cubierta verde por mes y por año (HLS desde 2013).
   */
  green_cover: {
    _codigo?: string;
    source?: string;
    /**
     * Un texto de 12 letras por año, de enero a diciembre: C = con plantas verdes · B = sin plantas verdes · N = sin dato (nubes).
     */
    years: {
      [k: string]: string;
    };
  };
  /**
   * Temporadas recientes: falta de agua en la floración (mm, p10/p50/p90) y días de calor que daña.
   */
  seasons: {
    year: number;
    deficit: {
      p10: number;
      p50: number;
      p90: number;
    };
    heat_days: number;
  }[];
  /**
   * Umbrales que marcan una temporada difícil (a validar con el técnico).
   */
  thresholds: {
    deficit_mm: number;
    heat_c: number;
  };
  /**
   * Opcional. Lo normal en la zona (p10–p90 de temporadas anteriores), para decir si un dato es mucho o poco.
   */
  normals?: {
    _nota?: string;
    rain?: Normal;
    heat?: Normal;
  };
  restrictions?: Restrictions;
  rotation?: Rotation;
  /**
   * Opcional (P1, de lo primero que se corta). Cuadros de 30 m en METROS LOCALES, sin georreferencia: no publica la ubicación. Solo para la parcela de ejemplo o con permiso por escrito.
   */
  map_30m?: {
    _nota?: string;
    cell_m: number;
    /**
     * Filas de norte a sur. . fuera · e borde descartado · c cuadro limpio.
     *
     * @minItems 1
     */
    mask: string[];
    /**
     * Contorno en metros locales (x al este, y al norte, origen abajo a la izquierda).
     *
     * @minItems 3
     */
    polygon_m: number[][];
    layers: {
      bare_months: MapLayer;
      slope_pct: MapLayer;
    };
  };
  simulation?: Simulation;
}
/**
 * Un valor del contrato de datos. El motor nunca recibe un número suelto: cada valor trae su rango, su fuente, su resolución, su nivel de soporte y cómo se obtuvo (docs/AGENTS-context.md). Si falta support_level, p10 o p90, el valor no sale del pipeline.
 */
export interface ContractValue {
  /**
   * Nombre de la variable en el código (snake_case): rain_season, tmax_may, root_depth…
   */
  variable: string;
  /**
   * Mejor estimación. null = sin dato (la fuente falló o no cubre la parcela): nunca se inventa.
   */
  value: number | null;
  /**
   * Percentil 10 del rango. null solo si value es null.
   */
  p10: number | null;
  /**
   * Percentil 90 del rango. null solo si value es null.
   */
  p90: number | null;
  /**
   * Unidad: mm, °C, days, cm, %, m³/m³…
   */
  unit: string;
  /**
   * Fuente en palabras cortas: «GPM IMERG», «NASA POWER», «HLS»…
   */
  source: string;
  /**
   * Resolución con que la fuente mide: «30 m», «0.1°». «declared» si lo declaró el técnico.
   */
  native_resolution: string;
  /**
   * Resolución a la que kinilum lo usa, si es distinta.
   */
  derived_resolution?: string;
  support_level: SupportLevel;
  /**
   * Fecha del dato: AAAA, AAAA-MM o AAAA-MM-DD.
   */
  timestamp: string;
  method: Method;
  quality?: Quality;
  /**
   * Supuestos que el valor arrastra. Cada clave tiene su texto en es.json y en.json (assumptions.*).
   */
  assumptions?: Assumption[];
  /**
   * De dónde salió, paso a paso: producto y versión, máscara, agregación. Lo escribe la ingesta; una fuente que falla lo dice aquí.
   */
  provenance?: string[];
}
export interface Normal {
  p10: number;
  p90: number;
  unit: string;
  period: string;
  source: string;
}
/**
 * Restricciones = filtros (un WHERE), no pesos.
 */
export interface Restrictions {
  _nota?: string;
  water: 'rainfed' | 'irrigation';
  machinery: 'manual' | 'hired';
  /**
   * Además del maíz, qué cultivos de rotación acepta sembrar. No se simulan más cultivos que estos cuatro.
   */
  cultivos_aceptados: RotationCrop[];
  /**
   * Para qué cultivos tiene comprador o venta local.
   */
  market: RotationCrop[];
  sowing: 'may' | 'june' | 'july' | 'november' | 'december';
  /**
   * Suelo declarado. alluvial = valle aluvial; ni alluvial ni undeclared tienen profundidad de raíz definida.
   */
  soil: 'alluvial' | 'undeclared';
  /**
   * Opcional. true si la temperatura máxima de la zona (values.heat) alcanza el umbral de calor que daña (thresholds.heat_c). Lo calcula el armador; falta si no hay dato de calor.
   */
  extreme_heat?: boolean;
}
/**
 * Por estrategia, el cultivo de rotación que trae. E0 (actual) y E1 (cobertura) no traen un cultivo del catálogo.
 */
export interface Rotation {
  /**
   * Versión del catálogo de cultivos de donde salen.
   */
  rules_version: string;
  E2: {
    rotation_crop: 'frijol';
    /**
     * Variante del frijol regional que se simula.
     */
    variant: 'negro';
    /**
     * Quién la eligió: el técnico o, en el caso ilustrativo, el equipo.
     */
    variant_chosen_by: 'technician' | 'team';
  };
  E3: RotationEntry;
  E4: RotationEntry;
  E5: RotationEntry;
}
export interface RotationEntry {
  rotation_crop: RotationCrop;
}
export interface MapLayer {
  source: string;
  resolution: string;
  method: Method;
  unit: string;
  /**
   * Una fila por fila de la máscara; null = sin dato (nubes).
   */
  values: (number | null)[][];
}
export interface Simulation {
  /**
   * Orden de las estrategias en cada bloque de puntajes. E0 actual · E1 maíz + cobertura · E2 maíz → frijol regional → maíz · E3 maíz → sorgo → maíz · E4 maíz → garbanzo → maíz · E5 maíz → trigo → maíz.
   */
  strategies: ['E0', 'E1', 'E2', 'E3', 'E4', 'E5'];
  /**
   * Orden de los criterios en cada bloque de puntajes.
   */
  criteria: ['water', 'soil', 'erosion', 'climate', 'income'];
  /**
   * Versión del perfil de cultivos (pipeline/rules/) con que se simuló.
   */
  rules_version: string;
  /**
   * Opcional. Por estrategia, los criterios que no se pudieron calcular porque al cultivo le falta un parámetro. Se declaran aquí y sus bytes valen 255 en todas las corridas; nunca se rellenan con un valor inventado.
   */
  no_data?: {
    /**
     * @minItems 1
     *
     * This interface was referenced by `undefined`'s JSON-Schema definition
     * via the `patternProperty` "^E[0-5]$".
     */
    [k: string]: ('water' | 'soil' | 'erosion' | 'climate' | 'income')[];
  };
  /**
   * Qué lo generó (módulo y versión), para poder repetirlo.
   */
  generator?: string;
  /**
   * Las 49 celdas de la grilla de «¿Qué pasa si…?» (lluvia −30…+30 % de 10 en 10 × temperatura −2…+4 °C de 1 en 1). Las 6 que coinciden con un escenario con nombre llevan 500 corridas y su nombre; las otras, 100. Cada celda toma lluvia y temperatura JUNTAS de un año real del historial.
   *
   * @minItems 49
   * @maxItems 49
   */
  cells: SimulationCell[];
}
export interface SimulationCell {
  /**
   * Solo en las 6 celdas con nombre.
   */
  scenario?: 'normal' | 'dry' | 'veryDry' | 'wet' | 'hot' | 'dryHot';
  /**
   * Cambio de lluvia, en %.
   */
  rain: -30 | -20 | -10 | 0 | 10 | 20 | 30;
  /**
   * Cambio de temperatura, en °C.
   */
  temp: -2 | -1 | 0 | 1 | 2 | 3 | 4;
  /**
   * Corridas (años simulados) de esta celda: 500 con nombre, 100 en las demás.
   */
  runs: 100 | 500;
  /**
   * Bytes sin signo en base64. Disposición [estrategia][criterio][corrida], con el orden de strategies y criteria: longitud = 6 × 5 × runs bytes. Cada byte es un puntaje entero 0–100, o 255 si el criterio está declarado en no_data. La corrida i es el MISMO año simulado para las seis estrategias y los cinco criterios.
   */
  scores: string;
}

/**
 * public/packages/index.json: a qué archivo apunta cada parcela. La app lo pide SIEMPRE a la red (nunca de caché) para saber si hay un paquete más nuevo. Si cambia el contenido de un paquete, cambia su nombre: así ningún celular mezcla uno nuevo con uno viejo en caché.
 */
export interface PackageIndex {
  _nota?: string;
  parcels: {
    [k: string]: {
      /**
       * <parcela>.<fecha>.json; si se regenera el mismo día, <parcela>.<fecha>.r2.json, .r3.json…
       */
      file: string;
      generated_at: string;
    };
  };
}
