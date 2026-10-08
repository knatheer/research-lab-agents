# Study protocol (pre-registered): NitroGrow wheat trial

**Hypothesis H1.** Plots treated with NitroGrow have a higher mean grain yield (yield_t_ha) than control plots.

**Primary outcome.** yield_t_ha.

**Primary analysis.** Welch two-sample t-test comparing `nitrogrow` vs `control`, two-sided, alpha = 0.05.
Report: n per group, group means, mean difference with 95% confidence interval, t, p-value, and Cohen's d.

**Pre-registered exclusion rules (apply BEFORE the primary analysis):**
1. Duplicate plot_id rows: keep the first occurrence, drop the rest.
2. Rows with a missing primary outcome are excluded.
3. Implausible yields (below 0 or above 15 t/ha) are excluded as data-entry errors.

All exclusions must be reported in the manuscript with counts.

**Secondary analysis.** Mean yield by site and treatment.
