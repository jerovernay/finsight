import pandas as pd

# Columnas canónicas que produce siempre el parser
COLUMNAS_SALIDA = ["fecha", "descripcion", "monto", "tipo"]

# Headers que identifican cada formato (en minúsculas sin espacios extra)
_HEADERS_FORMATOS = {
    "A": {"fecha", "descripcion", "monto", "tipo"},
    "B": {"date", "concept", "amount", "debit/credit"},
    "C": {"fecha operación", "detalle", "importe"},
}


def _detectar_formato(columnas_lower: set) -> str:
    """Detecta el formato del CSV comparando sus headers contra los formatos conocidos."""
    for formato, headers in _HEADERS_FORMATOS.items():
        if headers.issubset(columnas_lower):
            return formato
    raise ValueError(
        f"Formato de CSV no reconocido. Columnas encontradas: {sorted(columnas_lower)}. "
        f"Formatos soportados:\n"
        f"  A: {sorted(_HEADERS_FORMATOS['A'])}\n"
        f"  B: {sorted(_HEADERS_FORMATOS['B'])}\n"
        f"  C: {sorted(_HEADERS_FORMATOS['C'])}"
    )


def _normalizar_a(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza Formato A: fecha (YYYY-MM-DD), descripcion, monto, tipo (debito/credito).
    """
    resultado = pd.DataFrame()
    resultado["fecha"] = pd.to_datetime(df["fecha"], format="%Y-%m-%d", errors="coerce")
    resultado["descripcion"] = df["descripcion"].astype(str).str.strip()
    resultado["monto"] = pd.to_numeric(df["monto"], errors="coerce").abs()
    resultado["tipo"] = df["tipo"].astype(str).str.strip().str.lower()
    return resultado


def _normalizar_b(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza Formato B: date (MM/DD/YYYY), concept, amount, debit/credit.
    Los valores de tipo 'debit'→'debito' y 'credit'→'credito'.
    """
    MAPA_TIPO = {"debit": "debito", "credit": "credito"}
    resultado = pd.DataFrame()
    resultado["fecha"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")
    resultado["descripcion"] = df["concept"].astype(str).str.strip()
    resultado["monto"] = pd.to_numeric(df["amount"], errors="coerce").abs()
    tipo_raw = df["debit/credit"].astype(str).str.strip().str.lower()
    resultado["tipo"] = tipo_raw.map(MAPA_TIPO).fillna(tipo_raw)
    return resultado


def _normalizar_c(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza Formato C: Fecha operación (DD-MM-YYYY), Detalle, Importe.
    El tipo se infiere del signo del importe: positivo→credito, negativo→debito.
    """
    resultado = pd.DataFrame()
    resultado["fecha"] = pd.to_datetime(
        df["fecha operación"], format="%d-%m-%Y", errors="coerce"
    )
    resultado["descripcion"] = df["detalle"].astype(str).str.strip()
    importe = pd.to_numeric(df["importe"], errors="coerce")
    resultado["monto"] = importe.abs()
    resultado["tipo"] = importe.apply(lambda x: "credito" if x >= 0 else "debito")
    return resultado


_NORMALIZADORES = {
    "A": _normalizar_a,
    "B": _normalizar_b,
    "C": _normalizar_c,
}


def cargar_csv(archivo) -> pd.DataFrame:
    """
    Carga y normaliza un CSV de movimientos bancarios.

    Detecta automáticamente el formato por los headers y lo normaliza
    al esquema unificado: fecha, descripcion, monto, tipo.

    Formatos soportados
    -------------------
    A — fecha, descripcion, monto, tipo
    B — date, concept, amount, debit/credit
    C — Fecha operación, Detalle, Importe  (tipo inferido del signo)

    Parámetros
    ----------
    archivo : str o archivo-objeto
        Ruta al CSV o objeto de archivo compatible con st.file_uploader.

    Retorna
    -------
    pd.DataFrame con columnas: fecha (datetime64), descripcion (str),
    monto (float positivo), tipo (str 'debito'/'credito').
    Ordenado por fecha ascendente.

    Lanza
    -----
    ValueError si el formato no es reconocido o el archivo queda vacío.
    """
    df_raw = pd.read_csv(archivo)
    df_raw.columns = df_raw.columns.str.strip()

    columnas_lower = set(df_raw.columns.str.lower())
    df_raw.columns = df_raw.columns.str.lower()

    formato = _detectar_formato(columnas_lower)
    df = _NORMALIZADORES[formato](df_raw)

    df = df.dropna(subset=["fecha", "monto"])

    if df.empty:
        raise ValueError("El CSV no contiene filas válidas luego de la limpieza.")

    df = df[COLUMNAS_SALIDA].sort_values("fecha").reset_index(drop=True)
    return df
