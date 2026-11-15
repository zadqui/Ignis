"""Streamlit panel (bilingual). Reads ONLY the read-only API (JSON contract), never the database directly.

Run: ``uv run fif-app api`` and then ``uv run fif-app panel``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import altair as alt
import httpx
import pandas as pd
import streamlit as st

API = os.environ.get("FIF_API", "http://127.0.0.1:8000")
I18N = {lang: json.loads((Path(__file__).parent / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in ("en", "es")}

st.set_page_config(page_title="Flame in Freefall", layout="wide")
lang = st.sidebar.selectbox("Language / Idioma", ["en", "es"], index=1)
T = I18N[lang]


def t(key: str, **kw) -> str:
    s = T.get(key, key)
    return s.format(**kw) if kw else s


@st.cache_data(ttl=30, show_spinner=False)
def get(path: str, params: tuple = ()) -> dict:
    r = httpx.get(API + path, params=dict(params), timeout=60)
    r.raise_for_status()
    return r.json()


def shown(claim: str | None) -> str:
    """A claim withheld by the publication policy (ND source) is labelled, never shown blank."""
    return claim if claim is not None else t("claim_withheld_nd")


def badge(display_status: str | None) -> str:
    ds = display_status or ""
    if ds.startswith("scientifically_confirmed"):
        return f"🟢 {t('badge_confirmed')}"
    if ds.startswith("scientifically_rejected"):
        return f"🔴 {t('badge_rejected')}"
    if ds.startswith("machine_verified"):
        return f"🟡 {t('badge_machine')}"
    if "provisional" in ds:
        return f"🟠 {t('badge_provisional')}"
    return ds


st.title(t("app_title"))
st.caption(t("app_subtitle"))
try:
    status = get("/status")
except httpx.HTTPError:
    st.error(t("api_unreachable", url=API))
    st.stop()

with st.expander("⚠️ " + t("limitations_title"), expanded=True):
    for lim in status["meta"]["limitations"]:
        st.markdown("- " + t("lim_" + lim["key"], **{k: v for k, v in lim.items() if k != "key"}))
    st.caption(t("versions") + ": " + ", ".join(f"{k} {v}" for k, v in status["meta"]["versions"].items() if v))

sections = ["sec_coverage", "sec_gapmap", "sec_explorer", "sec_study", "sec_new", "sec_check"]
sec = st.sidebar.radio(t("section"), sections, format_func=t)

# ------------------------------------------------------------------ coverage
if sec == "sec_coverage":
    st.header(t("sec_coverage"))
    st.caption(t("cov_intro"))
    df = pd.DataFrame(get("/coverage")["data"])
    cols = {"inv_id": "PSI", "acronym": "acronym", "project_type": "type", "psi_docs": t("cov_docs"),
            "psi_docs_with_text": t("cov_docs_text"), "psi_docs_blocked": t("cov_blocked"), "works": t("cov_works"),
            "works_full_text": t("cov_works_full"), "works_abstract": t("cov_works_abs"),
            "works_title_only": t("cov_works_title"), "exp_tables": t("cov_tables"), "mapping_status": t("cov_mapping"),
            "trials": t("cov_trials"), "text_units": t("cov_units"), "units_extracted": t("cov_extracted"),
            "findings_machine_verified": t("cov_mv"), "findings_scientifically_confirmed": t("cov_confirmed")}
    st.dataframe(df[list(cols)].rename(columns=cols), hide_index=True, width="stretch")
    st.caption(f"{t('cov_mapping')} draft = 🟠 {t('badge_draft')}")

# ------------------------------------------------------------------ gap map
elif sec == "sec_gapmap":
    st.header(t("sec_gapmap"))
    scen = get("/scenarios")["data"]
    names = {s["scenario_id"]: (s["name_es"] if lang == "es" else s["name_en"]) + (" ⚓" if s["anchor"] else "") for s in scen}
    sid = st.selectbox(t("gap_scenario"), list(names), format_func=names.get)
    s = next(x for x in scen if x["scenario_id"] == sid)
    c1, c2 = st.columns([1, 2])
    c1.metric(t("gap_scenario_status"), f"{s['status']}")
    c1.caption(f"🟠 {t('badge_provisional')} · {s['n_assumptions']} × {t('badge_assumption')}")
    with c2.expander(t("gap_sources")):
        st.json({"ranges": s["ranges"], "gravity_regime": s["gravity_regime"], "sources": s["sources"]})

    st.subheader(t("gap_summary"))
    summ = pd.DataFrame(get(f"/scenarios/{sid}/summary")["data"])
    st.dataframe(summ[["dimension", "n_in_range", "n_overlaps", "n_near", "n_outside", "n_unknown", "n_invs_in_or_near",
                       "all_mappings_approved"]], hide_index=True, width="stretch")
    st.caption(t("gap_status_legend") + f" · 🟠 {t('badge_draft')} · {t('tolerance_exploratory')}")
    unranged = [d for d in summ["dimension"] if s["ranges"].get(d) is None]
    if unranged:  # e.g. ISS: gravity is a regime with no numeric level, so its all-zero row is "not evaluated"
        st.caption("ℹ️ " + t("gap_dim_not_evaluated").format(dims=", ".join(unranged), regime=s["gravity_regime"]))

    st.subheader(t("gap_dims"))
    colors = alt.Scale(domain=["in_range", "overlaps", "near", "outside"],
                       range=["#2e7d32", "#f9a825", "#1e88e5", "#9e9e9e"])
    for dim, label in (("o2_pct", "O2 (%)"), ("pressure_kpa", "pressure (kPa)"), ("flow_cm_s", "flow (cm/s)")):
        dd = pd.DataFrame(get(f"/scenarios/{sid}/dimension/{dim}")["data"])
        rng = s["ranges"].get(dim)
        if dd.empty:
            st.caption(f"{label}: {t('gap_dim_none')}")
            continue
        dd["trial_max"] = dd.trial_max.fillna(dd.trial_min)
        ch = alt.Chart(dd).mark_rule(strokeWidth=3, opacity=0.6).encode(
            x=alt.X("trial_min:Q", title=label), x2="trial_max:Q", y=alt.Y("inv_id:N", title=None),
            color=alt.Color("status:N", scale=colors), tooltip=["inv_id", "trial_key", "row_grain", "trial_min",
                                                               "trial_max", "status", "verification_level"])
        pts = alt.Chart(dd).mark_tick(thickness=2).encode(x="trial_min:Q", y="inv_id:N",
                                                            color=alt.Color("status:N", scale=colors))
        layers = [ch, pts]
        if rng:
            band = pd.DataFrame([{"x": rng[0], "x2": rng[1]}])
            layers.insert(0, alt.Chart(band).mark_rect(opacity=0.15, color="#d32f2f").encode(x="x:Q", x2="x2:Q"))
        st.altair_chart(alt.layer(*layers).properties(height=28 * max(3, dd.inv_id.nunique())), width="stretch")
    st.subheader(t("gap_cut"))
    pts = pd.DataFrame(get(f"/scenarios/{sid}/points")["data"])
    known = pts[(pts.o2_status != "unknown") & (pts.p_status != "unknown")].copy()
    st.caption(t("gap_cut_missing", n=len(pts) - len(known)))
    if not known.empty:
        def combo(r):
            stt = {r.o2_status, r.p_status}
            if "outside" in stt:
                return "outside"
            if "overlaps" in stt:
                return "overlaps"
            if "near" in stt:
                return "near"
            return "in_range"
        known["status"] = known.apply(combo, axis=1)
        known["o2_mid"] = (known.o2_min + known.o2_max.fillna(known.o2_min)) / 2
        known["p_mid"] = (known.p_min + known.p_max.fillna(known.p_min)) / 2
        base = alt.Chart(known)
        bars_x = base.mark_rule(opacity=0.35).encode(x="o2_min:Q", x2="o2_max:Q", y="p_mid:Q", color="status:N")
        bars_y = base.mark_rule(opacity=0.35).encode(y="p_min:Q", y2="p_max:Q", x="o2_mid:Q", color="status:N")
        dots = base.mark_circle(size=60).encode(
            x=alt.X("o2_mid:Q", title="O2 (%)"), y=alt.Y("p_mid:Q", title="pressure (kPa)"),
            color=alt.Color("status:N", scale=alt.Scale(domain=["in_range", "overlaps", "near", "outside"],
                                                         range=["#2e7d32", "#f9a825", "#1e88e5", "#9e9e9e"])),
            tooltip=["inv_id", "trial_key", "row_grain", "o2_min", "o2_max", "p_min", "p_max", "o2_status", "p_status",
                     "verification_level", "gravity_context"])
        layers = [bars_x, bars_y, dots]
        r = s["ranges"]
        if r.get("o2_pct") and r.get("pressure_kpa"):
            box = pd.DataFrame([{"x": r["o2_pct"][0], "x2": r["o2_pct"][1], "y": r["pressure_kpa"][0],
                                 "y2": r["pressure_kpa"][1], "label": t("gap_box")}])
            layers.insert(0, alt.Chart(box).mark_rect(opacity=0.15, color="#d32f2f", stroke="#d32f2f").encode(
                x="x:Q", x2="x2:Q", y="y:Q", y2="y2:Q", tooltip=["label"]))
        st.altair_chart(alt.layer(*layers).interactive(), width="stretch")

    st.subheader(t("gap_families"))
    gaps = get(f"/scenarios/{sid}/gaps")["data"]
    for fam in ("scientific_possible", "not_assessable", "source_structure", "system"):
        g = [x for x in gaps if x["gap_family"] == fam]
        with st.expander(f"{t('fam_' + fam)} ({len(g)})", expanded=fam in ("scientific_possible", "not_assessable")):
            if fam == "scientific_possible":
                st.caption(t("gap_scientific_note"))
            if not g:
                st.write(t("fam_none"))
            else:
                st.dataframe(pd.DataFrame([{"class": x["gap_class"], "inv": x["inv_id"], "dimension": x["dimension"],
                                            "provisional": x["provisional"], "cause": x["cause"],
                                            "evidence": json.dumps(x["evidence"])[:300]} for x in g]),
                             hide_index=True, width="stretch")
    st.subheader(t("gap_declared"))
    decl = get("/findings", (("claim_type", "limitation"),))["data"] + get("/findings", (("claim_type", "future_work"),))["data"]
    st.caption("⚠️ " + t("gap_declared_note", n=len(decl)))
    if decl:
        st.dataframe(pd.DataFrame([{"inv": ", ".join(d["inv_ids"]), "type": d["claim_type"], "claim": shown(d["claim"]),
                                    "status": badge(d["display_status"])} for d in decl]),
                     hide_index=True, width="stretch")

# ------------------------------------------------------------------ explorer
elif sec == "sec_explorer":
    st.header(t("sec_explorer"))
    invs = [c["inv_id"] for c in get("/coverage")["data"]]
    c1, c2, c3, c4 = st.columns(4)
    inv = c1.selectbox(t("exp_inv"), [""] + invs, format_func=lambda x: x or t("exp_any"))
    ctype = c2.selectbox(t("exp_type"), ["", "result", "limitation", "future_work"], format_func=lambda x: x or t("exp_any"))
    q = c3.text_input(t("exp_text"))
    hist = c4.checkbox(t("exp_history"))
    params = tuple((k, v) for k, v in (("inv", inv), ("claim_type", ctype), ("q", q),
                                       ("include_history", str(hist).lower())) if v)
    fs = get("/findings", params)["data"]
    if not fs:
        st.info(t("exp_none"))
    else:
        df = pd.DataFrame([{"finding_id": f["finding_id"], "inv": ", ".join(f["inv_ids"]), "type": f["claim_type"],
                            "claim": f["claim"] if f["claim"] is not None else t("claim_withheld_nd"),
                            "status": badge(f["display_status"]),
                            "attribution": f.get("attribution"), "prompt": f.get("prompt_version"),
                            "active": f["active"]} for f in fs])
        st.dataframe(df, hide_index=True, width="stretch")
        if len(fs) >= 500:  # API default limit: say so instead of silently truncating
            st.caption(t("exp_truncated", n=len(fs)))
        fid = st.selectbox(t("exp_select"), df.finding_id.tolist())
        d = get(f"/findings/{fid}")["data"]
        src = d.get("source") or {}
        claim = d["claim"] if d["claim"] is not None and src.get("show_claim", True) else t("claim_withheld_nd")
        st.markdown(f"**{claim}**  \n{badge(d['display_status'])} · `{d['claim_type']}` · {', '.join(d['inv_ids'])}")
        st.markdown(f"**{t('exp_quote')}** ({t('exp_page')} {d.get('page_no')}):")
        st.info(d.get("claim_quote") or "")
        # attribution of the source (title, authors, licence, DOI/link) + review status, always shown with the quote
        lines = [f"**{t('src_title')}:** {src.get('title') or d['doc_id']}",
                 f"**{t('src_authors')}:** {src.get('authors') or src.get('publisher_context') or t('src_not_recorded')}",
                 f"**{t('src_license')}:** {src.get('license_label') or t('src_not_recorded')}",
                 f"**{t('src_link')}:** {src.get('link') or t('src_not_recorded')}",
                 f"**{t('src_review')}:** {badge(d['display_status'])}"]
        st.caption("  \n".join(lines))
        if src.get("pub_class") == "public_no_derivatives":
            st.caption(t("src_nd_note"))
        with st.expander(t("exp_checks")):
            st.dataframe(pd.DataFrame(d["checks"]), hide_index=True, width="stretch")
        with st.expander(f"{t('exp_relations')} ({len(d['relations'])})"):
            st.dataframe(pd.DataFrame(d["relations"]), hide_index=True, width="stretch")
            if d.get("related_topic_hidden"):
                st.caption(t("related_topic_hidden", n=d["related_topic_hidden"]))

# ------------------------------------------------------------------ study + contrast
elif sec == "sec_study":
    st.header(t("sec_study"))
    invs = [c["inv_id"] for c in get("/coverage")["data"]]
    inv = st.selectbox(t("study_pick"), invs)
    sd = get(f"/investigations/{inv}/study")["data"]
    st.subheader(t("study_own"))
    if sd["findings"]:
        st.dataframe(pd.DataFrame([{"type": f["claim_type"], "claim": shown(f["claim"]), "page": f.get("page_no"),
                                    "status": badge(f["display_status"])} for f in sd["findings"]]),
                     hide_index=True, width="stretch")
    st.subheader(t("study_contrast"))
    st.caption(t("study_contrast_note"))
    if not sd["contrast"]:
        st.write(t("study_none"))
    else:
        st.dataframe(pd.DataFrame([{"relation": c["relation_type"] + ("" if c["is_scientific_relation"] else " (exploratory)"),
                                    "status": c["display_status"], "independence": c["independence"],
                                    "other_inv": ", ".join(c["other_inv_ids"]), "other_claim": shown(c["other_claim"]),
                                    "similarity": c["similarity"]} for c in sd["contrast"]]),
                     hide_index=True, width="stretch")
    if sd.get("related_topic_hidden"):
        st.caption(t("related_topic_hidden", n=sd["related_topic_hidden"]))

# ------------------------------------------------------------------ what's new
elif sec == "sec_new":
    st.header(t("sec_new"))
    wn = get("/whats-new")["data"]
    st.subheader(t("new_runs"))
    st.dataframe(pd.DataFrame(wn["runs"]), hide_index=True, width="stretch")
    st.subheader(t("new_singular"))
    sg = wn.get("singularity") or {}
    if not sg.get("calibrated", False):
        st.warning(t("new_singular_uncalibrated", tau=sg.get("tau"), n=sg.get("n_flagged", 0)))
    if wn["singular_candidates"]:
        st.dataframe(pd.DataFrame([{"claim": shown(s["claim"]), "inv": ", ".join(s["inv_ids"]), "rarity": s["rarity"],
                                    "status": badge(s["display_status"])} for s in wn["singular_candidates"]]),
                     hide_index=True, width="stretch")

# ------------------------------------------------------------------ consistency
else:
    st.header(t("sec_check"))
    chk = get("/check")["data"]
    (st.success if chk["ok"] else st.error)(t("check_ok") if chk["ok"] else t("check_fail"))
    st.dataframe(pd.DataFrame(chk["checks"]), hide_index=True, width="stretch")
    st.json(status["data"])
