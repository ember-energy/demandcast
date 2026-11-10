# Data retrieval and projection methodology

This note explains how DemandCast retrieves historical data and builds
future projections for each input variable. For each variable, it
describes the **default method** used for all countries, and then the
**country-specific methods** used for the Philippines (`PHL`),
Singapore (`SGP`), Thailand (`THA`), Malaysia (`MYS`), Viet Nam (`VNM`)
and Indonesia (`IDN`).

More detail on the Philippines and on data centres is in:

- [README_PHL_subnational.md](..docs/README_PHL_subnational.md)
- [README_data_centre_demand.md](..docs/README_data_centre_demand.md)

## Contents

1. [How the variables fit together](#1-how-the-variables-fit-together)
2. [Hourly electricity demand](#2-hourly-electricity-demand)
3. [Subdivision shapes](#3-subdivision-shapes)
4. [Population](#4-population)
5. [Annual electricity demand per capita](#5-annual-electricity-demand-per-capita)
6. [GDP PPP per capita](#6-gdp-ppp-per-capita)
7. [Temperature and gridded data](#7-temperature-and-gridded-data)
8. [Calendar and holiday features](#8-calendar-and-holiday-features)
9. [Data centre demand profiles](#9-data-centre-demand-profiles)
10. [Scenarios and how to combine them](#10-scenarios-and-how-to-combine-them)
11. [Summary by country](#11-summary-by-country)
12. [Known limitations](#12-known-limitations)

---

## 1. How the variables fit together

The pipeline runs in four steps:

```
retrieve.py  →  assemble.py  →  train.py  →  forecast.py
```

1. **Retrieve** each variable for each country or subdivision
   (`config/retrieve_config.yaml`). Yearly variables are expanded to an
   hourly series in local time: every hour of a year holds that year's
   value.
2. **Assemble** the variables into one table, joined on `Time (UTC)`
   and `Entity code` (`config/assemble_config.yaml`).
3. **Train** an XGBoost model to predict the hourly load as a
   **fraction of the annual total** (`Load (fraction of annual total)`).
   The features are listed in [`config/ml_config.yaml`](../config/ml_config.yaml).
4. **Forecast** the hourly fractions, normalise them so that each local
   year sums to 1, and scale them to MW:

```
load (MW) = fraction × annual electricity demand per capita (kWh) × population / 1000
```

So the model sets **the shape** of the load profile, and two variables
set **the total energy**:

| Variable | Role |
|---|---|
| Hourly electricity demand | Target for training (shape only) |
| Annual electricity demand per capita | Feature, and scaling variable for total energy |
| Population | Scaling variable for total energy |
| GDP PPP per capita | Feature |
| Temperature | Features (several statistics) |
| Calendar and holidays | Features |

Any error in annual demand per capita or population carries straight
into the level of the forecast.

---

## 2. Hourly electricity demand

Module: [`retrievals/electricity_demand.py`](../retrievals/electricity_demand.py),
with one module and one yaml file per source in
[`retrievals/electricity_demand_data_sources/`](../retrievals/electricity_demand_data_sources/).
The yaml file lists the entities, start and end dates, and time zones
of each source.

### 2.1 Default method

Hourly or sub-hourly demand is downloaded from a public source (system
operator, utility or market operator), cleaned and saved in
`data/electricity_demand/<date>/<code>.csv` and `.parquet`, with time
in UTC and load in MW. This is used only for training: the model learns
the shape of the profile from it.

### 2.2 Country-specific sources

| Code | Source | Module | Coverage | Method |
|---|---|---|---|---|
| `PHL`, `PHL_LU`, `PHL_VI`, `PHL_MI` | National Grid Corporation of the Philippines (NGCP) | [`ngcp.py`](../retrievals/electricity_demand_data_sources/ngcp.py) | 2013 – 2024 | Measured demand of each grid. `PHL` is the sum of the three grids. |
| `SGP` | Energy Market Authority (EMA) | [`ema.py`](../retrievals/electricity_demand_data_sources/ema.py) | 6 Jan 2014 – today, half-hourly | Measured system demand, downloaded in one-week requests. |
| `THA` | Electricity Generating Authority of Thailand (EGAT) | [`egat.py`](../retrievals/electricity_demand_data_sources/egat.py) | 1 Jul 2024 – today | Measured national demand from the EGAT API. |
| `THA_CEN`, `THA_NOR`, `THA_NEA`, `THA_SOU` | EGAT (derived) | [`egat.py`](../retrievals/electricity_demand_data_sources/egat.py) | 1 Jul 2024 – today | National demand × regional share (see below). |
| `MYS`, `MYS_PEN` | Grid System Operator (GSO) | [`gso.py`](../retrievals/electricity_demand_data_sources/gso.py) | Sep 2016 – today, 10-minute | Measured demand of **Peninsular Malaysia only**. |
| `MYS_SAB`, `MYS_SAR` | DOSM eStatistik + GSO (synthetic) | [`estatistik.py`](../retrievals/electricity_demand_data_sources/estatistik.py) | Monthly totals | Peninsular shape × monthly consumption (see below). |
| `VNM`, `VNM_NOR`, `VNM_CEN`, `VNM_SOU` | National Power System and Market Operator (NSMO) | [`nsmo.py`](../retrievals/electricity_demand_data_sources/nsmo.py) | Sep 2022 – Dec 2025, half-hourly | Measured demand of each region, from monthly files downloaded manually. |
| `IDN` and 8 grid nodes | GSO shape + PLN/ESDM sales (synthetic) | [`esdm.py`](../retrievals/electricity_demand_data_sources/esdm.py) | Years with both GSO data and PLN sales | Peninsular Malaysia shape × annual PLN sales (see below). |

#### Thailand regions (EGAT)

EGAT publishes only the national hourly demand. The regional demand is:

```
demand(region, hour) = national demand(hour) × share(region, month, day, hour)
```

The shares come from the EGAT regional demand of 2023 and 2024
(`system_2023.csv`, `system_2024.csv` in
`socio_economic_data_sources/manual_downloads`), downloaded from a [dataset collected from EGAT](https://zenodo.org/records/17109911): the share of each
region is calculated for each hour, and averaged over the two years at
the same month, day and hour. Metropolitan and Central are combined
into `THA_CEN`.

`egat.get_annual_energy_shares(2025)` gives each region's share of
annual energy. The year is set by `SHARE_YEAR = 2025` in
[`eppo_thailand.py`](../retrievals/socio_economic_data_sources/eppo_thailand.py).
2025 is used because it is the **only complete calendar year** of EGAT
national data: the data starts on 1 July 2024, and a partial year would
bias the shares towards the seasons it covers. The function raises an
error unless all 8,760 hours (8,784 in a leap year) of the year are
downloaded, so retrieve the whole of 2025 first.

The function takes each hour of the 2025 national demand, splits it
with the 2023–2024 hourly regional shares above, and sums each region
over the year. So 2025 sets the **weight of each hour** in the annual
total, and 2023–2024 set **how each hour is split** between the
regions.

The 2025 shares are used in two places (Section 5.5):

1. to **calibrate the EPPO regional projection**, so that it starts
   from the EGAT regional split in 2025 and follows the EPPO trend
   afterwards;
2. to **split the historical national demand** of Ember into the
   regions, with the same 2025 share for every historical year.

#### Sabah and Sarawak (eStatistik)

No hourly data is published for Sabah and Sarawak grid in Malaysia, so a synthetic profile
is built:

1. The monthly consumption of Sabah and Sarawak is read from table
   "Jadual 18.3 Sbh & Swk" of the [DOSM eStatistik](https://newss.statistics.gov.my/newss-portalx/ep/epProductFreeDownloadSearch.seam) "B18 Pertanian &
   Elektrik" workbooks (manual downloads). Where vintages overlap, the
   latest vintage of each month is kept.
2. The shape of each month is taken from the 10-minute Peninsular load
   (GSO): the share of each 10-minute step in the monthly total energy.
   Months with less than 95% coverage are not used.
3. Load = share × monthly consumption, converted to MW.
4. `resample_to_hourly` averages to hourly values, fills gaps by linear
   interpolation, and rescales each month to match the eStatistik total.

Data caveats:

- **Sabah, Mar and Apr 2022**: the reported values (147 and 168 GWh,
  against about 470 GWh in other months) are treated as errors and
  rebuilt from the month-on-month changes of 2023.
- **Sarawak, 2023**: the latest vintages report about 2,100 GWh per
  month, well below 2022 and 2024. The 12_2023 vintage is used instead.
- **Sarawak, 2022**: the values are flagged as estimates and are almost
  flat, so the seasonality of that year comes only from the Peninsular
  shape.

#### Indonesia (ESDM / PLN)

There is no public high-resolution demand data for Indonesia, so the
Peninsular Malaysia shape from [GSO](https://www.gso.org.my/SystemData/SystemDemand.aspx/GetChartDataSource) is used as a proxy:

1. Read the latest GSO 10-minute Peninsular load.
2. For each local year, calculate the share of each 10-minute step in
   the annual energy (gaps are linearly interpolated).
3. Move the shape from Malaysian local time to the local time of the
   Indonesian node to depict evening/morning peaks.
4. Scale each year by the annual PLN electricity sales of the node
   (sheet `Node_totals` in `manual_downloads/esdm_pusdastin`). PLN
   sales by node are available for 2017–2024. For 2025, the node sales
   are estimated as the average share of each node × the total PLN
   sales in the ESDM Handbook of Energy & Economic Statistics of
   Indonesia 2025 (HEESI 2025).
5. Resample to hourly means. `IDN` is the sum of the nodes.

The nodes are `IDN_JAW` (Jawa-Bali), `IDN_SUM` (Sumatera), `IDN_BTM`
(Batam-Riau Islands), `IDN_KAL` (Kalimantan), `IDN_SUL` (Sulawesi),
`IDN_NUS` (Nusa Tenggara), `IDN_MAL` (Maluku) and `IDN_PAP` (Papua).

#### Viet Nam (NSMO)

The monthly NSMO files (`manual_downloads/nsmo/<YYYY-MM-01>`) hold the
half-hourly load of the North (Bắc), Central (Trung), South (Nam) and
the whole country (Quốc gia). The hour labels are period-ending, so
they are shifted to period-starting before being averaged into hourly
values. Some months are missing. `nsmo.py` includes helper functions to
fill these gaps by backcasting with a trained model, then merging the
backcast with the measured data.

---

## 3. Subdivision shapes

Shapes of non-standard subdivisions are generated by the scripts in
[`shapes/`](../shapes/) (run all with `shapes/run_all.sh`). They are
used to aggregate gridded data (population, GDP, temperature) for each
subdivision. Provinces are grouped so that each shape matches the area
covered by the demand or population data.

| Script | Country | Subdivisions | Grouping |
|---|---|---|---|
| [`ngcp.py`](../shapes/ngcp.py) | PHL | `LU`, `VI`, `MI` | PSA administrative regions. MIMAROPA (largely off-grid) is in Luzon. |
| [`egat.py`](../shapes/egat.py) | THA | `CEN`, `NOR`, `NEA`, `SOU` | The 77 provinces, grouped as in the NSO population data (not the Natural Earth regions). |
| [`gso.py`](../shapes/gso.py) | MYS | `PEN`, `SAB`, `SAR` | States by ISO 3166-2 code. Labuan is in Sabah. |
| [`nsmo.py`](../shapes/nsmo.py) | VNM | `NOR`, `CEN`, `SOU` | The 63 provinces before the 2025 reform, grouped by the Northern, Central and Southern Power Corporations. |
| [`esdm.py`](../shapes/esdm.py) | IDN | `JAW`, `SUM`, `BTM`,`KAL`, `SUL`,`NUS`,`MAL`,`PAP`| Provinces grouped as in the ASEAN Data Centre report. |

---

## 4. Population

Module: [`retrievals/population.py`](../retrievals/population.py).
Stored as **Population** (number of people).

### 4.1 Default method

| Entity | Historical | Future |
|---|---|---|
| Country | World Bank (`SP.POP.TOTL`). The last available value is held for later years. | IIASA SSP projection of the selected scenario (`SSP1`–`SSP5`), interpolated to every year. The default scenario used in ASEAN DC Study is `SSP2`.|
| Subdivision | National World Bank value × the subdivision's share of the national **gridded** population (SEDAC GPW v4, 2000–2020). | National IIASA value × the subdivision's share of the national gridded SSP population (Wang X. et al., 2025–2100). |

Gridded population is available only every 5 years from 2000 to 2020,
so each year uses the closest gridded year, and **years after 2020 use
the 2020 shares**. Because only the shares come from the gridded data,
the subdivisions always add up to the national total.

This default is used for the subdivisions of **Malaysia, Viet Nam and
Indonesia**, and for **Singapore** (country only).

### 4.2 Philippines

Source: [Philippine Statistics Authority (PSA)](https://psa.gov.ph/statistics/population-and-housing),
[`psa_philippines.py`](../retrievals/socio_economic_data_sources/psa_philippines.py).

- **Historical**: national World Bank value × the grid's share of the
  PSA census population (censuses of 2000, 2010, 2015, 2020 and 2024).
  Shares are linearly interpolated between censuses, and held at the
  first or last census outside that range.
- **Future**: the PSA national projection ([2020 Census-Based Population
  Projections](https://psa.gov.ph/statistics/population-and-housing/node/165009)) replaces IIASA, with scenarios `PSA1` (Default), `PSA2` and
  `PSA3`. The grids use the 2024 census shares.

### 4.3 Thailand

Source: [National Statistical Office (NSO)](https://www.nso.go.th/nsoweb/index#gsc.tab=0), registered population by provinces and regions
2012–2025,
[`nso_thailand.py`](../retrievals/socio_economic_data_sources/nso_thailand.py).

| Period | National (`THA`) | Regions |
|---|---|---|
| Before 2012 | World Bank | World Bank × average NSO share of 2012–2025 |
| 2012–2025 | World Bank (default, `USE_NSO_NATIONAL_TOTAL = False`) | World Bank × NSO share of the same year |
| Future | IIASA SSP | IIASA SSP × NSO share of 2025 |

The NSO registered population is about 8–10% lower than the World Bank
estimate, possibly exluding unregistered residents such as migrants.
With the default setting, the NSO is used **only to split** the
national population, so there is no step in the national series. Set
`USE_NSO_NATIONAL_TOTAL = True` to use the NSO national total in
2012–2025 instead.

---

## 5. Annual electricity demand per capita

Module: [`retrievals/annual_electricity_demand_per_capita.py`](../retrievals/annual_electricity_demand_per_capita.py).
Stored as **Annual electricity demand per capita (kWh)**. Future files
are named `<code>_<scenario>.csv`, with `-` replaced by `_`.

### 5.1 Default historical method

The national value is the **average of Ember and the World Bank**, or
whichever one is available:

- **Ember**
  ([`ember.py`](../retrievals/socio_economic_data_sources/ember.py)):
  total electricity demand (TWh, the "Demand" row of the yearly global
  dataset) divided by the World Bank population. Since July 2026, Ember
  no longer publishes demand per capita directly, so it is calculated.
- **World Bank**
  ([`world_bank.py`](../retrievals/socio_economic_data_sources/world_bank.py)):
  electric power consumption per capita (`EG.USE.ELEC.KH.PC`).

**Subdivisions use the national value** unless a country-specific
method exists. This applies to the subdivisions of Malaysia, Viet Nam
and Indonesia: every subdivision has the same demand per capita as its
country.

### 5.2 Default future method

The IIASA growth rates of electricity demand per capita
(`IAM_regional_annual_electricity_demand_per_capita_growth.xlsx`) are
applied year by year to the last historical value
(`iiasa.extrapolate`). The growth rates are given for IAM regions and
mapped to countries in
[`iam_regions_mapping.yaml`](../retrievals/socio_economic_data_sources/iam_regions_mapping.yaml).
All six countries covered here are in **`R5.2ASIA`**, so they share the
same growth rates.

Scenarios: `SSP1-Baseline` to `SSP5-60` (default scenario is `SSP2-Baseline`).

### 5.3 Philippines

| | National (`PHL`) | Grids (`PHL_LU`, `PHL_VI`, `PHL_MI`) |
|---|---|---|
| Historical | Default (Ember/World Bank average) | 2003–2025: DOE gross generation of the grid / grid population. Before 2003: national value × (grid / national ratio in 2003). |
| Future | Sum of the grid demands / PSA projected population | PEP demand of the grid / PSA projected population of the grid |

- **DOE**
  ([`doe_philippines.py`](../retrievals/socio_economic_data_sources/doe_philippines.py)):
  "Gross Power Generation per Grid in GWh", parsed from the DOE Power
  Statistics summary PDF on each run.
- **PEP**
  ([`pep_philippines.py`](../retrievals/socio_economic_data_sources/pep_philippines.py)):
  projected electricity sales of each grid from the Philippine Energy
  Plan, Reference (`REF` as default) and Clean Energy (`CES`) scenarios. Sales are
  converted to demand with grid-load factors (gross generation / sales,
  from NGCP generation and DOE sales): Luzon 1.14, Visayas 1.23,
  Mindanao 1.19.

```
demand per capita (kWh/capita) = PEP sales (MWh) × grid-load factor × 1000 / PSA population
```

Scenarios: `PEP-<REF|CES>-<PSA1|PSA2|PSA3>`, for example
`PEP-REF-PSA1` (Default). The future series covers only the years where both the
PEP and the PSA projections exist. It does not use the IIASA growth
rates. (**Need to update this for future years as Singapore (oh my low cortisol country)**)

### 5.4 Singapore

- **Historical**: as default.
- **Future**
  ([`ema_singapore.py`](../retrievals/socio_economic_data_sources/ema_singapore.py)):
  EMA "Electricity Demand and Supply Outlook 2025", Table 1b (page 5),
  projected total generation (GWh) to meet either the **Base**
  Electricity Demand Forecast (`BASE` as Default) or the **Upper-bound** EDF
  (`UPPER`). It is read from the PDF in `manual_downloads/ema`.

| Years | Value |
|---|---|
| Last historical year + 1 to 2025 | Last historical value × IIASA growth rates |
| 2026–2034 | EMA generation × 10⁶ / IIASA SSP population |
| 2035 onwards | 2034 value × IIASA growth rates |

Scenarios: `EMA-<BASE|UPPER>-<IAMC scenario>`, for example
`EMA-BASE-SSP2-45`. The SSP in the name (here `SSP2`) also sets the
population used as denominator.

### 5.5 Thailand

| | National (`THA`) | Regions |
|---|---|---|
| Historical | Default (Ember/World Bank average) | Ember national demand (TWh) × EGAT 2025 energy share of the region / regional population |
| Future, 2026–2037 | EPPO national demand / projected population | EPPO regional demand (calibrated to EGAT) / projected regional population |
| Future, other years | IIASA growth rates (see Singapore) | IIASA growth rates of `THA` |

- **EPPO**
  ([`eppo_thailand.py`](../retrievals/socio_economic_data_sources/eppo_thailand.py)):
  draft [Power Development Plan 2024 (PDP2024)](https://www.oap.go.th/wp-content/uploads/2025/02/%E0%B8%A3%E0%B9%88%E0%B8%B2%E0%B8%87-%E0%B9%81%E0%B8%9C%E0%B8%99%E0%B8%9E%E0%B8%B1%E0%B8%92%E0%B8%99%E0%B8%B2%E0%B8%81%E0%B8%B3%E0%B8%A5%E0%B8%B1%E0%B8%87%E0%B8%81%E0%B8%B2%E0%B8%A3%E0%B8%9C%E0%B8%A5%E0%B8%B4%E0%B8%95%E0%B9%84%E0%B8%9F%E0%B8%9F%E0%B9%89%E0%B8%B2-Power-Development-Plan-PDP.pdf), BASE case, sheet
  `Regional_Energy` of a manually prepared Excel file. The national
  value is the generation requirement of the 3-utility system (EGAT,
  MEA, PEA). It is printed in the PDP for 2024, 2030 and 2037 and read
  from the PDP charts for the other years.
- The **regional EPPO values are not published by EPPO**. They are
  estimated by allocating the national value with regional peak shares.
  They are then calibrated so that 2025 matches EGAT:

```
regional demand'(region, year) = EPPO regional(region, year) × EGAT share(region, 2025) / EPPO share(region, 2025)
regional demand(region, year)  = regional demand' rescaled so that the regions add up to the EPPO national value
```

So the regions start from the EGAT 2025 shares and follow the EPPO
trend afterwards. The national projection is not changed.

- The **historical regional shares** are the EGAT 2025 shares, held
  constant for all historical years.

Scenarios: `EPPO-<IAMC scenario>`, for example `EPPO-SSP2-Baseline` (Default). The SSP
also sets the population used as denominator.

### 5.6 Malaysia, Viet Nam and Indonesia (To be updated)

Default method for the countries. Subdivisions use the national value
(Section 5.1), and the future follows the IIASA `R5.2ASIA` growth rates.

---

## 6. GDP PPP per capita

Module: [`retrievals/gdp_ppp_per_capita.py`](../retrievals/gdp_ppp_per_capita.py).
Stored as **GDP PPP per capita (2021 international $)**. No
country-specific method is used: all countries follow the default.

| Entity | Historical | Future |
|---|---|---|
| Country | Average of the World Bank (`NY.GDP.PCAP.PP.KD`) and IMF WEO, or whichever is available, up to the year before the current year | IIASA SSP projection, interpolated |
| Subdivision | National value × (gridded GDP per capita of the subdivision / that of the country) | Same, with the gridded SSP data |

The gridded GDP is from Wang T. et al. (2022), divided by the gridded
population. Years outside the gridded range use the ratio of the
closest gridded year.

---

## 7. Temperature and gridded data

Modules: [`gridded_weather.py`](../retrievals/gridded_weather.py),
[`temperature.py`](../retrievals/temperature.py),
[`gridded_population.py`](../retrievals/gridded_population.py),
[`gridded_gdp_ppp.py`](../retrievals/gridded_gdp_ppp.py). No
country-specific method is used.

| Data | Historical | Future |
|---|---|---|
| Temperature | ERA5 reanalysis (Copernicus CDS) | CMIP6 projections, by climate model and scenario (for example `CNRM-ESM2-1`, `SSP2-4.5`) |
| Gridded population | SEDAC GPW v4 (2000–2020, every 5 years) | Wang X. et al. (2022), SSPs, 2025–2100 |
| Gridded GDP PPP | Wang T. et al. (2022) | Wang T. et al. (2022), SSPs |

All gridded data is extracted for each country or subdivision shape at
0.25° resolution. Temperature is taken at the **most populous grid
cells** in the shape, and the following features are built:

- hourly temperature of the most populous cell (Top 1) and the average
  of the 3 most populous cells (Top 3);
- monthly average temperature (Top 1) and its rank among the 12 months;
- annual average temperature (Top 1);
- 5th and 95th percentile temperature (Top 1).

Specify the climate model in `retrieve_config.yaml` for future years,
or every model is processed, which is slow.

---

## 8. Calendar and holiday features

Built in [`assemble.py`](../assemble.py) from the local time of each
entity:

- local hour of the day, local month of the year, weekend indicator;
- **major holiday indicator**: holidays when most economic activity
  stops for several days (`MAJOR_HOLIDAYS`);
- **other holiday indicator**: all other public holidays from the
  `holidays` package, including special non-working days.

Country-specific major holidays (To be updated for other countries):

| Country | Major holidays |
|---|---|
| PHL | Holy Week (Maundy Thursday, Good Friday, Black Saturday); 24 Dec – 1 Jan |
| SGP | Chinese New Year (both days and any observed day), plus the eve and the day after, when load is still 7–13% lower than usual |
| THA | New Year (29 Dec – 3 Jan) and Songkran (12 – 17 Apr), when load drops by 15–35%, against about 10% on a normal Sunday |

Other countries have no major holidays defined, so all their holidays
are "other holidays".

Every entity to be modelled must be listed under `categorical_values`
→ `Entity code` in [`config/ml_config.yaml`](../config/ml_config.yaml).
Numeric categorical features (hour, month, holiday indicators) also use
fixed categories, so that training and forecasting sets use the same
codes even when a set does not cover every month.

---

## 9. Data centre demand profiles

Data centre profiles are built separately from the main pipeline. They
are not features of the model and are not run by `retrieve.py`.

1. [`ukpn_data_centres.py`](../retrievals/electricity_demand_data_sources/ukpn_data_centres.py)
   downloads the half-hourly utilisation of UK data centres (UK Power
   Networks) and builds normalised weekday and weekend shapes (mean = 1).
   See [README_data_centre_demand.md](../retrievals/README_data_centre_demand.md).
2. [`iso_data_centre_demand.py`](../retrievals/electricity_demand_data_sources/iso_data_centre_demand.py)
   maps those shapes onto the local calendar of **any** country or
   subdivision (previously only the Philippines):
   - weekdays use the weekday shape; weekends and public holidays use
     the weekend shape (`TREAT_HOLIDAYS_AS_WEEKENDS = True`);
   - each hour is matched by local clock hour;
   - the shape weights are `DC_TYPE_WEIGHTS` (default: co-located only);
3. **Only for ASEAN DC Study**: The profile is scaled to MW with the capacity scenarios of
   [`dc_scenarios.py`](../retrievals/socio_economic_data_sources/dc_scenarios.py),
   read from `DC Demand Scenarios - ASEAN.xlsx`:

```
demand (MW, t) = IT capacity × occupancy × utilisation × PUE × normalised profile(t)
```

| Setting | Values |
|---|---|
| Countries | PHL, IDN, MYS, SGP, THA, VNM, by grid node |
| Scenarios | `Low` (C&W full book), `Mid` (existing + 50% of pipeline), `High` (existing + 100% of pipeline), `Suitable sites` (High capacity reallocated by suitability scores) |
| Years | `2026`: existing capacity (same in all scenarios). `2030`: **only the capacity added** between 2026 and 2030 are made from the script. To find total 2030 capacity, use 2026 + 2030 values. |
| Occupancy, utilisation, PUE | From the workbook for each country and scenario (`USE_WORKBOOK_PARAMETERS = True`) |

`run_all()` builds the 2030 added-capacity profiles for all scenarios,
countries and nodes, skipping nodes without capacity. `run()` builds
only `SCENARIO`, `YEAR` and `COUNTRY`.

The UKPN shapes are measured at the grid connection, so they already
include cooling. Do not apply PUE to the shape, only to an IT capacity.

---

## 10. Scenarios and how to combine them

Future data needs one scenario per variable. Choose them consistently
in `assemble_config.yaml`: the population used for scaling should be
the same as the one used as denominator of annual demand per capita.

| Country | `scenario_for_population` | `scenario_for_annual_electricity_demand_per_capita` | GDP and temperature |
|---|---|---|---|
| Default | `SSP2` | `SSP2-45` (or any IAMC scenario) | `SSP2`; `SSP2-4.5` |
| PHL and grids | `PSA2` | `PEP-REF-PSA2` or `PEP-CES-PSA2` | `SSP2`; `SSP2-4.5` |
| SGP | `SSP2` | `EMA-BASE-SSP2-45` or `EMA-UPPER-SSP2-45` | `SSP2`; `SSP2-4.5` |
| THA and regions | `SSP2` | `EPPO-SSP2-45` | `SSP2`; `SSP2-4.5` |

If a scenario is requested for an entity that does not support it (for
example, `SSP2` population for `PHL`), a warning is logged and no
future data is produced for that entity.

Output files already in the dated folder are skipped. Delete them, or
run on another day, after changing a source or a method. This includes
future files, because they are built from the last historical value.

---

## 11. Summary by country

| | Hourly demand | Population | Annual demand per capita (historical) | Annual demand per capita (future) | Major holidays |
|---|---|---|---|---|---|
| **Default** | Public source | World Bank / IIASA; gridded shares for subdivisions | Ember + World Bank; national value for subdivisions | IIASA growth rates | None |
| **PHL** | NGCP (by grid) | PSA census shares; PSA projections | DOE generation by grid (from 2003) | PEP sales × grid-load factor / PSA population | Holy Week, Christmas–New Year |
| **SGP** | EMA | Default | Default | EMA 2026–2034, then IIASA growth | Chinese New Year ± 1 day |
| **THA** | EGAT (regions from EGAT 2023–2024 shares) | NSO shares; IIASA × NSO 2025 shares | Ember × EGAT 2025 shares for regions | EPPO PDP2024 2026–2037, then IIASA growth | New Year, Songkran |
| **MYS** | GSO (Peninsula); eStatistik × GSO shape (Sabah, Sarawak) | (TBC) | (TBC) | (TBC) | (TBC) |
| **VNM** | NSMO (by region) | (TBC) | (TBC) | (TBC) | (TBC) |
| **IDN** | Synthetic: GSO shape × PLN sales by node | (TBC) | (TBC) | (TBC) | (TBC) |

---

## 12. Known limitations

- **Subdivisions of MYS, VNM and IDN share the national demand per
  capita.** Differences in total energy between their subdivisions come
  only from population.
- **Shared IIASA growth rates.** All six countries are in `R5.2ASIA`,
  so the default future growth of demand per capita is the same for all
  of them.
- **Synthetic profiles.** Sabah, Sarawak and Indonesia use the
  Peninsular Malaysia shape. They do not capture local differences in
  climate, industry or daily routine, nor the local time of sunrise and
  sunset (beyond the shift between time zones).
- **Thai regional demand is derived.** EGAT regional profiles come from
  the national demand and 2023–2024 average shares. The historical
  regional demand per capita uses the 2025 EGAT shares for all years.
  The EPPO regional projection is an estimate based on peak shares, not
  published by EPPO.
- **Frozen shares.** Regional population shares are held at their last
  observed value in future years (PSA 2024, NSO 2025), and gridded
  shares at 2020 for other subdivisions.
- **Different definitions.** For the Philippine grids, DOE gross
  generation includes own use and losses, while national values follow
  the Ember/World Bank average. The population-weighted grid values do
  not add up to the national value. Generation by grid also differs
  from demand by grid because of inter-grid transfers.
- **Projection horizons.** The PEP-based Philippine projection covers
  only the years with both PEP and PSA data. EMA (Singapore) and EPPO
  (Thailand) are extended with IIASA growth rates after 2034 and 2037.
- **Short records.** EGAT data starts in July 2024 and NSMO data has
  missing months, so Thailand and Viet Nam have few training years.
- **Manual downloads.** Many country-specific inputs are Excel or PDF
  files in `socio_economic_data_sources/manual_downloads`. They must be
  updated by hand when a new edition is published, and parsers raise
  errors if the format changes.
