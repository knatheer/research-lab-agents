"""Generate the synthetic NitroGrow wheat trial dataset.

Instructor-only. The CSV in data/ was produced by this script with the seed below,
so every student gets identical numbers. Re-running it reproduces the same file.

Ground truth (do not show students before Lab 6):
  * True treatment effect: +0.30 t/ha
  * Planted problems:
      - 5 yields at Coast Farm entered in kg/ha instead of t/ha (values ~3000+)
      - 4 duplicated rows (same plot_id entered twice)
      - 2 missing yields
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 7
ROOT = Path(__file__).resolve().parents[1]

SITES = {
    "North Farm": {"base": 3.4, "rain": 520},
    "River Farm": {"base": 3.1, "rain": 610},
    "Hill Farm": {"base": 2.8, "rain": 450},
    "Coast Farm": {"base": 3.2, "rain": 580},
}
TRUE_EFFECT = 0.30
SD = 0.45
PLOTS_PER_ARM = 15


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows = []
    tech_ids = ["tech_01", "tech_03", "tech_04", "tech_07"]
    for s_idx, (site, p) in enumerate(SITES.items()):
        for arm in ("control", "nitrogrow"):
            for k in range(PLOTS_PER_ARM):
                plot_no = len(rows) + 1
                ph = round(float(rng.normal(6.5, 0.35)), 2)
                rain = int(rng.normal(p["rain"], 25))
                y = p["base"] + (TRUE_EFFECT if arm == "nitrogrow" else 0.0)
                y += 0.15 * (ph - 6.5) + rng.normal(0, SD)
                rows.append(
                    {
                        "plot_id": f"P{plot_no:03d}",
                        "site": site,
                        "treatment": arm,
                        "yield_t_ha": round(float(y), 2),
                        "soil_ph": ph,
                        "rainfall_mm": rain,
                        "recorded_by": tech_ids[s_idx],
                    }
                )
    df = pd.DataFrame(rows)

    # Problem 1: unit error at Coast Farm (kg/ha instead of t/ha) on 5 treated plots.
    coast_treated = df[(df.site == "Coast Farm") & (df.treatment == "nitrogrow")].index[:5]
    df.loc[coast_treated, "yield_t_ha"] = (df.loc[coast_treated, "yield_t_ha"] * 1000).round(0)

    # Problem 2: two missing yields in the control arm.
    missing = df[(df.site == "River Farm") & (df.treatment == "control")].index[[2, 9]]
    df.loc[missing, "yield_t_ha"] = np.nan

    # Problem 3: four duplicated rows (re-entered plots), all in the treatment arm.
    dup_src = df[(df.treatment == "nitrogrow") & (df.site.isin(["North Farm", "Hill Farm"]))]
    dups = dup_src.sample(4, random_state=SEED)
    df = pd.concat([df, dups], ignore_index=True)

    # Shuffle so problems are not at the bottom of the file.
    df = df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)

    out = ROOT / "data" / "nitrogrow_trial.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"Wrote {len(df)} rows to {out}")


if __name__ == "__main__":
    main()
