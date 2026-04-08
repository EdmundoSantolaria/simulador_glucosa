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
# SIDEBAR — dos tabs: Parámetros | Guía
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    _tab_params, _tab_guide = st.tabs(["⚙️ Parámetros", "📖 Guía"])

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 1 — PARÁMETROS DE ENTRADA
    # ═════════════════════════════════════════════════════════════════════════

    with _tab_params:

        # ── GRUPO: Comida ────────────────────────────────────────────────────
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

        # ── GRUPO: Paciente ──────────────────────────────────────────────────
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

        # ── CÁLCULO DE DOSIS RECOMENDADA ─────────────────────────────────────
        _coverage = carbs_g / ic_ratio if ic_ratio > 0 else 0.0
        _correction = (
            max(0.0, (glucose_initial - glucose_target) / correction_factor)
            if correction_factor > 0 else 0.0
        )
        _suggested = _coverage + _correction
        _suggested_rounded = round(_suggested * 2) / 2

        _glucose_excess_wait = min(15, int(max(0.0, glucose_initial - glucose_target) / 20) * 5)
        _gi_wait = 10 if glycemic_index > 70 else (5 if glycemic_index > 55 else 0)
        _rec_wait = int(round(min(30, _glucose_excess_wait + _gi_wait) / 5) * 5)

        if "insulin_units_val" not in st.session_state:
            st.session_state["insulin_units_val"] = _suggested_rounded
        if "wait_time_val" not in st.session_state:
            st.session_state["wait_time_val"] = _rec_wait

        # ── GRUPO: Insulina ──────────────────────────────────────────────────
        with st.expander("💉 Insulina", expanded=True):

            st.metric(
                label="Dosis recomendada",
                value=f"{_suggested_rounded:.1f} U",
                delta=f"Cobertura {_coverage:.1f} + Corrección {_correction:.1f} U",
                delta_color="off",
                help=(
                    f"Cobertura = {carbs_g} g ÷ {ic_ratio} g/U = {_coverage:.1f} U  \n"
                    f"Corrección = ({glucose_initial}−{glucose_target}) mg/dL "
                    f"÷ {correction_factor} mg/dL·U⁻¹ = {_correction:.1f} U  \n"
                    "Usa los botones **← Usar** que hay debajo del gráfico para aplicar."
                ),
            )
            st.divider()

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
                index=0,
                help=(
                    "**Humalog Junior (lispro):** onset 15 min, pico ~60 min, duración ~4-5 h.  \n"
                    "Curva log-normal: subida rápida (45 min al pico), bajada más lenta.  \n"
                    "---  \n"
                    "**Ultrarrápida / Rápida / Regular:** perfiles genéricos con distribución Gamma."
                ),
            )
            wait_time_min = st.slider(
                "Tiempo de espera bolo → comida (min)",
                min_value=-30, max_value=60, step=5,
                key="wait_time_val",
                help=(
                    "Minutos entre la inyección de insulina y el inicio de la comida.  \n"
                    "**Positivo (+15):** pre-bolo, insulina inyectada 15 min antes de comer.  \n"
                    "**Cero (0):** bolo simultáneo al inicio de la comida.  \n"
                    "**Negativo (-15):** post-bolo, insulina inyectada 15 min después de empezar.  \n"
                    "Usa **← Usar tiempo recomendado** bajo el gráfico para el valor óptimo."
                ),
            )

        # ── GRUPO: Simulación ────────────────────────────────────────────────
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

        # ── GRUPO: Parámetros opcionales ─────────────────────────────────────
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

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 2 — GUÍA DE LA APLICACIÓN
    # ═════════════════════════════════════════════════════════════════════════

    with _tab_guide:

        # ── Introducción ─────────────────────────────────────────────────────
        st.markdown(
            "Bienvenido/a a esta guía. Aquí aprenderás a leer la simulación "
            "y a entender cómo cada decisión afecta a tu glucosa. "
            "Usa la tab **⚙️ Parámetros** para ajustar los valores y observa "
            "los cambios en tiempo real."
        )

        # ── SECCIÓN 1: Cómo interpretar la simulación ─────────────────────────
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

        # ── SECCIÓN 2: Factores clave ─────────────────────────────────────────
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
            st.markdown("#### ⏱️ C. Tiempo de espera (pre-bolo)")
            st.markdown("""
El **pre-bolo** es el tiempo que esperas entre ponerte la insulina y empezar
a comer. Es uno de los factores que más influye en el control glucémico
postprandial, especialmente con insulinas rápidas.

- **Sin espera (0 min):** la insulina y la comida empiezan a la vez. La
  glucosa sube antes de que la insulina tenga efecto → pico más alto.
- **Con espera (+15 min):** la insulina lleva ventaja. Cuando el azúcar
  de la comida empieza a subir, la insulina ya está actuando → pico más bajo.
- **Post-bolo (valor negativo):** te pones la insulina después de empezar
  a comer. El pico inicial es aún mayor.

| Si... | En la curva verás... |
|---|---|
| **Aumentas** el tiempo de espera | El pico baja y la curva es más plana |
| **Reduces** el tiempo de espera | El pico sube más y ocurre antes |

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

        # ── SECCIÓN 3: Prueba estos escenarios ───────────────────────────────
        with st.expander("🧪 Prueba estos escenarios", expanded=False):
            st.markdown("""
Estos experimentos guiados te ayudarán a entender de forma práctica cómo
interactúan los distintos factores. Pruébalos en la tab **⚙️ Parámetros**.
            """)

            st.markdown("---")
            st.markdown("##### 🔴 Escenario 1: Comida de IG alto sin espera")
            st.markdown("""
**Configuración:**
- Hidratos de carbono: **80 g**
- Índice glucémico: **85** (pan blanco, arroz)
- Tiempo de espera: **0 min**
- Dosis: usa la recomendada

**¿Qué verás?**
Un pico de glucosa muy alto y rápido (probablemente por encima de 200 mg/dL).
La insulina no ha dado tiempo a actuar antes de que el azúcar suba.

**Qué aprender:** los alimentos de IG alto necesitan pre-bolo o dosis ajustada.
            """)

            st.markdown("---")
            st.markdown("##### 🟡 Escenario 2: El efecto del pre-bolo (10 vs 20 min)")
            st.markdown("""
**Paso 1:** pon el tiempo de espera a **0 min** y observa el pico.

**Paso 2:** pon el tiempo de espera a **15 min** y compara.

**Paso 3:** sube a **20 min** y vuelve a comparar.

**¿Qué verás?**
A medida que aumentas el tiempo de espera, el pico de glucosa baja y la
curva se aplana. El TIR mejora (más tiempo dentro de la banda verde).

**Qué aprender:** unos pocos minutos de diferencia tienen un impacto visible
en el control glucémico.
            """)

            st.markdown("---")
            st.markdown("##### 🟠 Escenario 3: Mismo IG, más o menos hidratos")
            st.markdown("""
**Configura:**
- Índice glucémico: **60** (valor medio)
- Tiempo de espera: **15 min**
- Dosis: usa siempre la recomendada (se recalcula sola)

Prueba con **40 g**, luego **80 g** y finalmente **120 g** de HC.

**¿Qué verás?**
La altura del pico crece con los hidratos. La dosis también aumenta
automáticamente, pero el pico sigue siendo mayor porque hay más azúcar
que absorber.

**Qué aprender:** reducir la cantidad de HC en una comida es tan efectivo
como ajustar la insulina para controlar el pico.
            """)

            st.markdown("---")
            st.markdown("##### 🟢 Escenario 4: Comparar insulina rápida vs Humalog")
            st.markdown("""
**Configura:**
- Hidratos de carbono: **60 g**
- Índice glucémico: **70**
- Tiempo de espera: **15 min**

Prueba con **insulina rápida** y luego con **Humalog Junior (lispro)**.

**¿Qué verás?**
Con Humalog, la insulina actúa antes y el pico inicial es más bajo.
Con insulina rápida, la acción es más lenta y el pico tiende a ser mayor.

**Qué aprender:** el tipo de insulina importa: las de acción más rápida
se sincronizan mejor con la absorción de la comida.
            """)

        # ── SECCIÓN 4: Cómo funciona el modelo (de forma sencilla) ───────────
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

        # ── SECCIÓN 5: Importante ─────────────────────────────────────────────
        with st.expander("⚠️ Importante — Lee antes de usar", expanded=False):
            st.markdown("""
**Esta aplicación es solo educativa.**

El simulador te ayuda a entender conceptos y a visualizar cómo afectan
distintos factores a la glucosa. No es una herramienta de uso clínico.
            """)
            st.error(
                "**No uses esta aplicación para calcular dosis reales de insulina.**  \n"
                "Las dosis de insulina son altamente individuales y deben ser "
                "establecidas y ajustadas únicamente por tu médico o educador "
                "en diabetes.",
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

# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULOS AUXILIARES — Insulina sugerida vs administrada
# ─────────────────────────────────────────────────────────────────────────────

insulin_coverage   = _coverage
insulin_correction = _correction
insulin_suggested  = _suggested
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

fig.add_hrect(
    y0=70, y1=180,
    fillcolor="rgba(144, 238, 144, 0.12)",
    line_width=0,
    annotation_text="Rango TIR (70-180)",
    annotation_position="top left",
    annotation_font_size=11,
    annotation_font_color="green",
)

fig.add_trace(go.Scatter(
    x=t,
    y=glucose_no_insulin,
    name="Sin insulina (referencia)",
    line=dict(color="#ff7f0e", width=1.5, dash="dot"),
    opacity=0.7,
    hovertemplate="t=%{x} min<br>Sin insulina=%{y:.1f} mg/dL<extra></extra>",
))

fig.add_trace(go.Scatter(
    x=t,
    y=glucose,
    name="Glucosa resultante",
    line=dict(color="#1f77b4", width=3),
    hovertemplate="t=%{x} min<br>Glucosa=%{y:.1f} mg/dL<extra></extra>",
))

fig.add_hline(
    y=glucose_initial,
    line_dash="dash",
    line_color="gray",
    line_width=1,
    annotation_text=f"Basal: {glucose_initial} mg/dL",
    annotation_position="right",
)

if glucose_target != glucose_initial:
    fig.add_hline(
        y=glucose_target,
        line_dash="longdash",
        line_color="#d62728",
        line_width=1,
        annotation_text=f"Objetivo: {glucose_target} mg/dL",
        annotation_position="right",
    )

y_max = max(float(np.max(glucose_no_insulin)), float(np.max(glucose))) + 30
y_min = max(20.0, float(np.min(glucose)) - 20)

fig.update_layout(
    title=dict(text="Evolución de glucosa en sangre", font=dict(size=18)),
    xaxis=dict(
        title="Tiempo (minutos desde el inicio de la comida)",
        tickmode="auto", nticks=12, gridcolor="#e8e8e8",
    ),
    yaxis=dict(
        title="Glucosa (mg/dL)", gridcolor="#e8e8e8", range=[y_min, y_max],
    ),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    hovermode="x unified",
    plot_bgcolor="white",
    paper_bgcolor="white",
    height=480,
    margin=dict(r=160),
)

st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# RECOMENDACIÓN PERSONALIZADA
# ─────────────────────────────────────────────────────────────────────────────

with st.container(border=True):
    st.subheader("💡 Recomendación personalizada")
    st.caption(
        f"Calculada para: **{carbs_g} g HC** · IG **{glycemic_index}** · "
        f"Glucosa inicial **{glucose_initial} mg/dL** → objetivo **{glucose_target} mg/dL** · "
        f"Ratio **{ic_ratio} g/U** · FC **{correction_factor} mg/dL·U⁻¹**"
    )

    rcol1, rcol2, rcol3 = st.columns([5, 5, 3])

    with rcol1:
        st.markdown("**🩹 Dosis de insulina**")
        ins_lines = [f"- Cobertura: {carbs_g} g ÷ {ic_ratio} g/U = **{_coverage:.1f} U**"]
        if _correction > 0:
            ins_lines.append(
                f"- Corrección: ({glucose_initial}−{glucose_target})÷{correction_factor}"
                f" = **{_correction:.1f} U**"
            )
        else:
            ins_lines.append("- Corrección: glucosa en/bajo objetivo → **0 U**")
        ins_lines.append(f"- **→ Total recomendado: {_suggested_rounded} U**")
        st.markdown("\n".join(ins_lines))

        def _use_insulin():
            st.session_state["insulin_units_val"] = _suggested_rounded

        st.button(
            "← Usar dosis recomendada",
            on_click=_use_insulin,
            use_container_width=True,
            key="btn_use_ins",
        )

    with rcol2:
        st.markdown("**⏱️ Tiempo de espera (pre-bolo)**")
        wait_lines = []
        if _glucose_excess_wait > 0:
            wait_lines.append(
                f"- Glucosa **{int(glucose_initial - glucose_target)} mg/dL** sobre objetivo"
                f" → **+{_glucose_excess_wait} min**"
            )
        else:
            wait_lines.append("- Glucosa en/bajo objetivo → **+0 min**")
        if _gi_wait > 0:
            gi_label = "alto" if glycemic_index > 70 else "medio"
            wait_lines.append(f"- IG {glycemic_index} ({gi_label}) → **+{_gi_wait} min**")
        else:
            wait_lines.append(f"- IG {glycemic_index} (bajo) → **+0 min**")
        wait_lines.append(f"- **→ Pre-bolo recomendado: {_rec_wait} min**")
        st.markdown("\n".join(wait_lines))

        def _use_wait():
            st.session_state["wait_time_val"] = _rec_wait

        st.button(
            "← Usar tiempo recomendado",
            on_click=_use_wait,
            use_container_width=True,
            key="btn_use_wait",
        )

    with rcol3:
        st.markdown("&nbsp;")

        def _apply_both():
            st.session_state["insulin_units_val"] = _suggested_rounded
            st.session_state["wait_time_val"] = _rec_wait

        st.button(
            "← Aplicar ambos",
            on_click=_apply_both,
            use_container_width=True,
            type="primary",
            key="btn_apply_both",
            help=(
                "Aplica simultáneamente la dosis y el tiempo de espera recomendados "
                "a los sliders del panel lateral. El gráfico se actualizará al instante."
            ),
        )

        ins_diff = insulin_units - _suggested_rounded
        wait_diff = wait_time_min - _rec_wait
        if abs(ins_diff) < 0.26 and abs(wait_diff) < 3:
            st.success("✓ Usando valores recomendados")
        else:
            diff_parts = []
            if abs(ins_diff) >= 0.26:
                diff_parts.append(f"Insulina: {ins_diff:+.1f} U")
            if abs(wait_diff) >= 3:
                diff_parts.append(f"Espera: {wait_diff:+.0f} min")
            st.info("Diferencia vs recomendación:  \n" + "  \n".join(diff_parts))

# ─────────────────────────────────────────────────────────────────────────────
# GRÁFICO AUXILIAR — Tasas de absorción e insulina
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("📊 Ver tasas de absorción e insulina (curvas internas del modelo)", expanded=False):
    fig2 = go.Figure()

    fig2.add_trace(go.Scatter(
        x=t, y=meal_rate,
        name="Tasa absorción glucosa (comida)",
        line=dict(color="#ff7f0e", width=2),
        fill="tozeroy", fillcolor="rgba(255, 127, 14, 0.15)",
        hovertemplate="t=%{x} min<br>Tasa comida=%{y:.4f} mg/dL·min⁻¹<extra></extra>",
    ))

    fig2.add_trace(go.Scatter(
        x=t, y=insulin_rate,
        name="Tasa efecto insulina",
        line=dict(color="#2ca02c", width=2),
        fill="tozeroy", fillcolor="rgba(44, 160, 44, 0.15)",
        hovertemplate="t=%{x} min<br>Tasa insulina=%{y:.4f} mg/dL·min⁻¹<extra></extra>",
    ))

    fig2.update_layout(
        title="Tasas de absorción de glucosa y efecto de insulina (mg/dL/min)",
        xaxis=dict(title="Tiempo (minutos)", gridcolor="#e8e8e8"),
        yaxis=dict(title="Tasa (mg/dL/min)", gridcolor="#e8e8e8"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
        plot_bgcolor="white", paper_bgcolor="white", height=300,
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
