import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from parser import cargar_csv
from categorizer import categorizar_gastos
from chat import responder_pregunta
from scoring import generar_score_financiero

st.set_page_config(page_title="FinSight", page_icon="💰", layout="wide")

# ── Estado de sesión ──────────────────────────────────────────────────────────
st.session_state.setdefault("df_crudo", None)
st.session_state.setdefault("df_categorizado", None)
st.session_state.setdefault("historial_chat", [])
st.session_state.setdefault("score_financiero", None)
st.session_state.setdefault("pagina", "cargar")


def _ir_a(destino: str) -> None:
    """Callback on_click para botones de navegación."""
    st.session_state.pagina = destino


# ── Pre-requisitos de cada paso ───────────────────────────────────────────────
datos_listos   = st.session_state.df_crudo is not None
analisis_listo = st.session_state.df_categorizado is not None
score_listo    = st.session_state.score_financiero is not None

PASOS = [
    ("cargar",    "Cargar datos",     True),
    ("analisis",  "Análisis",         datos_listos),
    ("score",     "Score financiero", analisis_listo),
    ("simulador", "Simulador",        score_listo),
]

# Auto-redirect si el paso activo perdió sus requisitos
pagina = st.session_state.pagina
if pagina == "simulador" and not score_listo:
    pagina = st.session_state.pagina = "score" if analisis_listo else ("analisis" if datos_listos else "cargar")
elif pagina == "score" and not analisis_listo:
    pagina = st.session_state.pagina = "analisis" if datos_listos else "cargar"
elif pagina == "analisis" and not datos_listos:
    pagina = st.session_state.pagina = "cargar"

# ── Sidebar de navegación ─────────────────────────────────────────────────────
with st.sidebar:
    st.title("💰 FinSight")
    st.caption("Analizá tus finanzas personales con IA")
    st.divider()

    for i, (key, label, habilitado) in enumerate(PASOS, 1):
        completado = (
            (key == "cargar"   and datos_listos)  or
            (key == "analisis" and analisis_listo) or
            (key == "score"    and score_listo)
        )
        es_actual = (pagina == key)
        icono = "✅" if completado else ("▶" if es_actual else ("🔒" if not habilitado else "○"))

        st.button(
            f"{icono}  {i}. {label}",
            key=f"nav_{key}",
            disabled=not habilitado,
            use_container_width=True,
            type="primary" if es_actual else "secondary",
            on_click=_ir_a,
            args=(key,),
        )

    st.divider()
    pasos_ok = sum([datos_listos, analisis_listo, score_listo])
    st.progress(pasos_ok / 3, text=f"Progreso: {pasos_ok} / 3 pasos")

# ── Paso 1: Cargar datos ──────────────────────────────────────────────────────
if pagina == "cargar":
    st.header("Paso 1 — Cargar datos")
    col_izq, col_der = st.columns([1, 2])

    with col_izq:
        archivos = st.file_uploader(
            "Subí tus CSVs de movimientos",
            type=["csv"],
            accept_multiple_files=True,
        )

        if archivos:
            nombres = tuple(sorted(f.name for f in archivos))
            if nombres != st.session_state.get("_archivos_cargados"):
                dfs, errores = [], []
                for f in archivos:
                    try:
                        dfs.append(cargar_csv(f))
                    except ValueError as e:
                        errores.append(f"{f.name}: {e}")
                for msg in errores:
                    st.error(msg)
                if dfs:
                    df_concat = (
                        pd.concat(dfs, ignore_index=True)
                        .sort_values("fecha")
                        .reset_index(drop=True)
                    )
                    st.session_state.df_crudo = df_concat
                    st.session_state.df_categorizado = None
                    st.session_state.historial_chat = []
                    st.session_state.score_financiero = None
                    st.session_state["_archivos_cargados"] = nombres
                    st.session_state["_n_archivos"] = len(dfs)

        st.write("— o —")

        if st.button("Usar datos de ejemplo", use_container_width=True):
            try:
                st.session_state.df_crudo = cargar_csv("sample_data.csv")
                st.session_state.df_categorizado = None
                st.session_state.historial_chat = []
                st.session_state.score_financiero = None
                st.session_state["_archivos_cargados"] = ()
                st.session_state["_n_archivos"] = 1
            except Exception as e:
                st.error(f"No se pudieron cargar los datos de ejemplo: {e}")

        if st.session_state.df_crudo is not None:
            st.divider()
            n_arch = st.session_state.get("_n_archivos", 1)
            col_ma, col_mr = st.columns(2)
            col_ma.metric("Archivos cargados", n_arch)
            col_mr.metric("Movimientos totales", len(st.session_state.df_crudo))
            st.button(
                "Ir a Análisis →",
                type="primary",
                use_container_width=True,
                on_click=_ir_a,
                args=("analisis",),
            )

    with col_der:
        if st.session_state.df_crudo is not None:
            st.subheader("Vista previa de datos")
            st.dataframe(st.session_state.df_crudo, use_container_width=True, hide_index=True)

# ── Paso 2: Análisis ──────────────────────────────────────────────────────────
elif pagina == "analisis":
    st.header("Paso 2 — Análisis")

    if not analisis_listo:
        st.info(
            f"Tenés **{len(st.session_state.df_crudo)} movimientos** cargados. "
            "Categorizalos con IA para ver el análisis completo."
        )
        if st.button("✨ Categorizar con IA", type="primary"):
            with st.spinner("Categorizando movimientos... puede tomar unos segundos"):
                try:
                    st.session_state.df_categorizado = categorizar_gastos(
                        st.session_state.df_crudo
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al categorizar: {e}")
    else:
        df       = st.session_state.df_categorizado
        debitos  = df[df["tipo"] == "debito"]
        creditos = df[df["tipo"] == "credito"]
        total_ingresos = creditos["monto"].sum()
        total_gastos   = debitos["monto"].sum()
        balance        = total_ingresos - total_gastos

        col_m1, col_m2, col_m3, col_recat = st.columns(4)
        col_m1.metric("Total ingresos", f"${total_ingresos:,.0f}")
        col_m2.metric("Total gastos",   f"${total_gastos:,.0f}")
        col_m3.metric("Balance neto",   f"${balance:,.0f}", delta=f"${balance:,.0f}")
        with col_recat:
            if st.button("↺ Re-categorizar", use_container_width=True):
                with st.spinner("Re-categorizando..."):
                    try:
                        st.session_state.df_categorizado = categorizar_gastos(
                            st.session_state.df_crudo
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        with st.expander("Ver tabla completa de movimientos", expanded=False):
            st.dataframe(df, use_container_width=True, hide_index=True)

        tab_torta, tab_barras, tab_linea = st.tabs(
            ["Distribución por categoría", "Gasto mensual", "Evolución del balance"]
        )

        with tab_torta:
            por_cat = debitos.groupby("categoria")["monto"].sum().reset_index()
            fig_torta = px.pie(
                por_cat, values="monto", names="categoria",
                title="Distribución de gastos por categoría", hole=0.35,
            )
            fig_torta.update_layout(legend_title_text="Categoría")
            st.plotly_chart(fig_torta, use_container_width=True)

        with tab_barras:
            debitos_mes = debitos.copy()
            debitos_mes["mes"] = debitos_mes["fecha"].dt.to_period("M").astype(str)
            por_mes_cat = debitos_mes.groupby(["mes", "categoria"])["monto"].sum().reset_index()
            fig_barras = px.bar(
                por_mes_cat, x="mes", y="monto", color="categoria",
                title="Gasto mensual por categoría",
                labels={"monto": "Monto (ARS)", "mes": "Mes", "categoria": "Categoría"},
                barmode="stack",
            )
            fig_barras.update_layout(yaxis_tickprefix="$", yaxis_tickformat=",.0f")
            st.plotly_chart(fig_barras, use_container_width=True)

        with tab_linea:
            df_orden = df.sort_values("fecha").copy()
            df_orden["flujo"] = df_orden["monto"].where(
                df_orden["tipo"] == "credito", -df_orden["monto"]
            )
            df_orden["balance_acumulado"] = df_orden["flujo"].cumsum()
            fig_linea = px.line(
                df_orden, x="fecha", y="balance_acumulado",
                title="Evolución del balance acumulado",
                labels={"balance_acumulado": "Balance (ARS)", "fecha": "Fecha"},
                markers=True,
                hover_data={"descripcion": True, "monto": True, "tipo": True},
            )
            fig_linea.add_hline(
                y=0, line_dash="dash", line_color="red", opacity=0.5, annotation_text="$0"
            )
            fig_linea.update_layout(yaxis_tickprefix="$", yaxis_tickformat=",.0f")
            st.plotly_chart(fig_linea, use_container_width=True)

        st.divider()
        st.button(
            "Ir a Score financiero →",
            type="primary",
            on_click=_ir_a,
            args=("score",),
        )

        # Chat al pie del análisis
        st.divider()
        st.subheader("Chat con tus finanzas")
        for mensaje in st.session_state.historial_chat:
            with st.chat_message(mensaje["role"]):
                st.markdown(mensaje["content"])

        pregunta = st.chat_input("Preguntale algo a FinSight sobre tus gastos...")
        if pregunta:
            with st.chat_message("user"):
                st.markdown(pregunta)
            st.session_state.historial_chat.append({"role": "user", "content": pregunta})
            with st.chat_message("assistant"):
                with st.spinner("Pensando..."):
                    try:
                        respuesta = responder_pregunta(
                            pregunta,
                            st.session_state.df_categorizado,
                            st.session_state.historial_chat[:-1],
                        )
                    except Exception as e:
                        respuesta = f"Lo siento, ocurrió un error al procesar tu pregunta: {e}"
                st.markdown(respuesta)
            st.session_state.historial_chat.append({"role": "assistant", "content": respuesta})

# ── Paso 3: Score financiero ──────────────────────────────────────────────────
elif pagina == "score":
    st.header("Paso 3 — Score financiero")

    if st.button("🧮 Generar score financiero", type="primary"):
        with st.spinner("Analizando tu situación financiera..."):
            try:
                st.session_state.score_financiero = generar_score_financiero(
                    st.session_state.df_categorizado
                )
            except Exception as e:
                st.error(f"Error al generar el score: {e}")

    score_data = st.session_state.score_financiero
    if score_data is not None:
        score = score_data["score"]
        nivel = score_data["nivel_riesgo"]
        COLOR_NIVEL = {"bajo": "normal", "medio": "off",     "alto": "inverse"}
        ICONO_NIVEL = {"bajo": "✅",      "medio": "⚠️", "alto": "🚨"}

        col_score, col_nivel = st.columns([1, 2])
        with col_score:
            st.metric("Puntaje financiero", f"{score} / 100",
                      delta_color=COLOR_NIVEL.get(nivel, "normal"))
        with col_nivel:
            st.metric("Nivel de riesgo", f"{ICONO_NIVEL.get(nivel, '')} {nivel.capitalize()}")

        col_pos, col_riesgo = st.columns(2)
        with col_pos:
            st.markdown("**Factores positivos**")
            for factor in score_data["factores_positivos"]:
                st.markdown(f"✔ {factor}")
        with col_riesgo:
            st.markdown("**Factores de riesgo**")
            for factor in score_data["factores_riesgo"]:
                st.markdown(f"✖ {factor}")

        st.info(f"**Recomendación:** {score_data['recomendacion']}")

        if score_data.get("explicacion_score"):
            st.divider()
            st.markdown("#### Cómo se calculó el score")
            st.write(score_data["explicacion_score"])

        if score_data.get("benchmarks"):
            st.markdown("#### Benchmarks")
            st.warning(score_data["benchmarks"])

        if score_data.get("recomendaciones"):
            st.markdown("#### Acciones concretas")
            for i, accion in enumerate(score_data["recomendaciones"], 1):
                st.markdown(f"**{i}.** {accion}")

        st.divider()
        st.button(
            "Ir al Simulador →",
            type="primary",
            on_click=_ir_a,
            args=("simulador",),
        )

# ── Paso 4: Simulador de crédito ──────────────────────────────────────────────
elif pagina == "simulador":
    TASA_MENSUAL = 0.03
    st.header("Paso 4 — Simulador de crédito")

    df_sim           = st.session_state.df_crudo
    creditos_sim     = df_sim[df_sim["tipo"] == "credito"]
    ingresos_por_mes = creditos_sim.groupby(
        creditos_sim["fecha"].dt.to_period("M")
    )["monto"].sum()
    ingreso_mensual_promedio = ingresos_por_mes.mean() if not ingresos_por_mes.empty else 0.0

    col_sliders, col_resultados = st.columns([1, 1])

    with col_sliders:
        monto = st.slider(
            "Monto del crédito",
            min_value=50_000, max_value=1_000_000, value=200_000, step=10_000, format="$%d",
        )
        plazo = st.slider("Plazo (meses)", min_value=3, max_value=24, value=12)
        pct_retencion = st.slider(
            "Retención sobre ingresos", min_value=5, max_value=15, value=10, format="%d%%",
        )

    factor          = (1 + TASA_MENSUAL) ** plazo
    cuota           = monto * TASA_MENSUAL * factor / (factor - 1)
    total_a_pagar   = cuota * plazo
    total_intereses = total_a_pagar - monto
    ingreso_asignado = ingreso_mensual_promedio * pct_retencion / 100

    if ingreso_mensual_promedio == 0:
        repago_txt, repago_viable = "Sin ingresos en el CSV", False
    elif ingreso_asignado < cuota:
        repago_txt, repago_viable = "Cuota supera ingreso asignado", False
    else:
        repago_txt, repago_viable = f"{total_a_pagar / ingreso_asignado:.1f} meses", True

    with col_resultados:
        st.metric("Cuota mensual estimada", f"${cuota:,.0f}")
        st.metric(
            "Total a pagar", f"${total_a_pagar:,.0f}",
            delta=f"+${total_intereses:,.0f} en intereses", delta_color="inverse",
        )
        st.metric("Ingreso mensual promedio (CSV)", f"${ingreso_mensual_promedio:,.0f}")
        st.metric("Tiempo estimado de repago", repago_txt)

    if not repago_viable and ingreso_mensual_promedio > 0:
        st.warning(
            f"La cuota mensual (${cuota:,.0f}) supera el ingreso asignado "
            f"(${ingreso_asignado:,.0f}). Reducí el monto o extendé el plazo."
        )

    n_meses_grafico = min(max(plazo, 36), 48)
    meses = list(range(n_meses_grafico + 1))
    saldos, ingresos_acum, saldo_actual = [], [], float(monto)
    for mes in meses:
        saldos.append(max(saldo_actual, 0))
        ingresos_acum.append(mes * ingreso_asignado)
        saldo_actual = max(saldo_actual * (1 + TASA_MENSUAL) - cuota, 0)

    fig_sim = go.Figure()
    fig_sim.add_trace(go.Scatter(
        x=meses, y=saldos, name="Saldo del crédito",
        line=dict(color="#EF553B", width=2),
        fill="tozeroy", fillcolor="rgba(239, 85, 59, 0.08)",
    ))
    fig_sim.add_trace(go.Scatter(
        x=meses, y=ingresos_acum,
        name=f"Ingresos acumulados asignados ({pct_retencion}%)",
        line=dict(color="#00CC96", width=2, dash="dash"),
    ))
    fig_sim.add_vline(
        x=plazo, line_dash="dot", line_color="gray",
        annotation_text=f"Vencimiento (mes {plazo})", annotation_position="top right",
    )
    fig_sim.update_layout(
        title="Proyección: saldo del crédito vs ingresos acumulados asignados",
        xaxis_title="Mes", yaxis_title="Monto (ARS)",
        yaxis_tickprefix="$", yaxis_tickformat=",.0f",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig_sim, use_container_width=True)
