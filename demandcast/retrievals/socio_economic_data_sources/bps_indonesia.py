# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This module reads the population of Indonesia, of its 34 provinces,
    and of the eight grid nodes defined in shapes/esdm.py, from
    BPS-Statistics Indonesia, for 2015 to 2050:

    - 2015-2019: the Web API of BPS, var 1886 "Total Population
      Projection Result by Province and Gender" (thousand people, total
      of both sexes), i.e., the Indonesia Population Projection
      2015-2045 based on SUPAS 2015 (mid-year).
    - 2020-2050: the Indonesia Population Projection 2020-2050, results
      of the 2020 Population Census (BPS, 2023, trend scenario,
      mid-year), from a manually compiled Excel file (manual_downloads/
      bps/Indonesia_Population_Projection_by_Province_2020-2050.xlsx,
      thousand people).

    The two projections have different bases, so there is a small break
    in the series between 2019 and 2020.

    The 34 provinces of the 2020 Census are used (before the split of
    Papua and Papua Barat in 2022), which match the Natural Earth shapes
    of shapes/esdm.py. The provinces are mapped to the grid nodes as in
    shapes/esdm.py. Kalimantan Utara (created in 2012 from Kalimantan
    Timur, and part of it in Natural Earth) is mapped to IDN_KAL.

    In retrievals.population, the BPS data are only used for the shares
    of the nodes in the national population (get_node_shares). The
    national population of Indonesia stays the default one (World Bank
    for historical years, IIASA for future years), so that it is
    consistent with the electricity demand per capita of Ember (which is
    divided by the World Bank population). The share of 2015 is used
    before 2015, and the share of 2050 after 2050.

    The BPS API key is read from the BPS_API_KEY variable of the .env
    file in the root folder (demandcast/.env).

    Usage (from the demandcast folder), to save the population of the
    provinces and of the nodes into CSV files:
        python -m retrievals.socio_economic_data_sources.bps_indonesia

    Sources:
    - https://webapi.bps.go.id (BPS-Statistics Indonesia)
    - https://www.bps.go.id/id/publication/2023/05/16/fad83131cd3bb9be3bb2a657/proyeksi-penduduk-indonesia-2020-2050-hasil-sensus-penduduk-2020.html
"""

import functools
import logging
import os

import pandas
import requests
from dotenv import load_dotenv

import utils.config

# Define the base URL of the BPS Web API (domain 0000: national level).
BASE_URL = "https://webapi.bps.go.id/v1/api/list/model"
DOMAIN = "0000"

# Define the BPS variable of the population projection 2015-2045, and
# its category of the total of both sexes.
API_VAR = 1886
API_TOTAL_SEX = 585

# Define the years retrieved from the API.
API_YEARS = list(range(2015, 2020))

# Define the Excel file of the population projection 2020-2050.
PROJECTION_FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    "manual_downloads",
    "bps",
    "Indonesia_Population_Projection_by_Province_2020-2050.xlsx",
)
PROJECTION_SHEET_NAME = "Provinces 2020-2050"
PROJECTION_HEADER_ROW = 3  # The table header is on the fourth row.

# Define the BPS code of Indonesia, its name in the Excel file, and its
# ISO Alpha-3 code.
INDONESIA_BPS_CODE = 9999
INDONESIA_NAME = "INDONESIA"
CODE = "IDN"

# Define the provinces by their BPS code, with their name (as in the
# Excel file), their ISO 3166-2 code (as in shapes/esdm.py), and their
# grid node.
PROVINCES = {
    1100: ("Aceh", "ID-AC", "IDN_SUM"),
    1200: ("Sumatera Utara", "ID-SU", "IDN_SUM"),
    1300: ("Sumatera Barat", "ID-SB", "IDN_SUM"),
    1400: ("Riau", "ID-RI", "IDN_SUM"),
    1500: ("Jambi", "ID-JA", "IDN_SUM"),
    1600: ("Sumatera Selatan", "ID-SS", "IDN_SUM"),
    1700: ("Bengkulu", "ID-BE", "IDN_SUM"),
    1800: ("Lampung", "ID-LA", "IDN_SUM"),
    1900: ("Kepulauan Bangka Belitung", "ID-BB", "IDN_SUM"),
    2100: ("Kepulauan Riau", "ID-KR", "IDN_BTM"),
    3100: ("DKI Jakarta", "ID-JK", "IDN_JAW"),
    3200: ("Jawa Barat", "ID-JB", "IDN_JAW"),
    3300: ("Jawa Tengah", "ID-JT", "IDN_JAW"),
    3400: ("DI Yogyakarta", "ID-YO", "IDN_JAW"),
    3500: ("Jawa Timur", "ID-JI", "IDN_JAW"),
    3600: ("Banten", "ID-BT", "IDN_JAW"),
    5100: ("Bali", "ID-BA", "IDN_JAW"),
    5200: ("Nusa Tenggara Barat", "ID-NB", "IDN_NUS"),
    5300: ("Nusa Tenggara Timur", "ID-NT", "IDN_NUS"),
    6100: ("Kalimantan Barat", "ID-KB", "IDN_KAL"),
    6200: ("Kalimantan Tengah", "ID-KT", "IDN_KAL"),
    6300: ("Kalimantan Selatan", "ID-KS", "IDN_KAL"),
    6400: ("Kalimantan Timur", "ID-KI", "IDN_KAL"),
    6500: ("Kalimantan Utara", "ID-KU", "IDN_KAL"),
    7100: ("Sulawesi Utara", "ID-SA", "IDN_SUL"),
    7200: ("Sulawesi Tengah", "ID-ST", "IDN_SUL"),
    7300: ("Sulawesi Selatan", "ID-SN", "IDN_SUL"),
    7400: ("Sulawesi Tenggara", "ID-SG", "IDN_SUL"),
    7500: ("Gorontalo", "ID-GO", "IDN_SUL"),
    7600: ("Sulawesi Barat", "ID-SR", "IDN_SUL"),
    8100: ("Maluku", "ID-MA", "IDN_MAL"),
    8200: ("Maluku Utara", "ID-MU", "IDN_MAL"),
    # Boundaries of the 2020 Census (including Papua Barat Daya).
    9100: ("Papua Barat", "ID-PB", "IDN_PAP"),
    # Boundaries of the 2020 Census (including Papua Selatan, Papua
    # Tengah, and Papua Pegunungan).
    9400: ("Papua", "ID-PA", "IDN_PAP"),
}

# Define the names of the grid nodes, as in shapes/esdm.py.
NODE_NAMES = {
    "IDN_SUM": "Indonesia Sumatera",
    "IDN_BTM": "Indonesia Batam-Riau Islands",
    "IDN_JAW": "Indonesia Jawa",
    "IDN_KAL": "Indonesia Kalimantan",
    "IDN_SUL": "Indonesia Sulawesi",
    "IDN_NUS": "Indonesia Nusa Tenggara",
    "IDN_MAL": "Indonesia Maluku",
    "IDN_PAP": "Indonesia Papua",
}

# Define the tolerance (in people) when checking that the provinces add
# up to the national total. The values are rounded to 0.1 (API) or 0.01
# (Excel file) thousand people, so the sum of 34 provinces can differ
# from the national total by a few thousand people.
TOLERANCE = 5000


def get_codes() -> list[str]:
    """
    Get the codes of the grid nodes of Indonesia.

    Returns
    -------
    list[str]
        The codes of the grid nodes.
    """
    return list(NODE_NAMES)


def _get_api_key() -> str:
    """
    Get the BPS API key from the .env file in the root folder.

    Returns
    -------
    str
        The BPS API key.

    Raises
    ------
    ValueError
        If the API key is not set.
    """
    root_directory = utils.config.read_folders_structure()["root_folder"]
    load_dotenv(dotenv_path=os.path.join(root_directory, ".env"))
    api_key = os.getenv("BPS_API_KEY")
    if api_key is None:
        raise ValueError(
            "The BPS API key is not set. Please set the BPS_API_KEY "
            "environment variable in the .env file."
        )
    return api_key


def _request(path: str) -> dict:
    """
    Send a request to the BPS Web API.

    Parameters
    ----------
    path : str
        The path of the request after the base URL, without the key.

    Returns
    -------
    dict
        The JSON response.

    Raises
    ------
    ValueError
        If the API does not return data.
    """
    url = f"{BASE_URL}/{path}/key/{_get_api_key()}"
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    content = response.json()
    if (
        content.get("status") != "OK"
        or content.get("data-availability") != "available"
    ):
        raise ValueError(
            f"No data returned by the BPS API for {path}: "
            f"{content.get('status')}, {content.get('data-availability')}."
        )
    return content


def _get_year_ids(var: int) -> dict[int, int]:
    """
    Get the BPS identifiers of the years available for a BPS variable.

    Parameters
    ----------
    var : int
        The BPS variable.

    Returns
    -------
    dict[int, int]
        The BPS year identifiers (th_id), with the years as keys.
    """
    year_ids = {}
    page = 1
    while True:
        content = _request(
            f"th/lang/eng/domain/{DOMAIN}/var/{var}/page/{page}"
        )
        pagination, records = content["data"]
        year_ids.update({int(r["th"]): int(r["th_id"]) for r in records})
        if page >= pagination["pages"]:
            return year_ids
        page += 1


def _get_api_values(year_id: int) -> pandas.Series:
    """
    Get the population of the provinces and of Indonesia in a year from
    the BPS Web API.

    The keys of the "datacontent" field of the response are the
    concatenation of the region code (vervar), the variable, the
    category (turvar), the year identifier (th), and the period
    (turtahun, 0 for annual data).

    Parameters
    ----------
    year_id : int
        The BPS year identifier.

    Returns
    -------
    pandas.Series
        The population in number of people, with the BPS codes of the
        provinces and of Indonesia as index.

    Raises
    ------
    ValueError
        If a province or Indonesia is missing.
    """
    content = _request(
        f"data/lang/eng/domain/{DOMAIN}/var/{API_VAR}/th/{year_id}"
    )
    data = content["datacontent"]
    values = {}
    for region in [*PROVINCES, INDONESIA_BPS_CODE]:
        key = f"{region}{API_VAR}{API_TOTAL_SEX}{year_id}0"
        if key not in data:
            raise ValueError(
                f"The population of {region} was not found in var "
                f"{API_VAR} (year identifier {year_id})."
            )
        # Convert from thousand people to people.
        values[region] = float(data[key]) * 1000
    return pandas.Series(values, dtype=float)


def _read_api_population() -> pandas.DataFrame:
    """
    Read the population of the provinces and of Indonesia in 2015-2019
    from the BPS Web API.

    Returns
    -------
    pandas.DataFrame
        The population in number of people, with the BPS codes as index
        and the years as columns.

    Raises
    ------
    ValueError
        If a year is not available in the API.
    """
    year_ids = _get_year_ids(API_VAR)
    missing_years = sorted(set(API_YEARS) - set(year_ids))
    if missing_years:
        raise ValueError(
            f"The years {missing_years} are not available in var {API_VAR} "
            "of the BPS API."
        )
    return pandas.DataFrame(
        {year: _get_api_values(year_ids[year]) for year in API_YEARS}
    )


def _read_projection_population() -> pandas.DataFrame:
    """
    Read the population of the provinces and of Indonesia in 2020-2050
    from the Excel file of the BPS projection.

    Returns
    -------
    pandas.DataFrame
        The population in number of people, with the BPS codes as index
        and the years as columns.

    Raises
    ------
    ValueError
        If a province or Indonesia is missing in the file.
    """
    sheet = pandas.read_excel(
        PROJECTION_FILE_PATH,
        sheet_name=PROJECTION_SHEET_NAME,
        header=PROJECTION_HEADER_ROW,
    )
    sheet["Province"] = sheet["Province"].astype(str).str.strip()

    # Get the year columns (e.g., 2020 or 2020.0).
    year_columns = {
        column: int(float(column))
        for column in sheet.columns
        if str(column)[:4].isdigit()
    }

    # Map the names of the provinces and of Indonesia to their BPS codes.
    codes_by_name = {name: code for code, (name, _, _) in PROVINCES.items()}
    codes_by_name[INDONESIA_NAME] = INDONESIA_BPS_CODE
    missing = set(codes_by_name) - set(sheet["Province"])
    if missing:
        raise ValueError(
            f"The rows {sorted(missing)} were not found in the sheet "
            f"{PROJECTION_SHEET_NAME} of {PROJECTION_FILE_PATH}."
        )

    # Keep the rows of the provinces and of Indonesia, and convert from
    # thousand people to people.
    return (
        sheet[sheet["Province"].isin(codes_by_name)]
        .set_index("Province")[list(year_columns)]
        .rename(index=codes_by_name, columns=year_columns)
        .astype(float)
        * 1000
    )


@functools.lru_cache(maxsize=1)
def read_province_population() -> pandas.DataFrame:
    """
    Read the population of the provinces of Indonesia and of Indonesia
    from BPS (Web API for 2015-2019, Excel file for 2020-2050).

    Returns
    -------
    pandas.DataFrame
        The population in number of people, with the BPS codes of the
        provinces and of Indonesia as index and the years as columns.

    Raises
    ------
    ValueError
        If the provinces do not add up to the national total.
    """
    logging.info("Reading the population of Indonesia from BPS.")

    population = pandas.concat(
        [_read_api_population(), _read_projection_population()], axis=1
    ).reindex([*PROVINCES, INDONESIA_BPS_CODE])

    # Check that the provinces add up to the national total.
    difference = (
        population.loc[list(PROVINCES)].sum()
        - population.loc[INDONESIA_BPS_CODE]
    ).abs()
    if (difference > TOLERANCE).any():
        raise ValueError(
            "The provinces do not add up to the population of Indonesia "
            f"in the years {difference[difference > TOLERANCE].index.tolist()}."
        )

    population.index.name = "BPS code"
    population.columns.name = "Year"
    return population


def read_population() -> pandas.DataFrame:
    """
    Read the population of the grid nodes of Indonesia and of Indonesia
    from BPS.

    Returns
    -------
    pandas.DataFrame
        The population in number of people, with the codes of the grid
        nodes and of Indonesia (the national total of BPS) as index and
        the years (2015-2050) as columns.
    """
    province_population = read_province_population()
    provinces = province_population.loc[list(PROVINCES)]

    # Sum the provinces of each grid node.
    nodes = (
        provinces.groupby(provinces.index.map(lambda code: PROVINCES[code][2]))
        .sum()
        .reindex(get_codes())
    )

    # Add the national total.
    nodes.loc[CODE] = province_population.loc[INDONESIA_BPS_CODE]

    nodes.index.name = "Code"
    return nodes


def get_node_shares(years: list[int]) -> pandas.DataFrame:
    """
    Get the share of each grid node in the population of Indonesia.

    The share of a year in the BPS data (2015-2050) is the BPS
    population of the node divided by the sum of the nodes. The years
    before the first year of the BPS data use the share of the first
    year, and the years after the last year use the share of the last
    year.

    Parameters
    ----------
    years : list[int]
        The years of interest.

    Returns
    -------
    pandas.DataFrame
        The shares, with the codes of the grid nodes as index and the
        years as columns. The shares of each year sum to 1.
    """
    nodes = read_population().loc[get_codes()]
    shares = nodes / nodes.sum()
    first_year, last_year = shares.columns.min(), shares.columns.max()
    used_years = [min(max(year, first_year), last_year) for year in years]
    return shares[used_years].set_axis(years, axis=1)


def _format_provinces(
    province_population: pandas.DataFrame,
) -> pandas.DataFrame:
    """
    Add the names, ISO codes, and grid nodes to the province population.

    Parameters
    ----------
    province_population : pandas.DataFrame
        The output of read_province_population.

    Returns
    -------
    pandas.DataFrame
        The population of the provinces and of Indonesia, with columns
        for the name, ISO 3166-2 code, and grid node.
    """
    info = pandas.DataFrame(
        {
            code: {"Name": name, "ISO code": iso, "Node": node}
            for code, (name, iso, node) in PROVINCES.items()
        }
    ).T
    info.loc[INDONESIA_BPS_CODE] = ["Indonesia", CODE, CODE]
    info.index.name = "BPS code"
    return info.join(province_population)


def save_population() -> None:
    """
    Save the population of Indonesia, of its provinces, and of its grid
    nodes in the population folder of the data directory, in two CSV
    files:

    - IDN_province_population_bps.csv: the provinces and Indonesia;
    - IDN_node_population_bps.csv: the grid nodes and Indonesia.
    """
    output_directory = utils.config.read_folders_structure()[
        "population_folder"
    ]
    os.makedirs(output_directory, exist_ok=True)

    provinces = _format_provinces(read_province_population())
    provinces.to_csv(
        os.path.join(output_directory, "IDN_province_population_bps.csv")
    )

    nodes = read_population()
    nodes.insert(
        0, "Name", nodes.index.map({**NODE_NAMES, CODE: "Indonesia"})
    )
    nodes.to_csv(os.path.join(output_directory, "IDN_node_population_bps.csv"))

    logging.info(f"Saved the population of Indonesia in {output_directory}.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    save_population()
