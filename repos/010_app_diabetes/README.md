# Simulador de Glucosa en Sangre

Aplicación interactiva en Streamlit para simular la evolución de la glucosa en sangre tras la ingesta de una comida y la administración de un bolo de insulina prandial.

> **Uso exclusivamente educativo.** No utilizar para decisiones clínicas reales.

## Requisitos

- Python 3.11+
- Las dependencias listadas en `requirements.txt`

## Instalación y ejecución

```bash
# 1. Crear y activar un entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar la app
streamlit run app.py
```

La app se abrirá automáticamente en el navegador en `http://localhost:8501`.

## Estructura del proyecto

```
010_app_diabetes/
├── app.py            # Interfaz Streamlit (sidebar, gráfico, métricas)
├── model.py          # Lógica matemática pura (numpy + math)
├── requirements.txt
└── README.md
```

## Modelo simplificado

### Curva de glucosa por comida

Se modela con una distribución **Gamma** parametrizada por el índice glucémico:

- **IG alto (>70):** pico temprano (~15 min), amplitud alta → `k=2, theta=15`
- **IG bajo (<55):** pico tardío (~60 min), curva suave → `k=4, theta=20`
- **IG medio:** interpolación lineal entre ambos extremos

Amplitud: `4 mg/dL × gramos de HC × sensibilidad` (factor simplificado, no fisiológico).

### Curva de acción de la insulina

También distribución Gamma, desplazada según el tiempo de espera entre inyección y comida:

| Tipo | Pico | theta |
|------|------|-------|
| Ultrarrápida | ~60 min | 30 |
| Rápida | ~90 min | 45 |
| Regular | ~120 min | 40 |

Efecto total = `unidades × factor de corrección` (mg/dL).

### Curva resultante

```
glucosa(t) = glucosa_basal + curva_comida(t) - curva_insulina(t)
```

Limitada a un mínimo de 40 mg/dL para visualización.

## Parámetros principales

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| Gramos HC | 60 g | Hidratos de carbono ingeridos |
| Índice glucémico | 60 | Velocidad de absorción del alimento |
| Glucosa inicial | 120 mg/dL | Glucosa en sangre al iniciar la comida |
| Glucosa objetivo | 100 mg/dL | Valor deseado para calcular corrección |
| Ratio HC/insulina | 10 g/U | Gramos de HC por unidad de insulina |
| Factor corrección | 40 mg/dL/U | Reducción por unidad de insulina |
| Unidades insulina | 6 U | Dosis del bolo administrada |
| Tipo insulina | rápida | Perfil farmacocinético |
| Tiempo espera | +15 min | Pre-bolo (+) o post-bolo (-) |
| Duración simulación | 300 min | Ventana temporal total |
