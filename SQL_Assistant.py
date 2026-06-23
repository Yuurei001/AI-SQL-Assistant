import re
import pandas as pd
import altair as alt
import streamlit as st
from agent_core.tools.validator_tool import ValidatorTool

def is_safe_query(query: str) -> tuple[bool, str]:
    return ValidatorTool.is_safe(query)

def highlight_sql(sql: str) -> str:
    import html as _h
    lines  = sql.split("\n")
    result = []
    kws = (
        r"\b(SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|ORDER|GROUP|BY|HAVING|"
        r"LIMIT|OFFSET|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|AS|DISTINCT|"
        r"COUNT|SUM|AVG|MIN|MAX|UPPER|LOWER|ROUND|COALESCE|CAST|CASE|WHEN|"
        r"THEN|ELSE|END|BETWEEN|LIKE|EXISTS|UNION|ALL|WITH|ASC|DESC|OVER|"
        r"PARTITION|ROW_NUMBER|RANK|DENSE_RANK|STRFTIME|DATE)\b"
    )
    for i, line in enumerate(lines, 1):
        s = _h.escape(line)
        s = re.sub(kws, r'<span class="kw">\1</span>', s, flags=re.IGNORECASE)
        s = re.sub(r"'([^']*)'", r'<span class="str">\'\1\'</span>', s)
        s = re.sub(r"\b(\d+(?:\.\d+)?)\b", r'<span class="num">\1</span>', s)
        s = re.sub(r"--.*$", r'<span class="cmt">\g<0></span>', s)
        lineno = f'<span class="sql-lineno">{i}</span>'
        result.append(lineno + s)
    return "\n".join(result)

def try_make_chart(df: pd.DataFrame):
    if len(df) < 2 or len(df.columns) < 2:
        return None
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    text_cols    = df.select_dtypes(include=["object", "string"]).columns.tolist()
    if not numeric_cols or not text_cols:
        return None
    if len(df) > 40:
        return None

    is_light = st.session_state.get("theme") == "light"
    bar_color    = "#0969DA" if is_light else "#58A6FF"
    label_color  = "#57606A" if is_light else "#8B949E"
    grid_color   = "#EAEEF2" if is_light else "#21262D"
    axis_color   = "#D0D7DE" if is_light else "#30363D"
    bg_color     = "#FFFFFF" if is_light else "#161B22"

    x_col = text_cols[0]
    y_col = numeric_cols[0]
    try:
        chart = (
            alt.Chart(df)
            .mark_bar(
                color=bar_color,
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4,
            )
            .encode(
                x=alt.X(
                    f"{x_col}:N",
                    sort="-y",
                    axis=alt.Axis(
                        labelAngle=-35,
                        labelColor=label_color,
                        titleColor=label_color,
                        labelFontSize=11,
                        labelFont="Inter",
                        domainColor=axis_color,
                        tickColor=axis_color,
                    ),
                ),
                y=alt.Y(
                    f"{y_col}:Q",
                    axis=alt.Axis(
                        labelColor=label_color,
                        titleColor=label_color,
                        labelFontSize=11,
                        labelFont="Inter",
                        gridColor=grid_color,
                        domainColor=axis_color,
                        tickColor=axis_color,
                    ),
                ),
                tooltip=[x_col, y_col],
            )
            .properties(
                height=320,
                background=bg_color,
                padding={"left": 10, "right": 10, "top": 20, "bottom": 10},
            )
            .configure_view(
                stroke="transparent",
            )
        )
        return chart
    except Exception:
        return None
