"""
app.py — Simulador interactivo de glucosa en sangre (Streamlit + Plotly).

Ejecutar con:
  streamlit run app.py

Este archivo gestiona únicamente la interfaz de usuario. Toda la lógica
matemática del simulador se encuentra en model.py.
"""

import streamlit as st
import plotly.graph_objects as go
import numpy as np

import model

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Simulador de Glucosa",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# AVISO EDUCATIVO — visible en la parte superior de la página
# ─────────────────────────────────────────────────────────────────────────────

st.warning(
    "⚠️ **Simulación simplificada con fines educativos.**  \n"
    "Este modelo usa distribuciones Gamma y una ODE de primer orden, no datos farmacocinéticos "
    "validados. Los resultados son orientativos y **no deben utilizarse para "
    "decisiones clínicas reales**. Consulta siempre a un profesional de la salud."
)

st.title("🩸 Simulador de Glucosa en Sangre")
st.caption(
    "Visualiza cómo interactúan la absorción de glucosa por una comida "
    "y el efecto de un bolo de insulina prandial."
)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — PARÁMETROS DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Parámetros de la simulación")

    # ── GRUPO: Comida ────────────────────────────────────────────────────────
    with st.expander("🍽️ Comida", expanded=True):
        carbs_g = st.slider(
            "Hidratos de carbono (g)",
            min_value=0, max_value=200, value=60, step=5,
            help="Gramos de HC de la comida ingerida. La tasa de absorción de glucosa crece linealmente con este valor.",
        )
        glycemic_index = st.slider(
            "Índice glucémico",
            min_value=1, max_value=100, value=60, step=1,
            help=(
                "Clasifica la velocidad de absorción del alimento. "
                "**IG alto (>70):** pico de glucosa más rápido y elevado. "
                "**IG bajo (<55):** curva más suave y tardía."
            ),
        )

    # ── GRUPO: Paciente ──────────────────────────────────────────────────────
    with st.expander("👤 Paciente", expanded=True):
        glucose_initial = st.slider(
            "Glucosa inicial (mg/dL)",
            min_value=40, max_value=400, value=120, step=5,
            help="Glucosa en sangre al inicio de la comida. También actúa como glucosa basal de referencia en el modelo.",
        )
        glucose_target = st.slider(
            "Glucosa objetivo (mg/dL)",
            min_value=70, max_value=180, value=100, step=5,
            help="Valor de glucosa deseado. Se usa para calcular la insulina de corrección sugerida.",
        )
        ic_ratio = st.slider(
            "Ratio HC/insulina (g/U)",
            min_value=1, max_value=30, value=10, step=1,
            help="Gramos de HC cubiertos por 1 unidad de insulina. Ej: ratio=10 → 60 g HC requieren 6 U de cobertura.",
        )
        correction_factor = st.slider(
            "Factor de corrección (mg/dL por U)",
            min_value=10, max_value=100, value=40, step=5,
            help="Cuántos mg/dL reduce 1 unidad de insulina respecto a la glucosa objetivo. También escala el efecto de la insulina en el modelo.",
        )

    # ── CÁLCULO DE DOSIS RECOMENDADA ─────────────────────────────────────────
    # Se calcula aquí (entre Paciente e Insulina) para que esté disponible en
    # el expander de Insulina y en el callback del botón "usar recomendada".
    _coverage = carbs_g / ic_ratio if ic_ratio > 0 else 0.0
    _correction = (
        max(0.0, (glucose_initial - glucose_target) / correction_factor)
        if correction_factor > 0 else 0.0
    )
    _suggested = _coverage + _correction
    # Redondear al múltiplo de 0.5 más cercano (granularidad de la pluma de insulina)
    _suggested_rounded = round(_suggested * 2) / 2

    # Inicializar el estado del slider la primera vez (usa la dosis recomendada)
    if "insulin_units_val" not in st.session_state:
        st.session_state["insulin_units_val"] = _suggested_rounded

    # ── GRUPO: Insulina ──────────────────────────────────────────────────────
    with st.expander("💉 Insulina", expanded=True):

        # Dosis recomendada dinámica —————————————————————————————————————————
        st.markdown("**Dosis recomendada**")
        rec_col1, rec_col2 = st.columns([3, 2])
        with rec_col1:
            st.metric(
                label="Cobertura + Corrección",
                value=f"{_suggested:.1f} U",
                delta=f"{_coverage:.1f} + {_correction:.1f} U",
                delta_color="off",
                help=(
                    f"Cobertura = {carbs_g} g ÷ {ic_ratio} g/U = {_coverage:.1f} U  \n"
                    f"Corrección = ({glucose_initial}−{glucose_target}) mg/dL "
                    f"÷ {correction_factor} mg/dL·U⁻¹ = {_correction:.1f} U"
                ),
            )
        with rec_col2:
            # Callback que actualiza el slider al valor recomendado actual
            def _apply_recommended():
                st.session_state["insulin_units_val"] = round(
                    (
                        (carbs_g / ic_ratio if ic_ratio > 0 else 0.0)
                        + max(0.0, (glucose_initial - glucose_target) / correction_factor
                              if correction_factor > 0 else 0.0)
                    ) * 2
                ) / 2

            st.button(
                "← Usar",
                on_click=_apply_recommended,
                help="Aplica la dosis recomendada al selector de abajo.",
                use_container_width=True,
            )

        st.divider()

        # Selector de dosis real (independiente de la recomendación) ————————
        insulin_units = st.slider(
            "Unidades administradas",
            min_value=0.0, max_value=50.0, step=0.5,
            key="insulin_units_val",
            help=(
                "Dosis real del bolo prandial.  \n"
                "Puede diferir de la recomendación. Usa **← Usar** para sincronizar."
            ),
        )

        st.divider()

        insulin_type = st.selectbox(
            "Tipo de insulina",
            options=list(model.INSULIN_PROFILES.keys()),
            index=0,  # Humalog Junior como opción por defecto
            help=(
                "**Humalog Junior (lispro):** onset 15 min, pico ~60 min, duración ~4-5 h.  \n"
                "Curva log-normal: subida rápida (45 min al pico), bajada más lenta.  \n"
                "---  \n"
                "**Ultrarrápida / Rápida / Regular:** perfiles genéricos con distribución Gamma."
            ),
        )
        wait_time_min = st.slider(
            "Tiempo de espera bolo → comida (min)",
            min_value=-30, max_value=60, value=0, step=5,
            help=(
                "Minutos entre la inyección de insulina y el inicio de la comida.  \n"
                "**Positivo (+15):** pre-bolo, insulina inyectada 15 min antes de comer.  \n"
                "**Cero (0):** bolo simultáneo al inicio de la comida.  \n"
                "**Negativo (-15):** post-bolo, insulina inyectada 15 min después de empezar."
            ),
        )

    # ── GRUPO: Simulación ────────────────────────────────────────────────────
    with st.expander("⚙️ Simulación", expanded=False):
        duration_min = st.slider(
            "Duración total (min)",
            min_value=60, max_value=600, value=300, step=30,
            help="Ventana temporal total de la simulación.",
        )
        resolution_min = st.slider(
            "Resolución temporal (min)",
            min_value=1, max_value=10, value=1, step=1,
            help="Intervalo entre puntos calculados. Valores menores = curvas más suaves.",
        )

    # ── GRUPO: Parámetros opcionales ─────────────────────────────────────────
    with st.expander("🔬 Avanzado (opcional)", expanded=False):
        absorption_time_min = st.slider(
            "Tiempo de absorción de la comida (min)",
            min_value=30, max_value=180, value=90, step=10,
            help=(
                "Modifica la anchura de la curva de absorción de glucosa. "
                "90 min es el valor de referencia neutro. "
                "Valores menores aceleran la absorción; mayores la prolongan."
            ),
        )
        gi_sensitivity = st.slider(
            "Sensibilidad al IG (multiplicador de amplitud)",
            min_value=0.5, max_value=2.0, value=1.0, step=0.1,
            help=(
                "Multiplica la amplitud total del pico glucémico de la comida. "
                "1.0 = respuesta estándar. "
                ">1.0 simula mayor sensibilidad glucémica (o peso corporal menor)."
            ),
        )

# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULOS AUXILIARES — Insulina sugerida vs administrada
# (calculados en el sidebar; aquí se exponen con nombres legibles)
# ─────────────────────────────────────────────────────────────────────────────

insulin_coverage   = _coverage    # cobertura de HC
insulin_correction = _correction  # corrección de hiperglucemia inicial
insulin_suggested  = _suggested   # total sugerido
delta_insulin      = insulin_units - insulin_suggested

# ─────────────────────────────────────────────────────────────────────────────
# LLAMADAS AL MODELO
# ─────────────────────────────────────────────────────────────────────────────

t = model.generate_time_axis(duration_min, resolution_min)

meal_rate = model.meal_glucose_rate(
    t=t,
    carbs_g=carbs_g,
    glycemic_index=glycemic_index,
    absorption_time_min=absorption_time_min,
    gi_sensitivity=gi_sensitivity,
)

insulin_rate = model.insulin_glucose_rate(
    t=t,
    units=insulin_units,
    insulin_type=insulin_type,
    correction_factor=correction_factor,
    wait_time_min=wait_time_min,
)

glucose = model.resulting_glucose_curve(
    t=t,
    basal_glucose=glucose_initial,
    meal_rate=meal_rate,
    insulin_rate=insulin_rate,
)

# Curvas de referencia sin insulina / sin comida (para el gráfico auxiliar)
glucose_no_insulin = model.resulting_glucose_curve(
    t=t,
    basal_glucose=glucose_initial,
    meal_rate=meal_rate,
    insulin_rate=np.zeros_like(t),
)

metrics = model.compute_summary_metrics(
    t=t,
    glucose_curve=glucose,
    target_glucose=glucose_target,
)

# ─────────────────────────────────────────────────────────────────────────────
# GRÁFICO PRINCIPAL — Plotly
# ─────────────────────────────────────────────────────────────────────────────

fig = go.Figure()

# Área TIR 70-180 mg/dL (relleno de fondo suave)
fig.add_hrect(
    y0=70, y1=180,
    fillcolor="rgba(144, 238, 144, 0.12)",
    line_width=0,
    annotation_text="Rango TIR (70-180)",
    annotation_position="top left",
    annotation_font_size=11,
    annotation_font_color="green",
)

# Curva de referencia sin insulina (línea punteada naranja)
fig.add_trace(go.Scatter(
    x=t,
    y=glucose_no_insulin,
    name="Sin insulina (referencia)",
    line=dict(color="#ff7f0e", width=1.5, dash="dot"),
    opacity=0.7,
    hovertemplate="t=%{x} min<br>Sin insulina=%{y:.1f} mg/dL<extra></extra>",
))

# Curva principal: glucosa resultante
fig.add_trace(go.Scatter(
    x=t,
    y=glucose,
    name="Glucosa resultante",
    line=dict(color="#1f77b4", width=3),
    hovertemplate="t=%{x} min<br>Glucosa=%{y:.1f} mg/dL<extra></extra>",
))

# Línea horizontal: glucosa basal (referencia inicial)
fig.add_hline(
    y=glucose_initial,
    line_dash="dash",
    line_color="gray",
    line_width=1,
    annotation_text=f"Basal: {glucose_initial} mg/dL",
    annotation_position="right",
)

# Línea horizontal: glucosa objetivo
if glucose_target != glucose_initial:
    fig.add_hline(
        y=glucose_target,
        line_dash="longdash",
        line_color="#d62728",
        line_width=1,
        annotation_text=f"Objetivo: {glucose_target} mg/dL",
        annotation_position="right",
    )

# Layout del gráfico
y_max = max(float(np.max(glucose_no_insulin)), float(np.max(glucose))) + 30
y_min = max(20.0, float(np.min(glucose)) - 20)

fig.update_layout(
    title=dict(
        text="Evolución de glucosa en sangre",
        font=dict(size=18),
    ),
    xaxis=dict(
        title="Tiempo (minutos desde el inicio de la comida)",
        tickmode="auto",
        nticks=12,
        gridcolor="#e8e8e8",
    ),
    yaxis=dict(
        title="Glucosa (mg/dL)",
        gridcolor="#e8e8e8",
        range=[y_min, y_max],
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
    ),
    hovermode="x unified",
    plot_bgcolor="white",
    paper_bgcolor="white",
    height=480,
    margin=dict(r=160),
)

st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# GRÁFICO AUXILIAR — Tasas de absorción e insulina
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("📊 Ver tasas de absorción e insulina (curvas internas del modelo)", expanded=False):
    fig2 = go.Figure()

    fig2.add_trace(go.Scatter(
        x=t,
        y=meal_rate,
        name="Tasa absorción glucosa (comida)",
        line=dict(color="#ff7f0e", width=2),
        fill="tozeroy",
        fillcolor="rgba(255, 127, 14, 0.15)",
        hovertemplate="t=%{x} min<br>Tasa comida=%{y:.4f} mg/dL·min⁻¹<extra></extra>",
    ))

    fig2.add_trace(go.Scatter(
        x=t,
        y=insulin_rate,
        name="Tasa efecto insulina",
        line=dict(color="#2ca02c", width=2),
        fill="tozeroy",
        fillcolor="rgba(44, 160, 44, 0.15)",
        hovertemplate="t=%{x} min<br>Tasa insulina=%{y:.4f} mg/dL·min⁻¹<extra></extra>",
    ))

    fig2.update_layout(
        title="Tasas de absorción de glucosa y efecto de insulina (mg/dL/min)",
        xaxis=dict(title="Tiempo (minutos)", gridcolor="#e8e8e8"),
        yaxis=dict(title="Tasa (mg/dL/min)", gridcolor="#e8e8e8"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=300,
    )

    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "Estas son las curvas internas del modelo (tasa de absorción, no glucosa absoluta). "
        "La diferencia entre ambas áreas determina la excursión glucémica resultante. "
        "Cuando la curva de insulina supera a la de comida en un momento dado, la glucosa tiende a bajar."
    )

# ─────────────────────────────────────────────────────────────────────────────
# MÉTRICAS DE RESUMEN
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("Resumen de la simulación")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    delta_peak = metrics["peak_glucose"] - glucose_initial
    st.metric(
        label="Glucosa máxima",
        value=f"{metrics['peak_glucose']:.0f} mg/dL",
        delta=f"+{delta_peak:.0f} vs basal | t={metrics['time_to_peak_min']:.0f} min",
        delta_color="inverse",
        help="Pico máximo de glucosa durante la simulación y tiempo al que ocurre.",
    )

with col2:
    delta_min = metrics["min_glucose"] - glucose_initial
    st.metric(
        label="Glucosa mínima",
        value=f"{metrics['min_glucose']:.0f} mg/dL",
        delta=f"{delta_min:.0f} vs basal | t={metrics['time_to_min_min']:.0f} min",
        delta_color="inverse",
        help="Glucosa mínima durante la simulación y tiempo al que ocurre.",
    )

with col3:
    tir_color = "normal" if metrics["time_in_range_pct"] >= 70 else "off"
    st.metric(
        label="Tiempo en rango (TIR)",
        value=f"{metrics['time_in_range_pct']:.1f}%",
        delta="objetivo ≥ 70%" if metrics["time_in_range_pct"] < 70 else "✓ objetivo cumplido",
        delta_color="off",
        help="Porcentaje del tiempo con glucosa entre 70 y 180 mg/dL (consenso TIR 2019).",
    )

with col4:
    st.metric(
        label="Tiempo en hiperglucemia",
        value=f"{metrics['time_above_min']:.0f} min",
        delta=f"Hipo (<70): {metrics['time_hypo_min']:.0f} min",
        delta_color="inverse",
        help="Tiempo con glucosa >180 mg/dL (arriba) y <70 mg/dL (abajo).",
    )

with col5:
    delta_final = metrics["final_glucose"] - glucose_target
    st.metric(
        label="Glucosa al final",
        value=f"{metrics['final_glucose']:.0f} mg/dL",
        delta=f"{delta_final:+.0f} vs objetivo",
        delta_color="inverse",
        help="Glucosa en sangre al final de la ventana de simulación.",
    )

# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS DE DOSIS — Insulina sugerida vs administrada
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("Análisis de la dosis de insulina")

dcol1, dcol2, dcol3, dcol4 = st.columns(4)

with dcol1:
    st.metric(
        label="Insulina de cobertura",
        value=f"{insulin_coverage:.1f} U",
        help=f"Cobertura = {carbs_g} g HC ÷ {ic_ratio} g/U",
    )

with dcol2:
    st.metric(
        label="Insulina de corrección",
        value=f"{insulin_correction:.1f} U",
        help=(
            f"Corrección = max(0, ({glucose_initial} − {glucose_target}) mg/dL "
            f"÷ {correction_factor} mg/dL·U⁻¹)  \n"
            "Solo aplica si glucosa inicial > objetivo."
        ),
    )

with dcol3:
    st.metric(
        label="Total sugerido",
        value=f"{insulin_suggested:.1f} U",
        help="Cobertura + Corrección",
    )

with dcol4:
    if abs(delta_insulin) < 0.05:
        delta_label = "dosis exacta"
    elif delta_insulin > 0:
        delta_label = "exceso"
    else:
        delta_label = "déficit"

    st.metric(
        label="Administrada vs sugerida",
        value=f"{insulin_units:.1f} U",
        delta=f"{delta_insulin:+.1f} U ({delta_label})",
        delta_color="inverse",
        help=(
            "**Positivo (exceso):** se administró más de lo sugerido "
            "→ mayor riesgo de hipoglucemia.  \n"
            "**Negativo (déficit):** se administró menos de lo sugerido "
            "→ puede quedar glucosa elevada."
        ),
    )

# ─────────────────────────────────────────────────────────────────────────────
# EXPANDER: Supuestos del modelo
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("📖 Supuestos y limitaciones del modelo"):
    st.markdown("""
    ### Modelo matemático

    **ODE del simulador:**
    ```
    dG/dt = meal_rate(t) − k_clear × (G(t) − G_basal) − insulin_rate(t)
    G(0) = glucosa_inicial
    ```

    - `meal_rate(t)`: tasa de absorción de glucosa (PDF de una Gamma parametrizada por el IG)
    - `insulin_rate(t)`: tasa de reducción por insulina (PDF Gamma o log-normal según el tipo)
    - `k_clear = 0.01 min⁻¹`: limpieza endógena de glucosa (semivida ≈ 69 min)

    **Por qué ODE y no suma directa de curvas:**
    La suma directa `G = basal + curva_comida − curva_insulina` no incluye la limpieza
    endógena. Sin ella, la insulina de larga duración sigue reduciendo glucosa mucho
    después de la absorción de la comida → hipoglucemia artificial. Con la ODE, cuando
    la glucosa ya está cerca de la basal, el término de limpieza se anula y la
    insulina residual tiene efecto mínimo.

    ### Perfiles de insulina (aproximados)

    | Tipo | Distribución | Onset | Pico (desde onset) | Parámetros |
    |------|-------------|-------|---------------------|------------|
    | **Humalog Junior (lispro)** | Log-normal | 15 min | ~45 min | μ=4.030, σ=0.472 |
    | Ultrarrápida | Gamma | 0 min | ~60 min | k=3.0, θ=30 |
    | Rápida | Gamma | 0 min | ~90 min | k=3.0, θ=45 |
    | Regular | Gamma | 0 min | ~120 min | k=4.0, θ=40 |

    **Humalog Junior:** la distribución log-normal reproduce la asimetría característica del
    lispro: subida rápida al pico (~45 min desde onset), bajada progresiva, efecto casi
    completo a las 2 h desde la inyección.

    ### Lo que NO modela este simulador

    - Resistencia a la insulina ni variabilidad inter-individual
    - Producción hepática de glucosa (gluconeogénesis dinámica)
    - Efecto del ejercicio físico o el estrés
    - Respuesta glucagón ante hipoglucemia severa
    - Absorción subcutánea variable de la insulina
    - Efecto de comidas múltiples o snacks
    """)
