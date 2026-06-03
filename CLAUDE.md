# FinSight — Analizador de gastos personales con IA

## Qué es este proyecto
App web en Python + Streamlit que permite al usuario subir un CSV con movimientos bancarios,
categorizarlos automáticamente con Claude (API de Anthropic), detectar patrones de gasto
y hacer preguntas en lenguaje natural sobre sus finanzas.

## Stack
- Python 3.11+
- Streamlit (UI)
- Ollama (desarrollo local) con modelo llama3.2 — API en http://localhost:11434/api/chat
- Pandas (procesamiento de datos)
- Plotly (visualizaciones)

## Estructura de archivos objetivo
finsight/
├── app.py              # Entry point de Streamlit
├── categorizer.py      # Lógica de categorización con Ollama
├── parser.py           # Parseo y limpieza de CSV
├── chat.py             # Chat conversacional sobre los datos
├── sample_data.csv     # Datos de ejemplo para demo
├── requirements.txt
└── CLAUDE.md

## Convenciones
- Todo el código en español (variables, comentarios, strings de UI)
- Funciones pequeñas y con docstring
- En desarrollo local se usa Ollama con llama3.2; no se requiere ANTHROPIC_API_KEY
- Los llamados a la API se hacen con `requests` (sin SDK externo de IA)
- Sin nuevas dependencias fuera del stack definido arriba

## Comandos útiles
- Correr la app: streamlit run app.py
- Instalar deps: pip install -r requirements.txt