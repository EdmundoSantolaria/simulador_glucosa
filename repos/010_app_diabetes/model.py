"""
model.py — Lógica matemática del simulador de glucosa en sangre.

MODELO:
─────────────────────────────────────────────────────────────────────────────
Se resuelve la siguiente ODE mediante integración de Euler (dt = resolución):

  dG/dt = meal_rate(t) - k_clear × (G(t) - G_basal) - insulin_rate(t)

donde:
  G(t)          : glucosa en sangre en mg/dL
  meal_rate(t)  : tasa de absorción de glucosa por la comida (mg/dL/min)
                  modelada como la PDF de una distribución Gamma
  insulin_rate(t): tasa de reducción de glucosa por la insulina (mg/dL/min)
                  modelada como la PDF de una distribución Gamma desplazada
  k_clear       : constante de limpieza endógena de glucosa (min⁻¹)
                  representa captación muscular + producción hepática basal
                  valor por defecto: 0.02 min⁻¹ → semivida ~35 min

POR QUÉ ODE (y no suma directa de curvas):
─────────────────────────────────────────────────────────────────────────────
El modelo directo (glucosa = basal + curva_comida - curva_insulina) no tiene
en cuenta que el organismo elimina glucosa continuamente. Sin este término de
limpieza, la insulina actúa durante su duración completa (3-6 h) mucho después
de que la comida ha sido absorbida, causando hipoglucemia severa artificial.

La ODE resuelve este problema porque el término -k_clear*(G-G_basal) devuelve
la glucosa a la basal de forma exponencial, independientemente de la insulina.
La insulina ACELERA este retorno, pero si el metabolismo ya está en basal, el
efecto neto de la insulina residual es mínimo (G~=G_basal → G-G_basal~=0 →
término de limpieza~=0 → G se estabiliza).

SUPUESTOS SIMPLIFICADOS (importante leer antes de modificar):
─────────────────────────────────────────────────────────────────────────────
1. La absorción de glucosa por la comida se modela con una distribución Gamma,
   una elección estándar en modelos farmacocinéticos de orden 1. No representa
   la fisiología real del tracto gastrointestinal.

2. k_clear = 0.02 min⁻¹ es una simplificación. Varía con el peso corporal,
   la resistencia a la insulina, el ejercicio y el estado metabólico.

3. El efecto de la insulina también se modela con una Gamma. Los parámetros
   (peak_time, k) son aproximaciones de perfiles clínicos publicados, no
   datos de bioequivalencia farmacocinética real.

4. No se modelan: resistencia a la insulina, efecto del glucagón, ejercicio
   físico, estrés, variabilidad inter-individual, ni la respuesta glucagón
   endógena ante hipoglucemia.

5. Este módulo no importa Streamlit: puede usarse y testearse de forma
   independiente desde notebooks o scripts.

Dependencias: numpy, math (stdlib)
"""

import math
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DEL MODELO
# ─────────────────────────────────────────────────────────────────────────────

# Factor de escala para la tasa de absorción de glucosa por la comida.
# Unidades: (mg/dL/min) por gramo de HC × unidades de la PDF Gamma.
#
# Calibrado para que:
#   - Sin insulina, 60g HC con IG=60, basal=120 → pico ≈ 266 mg/dL (t≈108 min)
#   - Con insulina óptima (6U rápida, wait=15, CF=40) → pico ≈ 182 mg/dL (TIR ≈ 94%)
#
# Relación aproximada en estado cuasi-estacionario:
#   G_pico ≈ G_basal + (MEAL_RATE_SCALE × carbs_g × ig_factor × max_pdf_meal) / k_clear
#
# Con k_clear=0.01 y MEAL_RATE_SCALE=4.0 para 60g HC, IG=60:
#   max_pdf_meal ≈ 0.01449 min⁻¹, ig_factor ≈ 1.08
#   G_pico ≈ 120 + (4.0 × 60 × 1.08 × 0.01449) / 0.01 ≈ 120 + 376 = 496... pero el pico
#   real es menor porque la Gamma crece gradualmente y el clearance actúa desde t=0.
#   El valor numérico real es ~266 mg/dL (calculado por integración).
MEAL_RATE_SCALE: float = 4.0  # (mg/dL/min) / (g × PDF_Gamma)

# Constante de limpieza endógena de glucosa.
# Representa la captación muscular + regulación hepática basal (endogenous glucose disposal).
#
# k_clear = 0.01 min⁻¹ → semivida de limpieza ≈ 69 min.
#   Más lento que la absorción de la comida → permite ver el pico postprandial.
#   Más rápido que la duración de la insulina → la glucosa vuelve a basal sin hypo severa.
#
# A mayor k_clear: glucosa sube menos pero vuelve más rápido a basal (y hay menos hypo).
# A menor k_clear: glucosa sube más y tarda más en volver.
GLUCOSE_CLEARANCE_RATE: float = 0.01  # min⁻¹

# Clamp fisiológico mínimo para visualización (hipoglucemia severa visual).
# No representa una barrera metabólica real; solo evita valores negativos en el gráfico.
MIN_GLUCOSE_MGDL: float = 40.0

# Perfiles de insulina: (peak_time_min, k_shape)
# theta se deriva como: theta = peak_time / (k - 1)
# Esto garantiza que el pico de la Gamma ocurra exactamente en peak_time.
#
# Fuente de referencia (aproximada):
#   - Ultrarrápida (lispro, aspart): onset ~10 min, pico ~60 min, duración ~4 h
#   - Rápida (regular soluble): onset ~20 min, pico ~90 min, duración ~5 h
#   - Regular (NPH-like simple): onset ~30 min, pico ~120 min, duración ~6 h
INSULIN_PROFILES: dict[str, dict[str, float]] = {
    "ultrarrápida": {"peak_time": 60.0,  "k": 3.0},
    "rápida":       {"peak_time": 90.0,  "k": 3.0},
    "regular":      {"peak_time": 120.0, "k": 4.0},
}

# Puntos de referencia para la parametrización por índice glucémico.
# IG bajo (<55): curva lenta y suave   → k=4.0, theta_base=20.0
# IG medio (55-70): interpolación lineal
# IG alto (>70): curva rápida y alta   → k=2.0, theta_base=15.0
GI_LOW_THRESHOLD: float = 55.0
GI_HIGH_THRESHOLD: float = 70.0
GI_LOW_K: float = 4.0
GI_HIGH_K: float = 2.0
GI_LOW_THETA: float = 20.0
GI_HIGH_THETA: float = 15.0


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN AUXILIAR INTERNA
# ─────────────────────────────────────────────────────────────────────────────

def _gamma_pdf_log_stable(t: np.ndarray, k: float, theta: float) -> np.ndarray:
    """
    Evalúa la PDF de la distribución Gamma en log-espacio para estabilidad numérica.

    PDF_Gamma(t; k, theta) = t^(k-1) * exp(-t/theta) / (theta^k * Gamma(k))

    En log-espacio:
      log(PDF) = (k-1)*log(t) - t/theta - k*log(theta) - lgamma(k)

    Se usa math.lgamma (stdlib) en lugar de scipy.special.gammaln para no
    añadir dependencias externas.

    Parámetros:
      t     : array de tiempos (valores >= 0; puede incluir valores negativos
               que se devuelven como 0)
      k     : parámetro de forma (shape) — controla asimetría del pico
      theta : parámetro de escala (scale) — controla anchura temporal

    Retorna:
      PDF evaluada en cada punto de t. Valores donde t <= 0 → 0.
    """
    lgamma_k = math.lgamma(k)
    log_theta = math.log(theta)

    with np.errstate(divide="ignore", invalid="ignore"):
        log_pdf = (
            (k - 1.0) * np.log(np.maximum(t, 1e-12))
            - t / theta
            - k * log_theta
            - lgamma_k
        )
        pdf = np.where(t > 0.0, np.exp(log_pdf), 0.0)

    return pdf


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES PÚBLICAS DEL MODELO
# ─────────────────────────────────────────────────────────────────────────────

def generate_time_axis(duration_min: float, resolution_min: float) -> np.ndarray:
    """
    Genera el eje temporal de la simulación.

    Parámetros:
      duration_min   : duración total de la simulación en minutos
      resolution_min : paso temporal en minutos (resolución)

    Retorna:
      Array 1D desde 0 hasta duration_min (inclusive) con paso resolution_min.

    Ejemplo:
      generate_time_axis(10, 2) → [0, 2, 4, 6, 8, 10]
    """
    return np.arange(0.0, duration_min + resolution_min * 0.5, resolution_min)


def meal_glucose_rate(
    t: np.ndarray,
    carbs_g: float,
    glycemic_index: float,
    absorption_time_min: float = 90.0,
    gi_sensitivity: float = 1.0,
) -> np.ndarray:
    """
    Calcula la TASA de absorción de glucosa por la comida (mg/dL/min).

    Esta función devuelve meal_rate(t), el término fuente de la ODE del modelo.
    NO es la glucosa en sangre directamente, sino la velocidad a la que se añade.

    MODELO: distribución Gamma parametrizada por el índice glucémico.
    La integral ∫ meal_rate(t) dt representa la glucosa total absorbida.

    Parametrización por índice glucémico (influye en FORMA y AMPLITUD del pico):
      IG alto (>70): k=2.0, theta=15.0  → pico temprano (~15 min) y alto
      IG bajo (<55): k=4.0, theta=20.0  → pico tardío (~60 min) y suave
      IG medio: interpolación lineal

    El IG también escala la AMPLITUD:
      ig_amplitude_factor: [0.6 (IG=0) → 1.4 (IG=100)]
    Esto modela que los alimentos con IG alto producen picos más altos a igualdad
    de gramos de HC (absorción más concentrada en el tiempo).

    Parámetros:
      t                   : eje temporal (array 1D, minutos desde el inicio de la comida)
      carbs_g             : gramos de hidratos de carbono ingeridos
      glycemic_index      : índice glucémico del alimento (1-100)
      absorption_time_min : modifica la escala theta (referencia neutra: 90 min)
      gi_sensitivity      : multiplicador de amplitud adicional [0.5-2.0]

    Retorna:
      Array 1D con la tasa de absorción en mg/dL/min.
    """
    ig = float(glycemic_index)

    # 1. Derivar k y theta base según el índice glucémico (interpolación lineal)
    if ig >= GI_HIGH_THRESHOLD:
        k_base = GI_HIGH_K
        theta_base = GI_HIGH_THETA
    elif ig <= GI_LOW_THRESHOLD:
        k_base = GI_LOW_K
        theta_base = GI_LOW_THETA
    else:
        frac = (ig - GI_LOW_THRESHOLD) / (GI_HIGH_THRESHOLD - GI_LOW_THRESHOLD)
        k_base = GI_LOW_K + frac * (GI_HIGH_K - GI_LOW_K)        # de 4.0 a 2.0
        theta_base = GI_LOW_THETA + frac * (GI_HIGH_THETA - GI_LOW_THETA)  # de 20.0 a 15.0

    # 2. Ajustar theta según tiempo de absorción
    theta = theta_base * (absorption_time_min / 90.0)
    theta = max(theta, 1.0)

    # 3. Factor de amplitud por IG
    # Mayor IG → curva más alta (mismos gramos, pero absorción más concentrada)
    ig_normalized = max(0.0, min(100.0, ig)) / 100.0
    ig_amplitude_factor = 0.6 + ig_normalized * 0.8   # rango [0.6, 1.4]

    # 4. Amplitud total de la tasa de absorción
    # MEAL_RATE_SCALE × carbs_g da la tasa en (mg/dL/min) por unidad de PDF.
    # Unidades de la PDF: min⁻¹ → amplitude tiene unidades de mg/dL.
    amplitude = carbs_g * MEAL_RATE_SCALE * gi_sensitivity * ig_amplitude_factor

    # 5. Evaluar la PDF de la Gamma (valores en min⁻¹)
    pdf = _gamma_pdf_log_stable(t, k_base, theta)

    return amplitude * pdf


def insulin_glucose_rate(
    t: np.ndarray,
    units: float,
    insulin_type: str,
    correction_factor: float,
    wait_time_min: float = 15.0,
) -> np.ndarray:
    """
    Calcula la TASA de reducción de glucosa por la insulina (mg/dL/min).

    Esta función devuelve insulin_rate(t), el término sumidero de la ODE.
    NO es la reducción total, sino la velocidad de reducción en cada instante.

    MODELO: distribución Gamma desplazada temporalmente.

    Perfiles predefinidos por tipo de insulina:
      ultrarrápida: peak_time=60 min, k=3.0 → theta=30
      rápida:        peak_time=90 min, k=3.0 → theta=45
      regular:       peak_time=120 min, k=4.0 → theta=40

    Relación exacta: t_pico = (k-1) × theta  →  theta = peak_time / (k-1)

    Escalado: correction_factor se usa para escalar la amplitud de la tasa.
    Unidades: correction_factor en (mg/dL/U) → amplitude en (mg/dL/U).
    La tasa es amplitude × PDF(t_action) donde PDF tiene unidades min⁻¹,
    así insulin_rate tiene unidades mg/dL/min.

    Convención del tiempo de espera:
      wait_time_min > 0 → pre-bolo: insulina inyectada ANTES de la comida.
        En t=0, la insulina lleva wait_time_min minutos actuando.
        t_action = t + wait_time_min
      wait_time_min < 0 → post-bolo: insulina inyectada DESPUÉS de empezar.
        t_action = t + wait_time_min < 0 para t pequeños → efecto = 0.
      wait_time_min = 0 → bolo simultáneo al inicio de la comida.

    Parámetros:
      t                : eje temporal (minutos desde el inicio de la comida)
      units            : unidades de insulina administradas
      insulin_type     : "ultrarrápida", "rápida" o "regular"
      correction_factor: mg/dL que reduce 1 unidad de insulina (factor de escala)
      wait_time_min    : minutos de antelación del bolo respecto a la comida

    Retorna:
      Array 1D con la tasa de reducción de glucosa (mg/dL/min) en cada instante.
    """
    if insulin_type not in INSULIN_PROFILES:
        raise ValueError(
            f"Tipo de insulina '{insulin_type}' no reconocido. "
            f"Opciones: {list(INSULIN_PROFILES.keys())}"
        )

    profile = INSULIN_PROFILES[insulin_type]
    k = profile["k"]
    peak_time = profile["peak_time"]

    # theta derivado para que el pico ocurra exactamente en peak_time
    theta = peak_time / (k - 1.0)

    # Amplitud de la tasa (mg/dL/U × U = mg/dL, que con la PDF min⁻¹ → mg/dL/min)
    amplitude = units * correction_factor

    # Desplazamiento temporal: pre-bolo positivo adelanta el efecto de la insulina.
    # En t=0 (inicio de comida), la insulina lleva wait_time_min minutos actuando.
    t_action = t + wait_time_min

    # Evaluar la PDF en t_action (0 donde t_action <= 0: insulina aún no actúa)
    pdf = _gamma_pdf_log_stable(t_action, k, theta)
    pdf = np.where(t_action > 0.0, pdf, 0.0)

    return amplitude * pdf


def resulting_glucose_curve(
    t: np.ndarray,
    basal_glucose: float,
    meal_rate: np.ndarray,
    insulin_rate: np.ndarray,
    k_clear: float = GLUCOSE_CLEARANCE_RATE,
) -> np.ndarray:
    """
    Resuelve la ODE del modelo de glucosa mediante integración de Euler.

    ECUACIÓN:
      dG/dt = meal_rate(t) - k_clear × (G(t) - G_basal) - insulin_rate(t)
      G(0)  = basal_glucose

    Términos:
      + meal_rate(t)               : glucosa añadida por absorción de la comida
      - k_clear × (G - G_basal)    : limpieza endógena proporcional al exceso de glucosa
                                     (captación muscular/hepática, sin insulina exógena)
                                     → tiende a devolver G hacia G_basal naturalmente
      - insulin_rate(t)            : reducción adicional por insulina exógena

    Por qué esta ODE y no suma directa de curvas:
    La suma directa (G = basal + meal_curve - insulin_curve) no incluye clearance.
    Sin clearance, la insulina de larga duración sigue reduciendo la glucosa mucho
    después de que la comida ha sido absorbida → hipoglucemia artificial.
    Con clearance: cuando G ≈ G_basal, el término -k_clear*(G-G_basal) ≈ 0, y la
    insulina residual se enfrenta a poca glucosa extra → efecto neto pequeño.

    Integración: Euler con paso dt = resolución temporal.
    Precisión: O(dt) — suficiente para resoluciones de 1-10 min.

    Parámetros:
      t             : eje temporal (minutos)
      basal_glucose : glucosa inicial (y de referencia basal) del paciente (mg/dL)
      meal_rate     : tasa de absorción de glucosa (mg/dL/min) — de meal_glucose_rate()
      insulin_rate  : tasa de reducción por insulina (mg/dL/min) — de insulin_glucose_rate()
      k_clear       : constante de limpieza endógena (min⁻¹), default=0.02

    Retorna:
      Array 1D con la glucosa en sangre (mg/dL) a lo largo del tiempo.
    """
    dt = float(t[1] - t[0]) if len(t) > 1 else 1.0
    n = len(t)

    glucose = np.empty(n)
    glucose[0] = basal_glucose

    for i in range(1, n):
        # Euler forward: G[i] = G[i-1] + dG/dt * dt
        dG_dt = (
            meal_rate[i - 1]
            - k_clear * (glucose[i - 1] - basal_glucose)
            - insulin_rate[i - 1]
        )
        glucose[i] = glucose[i - 1] + dG_dt * dt

    # Clamp fisiológico mínimo (solo para visualización)
    return np.maximum(glucose, MIN_GLUCOSE_MGDL)


def compute_summary_metrics(
    t: np.ndarray,
    glucose_curve: np.ndarray,
    target_glucose: float,
) -> dict:
    """
    Calcula métricas de resumen a partir de la curva de glucosa resultante.

    Métricas calculadas:
      peak_glucose      : valor máximo de glucosa (mg/dL)
      time_to_peak_min  : tiempo al pico máximo (min)
      min_glucose       : valor mínimo de glucosa (mg/dL)
      time_to_min_min   : tiempo al mínimo (min)
      final_glucose     : glucosa al final de la simulación (mg/dL)
      time_in_range_pct : % del tiempo con glucosa entre 70 y 180 mg/dL (TIR)
      time_above_min    : minutos con glucosa > 180 mg/dL (hiperglucemia)
      time_hypo_min     : minutos con glucosa < 70 mg/dL (hipoglucemia)

    Nota sobre TIR: rango 70-180 mg/dL según consenso internacional (Battelino 2019).
    Aquí es solo orientativo, no tiene valor clínico.

    Parámetros:
      t             : eje temporal (minutos)
      glucose_curve : curva de glucosa resultante (mg/dL)
      target_glucose: glucosa objetivo del paciente (mg/dL)

    Retorna:
      Diccionario con las métricas.
    """
    peak_idx = int(np.argmax(glucose_curve))
    min_idx = int(np.argmin(glucose_curve))
    total_points = float(len(glucose_curve))

    in_range_mask = (glucose_curve >= 70.0) & (glucose_curve <= 180.0)
    above_mask = glucose_curve > 180.0
    hypo_mask = glucose_curve < 70.0

    dt = float(t[1] - t[0]) if len(t) > 1 else 1.0

    return {
        "peak_glucose": float(glucose_curve[peak_idx]),
        "time_to_peak_min": float(t[peak_idx]),
        "min_glucose": float(glucose_curve[min_idx]),
        "time_to_min_min": float(t[min_idx]),
        "final_glucose": float(glucose_curve[-1]),
        "time_in_range_pct": round(float(np.sum(in_range_mask)) / total_points * 100.0, 1)
            if total_points > 0 else 0.0,
        "time_above_min": float(np.sum(above_mask)) * dt,
        "time_hypo_min": float(np.sum(hypo_mask)) * dt,
    }
