import json

import pandas as pd
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODELO = "llama3.2"

CATEGORIAS_VALIDAS = {
    "Alimentación",
    "Transporte",
    "Entretenimiento",
    "Suscripciones",
    "Salud",
    "Educación",
    "Transferencias",
    "Ingresos",
    "Otros",
}

_SISTEMA_CATEGORIZADOR = """Eres un categorizador experto de transacciones bancarias argentinas.
Tu única función es asignar una categoría a cada transacción que se te proporcione.

Las categorías válidas son EXACTAMENTE las siguientes (respeta mayúsculas y acentos):
- Alimentación
- Transporte
- Entretenimiento
- Suscripciones
- Salud
- Educación
- Transferencias
- Ingresos
- Otros

REGLAS CRÍTICAS:
1. Responde ÚNICAMENTE con un array JSON válido de strings.
2. El array debe tener exactamente el mismo número de elementos que transacciones recibidas.
3. Cada elemento debe ser una de las categorías válidas listadas arriba.
4. No incluyas texto, explicaciones ni bloques de código markdown. Solo el array JSON puro.
5. Ejemplo de formato para 3 transacciones: ["Alimentación", "Ingresos", "Transporte"]"""


def _llamar_ollama(sistema: str, usuario: str) -> str:
    """Realiza un llamado a la API de Ollama y retorna el texto de la respuesta."""
    payload = {
        "model": OLLAMA_MODELO,
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": usuario},
        ],
        "stream": False,
    }
    respuesta = requests.post(OLLAMA_URL, json=payload, timeout=120)
    respuesta.raise_for_status()
    return respuesta.json()["message"]["content"].strip()


def categorizar_gastos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Categoriza todos los movimientos del DataFrame en un único llamado a Ollama.

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame limpio con columnas: fecha, descripcion, monto, tipo.

    Retorna
    -------
    pd.DataFrame igual al original con una columna adicional 'categoria'.
    En caso de error, todos los registros quedan como 'Otros'.
    """
    resultado = df.copy()

    lineas = [
        f"{i + 1}. {fila.descripcion} | ${fila.monto:.2f} | {fila.tipo}"
        for i, fila in enumerate(df.itertuples())
    ]
    lista_transacciones = "\n".join(lineas)
    n = len(df)

    mensaje_usuario = (
        f"Categoriza las siguientes {n} transacciones bancarias en orden:\n\n"
        f"{lista_transacciones}\n\n"
        f"Devuelve exactamente {n} categorías en un array JSON."
    )

    try:
        texto = _llamar_ollama(_SISTEMA_CATEGORIZADOR, mensaje_usuario)

        # Eliminar fences de markdown si el modelo los incluye
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            if texto.startswith("json"):
                texto = texto[4:]
            texto = texto.strip()

        categorias = json.loads(texto)

        if len(categorias) != n:
            categorias = ["Otros"] * n
        else:
            categorias = [
                c if c in CATEGORIAS_VALIDAS else "Otros" for c in categorias
            ]

    except Exception:
        categorias = ["Otros"] * n

    resultado["categoria"] = categorias
    return resultado
