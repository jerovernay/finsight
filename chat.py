import pandas as pd
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODELO = "llama3.2"

_SISTEMA_CHAT = """Eres FinSight, un asistente financiero personal inteligente.
Analizás los datos financieros del usuario y respondés sus preguntas de forma clara,
concisa y en español argentino.
Cuando menciones montos, usá el formato $X.XXX (pesos argentinos).
Proporcioná insights útiles y accionables cuando sea relevante.
Nunca inventés datos que no estén en el resumen financiero provisto."""


def _construir_resumen(df: pd.DataFrame) -> str:
    """Genera un resumen compacto de los datos financieros para usar como contexto."""
    debitos = df[df["tipo"] == "debito"]
    creditos = df[df["tipo"] == "credito"]

    total_gastos = debitos["monto"].sum()
    total_ingresos = creditos["monto"].sum()
    balance = total_ingresos - total_gastos

    fecha_inicio = df["fecha"].min().strftime("%d/%m/%Y")
    fecha_fin = df["fecha"].max().strftime("%d/%m/%Y")

    por_categoria = (
        debitos.groupby("categoria")["monto"].sum().sort_values(ascending=False)
    )
    lineas_cat = "\n".join(
        f"  - {cat}: ${monto:,.0f}" for cat, monto in por_categoria.items()
    )

    return (
        f"Período analizado: {fecha_inicio} al {fecha_fin}\n"
        f"Total ingresos: ${total_ingresos:,.0f}\n"
        f"Total gastos: ${total_gastos:,.0f}\n"
        f"Balance neto: ${balance:,.0f}\n"
        f"Gastos por categoría:\n{lineas_cat}"
    )


def responder_pregunta(
    pregunta: str,
    df_con_categorias: pd.DataFrame,
    historial: list,
) -> str:
    """
    Responde una pregunta en lenguaje natural sobre los gastos del usuario.

    Parámetros
    ----------
    pregunta : str
        Pregunta del usuario sobre sus finanzas.
    df_con_categorias : pd.DataFrame
        DataFrame categorizado con columnas: fecha, descripcion, monto, tipo, categoria.
    historial : list
        Lista de dicts {"role": "user"/"assistant", "content": "..."} con el historial previo.

    Retorna
    -------
    str con la respuesta del modelo.
    """
    resumen = _construir_resumen(df_con_categorias)
    sistema = f"{_SISTEMA_CHAT}\n\nDatos financieros actuales del usuario:\n{resumen}"

    mensajes = [{"role": "system", "content": sistema}]
    mensajes += list(historial[-10:])
    mensajes.append({"role": "user", "content": pregunta})

    payload = {
        "model": OLLAMA_MODELO,
        "messages": mensajes,
        "stream": False,
    }
    respuesta = requests.post(OLLAMA_URL, json=payload, timeout=120)
    respuesta.raise_for_status()
    return respuesta.json()["message"]["content"]
