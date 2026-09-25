# Subnational data for the Philippines

This note describes how data is prepared for the Philippines (`PHL`)
and its three grids, Luzon (`PHL_LU`), Visayas (`PHL_VI`) and Mindanao
(`PHL_MI`), and how it is used in the model. It covers:

- [Population](#population)
- [Annual electricity demand per capita](#annual-electricity-demand-per-capita)

The grid shapes are built in [`shapes/ngcp.py`](../shapes/ngcp.py) by
grouping PSA administrative regions by whole region: NCR, CAR and
Regions I–V (including MIMAROPA, so Palawan and Mindoro, and Masbate in
Bicol) go to Luzon; Regions VI, VII, VIII and the Negros Island Region
to Visayas; and Regions IX–XIII and BARMM to Mindanao.

## Population

The variable is stored as **Population**. It is produced by
[`population.py`](population.py). The national total comes from the
World Bank (historical) or IIASA (future), and it is split between the
grids using census shares from the Philippine Statistics Authority
(PSA).

### Source

| Source | Module | Coverage | What is used |
|---|---|---|---|
| World Bank | [`world_bank.py`](socio_economic_data_sources/world_bank.py) | 1960–latest | National population |
| IIASA (SSP scenarios) | [`iiasa.py`](socio_economic_data_sources/iiasa.py) | Projections | National population, for future years |
| PSA census | [`psa_philippines.py`](socio_economic_data_sources/psa_philippines.py) | 2000, 2010, 2015, 2020, 2024 | Population of each administrative region |

The census counts are in the `Regional_Census` sheet of
[`manual_downloads/Philippines_Population_Luzon_Visayas_Mindanao_2000-2024.xlsx`](socio_economic_data_sources/manual_downloads/Philippines_Population_Luzon_Visayas_Mindanao_2000-2024.xlsx),
transcribed from PSA publications (source links are in the sheet). The
regions are added up by the sheet's `Island group` column. Each census
counts as the value of its year, regardless of its reference date (for
example, 1 August 2015 or 1 July 2024).

Boundary changes between 2020 and 2024 happen within a single grid: the
Negros Island Region was formed from Regions VI and VII (both Visayas),
and Cotabato City moved from Region XII to BARMM (both Mindanao). Grid
totals are therefore comparable across all census years.

### Method

```
share(grid, census year) = census population(grid) / census population(all three grids)
population(grid, year)   = share(grid, year) × national population(PHL, year)
```

- **Between census years**, the shares are linearly interpolated.
- **Before 2000**, the 2000 shares are used.
- **After 2024**, including all future years, the 2024 shares are used.
  The recent trend is not projected forward, because small changes in
  the shares would build up over decades.
- The national population is the World Bank value for historical years
  (held at the last available year if a later year is requested) and
  the IIASA value for the selected SSP scenario in future years.

Because only the shares come from the census, the three grids always
add up exactly to the national population used by the rest of the
model.

Current census shares:

| Grid | 2000 | 2010 | 2015 | 2020 | 2024 |
|---|---|---|---|---|---|
| Luzon | 56.0% | 56.7% | 56.9% | 57.0% | 56.9% |
| Visayas | 20.3% | 19.5% | 19.2% | 18.9% | 18.7% |
| Mindanao | 23.7% | 23.8% | 23.9% | 24.1% | 24.4% |

### Why census shares instead of gridded shares

Other subdivisions in the model split the national population using
their share of the gridded population. That approach had two problems
for the Philippines:

- **The gridded data ends in 2020**, so the shares were fixed at their
  2020 values for all later years.
- **It does not match the census.** In 2020 it gave Luzon 59.7%,
  Visayas 16.4% and Mindanao 23.3%. Visayas was about 2.5 percentage
  points (roughly 13%) below the census.

The census shares are used only for the codes in
`psa_philippines.get_codes()`. Other subdivisions still use gridded
shares.

### Where population is used

- It is the denominator of the grid **annual electricity demand per
  capita** (below).
- It is one of the **scaling variables** that convert predicted load
  fractions into MW (see [How the model uses it](#how-the-model-uses-it)).
- The GDP PPP per capita of the grids does **not** use it yet. The ratio
  between each grid and the country in
  [`gdp_ppp_per_capita.py`](gdp_ppp_per_capita.py) is still based on
  gridded GDP divided by gridded population.

## Annual electricity demand per capita

The variable is stored as **Annual electricity demand per capita
(kWh)**. It is produced by
[`annual_electricity_demand_per_capita.py`](annual_electricity_demand_per_capita.py).

### Sources

| Source | Module | Coverage for PHL | What is used |
|---|---|---|---|
| Ember | [`ember.py`](socio_economic_data_sources/ember.py) | 2000–2025 | Electricity demand per capita (generation plus net imports) |
| World Bank | [`world_bank.py`](socio_economic_data_sources/world_bank.py) | 1990–2023 | Electric power consumption per capita |
| DOE Philippines | [`doe_philippines.py`](socio_economic_data_sources/doe_philippines.py) | 2003–2025 | Gross Power Generation per Grid in GWh |
| IIASA (IAMC scenarios) | [`iiasa.py`](socio_economic_data_sources/iiasa.py) | Projections | Annual growth rates of electricity demand per capita, for future years |

The DOE data comes from the table "Gross Power Generation per Grid in
GWh" in the
[2025 Power Statistics summary](https://prod-cms.doe.gov.ph/documents/d/guest/annex-1_summary-electric-consumption-system-demand-gross-generation-installed-and-dependable-capacity-2003-2025-pdf)
PDF (Annex 1). The PDF is downloaded and parsed on every run. The
Luzon, Visayas and Mindanao rows are read, along with the "Total Gross
Generation" row, which is read but not currently used. Values are
converted from GWh to MWh.

### Historical data

#### National (`PHL`)

The national series comes from `get_historical_data()`: the average of
Ember and the World Bank, or whichever one is available.

| Years | Value |
|---|---|
| 1990–1999 | World Bank only |
| 2000–2023 | Average of World Bank and Ember |
| 2024–2025 | Ember only |

DOE data is **not** used for national `PHL`.

#### Grids (`PHL_LU`, `PHL_VI`, `PHL_MI`)

The grids are listed by `get_regional_codes()`. Their series combines
DOE data with a scaled version of the national series.

**2003–2025 (DOE):**

```
demand per capita (kWh) = DOE gross generation of the grid (MWh) × 1000
                          / population of the grid
```

The grid population comes from `retrievals.population.get_historical_population()`,
using the census shares described in [Population](#population).

**Before 2003 (scaled national):** the national value is multiplied by
the ratio between the grid and the country in the first DOE year, so
that the series has no break in 2003:

```
ratio(grid)            = DOE-based value(grid, 2003) / national value(PHL, 2003)
value(grid, year<2003) = national value(PHL, year) × ratio(grid)
```

With the current data, the ratios are about 1.34 for Luzon, 0.89 for
Visayas and 0.56 for Mindanao. The grids therefore follow the national
trend before 2003, at their own levels.

#### Output

Yearly values are expanded to an hourly series in the local time zone
(`utils.time_series.convert_from_yearly_to_hourly`): every hour of a
year holds that year's value. The series is saved as
`data/annual_electricity_demand_per_capita/<date>/<code>.csv` and `.parquet`.

### Future data

For future years, the IIASA growth rates for `PHL` (under the chosen
SSP scenario) are applied to the last historical value of each entity
(`iiasa.extrapolate`). The grids use the national growth rates but
start from their own 2025 DOE-based value. Output files are named
`<code>_<scenario>.csv`, for example `PHL_LU_SSP2_Baseline.csv`.

### How the model uses it

The variable is used in two places.

1. **As a feature.** `assemble.py` merges it with GDP PPP per capita,
   population, temperature and, for training, hourly load, joined on
   `Time (UTC)` and `Entity code`. It is one of the XGBoost features
   listed in [`config/ml_config.yaml`](../config/ml_config.yaml). The
   model is trained to predict the **hourly load as a fraction of the
   annual total** (`Load (fraction of annual total)`), so this feature
   helps it learn how the shape of the load profile changes with the
   level of demand.

2. **To scale predictions to MW.** In `forecast.py`, the predicted
   hourly fractions are first normalized so that each year sums to 1.
   They are then multiplied by the scaling variables in
   `ml_config.yaml`:

   ```
   load (MW) = fraction × annual electricity demand per capita (kWh)
               × population / 1000
   ```

   The annual demand per capita therefore sets the **total annual
   energy** of the forecast, and the model sets **how it is spread
   across the hours**. Errors in this variable carry straight into the
   forecast level.

## Running the retrieval

In [`config/retrieve_config.yaml`](../config/retrieve_config.yaml), set
the variable and the grids:

```yaml
variable: population   # then annual_electricity_demand_per_capita
file: "config/target_subnationals_config.yaml"   # PHL_LU, PHL_VI, PHL_MI
start_year: 2003
end_year: 2025
```

Then run, once per variable:

```bash
uv run retrieve.py
```

The annual electricity demand retrieval computes grid population
itself, through `get_historical_population()`, so the two variables
can be retrieved in either order.

Files that already exist in the dated output folder are skipped. Delete
them, or run on a new date, to regenerate them after changing the
sources or the method. This includes the `_<scenario>` files, because
future values are built from the last historical value.

## Known limitations

- **Generation is not the same as demand per grid.** DOE gross
  generation is measured where power is generated, not where it is
  used. Power flows between grids, over the Leyte–Luzon HVDC link and,
  since 2024, the Mindanao–Visayas interconnection, so a grid's
  generation can differ from its demand. In 2024, Visayas generation
  fell by 11% and Mindanao's rose by 24%, which is likely Mindanao
  exporting to Visayas. As a result, 2024–2025 values are probably too
  low for Visayas and too high for Mindanao.
- **National and grid values use different definitions.** From 2003,
  the grids follow DOE gross generation, which includes own use and
  system losses. National `PHL` follows the Ember/World Bank average.
  The population-weighted grid values do not add up to the national
  value.
- **The national series changes source twice**, in 2000 and 2024 (see
  the table above), which can shift its level.
- **Off-grid generation**: the DOE excludes off-grid generation from
  2021 onwards.
- **Population shares after 2024** are held at the 2024 census values,
  including in all future scenarios. Update the Excel file when a new
  PSA census is published.
- **Census shares apply to population only.** The grid ratios for GDP
  PPP per capita still use gridded population, so the two per-capita
  variables do not share the same denominator.
- **The DOE PDF may change.** The parser raises an error if the table
  or a grid row is missing, or if a row does not have one value per
  year. If the DOE publishes a new edition under a different URL,
  update `URL` in
  [`doe_philippines.py`](socio_economic_data_sources/doe_philippines.py).
