"""Lab 1 solution: your first MCP server, "Lab Instruments" v1.

Three tools: list_datasets, describe_dataset, compare_groups.

Try it:  uv run mcp dev solutions/lab01/instruments_server.py
"""

import math
from typing import Any

import pandas as pd
from mcp.server import MCPServer
from scipy import stats

from common.config import DATA_DIR, WORKSPACE_DIR

mcp = MCPServer("Lab Instruments")


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



if __name__ == "__main__":
    mcp.run()
