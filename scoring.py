import json
import re

import pandas as pd
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODELO = "llama3.2"

_SISTEMA_SCORING = """Eres un analista financiero experto en finanzas personales argentinas.
Recibís métricas calculadas de los movimientos bancarios de un usuario y generás una
evaluación financiera estructurada.

REGLA CRÍTICA: Respondé ÚNICAMENTE con un objeto JSON válido. Sin texto adicional, sin markdown.

El JSON debe tener exactamente esta estructura:
{
  "score": <entero entre 0 y 100>,
  "nivel_riesgo": <"bajo" | "medio" | "alto">,
  "factores_positivos": [<string>, <string>, <string>],
  "factores_riesgo": [<string>, <string>, <string>],
  "recomendacion": <string de 2-3 oraciones en español rioplatense>,
  "explicacion_score": <string de 1-2 oraciones explicando cómo se llegó al número>,
  "recomendaciones": [<acción concreta 1>, <acción concreta 2>, <acción concreta 3>],
  "benchmarks": <string comparando las métricas del usuario con promedios saludables, ej: "Tu ratio gasto/ingreso es 78%, el promedio saludable es menor a 60%.">
}

Criterios para el score:
- 80-100: finanzas saludables, buen ahorro, gastos controlados
- 60-79: situación aceptable con áreas de mejora
- 40-59: alerta, riesgos moderados
- 0-39: situación crítica, intervención urgente"""


def _calcular_metricas(df: pd.DataFrame) -> dict:
    """Calcula métricas numéricas del DataFrame para pasarle al modelo."""
    debitos = df[df["tipo"] == "debito"]
    creditos = df[df["tipo"] == "credito"]

    total_ingresos = creditos["monto"].sum()
    total_gastos = debitos["monto"].sum()
    ratio_ahorro = ((total_ingresos - total_gastos) / total_ingresos * 100) if total_ingresos > 0 else 0

    # Ingresos por mes y estabilidad
    creditos_mes = creditos.copy()
    creditos_mes["mes"] = creditos_mes["fecha"].dt.to_period("M").astype(str)
    ingresos_por_mes = creditos_mes.groupby("mes")["monto"].sum()
    cv_ingresos = (ingresos_por_mes.std() / ingresos_por_mes.mean() * 100) if len(ingresos_por_mes) > 1 else 0

    # Categoría dominante
    gastos_por_cat = debitos.groupby("categoria")["monto"].sum().sort_values(ascending=False)
    cat_top = gastos_por_cat.index[0] if not gastos_por_cat.empty else "N/A"
    pct_top = (gastos_por_cat.iloc[0] / total_gastos * 100) if total_gastos > 0 else 0

    # Tendencia: comparar gasto promedio mensual primera mitad vs segunda
    debitos_mes = debitos.copy()
    debitos_mes["mes"] = debitos_mes["fecha"].dt.to_period("M")
    gastos_por_mes = debitos_mes.groupby("mes")["monto"].sum().sort_index()
    n_meses = len(gastos_por_mes)
    if n_meses >= 2:
        mitad = n_meses // 2
        prom_primera = gastos_por_mes.iloc[:mitad].mean()
        prom_segunda = gastos_por_mes.iloc[mitad:].mean()
        delta_tendencia = ((prom_segunda - prom_primera) / prom_primera * 100) if prom_primera > 0 else 0
    else:
        delta_tendencia = 0

    return {
        "total_ingresos": total_ingresos,
        "total_gastos": total_gastos,
        "ratio_ahorro": ratio_ahorro,
        "n_meses": n_meses,
        "ingresos_por_mes": ingresos_por_mes.to_dict(),
        "cv_ingresos": cv_ingresos,
        "cat_top": cat_top,
        "pct_top": pct_top,
        "gastos_por_cat": gastos_por_cat.to_dict(),
        "delta_tendencia": delta_tendencia,
        "fecha_inicio": df["fecha"].min().strftime("%d/%m/%Y"),
        "fecha_fin": df["fecha"].max().strftime("%d/%m/%Y"),
    }


def _construir_prompt(m: dict) -> str:
    """Arma el mensaje con las métricas calculadas."""
    lineas_cat = "\n".join(
        f"  - {cat}: ${monto:,.0f} ({monto / m['total_gastos'] * 100:.1f}%)"
        for cat, monto in m["gastos_por_cat"].items()
    )
    lineas_ingresos = ", ".join(
        f"{mes}: ${monto:,.0f}" for mes, monto in m["ingresos_por_mes"].items()
    )

    tendencia_txt = (
        f"gastos subiendo {m['delta_tendencia']:+.1f}% en la segunda mitad del período"
        if m["delta_tendencia"] > 0
        else f"gastos bajando {m['delta_tendencia']:+.1f}% en la segunda mitad del período"
    )

    estabilidad_txt = (
        "muy estables (CV < 10%)" if m["cv_ingresos"] < 10
        else "moderadamente estables (CV 10–30%)" if m["cv_ingresos"] < 30
        else f"erráticos (CV {m['cv_ingresos']:.1f}%)"
    )

    return (
        f"Analizá las siguientes métricas financieras y generá el JSON de evaluación:\n\n"
        f"PERÍODO: {m['fecha_inicio']} al {m['fecha_fin']} ({m['n_meses']} meses)\n\n"
        f"RESUMEN ECONÓMICO:\n"
        f"  - Total ingresos: ${m['total_ingresos']:,.0f}\n"
        f"  - Total gastos:   ${m['total_gastos']:,.0f}\n"
        f"  - Ratio de ahorro: {m['ratio_ahorro']:.1f}% de los ingresos\n\n"
        f"ESTABILIDAD DE INGRESOS:\n"
        f"  - Ingresos por mes: {lineas_ingresos}\n"
        f"  - Evaluación: {estabilidad_txt}\n\n"
        f"DISTRIBUCIÓN DE GASTOS:\n"
        f"{lineas_cat}\n"
        f"  - Categoría dominante: {m['cat_top']} ({m['pct_top']:.1f}% del total)\n\n"
        f"TENDENCIA: {tendencia_txt}\n\n"
        f"Generá el JSON de score financiero."
    )


def generar_score_financiero(df: pd.DataFrame) -> dict:
    """
    Analiza el DataFrame de gastos categorizados y genera un score financiero vía IA.

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame con columnas: fecha, descripcion, monto, tipo, categoria.

    Retorna
    -------
    dict con claves: score (int), nivel_riesgo (str), factores_positivos (list[str]),
    factores_riesgo (list[str]), recomendacion (str).

    Lanza
    -----
    ValueError si la respuesta del modelo no es JSON válido con la estructura esperada.
    requests.RequestException si Ollama no está disponible.
    """
    metricas = _calcular_metricas(df)
    prompt = _construir_prompt(metricas)

    payload = {
        "model": OLLAMA_MODELO,
        "messages": [
            {"role": "system", "content": _SISTEMA_SCORING},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    respuesta = requests.post(OLLAMA_URL, json=payload, timeout=120)
    respuesta.raise_for_status()

    texto = respuesta.json()["message"]["content"].strip()

    # Extraer el bloque JSON aunque haya texto antes o después
    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio != -1 and fin != -1:
        texto = texto[inicio : fin + 1]

    try:
        resultado = json.loads(texto)
    except json.JSONDecodeError:
        # Fallback mínimo si el modelo devuelve texto inválido
        resultado = {
            "score": 50,
            "nivel_riesgo": "medio",
            "factores_positivos": ["No se pudo analizar en detalle"],
            "factores_riesgo": ["La IA no devolvió un JSON válido"],
            "recomendacion": "Intentá generar el score nuevamente.",
            "explicacion_score": "El score no pudo calcularse correctamente esta vez.",
            "recomendaciones": ["Volvé a generar el score", "Verificá que Ollama esté activo", "Revisá los datos cargados"],
            "benchmarks": "No disponible por error en la respuesta del modelo.",
        }
        return resultado

    campos_requeridos = {"score", "nivel_riesgo", "factores_positivos", "factores_riesgo", "recomendacion"}
    faltantes = campos_requeridos - set(resultado.keys())
    if faltantes:
        raise ValueError(f"La respuesta del modelo no contiene los campos: {faltantes}")

    resultado["score"] = max(0, min(100, int(resultado["score"])))
    return resultado
