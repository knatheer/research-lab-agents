"""Lab 2 solution: the full "Lab Instruments" MCP server.

Tools      : list_datasets, describe_dataset, compare_groups, summarize_by,
             check_data_quality, clean_dataset, plot_groups
Resources  : lab://protocol, lab://datasets/{dataset}/dictionary
Prompts    : analysis_plan, manuscript_draft

Run it in the MCP Inspector:  uv run mcp dev solutions/lab02/instruments_server.py
"""

import math
from typing import Any

import numpy as np
import pandas as pd
from mcp.server import MCPServer
from scipy import stats

from common.config import DATA_DIR, WORKSPACE_DIR

mcp = MCPServer(
    "Lab Instruments",
    instructions="Statistical instruments for the NitroGrow wheat trial. Start with list_datasets.",
)


# ---------------------------------------------------------------- helpers
def _path(dataset: str):
    for folder in (DATA_DIR, WORKSPACE_DIR):
        p = folder / f"{dataset}.csv"
        if p.exists():
            return p
    raise ValueError(f"Unknown dataset '{dataset}'. Call list_datasets to see what exists.")


def _load(dataset: str) -> pd.DataFrame:
    return pd.read_csv(_path(dataset), encoding="utf-8")


def _r(x: float, nd: int = 4) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


# ---------------------------------------------------------------- Lab 1 tools
@mcp.tool()
def list_datasets() -> list[dict]:
    """List all datasets available to the lab (raw data and cleaned copies)."""
    out = []
    for folder, kind in ((DATA_DIR, "raw"), (WORKSPACE_DIR, "derived")):
        for p in sorted(folder.glob("*.csv")):
            out.append({"name": p.stem, "kind": kind, "rows": int(len(pd.read_csv(p)))})
    return out


@mcp.tool()
def describe_dataset(dataset: str) -> dict[str, Any]:
    """Describe a dataset: row count, columns, missing values, and basic statistics."""
    df = _load(dataset)
    cols = {}
    for c in df.columns:
        s = df[c]
        info = {"dtype": str(s.dtype), "missing": int(s.isna().sum())}
        if pd.api.types.is_numeric_dtype(s):
            info |= {"mean": _r(s.mean()), "sd": _r(s.std()), "min": _r(s.min()), "max": _r(s.max())}
        else:
            info["levels"] = sorted(map(str, s.dropna().unique()))[:12]
        cols[c] = info
    return {"dataset": dataset, "rows": int(len(df)), "columns": cols}


@mcp.tool()
def compare_groups(
    dataset: str,
    value_col: str = "yield_t_ha",
    group_col: str = "treatment",
    group_a: str = "nitrogrow",
    group_b: str = "control",
) -> dict[str, Any]:
    """Welch two-sample t-test of value_col between group_a and group_b.

    Returns n, means, mean difference (a - b) with 95% CI, t, p-value and Cohen's d.
    Rows with a missing value are ignored.
    """
    df = _load(dataset)
    a = df.loc[df[group_col] == group_a, value_col].dropna()
    b = df.loc[df[group_col] == group_b, value_col].dropna()
    if len(a) < 2 or len(b) < 2:
        raise ValueError("Each group needs at least 2 non-missing values.")
    res = stats.ttest_ind(a, b, equal_var=False)
    ci = res.confidence_interval(0.95)
    pooled_sd = math.sqrt((a.var() + b.var()) / 2)
    return {
        "dataset": dataset,
        "test": "Welch two-sample t-test (two-sided)",
        "value_col": value_col,
        "n_a": int(len(a)),
        "n_b": int(len(b)),
        "mean_a": _r(a.mean()),
        "mean_b": _r(b.mean()),
        "mean_diff": _r(a.mean() - b.mean()),
        "ci95_low": _r(ci.low),
        "ci95_high": _r(ci.high),
        "t": _r(res.statistic),
        "df": _r(res.df, 1),
        "p_value": _r(res.pvalue, 6),
        "cohens_d": _r((a.mean() - b.mean()) / pooled_sd if pooled_sd else float("nan"), 3),
        "groups": f"{group_a} vs {group_b}",
    }


# ---------------------------------------------------------------- Lab 2 tools
@mcp.tool()
def summarize_by(dataset: str, by: list[str], value_col: str = "yield_t_ha") -> list[dict]:
    """Mean, SD and count of value_col for every combination of the 'by' columns (e.g. ["site", "treatment"])."""
    df = _load(dataset)
    g = df.groupby(by)[value_col].agg(["count", "mean", "std"]).reset_index()
    return [{k: (_r(v) if isinstance(v, float) else v) for k, v in row.items()} for row in g.to_dict("records")]


@mcp.tool()
def check_data_quality(
    dataset: str, id_col: str = "plot_id", value_col: str = "yield_t_ha", plausible_max: float = 15.0
) -> dict[str, Any]:
    """Audit a dataset for duplicate IDs, missing outcomes and implausible values.

    Returns the offending IDs so they can be passed to clean_dataset.
    """
    df = _load(dataset)
    dup_ids = sorted(df.loc[df[id_col].duplicated(), id_col].astype(str).unique())
    missing_ids = sorted(df.loc[df[value_col].isna(), id_col].astype(str))
    bad = df[(df[value_col] < 0) | (df[value_col] > plausible_max)]
    implausible = [{"id": str(r[id_col]), "value": float(r[value_col])} for _, r in bad.iterrows()]
    n_issues = len(dup_ids) + len(missing_ids) + len(implausible)
    return {
        "dataset": dataset,
        "rows": int(len(df)),
        "duplicate_ids": dup_ids,
        "duplicate_rows_extra": int(df[id_col].duplicated().sum()),
        "missing_outcome_ids": missing_ids,
        "implausible_values": implausible,
        "plausible_range": [0, plausible_max],
        "clean": n_issues == 0,
    }


@mcp.tool()
def clean_dataset(
    dataset: str,
    drop_duplicates: bool = True,
    drop_missing: bool = True,
    drop_ids: list[str] | None = None,
    id_col: str = "plot_id",
    value_col: str = "yield_t_ha",
) -> dict[str, Any]:
    """Create a cleaned copy named '<dataset>_clean'. Never modifies the original.

    drop_duplicates keeps the first row per ID. drop_ids removes specific IDs
    (for example the implausible ones reported by check_data_quality).
    """
    df = _load(dataset)
    log = {"rows_before": int(len(df))}
    if drop_duplicates:
        before = len(df)
        df = df.drop_duplicates(subset=[id_col], keep="first")
        log["removed_duplicates"] = int(before - len(df))
    if drop_missing:
        before = len(df)
        df = df.dropna(subset=[value_col])
        log["removed_missing"] = int(before - len(df))
    if drop_ids:
        before = len(df)
        df = df[~df[id_col].astype(str).isin(drop_ids)]
        log["removed_by_id"] = int(before - len(df))
    name = dataset if dataset.endswith("_clean") else f"{dataset}_clean"
    df.to_csv(WORKSPACE_DIR / f"{name}.csv", index=False, encoding="utf-8")
    log |= {"rows_after": int(len(df)), "new_dataset": name}
    return log


@mcp.tool()
def plot_groups(dataset: str, value_col: str = "yield_t_ha", group_col: str = "treatment") -> str:
    """Save a box plot of value_col by group_col as PNG. Returns the file path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = _load(dataset)
    groups = sorted(df[group_col].dropna().unique())
    data = [df.loc[df[group_col] == g, value_col].dropna() for g in groups]
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.boxplot(data, tick_labels=groups)
    for i, d in enumerate(data, start=1):
        ax.scatter(np.full(len(d), i) + np.random.uniform(-0.08, 0.08, len(d)), d, s=8, alpha=0.6)
    ax.set_ylabel(value_col)
    ax.set_title(f"{value_col} by {group_col} ({dataset})")
    out = WORKSPACE_DIR / f"{dataset}_{value_col}_by_{group_col}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return str(out)


# ---------------------------------------------------------------- resources
@mcp.resource("lab://protocol", mime_type="text/markdown")
def protocol() -> str:
    """The pre-registered study protocol: hypothesis, primary analysis, exclusion rules."""
    return (DATA_DIR / "study_protocol.md").read_text(encoding="utf-8")


@mcp.resource("lab://datasets/{dataset}/dictionary", mime_type="text/markdown")
def dictionary(dataset: str) -> str:
    """Column definitions and units for a dataset."""
    base = dataset.removesuffix("_clean")
    p = DATA_DIR / "data_dictionary.md"
    if base != "nitrogrow_trial":
        return f"No data dictionary for {dataset}."
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- prompts
@mcp.prompt()
def analysis_plan(dataset: str = "nitrogrow_trial") -> str:
    """Ask the model to plan and run the pre-registered analysis."""
    return (
        f"You are analysing the dataset '{dataset}'. First read the protocol (resource lab://protocol). "
        "Then: 1) describe the dataset, 2) check data quality, 3) apply the protocol's exclusion rules "
        "with clean_dataset, 4) run the primary analysis with compare_groups on the cleaned data, "
        "5) run summarize_by on site and treatment. Report every exclusion with counts."
    )


@mcp.prompt()
def manuscript_draft(results_json: str, verification_json: str = "{}", related_work: str = "") -> str:
    """Instructions for drafting an IMRaD manuscript from verified results."""
    return f"""Write a short research manuscript in Markdown (600 to 900 words) with these sections:
# <Title>
## Abstract
## Introduction   (cite related work as [LIB-xxx])
## Methods        (design, protocol exclusions WITH counts, Welch t-test)
## Results        (n per group, means, mean difference with 95% CI, t, p, Cohen's d)
## Discussion     (compare with prior work, practical meaning, limitations)
## References     (list every [LIB-xxx] you cited)

Only report numbers that appear in the results below. Do not invent data.

VERIFIED RESULTS:
{results_json}

VERIFICATION REPORT:
{verification_json}

RELATED WORK NOTES:
{related_work}
"""


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
