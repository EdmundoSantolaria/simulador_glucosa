"""
app.py — Simulador interactivo de glucosa en sangre (Streamlit + Plotly).

Ejecutar con:
  streamlit run app.py

Toda la lógica matemática se encuentra en model.py.
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
# SIDEBAR — bloque 1: navegación
# El radio fija `page` antes de que se ejecuten los cálculos globales.
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🩸 Simulador de Glucosa")
    st.markdown("---")
    page = st.radio(
        "Sección",
        options=["🩸 Simulador", "📖 Guía", "🔬 Aproximaciones del modelo"],
        label_visibility="collapsed",
        key="nav_page",
    )

# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZACIÓN DE SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULTS: dict = {
    "carbs_g":             60,
    "glycemic_index":      60,
    "glucose_initial":    120,
    "glucose_target":     110,
    "ic_ratio":            18,
    "correction_factor":  142,
    "insulin_type_val":   list(model.INSULIN_PROFILES.keys())[0],
    "duration_min":       300,
    "resolution_min":       1,
    "absorption_time_min": 90,
    "gi_sensitivity":     1.0,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ─────────────────────────────────────────────────────────────────────────────
# LECTURA DE VALORES ACTUALES
# ─────────────────────────────────────────────────────────────────────────────

carbs_g             = int(st.session_state["carbs_g"])
glycemic_index      = int(st.session_state["glycemic_index"])
glucose_initial     = int(st.session_state["glucose_initial"])
glucose_target      = int(st.session_state["glucose_target"])
ic_ratio            = int(st.session_state["ic_ratio"])
correction_factor   = int(st.session_state["correction_factor"])
insulin_type        = st.session_state["insulin_type_val"]
duration_min        = int(st.session_state["duration_min"])
resolution_min      = int(st.session_state["resolution_min"])
absorption_time_min = int(st.session_state["absorption_time_min"])
gi_sensitivity      = float(st.session_state["gi_sensitivity"])

# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULO DE DOSIS RECOMENDADA
# ─────────────────────────────────────────────────────────────────────────────

_coverage           = carbs_g / ic_ratio if ic_ratio > 0 else 0.0
_correction         = (
    max(0.0, (glucose_initial - glucose_target) / correction_factor)
    if correction_factor > 0 else 0.0
)
_suggested          = _coverage + _correction
_suggested_rounded  = round(_suggested * 2) / 2

_glucose_excess_wait = min(15, int(max(0.0, glucose_initial - glucose_target) / 20) * 5)
_gi_wait   = 10 if glycemic_index > 70 else (5 if glycemic_index > 55 else 0)
_rec_wait  = int(round(min(30, _glucose_excess_wait + _gi_wait) / 5) * 5)

if "insulin_units_val" not in st.session_state:
    st.session_state["insulin_units_val"] = _suggested_rounded
if "wait_time_val" not in st.session_state:
    st.session_state["wait_time_val"] = _rec_wait

insulin_units = float(st.session_state["insulin_units_val"])
wait_time_min = int(st.session_state["wait_time_val"])

# ─────────────────────────────────────────────────────────────────────────────
# MODELO
# ─────────────────────────────────────────────────────────────────────────────

t = model.generate_time_axis(duration_min, resolution_min)

# Escala de comida coherente con el perfil del paciente.
# CF/IC ≈ mg/dL que sube 1 g de HC en este paciente.
# Garantiza que la dosis recomendada (carbs/IC unidades, cada una baja CF mg/dL)
# compense exactamente el efecto de la comida, sin hiper ni hipo artificial.
_meal_scale = correction_factor / max(ic_ratio, 1)

meal_rate = model.meal_glucose_rate(
    t=t, carbs_g=carbs_g, glycemic_index=glycemic_index,
    absorption_time_min=absorption_time_min, gi_sensitivity=gi_sensitivity,
    meal_rate_scale=_meal_scale,
)
insulin_rate = model.insulin_glucose_rate(
    t=t, units=insulin_units, insulin_type=insulin_type,
    correction_factor=correction_factor, wait_time_min=wait_time_min,
)
glucose = model.resulting_glucose_curve(
    t=t, basal_glucose=glucose_initial,
    meal_rate=meal_rate, insulin_rate=insulin_rate,
)
glucose_no_insulin = model.resulting_glucose_curve(
    t=t, basal_glucose=glucose_initial,
    meal_rate=meal_rate, insulin_rate=np.zeros_like(t),
)
metrics = model.compute_summary_metrics(
    t=t, glucose_curve=glucose, target_glucose=glucose_target,
)

insulin_coverage   = _coverage
insulin_correction = _correction
insulin_suggested  = _suggested
delta_insulin      = insulin_units - insulin_suggested

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — bloque 2: recomendación + KPIs (solo página Simulador)
# Aparece debajo de la navegación; usa los valores calculados arriba.
# ─────────────────────────────────────────────────────────────────────────────

if page == "🩸 Simulador":

    # Callbacks para los botones de recomendación
    def _use_insulin():
        st.session_state["insulin_units_val"] = _suggested_rounded

    def _use_wait():
        st.session_state["wait_time_val"] = _rec_wait

    def _apply_both():
        st.session_state["insulin_units_val"] = _suggested_rounded
        st.session_state["wait_time_val"]     = _rec_wait

    with st.sidebar:

        # ── Parámetros clave (afectan la recomendación) ──────────────────────
        st.markdown("---")
        st.markdown("#### 🍽️ Comida y espera")
        st.slider("Hidratos de carbono (g)", 0, 200, step=5, key="carbs_g",
            help="Gramos de HC de la comida. Cambia este valor para ver cómo se ajusta la dosis recomendada.")
        st.slider("Tiempo de espera (min)", -30, 60, step=5, key="wait_time_val",
            help="+ : primero insulina → luego come. − : primero come → luego insulina.")

        # ── Dosis recomendada ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 💡 Dosis recomendada")

        m1, m2 = st.columns(2)
        with m1:
            st.metric(
                "Insulina", f"{_suggested_rounded:.1f} U",
                delta=f"Cob {_coverage:.1f} + Corr {_correction:.1f}",
                delta_color="off",
                help=f"Cobertura: {carbs_g} g ÷ prop. 1:{ic_ratio} = {_coverage:.1f} U  \n"
                     f"Corrección: ({glucose_initial}−{glucose_target}) ÷ FC 1:{correction_factor} = {_correction:.1f} U",
            )
        with m2:
            st.metric(
                "Pre-bolo", f"{_rec_wait} min",
                help="Minutos recomendados de espera entre la inyección y el inicio de la comida.",
            )

        st.button(
            "← Aplicar ambos",
            on_click=_apply_both,
            use_container_width=True,
            type="primary",
            key="btn_apply_both",
            help="Aplica simultáneamente la dosis y el tiempo de espera recomendados.",
        )

        bc1, bc2 = st.columns(2)
        with bc1:
            st.button("← Solo dosis", on_click=_use_insulin,
                use_container_width=True, key="btn_use_ins")
        with bc2:
            st.button("← Solo espera", on_click=_use_wait,
                use_container_width=True, key="btn_use_wait")

        ins_diff  = insulin_units - _suggested_rounded
        wait_diff = wait_time_min - _rec_wait
        if abs(ins_diff) < 0.26 and abs(wait_diff) < 3:
            st.success("✓ Usando valores recomendados", icon="✅")
        else:
            parts = []
            if abs(ins_diff)  >= 0.26: parts.append(f"Ins: {ins_diff:+.1f} U")
            if abs(wait_diff) >= 3:    parts.append(f"Espera: {wait_diff:+.0f} min")
            st.caption("Diferencia vs recomendación: " + " · ".join(parts))

        # ── Análisis de dosis ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 💉 Análisis de dosis")

        st.metric("Cobertura HC", f"{insulin_coverage:.1f} U",
            help=f"{carbs_g} g HC ÷ proporción 1:{ic_ratio}")
        st.metric("Corrección glucemia", f"{insulin_correction:.1f} U",
            help=f"max(0, ({glucose_initial}−{glucose_target}) ÷ factor 1:{correction_factor})")
        st.metric("Total sugerido", f"{insulin_suggested:.1f} U",
            help="Cobertura + Corrección")
        _delta_label = (
            "dosis exacta" if abs(delta_insulin) < 0.05
            else ("exceso" if delta_insulin > 0 else "déficit")
        )
        st.metric(
            "Administrada", f"{insulin_units:.1f} U",
            delta=f"{delta_insulin:+.1f} U — {_delta_label}",
            delta_color="inverse",
            help="Positivo = exceso (riesgo hipo). Negativo = déficit (glucosa elevada).",
        )

        # ── Resumen glucémico ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 📋 Resumen glucémico")

        _delta_peak = metrics["peak_glucose"] - glucose_initial
        st.metric(
            "Glucosa máxima", f"{metrics['peak_glucose']:.0f} mg/dL",
            delta=f"+{_delta_peak:.0f} vs basal · t={metrics['time_to_peak_min']:.0f} min",
            delta_color="inverse",
            help="Pico máximo y el minuto en que ocurre.",
        )
        _delta_min = metrics["min_glucose"] - glucose_initial
        st.metric(
            "Glucosa mínima", f"{metrics['min_glucose']:.0f} mg/dL",
            delta=f"{_delta_min:.0f} vs basal · t={metrics['time_to_min_min']:.0f} min",
            delta_color="inverse",
        )
        st.metric(
            "TIR (70–180 mg/dL)", f"{metrics['time_in_range_pct']:.1f}%",
            delta="✓ objetivo cumplido" if metrics["time_in_range_pct"] >= 70 else "objetivo ≥ 70%",
            delta_color="off",
            help="Tiempo en Rango. Objetivo clínico: ≥ 70% del tiempo.",
        )
        st.metric(
            "Hiper (>180 mg/dL)", f"{metrics['time_above_min']:.0f} min",
            delta=f"Hipo (<70): {metrics['time_hypo_min']:.0f} min",
            delta_color="inverse",
        )
        _delta_final = metrics["final_glucose"] - glucose_target
        st.metric(
            "Glucosa al final", f"{metrics['final_glucose']:.0f} mg/dL",
            delta=f"{_delta_final:+.0f} vs objetivo",
            delta_color="inverse",
        )

        st.markdown("---")
        st.caption("Uso exclusivamente educativo. No utilizar para decisiones clínicas.")


# ═════════════════════════════════════════════════════════════════════════════
# PÁGINA: SIMULADOR
# ═════════════════════════════════════════════════════════════════════════════

if page == "🩸 Simulador":

    st.warning(
        "⚠️ **Simulación simplificada con fines educativos.**  \n"
        "Este modelo usa distribuciones Gamma y una ODE de primer orden, "
        "no datos farmacocinéticos validados. Los resultados son orientativos "
        "y **no deben utilizarse para decisiones clínicas reales**. "
        "Consulta siempre a un profesional de la salud."
    )
    st.title("🩸 Simulador de Glucosa en Sangre")
    st.caption(
        "Visualiza cómo interactúan la absorción de glucosa por una comida "
        "y el efecto de un bolo de insulina prandial. "
        "Ajusta los parámetros debajo del gráfico."
    )

    # ── Gráfico principal ────────────────────────────────────────────────────

    fig = go.Figure()

    fig.add_hrect(
        y0=70, y1=180,
        fillcolor="rgba(144, 238, 144, 0.12)", line_width=0,
        annotation_text="Rango TIR (70–180 mg/dL)",
        annotation_position="top left",
        annotation_font_size=11, annotation_font_color="green",
    )
    fig.add_trace(go.Scatter(
        x=t, y=glucose_no_insulin, name="Sin insulina (referencia)",
        line=dict(color="#ff7f0e", width=1.5, dash="dot"), opacity=0.7,
        hovertemplate="t=%{x} min<br>Sin insulina=%{y:.1f} mg/dL<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=t, y=glucose, name="Glucosa resultante",
        line=dict(color="#1f77b4", width=3),
        hovertemplate="t=%{x} min<br>Glucosa=%{y:.1f} mg/dL<extra></extra>",
    ))
    fig.add_hline(
        y=glucose_initial, line_dash="dash", line_color="gray", line_width=1,
        annotation_text=f"Basal: {glucose_initial} mg/dL", annotation_position="right",
    )
    if glucose_target != glucose_initial:
        fig.add_hline(
            y=glucose_target, line_dash="longdash", line_color="#d62728", line_width=1,
            annotation_text=f"Objetivo: {glucose_target} mg/dL", annotation_position="right",
        )

    y_max = max(float(np.max(glucose_no_insulin)), float(np.max(glucose))) + 30
    y_min = max(20.0, float(np.min(glucose)) - 20)
    fig.update_layout(
        title=dict(text="Evolución de glucosa en sangre", font=dict(size=18)),
        xaxis=dict(
            title="Tiempo (minutos desde el inicio de la comida)",
            tickmode="auto", nticks=12, gridcolor="#e8e8e8",
        ),
        yaxis=dict(title="Glucosa (mg/dL)", gridcolor="#e8e8e8", range=[y_min, y_max]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        plot_bgcolor="white", paper_bgcolor="white",
        height=480, margin=dict(r=160),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Parámetros — cuatro grupos desplegables bajo la curva ────────────────

    st.markdown("#### ⚙️ Parámetros de la simulación")
    st.caption("Despliega cada grupo para ajustar los valores. La curva se actualiza automáticamente.")

    pc1, pc2, pc3, pc4 = st.columns(4)

    with pc1:
        with st.expander("🍽️ Comida", expanded=False):
            st.slider("Índice glucémico", 1, 100, step=1, key="glycemic_index",
                help="IG alto (>70): pico rápido y alto. IG bajo (<55): curva suave y tardía.")

    with pc2:
        with st.expander("👤 Paciente", expanded=False):
            st.slider("Glucosa inicial (mg/dL)", 40, 400, step=5, key="glucose_initial",
                help="Glucosa en sangre al inicio de la comida (basal de referencia).")
            st.slider("Glucosa objetivo (mg/dL)", 70, 180, step=5, key="glucose_target",
                help="Valor deseado para calcular la insulina de corrección.")
            st.slider("Proporción de carbohidratos 1:X (g/U)", 5, 60, step=1, key="ic_ratio",
                help="Gramos de HC cubiertos por 1 U de insulina. Ej: 1:18 → 1 U cubre 18 g de HC.")
            st.slider("Factor de corrección 1:X (mg/dL/U)", 20, 300, step=5, key="correction_factor",
                help="mg/dL que reduce 1 U de insulina. Ej: 1:142 → 1 U baja 142 mg/dL.")

    with pc3:
        with st.expander("💉 Insulina", expanded=False):
            st.slider("Unidades administradas", 0.0, 50.0, step=0.1, key="insulin_units_val",
                help="Dosis real del bolo prandial. Paso de 0,1 U (útil para bomba).")
            st.selectbox(
                "Tipo de insulina", options=list(model.INSULIN_PROFILES.keys()),
                key="insulin_type_val",
                help="Humalog Junior: onset 15 min, pico ~60 min, duración ~4-5 h.",
            )

    with pc4:
        with st.expander("⚙️ Simulación", expanded=False):
            st.slider("Duración total (min)", 60, 600, step=30, key="duration_min",
                help="Ventana temporal total.")
            st.slider("Resolución temporal (min)", 1, 10, step=1, key="resolution_min",
                help="Menor valor = curvas más suaves.")
            st.divider()
            st.slider("Tiempo absorción comida (min)", 30, 180, step=10, key="absorption_time_min",
                help="Modifica la anchura de la curva de absorción. 90 min = neutro.")
            st.slider("Sensibilidad al IG (×)", 0.5, 2.0, step=0.1, key="gi_sensitivity",
                help="1.0 = respuesta estándar. >1.0 = mayor sensibilidad glucémica.")

    # ── Tasas internas del modelo ────────────────────────────────────────────

    with st.expander("📊 Tasas internas del modelo (absorción e insulina)", expanded=False):
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=t, y=meal_rate, name="Tasa absorción glucosa (comida)",
            line=dict(color="#ff7f0e", width=2),
            fill="tozeroy", fillcolor="rgba(255, 127, 14, 0.15)",
            hovertemplate="t=%{x} min<br>Comida=%{y:.4f} mg/dL·min⁻¹<extra></extra>",
        ))
        fig2.add_trace(go.Scatter(
            x=t, y=insulin_rate, name="Tasa efecto insulina",
            line=dict(color="#2ca02c", width=2),
            fill="tozeroy", fillcolor="rgba(44, 160, 44, 0.15)",
            hovertemplate="t=%{x} min<br>Insulina=%{y:.4f} mg/dL·min⁻¹<extra></extra>",
        ))
        fig2.update_layout(
            title="Tasas internas del modelo (mg/dL·min⁻¹)",
            xaxis=dict(title="Tiempo (min)", gridcolor="#e8e8e8"),
            yaxis=dict(title="Tasa (mg/dL/min)", gridcolor="#e8e8e8"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hovermode="x unified",
            plot_bgcolor="white", paper_bgcolor="white", height=300,
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.caption(
            "Estas son las entradas a la ODE, no la glucosa directamente. "
            "Cuando la curva de insulina supera a la de comida, la glucosa tiende a bajar."
        )


# ═════════════════════════════════════════════════════════════════════════════
# PÁGINA: GUÍA
# ═════════════════════════════════════════════════════════════════════════════

elif page == "📖 Guía":

    st.title("📖 Guía del Simulador")
    st.markdown(
        "Bienvenido/a a esta guía. Aquí aprenderás a leer la simulación "
        "y a entender cómo cada decisión afecta a tu glucosa. "
        "Ve al **🩸 Simulador** para ajustar los valores y observar los cambios en tiempo real."
    )

    with st.expander("📈 Cómo interpretar la simulación", expanded=True):
        st.markdown("""
**La curva azul** muestra cómo evoluciona tu glucosa en sangre desde el
momento en que empiezas a comer. La **línea naranja punteada** muestra qué
pasaría si no te pusieras insulina — sirve como comparación.

---

**¿Qué es un pico de glucosa?**
Es el punto más alto que alcanza la curva. Cuanto más alto y rápido sube,
más difícil es controlarlo. Un pico elevado (por encima de 180 mg/dL)
indica que el azúcar subió demasiado después de comer.

---

**¿Qué es el rango objetivo (la zona verde)?**
La banda verde del gráfico representa el **rango seguro: 70–180 mg/dL**.
- Por debajo de 70 mg/dL → **hipoglucemia** (glucosa demasiado baja, peligroso)
- Por encima de 180 mg/dL → **hiperglucemia** (glucosa demasiado alta)

El objetivo es que la curva pase la mayor parte del tiempo dentro de esta
banda. A esto se le llama **TIR** (Tiempo en Rango). Cuanto mayor sea el
TIR, mejor control glucémico.

---

**¿Por qué importa el momento en que te pones la insulina?**
La insulina tarda entre 15 y 30 minutos en empezar a actuar. Si te la
pones justo cuando empiezas a comer (o después), la comida lleva ventaja:
el azúcar ya está subiendo antes de que la insulina entre en acción.
Ponerte la insulina **unos minutos antes** de comer (pre-bolo) permite que
ambas curvas —comida e insulina— coincidan mejor en el tiempo.
        """)

    with st.expander("🔑 Factores clave que afectan a tu glucosa", expanded=False):

        st.markdown("#### 🍞 A. Hidratos de carbono (gramos)")
        st.markdown("""
Los hidratos de carbono (HC) son el principal combustible que eleva la
glucosa después de comer. Cuantos más gramos de HC tiene una comida,
más sube la glucosa.

| Si... | En la curva verás... |
|---|---|
| **Subes** los gramos de HC | El pico sube más alto |
| **Bajas** los gramos de HC | El pico es menor y más controlable |

> **Ejemplo:** una comida de 80 g de HC (pasta abundante) eleva mucho más
> la glucosa que una de 30 g (ensalada con pollo).
        """)

        st.divider()
        st.markdown("#### ⚡ B. Índice glucémico (IG)")
        st.markdown("""
El índice glucémico mide **la velocidad** a la que un alimento libera azúcar
en la sangre. No todos los carbohidratos son iguales: una manzana y un
vaso de zumo tienen HC similares, pero el zumo sube el azúcar mucho más rápido.

| IG | Tipo de alimento | Efecto |
|---|---|---|
| **Alto (>70)** | Pan blanco, arroz blanco, zumos | Pico rápido y elevado |
| **Medio (55–70)** | Pasta, plátano | Subida moderada |
| **Bajo (<55)** | Legumbres, manzana, lácteos | Subida lenta y suave |

| Si... | En la curva verás... |
|---|---|
| **Subes** el IG | El pico aparece antes y es más alto |
| **Bajas** el IG | La curva sube más despacio y de forma más gradual |
        """)

        st.divider()
        st.markdown("#### ⏱️ C. Tiempo de espera")
        st.markdown("""
El **tiempo de espera** es el tiempo entre la inyección de insulina y el
inicio de la comida. Es uno de los factores que más influye en el control
glucémico postprandial, especialmente con insulinas rápidas.

- **Valor positivo (+15 min): primero insulina → luego come.** La insulina
  lleva 15 minutos de ventaja. Cuando el azúcar empieza a subir, ya está
  actuando → pico más bajo.
- **Cero (0 min):** insulina y comida a la vez. La glucosa sube antes de
  que la insulina tenga efecto → pico más alto.
- **Valor negativo (−15 min): primero come → luego insulina.** La insulina
  se inyecta 15 min después de empezar a comer. El pico inicial es aún mayor.

| Si... | En la curva verás... |
|---|---|
| **Aumentas** el tiempo de espera (más positivo) | El pico baja y la curva es más plana |
| **Reduces** el tiempo de espera (negativo) | El pico sube más y ocurre antes |

> La recomendación varía: con glucosa alta antes de comer o alimentos de
> IG alto, conviene esperar más tiempo (15–20 min).
        """)

        st.divider()
        st.markdown("#### 💉 D. Dosis de insulina")
        st.markdown("""
La dosis de insulina determina cuánto baja la glucosa después de la comida.
Una dosis correcta devuelve la glucosa al rango objetivo sin pasarse.

- **Dosis insuficiente:** la insulina no cubre todos los HC → la glucosa
  se queda alta durante horas.
- **Dosis excesiva:** la insulina baja la glucosa por debajo de 70 mg/dL
  → **hipoglucemia**, que puede ser peligrosa.
- **Dosis correcta:** la curva sube, pero vuelve al rango objetivo de
  forma suave y sin caídas.

| Si... | En la curva verás... |
|---|---|
| **Subes** la dosis | La curva baja más. Con exceso → caída por debajo de 70 |
| **Bajas** la dosis | La curva se queda elevada durante más tiempo |

> La aplicación calcula una **dosis sugerida** según tus gramos de HC y
> tu glucosa inicial. Es solo orientativa — tu ratio real lo determina
> tu médico o educador en diabetes.
        """)

    with st.expander("🧪 Prueba estos escenarios", expanded=False):
        st.markdown("Estos experimentos te ayudarán a entender cómo interactúan los factores. "
                    "Pruébalos en el **🩸 Simulador**.")

        st.markdown("---")
        st.markdown("##### 🔴 Escenario 1: Comida de IG alto sin espera")
        st.markdown("""
**Configuración:** HC: **80 g** · IG: **85** · Tiempo espera: **0 min** · Dosis: recomendada

**¿Qué verás?** Un pico muy alto y rápido (probablemente por encima de 200 mg/dL).
La insulina no ha dado tiempo a actuar antes de que el azúcar suba.

**Qué aprender:** los alimentos de IG alto necesitan pre-bolo o dosis ajustada.
        """)

        st.markdown("---")
        st.markdown("##### 🟡 Escenario 2: El efecto del pre-bolo (0 vs 15 vs 20 min)")
        st.markdown("""
**Paso 1:** tiempo de espera a **0 min** → observa el pico.
**Paso 2:** tiempo de espera a **15 min** → compara.
**Paso 3:** tiempo de espera a **20 min** → compara de nuevo.

**¿Qué verás?** El pico baja y la curva se aplana. El TIR mejora.

**Qué aprender:** unos pocos minutos de diferencia tienen un impacto visible.
        """)

        st.markdown("---")
        st.markdown("##### 🟠 Escenario 3: Mismo IG, más o menos hidratos")
        st.markdown("""
**Configuración base:** IG: **60** · Tiempo espera: **15 min** · Dosis: siempre la recomendada

Prueba con **40 g**, luego **80 g** y finalmente **120 g** de HC.

**¿Qué verás?** El pico crece con los hidratos. La dosis sube automáticamente,
pero el pico sigue siendo mayor porque hay más azúcar que absorber.

**Qué aprender:** reducir HC es tan efectivo como ajustar la insulina.
        """)

        st.markdown("---")
        st.markdown("##### 🟢 Escenario 4: Insulina rápida vs Humalog")
        st.markdown("""
**Configuración:** HC: **60 g** · IG: **70** · Tiempo espera: **15 min**

Prueba con **insulina rápida** y luego con **Humalog Junior (lispro)**.

**¿Qué verás?** Con Humalog, la insulina actúa antes y el pico es más bajo.

**Qué aprender:** el tipo de insulina importa y cambia el comportamiento de la curva.
        """)

    with st.expander("⚙️ Cómo funciona el modelo (sin tecnicismos)", expanded=False):
        st.markdown("""
El simulador imita lo que ocurre en tu cuerpo después de una comida,
combinando tres fuerzas que actúan sobre tu glucosa al mismo tiempo:

---

**1. 🍽️ La comida sube el azúcar**
Cuando comes, los carbohidratos se convierten en glucosa y pasan a la
sangre. La velocidad a la que esto ocurre depende del tipo de alimento
(IG) y de la cantidad (gramos de HC).

---

**2. 💉 La insulina baja el azúcar**
La insulina actúa como una "llave" que permite que las células usen esa
glucosa. Pero tarda un tiempo en empezar a actuar (el onset depende del
tipo de insulina) y tiene un momento de máxima eficacia (el pico de acción).

---

**3. 🫀 El propio cuerpo regula**
Tu cuerpo tiene un mecanismo natural para llevar la glucosa hacia su nivel
basal. Si la glucosa está alta, las células la van absorbiendo poco a poco.
Este proceso actúa todo el tiempo, aunque más lentamente que la insulina.

---

**El resultado:**
La curva de glucosa que ves en el gráfico es el efecto combinado de
estas tres fuerzas. Cuando están bien sincronizadas, la glucosa sube
suavemente después de comer y vuelve al rango objetivo sin caídas bruscas.
        """)

    with st.expander("⚠️ Importante — Lee antes de usar", expanded=False):
        st.markdown("**Esta aplicación es solo educativa.**")
        st.error(
            "**No uses esta aplicación para calcular dosis reales de insulina.**  \n"
            "Las dosis de insulina son altamente individuales y deben ser "
            "establecidas y ajustadas únicamente por tu médico o educador en diabetes.",
            icon="🚫",
        )
        st.markdown("""
**El modelo no tiene en cuenta:**
- Tu resistencia a la insulina particular
- El efecto del ejercicio físico o el estrés
- Comidas múltiples a lo largo del día
- La insulina basal que ya llevas
- Enfermedades intercurrentes u otros medicamentos

**Para qué sí puede ayudarte:**
- Entender por qué sube el azúcar después de comer
- Ver el efecto del pre-bolo de forma visual
- Explorar la diferencia entre alimentos de IG alto y bajo
- Aprender los conceptos básicos del manejo de la diabetes tipo 1
        """)


# ═════════════════════════════════════════════════════════════════════════════
# PÁGINA: APROXIMACIONES DEL MODELO
# ═════════════════════════════════════════════════════════════════════════════

elif page == "🔬 Aproximaciones del modelo":

    st.title("🔬 Aproximaciones del modelo matemático")
    st.info(
        "Esta sección es técnica y está dirigida a usuarios con conocimientos de "
        "fisiología o matemáticas aplicadas. Los gráficos interactivos usan los "
        "mismos parámetros configurados en el **🩸 Simulador**.",
        icon="ℹ️",
    )

    with st.expander("📐 La ecuación diferencial completa", expanded=True):
        st.markdown("""
El simulador resuelve la siguiente **ODE de primer orden** mediante integración de Euler
con paso `dt = resolución temporal`:

```
dG/dt = meal_rate(t)  −  k_clear × (G(t) − G_basal)  −  insulin_rate(t)
G(0)  = glucosa_inicial
```

| Término | Signo | Descripción |
|---|---|---|
| `meal_rate(t)` | **+** | Velocidad de entrada de glucosa procedente de la comida |
| `k_clear × (G − G_basal)` | **−** | Eliminación endógena proporcional al exceso de glucosa |
| `insulin_rate(t)` | **−** | Velocidad de reducción adicional por la insulina exógena |
        """)

    with st.expander("🍽️ Término 1 — Absorción de glucosa: meal_rate(t)", expanded=False):
        st.markdown("""
**Formulación:**
```
meal_rate(t) = MEAL_RATE_SCALE × carbs_g × ig_amplitude_factor × gi_sensitivity × PDF_Gamma(t; k, θ)
```

**¿Por qué una distribución Gamma?**
La Gamma es la distribución estándar en modelos farmacocinéticos de absorción oral de orden 1.
Tiene soporte en `[0, ∞)`, es asimétrica hacia la derecha (como la absorción real), y es
controlable mediante dos parámetros: `k` (forma) y `θ` (escala).

**Parametrización por índice glucémico:**

| IG | k | θ (base) | Efecto |
|---|---|---|---|
| **Alto (>70)** | 2.0 | 15 | Pico temprano (~15 min), absorción concentrada |
| **Bajo (<55)** | 4.0 | 20 | Pico tardío (~60–80 min), absorción distribuida |
| **Medio** | Interpolación lineal | Interpolación lineal | Transición suave |

El IG también escala la **amplitud** mediante `ig_amplitude_factor ∈ [0.6, 1.4]`,
modelando que alimentos de IG alto generan picos más altos a igualdad de gramos.

**Calibración de MEAL_RATE_SCALE = 4.0:**
Ajustado para que 60 g HC con IG=60 y sin insulina genere un pico ~266 mg/dL,
coherente con la excursión glucémica postprandial típica en DT1 sin cobertura.
        """)

    with st.expander("💉 Término 2 — Efecto de la insulina: insulin_rate(t)", expanded=False):
        st.markdown("""
**Formulación general:**
```
insulin_rate(t) = units × correction_factor × PDF(t_desde_onset; parámetros)
t_desde_onset   = t + wait_time_min − onset_delay_min
```

**Dos distribuciones disponibles:**

**A) Distribución Gamma** (ultrarrápida, rápida, regular)

| Perfil | k | Pico desde onset | θ |
|---|---|---|---|
| Ultrarrápida | 3.0 | 60 min | 30 |
| Rápida | 3.0 | 90 min | 45 |
| Regular | 4.0 | 120 min | 40 |

**B) Distribución Log-Normal** (Humalog Junior / lispro)
```
PDF_LogNormal(t; μ=4.030, σ=0.472)
```
Reproduce la asimetría del lispro: subida rápida (~45 min desde onset), bajada gradual.
*Fuente: Howey et al. (1994, Diabetes); StatPearls Insulin Lispro.*

**Onset delay:** Humalog tiene 15 min de onset; los genéricos asumen 0 min.

**Escalado:** `units × correction_factor`. El `correction_factor` escala la amplitud total
de la curva de insulina en el modelo además de calcular la corrección de hiperglucemia.
        """)

    with st.expander("🫀 Término 3 — Regulación endógena: k_clear × (G − G_basal)", expanded=False):
        st.markdown("""
**Formulación:**
```
clearance(t) = k_clear × (G(t) − G_basal)
k_clear = 0.01 min⁻¹   →   semivida de limpieza ≈ 69 min
```

**¿Qué representa?**
La captación muscular, hepática y periférica de glucosa en exceso. Lleva exponencialmente
la glucosa de vuelta a `G_basal` en ausencia de otras fuerzas. Es proporcional al
**exceso** respecto a la basal, no al nivel absoluto.

**¿Por qué es imprescindible?**
Sin este término, tras la absorción de la comida, la insulina residual continuaría
reduciendo la glucosa sin freno → **hipoglucemia artificial severa**. Con clearance,
cuando `G ≈ G_basal`, el término `k_clear × (G − G_basal) ≈ 0` y la insulina residual
tiene efecto mínimo.

**Simplificaciones:**
- El valor real varía con peso, resistencia a la insulina y ejercicio. En el modelo es constante.
- Valor 0.01 min⁻¹ está en el rango bajo del *Bergman Minimal Model* (0.01–0.03 min⁻¹).
- No incluye gluconeogénesis hepática dinámica.
        """)

    with st.expander("🔢 Integración numérica — Método de Euler", expanded=False):
        st.markdown("""
```python
G[0] = basal_glucose
for i in range(1, n):
    dG_dt = meal_rate[i-1] - k_clear*(G[i-1] - G_basal) - insulin_rate[i-1]
    G[i]  = G[i-1] + dG_dt * dt
```

- Precisión de orden 1: error global `O(dt)`. Para `dt = 1 min`, suficiente para uso educativo.
- Para uso clínico se requeriría Runge-Kutta de orden 4 o métodos implícitos.
- **Clamp visual:** `G[i] = max(G[i], 40 mg/dL)`. No es una barrera fisiológica real.
        """)

    with st.expander("⚠️ Lo que el modelo simplifica o ignora", expanded=False):
        st.markdown("""
| Aspecto | Realidad | Simplificación |
|---|---|---|
| **Resistencia a la insulina** | Variable según hora, estrés, ciclo... | k_clear constante |
| **Gluconeogénesis hepática** | El hígado produce glucosa ante hipoglucemia | No modelada |
| **Respuesta glucagón** | Se libera ante hipoglucemia | No incluida |
| **Absorción subcutánea** | Variable por zona, temperatura, lipohipertrofia | Onset fijo |
| **Ejercicio físico** | Aumenta captación muscular; puede provocar hipo tardía | No incluido |
| **Comidas múltiples** | Cada comida genera su propia excursión | Solo una comida |
| **Insulina basal** | Mantiene glucemia basal entre comidas | No incluida |
| **Variabilidad inter-individual** | Perfiles PK muy distintos entre personas | Parámetros fijos |
        """)

    # ── Explorador interactivo ───────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔬 Explorador interactivo — activa o desactiva cada término")
    st.markdown(
        "Observa cómo cambia la curva cuando eliminas cada componente de la ODE. "
        f"Parámetros actuales del Simulador: "
        f"**{carbs_g} g HC · IG {glycemic_index} · {insulin_units} U {insulin_type} · "
        f"espera {wait_time_min} min · basal {glucose_initial} mg/dL**."
    )

    ck1, ck2, ck3 = st.columns(3)
    with ck1:
        use_meal = st.checkbox("🍽️ Absorción de glucosa", value=True, key="aprox_meal")
    with ck2:
        use_ins  = st.checkbox("💉 Efecto de la insulina", value=True, key="aprox_ins")
    with ck3:
        use_clr  = st.checkbox("🫀 Regulación endógena",   value=True, key="aprox_clr")

    active = tuple(
        x for x, on in [("comida", use_meal), ("insulina", use_ins), ("clearance", use_clr)] if on
    )
    scenario_notes = {
        ("comida", "insulina", "clearance"): "Modelo completo — curva idéntica a la del Simulador.",
        ("comida", "insulina"):              "Sin clearance: la insulina residual sigue actuando horas después de la comida → hipoglucemia artificial prolongada.",
        ("comida", "clearance"):             "Sin insulina: la glucosa sube con la comida y regresa lentamente solo por clearance. Equivale a la curva naranja punteada del Simulador.",
        ("insulina", "clearance"):           "Sin comida: la insulina baja la glucosa por debajo de la basal; el clearance la devuelve gradualmente.",
        ("comida",):                          "Solo comida: la glucosa sube con la absorción y no regresa — ninguna fuerza la reduce.",
        ("insulina",):                        "Solo insulina: la glucosa cae sin freno — hipoglucemia severa artificial.",
        ("clearance",):                       "Solo clearance: sin comida ni insulina, la curva permanece plana en la basal.",
        ():                                   "Ningún término activo: la glucosa permanece constante en el valor inicial.",
    }
    note = scenario_notes.get(active, "")
    if note:
        st.info(note, icon="💡")

    _mr = meal_rate    if use_meal else np.zeros_like(t)
    _ir = insulin_rate if use_ins  else np.zeros_like(t)
    _kc = model.GLUCOSE_CLEARANCE_RATE if use_clr else 0.0

    glucose_custom = model.resulting_glucose_curve(
        t=t, basal_glucose=glucose_initial,
        meal_rate=_mr, insulin_rate=_ir, k_clear=_kc,
    )

    fig_aprox = go.Figure()
    fig_aprox.add_hrect(y0=70, y1=180, fillcolor="rgba(144,238,144,0.10)", line_width=0)
    fig_aprox.add_trace(go.Scatter(
        x=t, y=glucose, name="Modelo completo (referencia)",
        line=dict(color="#1f77b4", width=1.5, dash="dot"), opacity=0.4,
    ))
    color_custom = "#1f77b4" if active == ("comida", "insulina", "clearance") else "#d62728"
    fig_aprox.add_trace(go.Scatter(
        x=t, y=glucose_custom, name="Combinación seleccionada",
        line=dict(color=color_custom, width=3),
        hovertemplate="t=%{x} min<br>Glucosa=%{y:.1f} mg/dL<extra></extra>",
    ))
    fig_aprox.add_hline(
        y=glucose_initial, line_dash="dash", line_color="gray", line_width=1,
        annotation_text=f"Basal: {glucose_initial} mg/dL", annotation_position="right",
    )
    y_vals = np.concatenate([glucose, glucose_custom])
    _fin   = y_vals[np.isfinite(y_vals)]
    y_max_a = min(float(np.nanmax(_fin)) + 30, 600) if _fin.size else 400
    y_min_a = max(20.0, float(np.nanmin(_fin)) - 20)  if _fin.size else 40
    fig_aprox.update_layout(
        title="Efecto de cada término de la ODE sobre la curva de glucosa",
        xaxis=dict(title="Tiempo (min)", gridcolor="#e8e8e8"),
        yaxis=dict(title="Glucosa (mg/dL)", gridcolor="#e8e8e8", range=[y_min_a, y_max_a]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        plot_bgcolor="white", paper_bgcolor="white", height=420, margin=dict(r=160),
    )
    st.plotly_chart(fig_aprox, use_container_width=True)

    term_col1, term_col2, term_col3 = st.columns(3)
    with term_col1:
        st.metric("🍽️ Absorción comida", "✅ Activo" if use_meal else "❌ Desactivado")
    with term_col2:
        st.metric("💉 Efecto insulina",   "✅ Activo" if use_ins  else "❌ Desactivado")
    with term_col3:
        st.metric("🫀 Clearance",         "✅ Activo" if use_clr  else "❌ Desactivado")
