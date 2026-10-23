"""Budget and financial tracking per project."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from hub import audit, db, engine_risk, ui
from hub.i18n import t


def render(ctx: dict) -> None:
    cid, edit, user = ctx["cid"], ctx["can_edit"], ctx["user"]
    cur = ctx["company"]["currency"] or "EUR"
    warn = db.settings(cid)["budget_warning_pct"]
    ui.page_header("budget", t("Budget & finance"), t("Approved, planned, actual and forecast spend ({c})", c=cur))
    st.info(t("Demonstration figures are sample estimates generated for the case study. They are not real financial records or transactions."))
    p = db.df("SELECT * FROM projects WHERE company_id = ? AND archived = 0 AND budget > 0 ORDER BY code", (cid,))
    if p.empty:
        st.info(t("No project budgets defined yet."))
        return
    p["remaining"] = p["budget"] - p["actual_spend"]
    p["util"] = (p["actual_spend"] / p["budget"] * 100).round(1)
    p["variance"] = p["budget"] - p["forecast_spend"]
    p["flag"] = p.apply(lambda r: "Over budget" if r["util"] > 100 else ("Forecast over budget" if r["forecast_spend"] > r["budget"]
                                                                          else ("Approaching budget" if r["util"] >= warn else "")), axis=1)
    p["type"] = p["financials_are_estimates"].map({1: "Sample estimate", 0: "Recorded"})
    tb, ta = p["budget"].sum(), p["actual_spend"].sum()
    ui.kpi_row([
        (t("Approved budget"), ui.money(tb, cur), t("{n} projects", n=len(p)), "neutral"),
        (t("Actual expenditure"), ui.money(ta, cur), f"{ta / tb * 100:.0f}%", "neutral"),
        (t("Forecast expenditure"), ui.money(p["forecast_spend"].sum(), cur), t("variance {v}", v=ui.money(tb - p["forecast_spend"].sum(), cur)),
         "bad" if p["forecast_spend"].sum() > tb else "good"),
        (t("Projects flagged"), int((p["flag"] != "").sum()), t("warning at {w}%", w=warn), "warn" if (p["flag"] != "").any() else "good"),
    ])
    ui.table(p, {"code": "ID", "name": "Project", "budget": "Approved", "planned_spend": "Planned to date", "actual_spend": "Actual",
                 "remaining": "Remaining", "util": "Utilisation %", "forecast_spend": "Forecast", "variance": "Variance", "flag": "Flag", "type": "Data type"},
             translate_values=("flag", "type"))
    c1, c2 = st.columns([1, 1])
    with c1:
        fig = go.Figure()
        fig.add_bar(x=p["code"], y=p["budget"], name=t("Approved budget"), marker_color="#c9d6e8")
        fig.add_bar(x=p["code"], y=p["actual_spend"], name=t("Actual"), marker_color=ui.NAVY)
        fig.add_scatter(x=p["code"], y=p["forecast_spend"], name=t("Forecast"), mode="markers", marker=dict(symbol="line-ew-open", size=26, color="#b3261e", line=dict(width=3)))
        fig.update_layout(barmode="group", title=t("Budget, actual and forecast by project"))
        st.plotly_chart(ui.style_fig(fig), key="b1")
    with c2:
        code = st.selectbox(t("Project"), p["code"].tolist(), format_func=lambda c: f"{c} · {p.set_index('code').loc[c, 'name']}")
        pid = int(p[p["code"] == code]["id"].iloc[0])
        bl = db.t_df("budget_lines", cid, "project_id = ?", (pid,), order="month")
        if not bl.empty:
            bl["cum_planned"] = bl["planned"].cumsum()
            bl["cum_actual"] = bl["actual"].fillna(0).cumsum().where(bl["actual"].notna())
            fig = go.Figure()
            fig.add_scatter(x=bl["month"], y=bl["cum_planned"], name=t("Planned (cumulative)"), line=dict(color="#7fa7d9", dash="dash"))
            fig.add_scatter(x=bl["month"], y=bl["cum_actual"], name=t("Actual (cumulative)"), line=dict(color=ui.NAVY, width=3))
            fig.add_hline(y=float(p[p["code"] == code]["budget"].iloc[0]), line_color="#b3261e", annotation_text=t("Approved budget"))
            fig.update_layout(title=t("Planned vs actual spending over time"))
            st.plotly_chart(ui.style_fig(fig), key="b2")
    if edit:
        with st.expander("✏️ " + t("Update financial figures")):
            row = db.t_get("projects", cid, pid)
            with st.form("fin"):
                c1, c2, c3 = st.columns(3)
                b = c1.number_input(t("Approved budget"), 0.0, value=float(row["budget"]), step=1000.0)
                a = c2.number_input(t("Actual expenditure"), 0.0, value=float(row["actual_spend"]), step=1000.0)
                f = c3.number_input(t("Forecast expenditure"), 0.0, value=float(row["forecast_spend"]), step=1000.0)
                est = st.checkbox(t("These figures are estimates"), value=bool(row["financials_are_estimates"]))
                if st.form_submit_button(t("Save"), type="primary"):
                    db.t_update("projects", cid, pid, {"budget": b, "actual_spend": a, "forecast_spend": f, "financials_are_estimates": int(est)})
                    audit.log(cid, user["email"], "budget_updated", "project", code, f"budget {row['budget']}→{b}, actual {row['actual_spend']}→{a}, forecast {row['forecast_spend']}→{f}")
                    engine_risk.run(cid)
                    st.success(t("Saved."))
                    st.rerun()
