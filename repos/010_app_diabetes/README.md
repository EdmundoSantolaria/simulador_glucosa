# Simulador de Glucosa en Sangre

Aplicación interactiva en Streamlit para simular la evolución de la glucosa en sangre tras la ingesta de una comida y la administración de un bolo de insulina prandial.

> **Uso exclusivamente educativo.** No utilizar para decisiones clínicas reales.

---

## 1. Instalación y ejecución (modo desarrollo)

### Requisitos

- Python 3.11+
- Las dependencias listadas en `requirements.txt`

### Pasos

```bash
# 1. Crear y activar un entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate      # Linux / macOS

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar la app
streamlit run app.py
```

La app se abrirá automáticamente en el navegador en `http://localhost:8501`.

Alternativamente, usa el launcher:

```bash
python run_app.py
```

Selecciona el primer puerto libre disponible y abre el navegador automáticamente.

---

## 2. Generar el ejecutable .exe (Windows)

El ejecutable incluye Python, todas las librerías y el código de la app. **No requiere Python instalado en el equipo destino.** Solo está disponible para Windows.

### Requisitos previos

- Windows con Python 3.11+ instalado
- Entorno virtual creado e instalado con las dependencias

### Pasos para compilar

Abre **PowerShell** o **CMD** en la carpeta del proyecto y ejecuta:

```powershell
# 1. Crear y activar el entorno virtual
python -m venv venv
.\venv\Scripts\Activate.ps1      # PowerShell
# venv\Scripts\activate.bat      # CMD

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Compilar el .exe
.\build_exe.bat
```

> **Nota PowerShell:** si el paso de activación falla por política de ejecución, ejecuta una vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### Qué hace `build_exe.bat` automáticamente

1. Activa el entorno virtual (`venv\` o `.venv\`) si existe.
2. Instala PyInstaller si no está presente.
3. Instala las dependencias de `requirements.txt`.
4. Elimina las carpetas `build\` y `dist\` para una compilación limpia.
5. Ejecuta `pyinstaller run_app.spec --clean`.

### Resultado

```
dist\SimuladorGlucosa.exe
```

- **Tamaño estimado:** 150–250 MB (incluye Python runtime + Streamlit + Plotly)
- **Primer arranque:** puede tardar varios segundos mientras PyInstaller extrae los archivos a un directorio temporal
- **Uso:** doble click → se abre el navegador automáticamente en `http://localhost:8501`

### Compilación manual (alternativa sin el .bat)

```powershell
# Instalar PyInstaller
pip install pyinstaller

# Compilar usando el spec incluido
pyinstaller run_app.spec --clean

# O compilar directamente sin spec (opción rápida, menos optimizada)
pyinstaller run_app.py --onefile --name SimuladorGlucosa --collect-all streamlit
```

---

## 3. Estructura del proyecto

```
010_app_diabetes/
├── app.py            # Interfaz Streamlit (sidebar, gráfico, métricas)
├── model.py          # Lógica matemática pura (numpy + math)
├── run_app.py        # Launcher (desarrollo + PyInstaller)
├── run_app.spec      # Configuración de PyInstaller
├── build_exe.bat     # Script de compilación para Windows
├── requirements.txt
└── README.md
```

---

## 4. Modelo matemático

### ODE del simulador

```
dG/dt = meal_rate(t) − k_clear × (G(t) − G_basal) − insulin_rate(t)
G(0)  = glucosa_inicial
```

- `meal_rate(t)`: tasa de absorción de glucosa — PDF de una distribución **Gamma** parametrizada por el índice glucémico
- `insulin_rate(t)`: tasa de reducción por insulina — PDF **Gamma** o **Log-normal** según el tipo
- `k_clear = 0.01 min⁻¹`: limpieza endógena de glucosa (semivida ≈ 69 min)

### Curva de glucosa por comida

Se modela con una distribución **Gamma** parametrizada por el índice glucémico:

- **IG alto (>70):** pico temprano (~15 min), amplitud alta → `k=2, theta=15`
- **IG bajo (<55):** pico tardío (~60 min), curva suave → `k=4, theta=20`
- **IG medio:** interpolación lineal entre ambos extremos

Amplitud: `4 mg/dL × gramos de HC × factor_IG × sensibilidad`.

### Perfiles de insulina

| Tipo | Distribución | Onset | Pico | Parámetros |
|------|-------------|-------|------|------------|
| **Humalog Junior (lispro)** | Log-normal | 15 min | ~60 min desde inyección | μ=4.030, σ=0.472 |
| Ultrarrápida | Gamma | 0 min | ~60 min | k=3.0, θ=30 |
| Rápida | Gamma | 0 min | ~90 min | k=3.0, θ=45 |
| Regular | Gamma | 0 min | ~120 min | k=4.0, θ=40 |

### Curva resultante

```
glucosa(t) = integración ODE Euler con paso dt = resolución temporal
```

Mínimo visual: 40 mg/dL (clamp de visualización, no barrera fisiológica).

---

## 5. Parámetros principales

| Parámetro | Default | Rango | Descripción |
|-----------|---------|-------|-------------|
| Gramos HC | 60 g | 0–200 g | Hidratos de carbono ingeridos |
| Índice glucémico | 60 | 1–100 | Velocidad de absorción del alimento |
| Glucosa inicial | 120 mg/dL | 40–400 mg/dL | Glucosa en sangre al iniciar la comida |
| Glucosa objetivo | 100 mg/dL | 70–180 mg/dL | Valor deseado para calcular corrección |
| Ratio HC/insulina | 10 g/U | 1–30 g/U | Gramos de HC por unidad de insulina |
| Factor corrección | 40 mg/dL/U | 10–100 mg/dL/U | Reducción por unidad de insulina |
| Unidades insulina | calculado | 0–50 U | Dosis del bolo administrada |
| Tipo insulina | Humalog Junior | — | Perfil farmacocinético |
| Tiempo espera | recomendado | −30 a +60 min | Pre-bolo (+) o post-bolo (−) |
| Duración simulación | 300 min | 60–600 min | Ventana temporal total |

---

## 6. Limitaciones conocidas

| Limitación | Detalle |
|-----------|---------|
| **No clínico** | Los resultados son orientativos. No usar para calcular dosis reales. |
| **Sin variabilidad inter-individual** | El modelo asume parámetros fijos; no simula resistencia a la insulina variable. |
| **Sin gluconeogénesis dinámica** | La producción hepática de glucosa no se modela activamente. |
| **Sin efectos externos** | Ejercicio, estrés, enfermedad y snacks intermedios no están incluidos. |
| **Integración Euler** | Precisión O(dt); suficiente para uso educativo, no para simulación clínica de alta precisión. |
| **Solo Windows (.exe)** | La compilación como ejecutable es exclusiva de Windows. En Linux/macOS: `streamlit run app.py`. |
