# edgar/core/db/report.py

import pandas as pd
from typing import Any

# Local

from edgar import db


def _select_facts_from_role(conn, access_nos: list[str], role: str) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in access_nos)
    query = f"""
        SELECT f.fid, f.access_no, f.cid, f.xid, f.unid, f.value
        FROM facts f
        JOIN contexts ctx ON f.xid = ctx.xid
        JOIN fact_roles fr ON fr.fid = f.fid
        WHERE f.access_no IN ({placeholders}) AND fr.role = ?
    """
    facts = db.store.select(conn, query, (*access_nos, role))
    return pd.DataFrame(facts)


def _merge_facts_with_dei(conn, facts: pd.DataFrame) -> pd.DataFrame:
    if facts.empty:
        return facts
    access_nos = tuple(facts["access_no"].unique())
    query = f"""
        SELECT access_no, fiscal_year, fiscal_period
        FROM dei
        WHERE access_no IN ({','.join(['?'] * len(access_nos))})
    """
    meta = pd.DataFrame(db.store.select(conn, query, access_nos))
    return pd.merge(facts, meta, on="access_no", how="left")


def _add_dimension(conn, facts: pd.DataFrame) -> pd.DataFrame:
    dims = db.store.select(conn, """
        SELECT fid, GROUP_CONCAT(dimension || '=' || member, '|') AS dimension
        FROM dimensions
        GROUP BY fid
    """)
    dims_df = pd.DataFrame(dims)
    if dims_df.empty:
        facts["dimension"] = "default"
        return facts
    facts["fid"] = facts["fid"].astype(int)
    dims_df["fid"] = dims_df["fid"].astype(int)
    facts = pd.merge(facts, dims_df, on="fid", how="left")
    facts["dimension"].fillna("default", inplace=True)
    return facts


def _derive_missing_quarters(df: pd.DataFrame) -> pd.DataFrame:
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    groups = df.groupby(["unid", "dimension", "fiscal_year"])
    derived = []

    for _, group in groups:
        if "Q4" in group.fiscal_period.values:
            continue
        if "FY" not in group.fiscal_period.values:
            continue

        fy = group[group.fiscal_period == "FY"]

        if group["mode"].eq("instant").all():
            derived.append(_copy_fy_as_q4(fy))
        elif _has_ytd_q3(group):
            derived.append(_subtract_ytd_q3_from_fy(fy, group))
        elif _has_all_quarters(group):
            derived.append(_subtract_q1_q2_q3_from_fy(fy, group))

    derived = [x.dropna(axis=1, how="all") for x in derived if not x.empty]
    if not derived:
        return df

    q4 = pd.concat(derived, ignore_index=True)
    return pd.concat([df, q4], ignore_index=True)


def _copy_fy_as_q4(fy: pd.DataFrame) -> pd.DataFrame:
    q4 = fy.copy()
    q4["fiscal_period"] = "Q4"
    return q4


def _has_ytd_q3(group: pd.DataFrame) -> bool:
    return any((group.fiscal_period == "Q3") & (group["mode"] == "threeQ"))


def _has_all_quarters(group: pd.DataFrame) -> bool:
    quarters = group[group["mode"] == "quarter"].fiscal_period.tolist()
    return all(q in quarters for q in ["Q1", "Q2", "Q3"])


def _subtract_ytd_q3_from_fy(fy: pd.DataFrame, group: pd.DataFrame) -> pd.DataFrame:
    q3 = group[(group.fiscal_period == "Q3") & (group["mode"] == "threeQ")]
    if q3.empty:
        return pd.DataFrame()
    q4 = fy.copy()
    q4["fiscal_period"] = "Q4"

    for col in fy.columns:
        if col not in ("fiscal_year", "fiscal_period", "mode", "unid", "dimension"):
            fy_val = fy[col].values[0]
            q3_val = q3[col].values[0]
            q4[col] = fy_val - q3_val if pd.notna(fy_val) and pd.notna(q3_val) else pd.NA

    q4["mode"] = "quarter"
    return q4


def _subtract_q1_q2_q3_from_fy(fy: pd.DataFrame, group: pd.DataFrame) -> pd.DataFrame:
    qs = {q: group[(group.fiscal_period == q) & (group["mode"] == "quarter")] for q in ["Q1", "Q2", "Q3"]}
    if not all(len(qs[q]) == 1 for q in qs):
        return pd.DataFrame()

    q4 = fy.copy()
    q4["fiscal_period"] = "Q4"

    for col in fy.columns:
        if col not in ("fiscal_year", "fiscal_period", "mode", "unid", "dimension"):
            val = fy[col].values[0]
            try:
                for q in ["Q1", "Q2", "Q3"]:
                    q_val = qs[q][col].values[0]
                    if pd.notna(val) and pd.notna(q_val):
                        val -= q_val
                    else:
                        val = pd.NA
                        break
                q4[col] = val
            except Exception:
                q4[col] = pd.NA

    q4["mode"] = "quarter"
    return q4


def report_by_quarter(conn, cik: str, access_nos: list[str], role: str, after: str | None = None, before: str | None = None) -> pd.DataFrame:
    facts = _select_facts_from_role(conn, access_nos, role)
    if facts.empty:
        raise ValueError(f"No facts found for role: {role}")

    facts = _merge_facts_with_dei(conn, facts)
    facts = _add_dimension(conn, facts)

    index = ["unid", "fiscal_year", "fiscal_period", "mode", "dimension"]
    df = facts.pivot_table(index=index, columns="cid", values="value", aggfunc="first")

    df.reset_index(inplace=True)
    df = _derive_missing_quarters(df)

    period_order = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}
    df["fiscal_period_order"] = df["fiscal_period"].map(period_order).fillna(99)
    df = df.sort_values(by=["fiscal_year", "fiscal_period_order"]).drop(columns="fiscal_period_order")
    df["fiscal_label"] = df.fiscal_year.astype(str).str[2:] + "-" + df.fiscal_period
    df["pos"] = range(len(df))

    df = db.store.filter_by_period(df, after, before)

    return df
