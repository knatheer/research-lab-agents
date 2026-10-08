# Data dictionary: nitrogrow_trial

Field trial of the NitroGrow biostimulant fertilizer on winter wheat, 4 farms, 2025 season.
Each row is one experimental plot. Plots were randomized to `control` or `nitrogrow` within each farm.

| Column | Type | Unit | Description |
|---|---|---|---|
| plot_id | string | | Unique plot identifier (P001 to P120). Must be unique. |
| site | category | | Farm name: North Farm, River Farm, Hill Farm, Coast Farm |
| treatment | category | | `control` (standard fertilizer) or `nitrogrow` (standard + NitroGrow) |
| yield_t_ha | float | tonnes per hectare | Grain yield at harvest. Plausible range for wheat: 0 to 15 t/ha. |
| soil_ph | float | pH | Soil pH measured at sowing |
| rainfall_mm | int | mm | Season rainfall at the plot's weather station |
| recorded_by | string | | Field technician ID who entered the row |

Note: the dataset is synthetic and was generated for teaching.
