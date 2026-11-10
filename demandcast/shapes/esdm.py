# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This script generates the shapes of the eight grid nodes of
    Indonesia used with the electricity sales data of the Ministry of
    Energy and Mineral Resources of Indonesia (ESDM) and of PLN
    (retrievals/electricity_demand_data_sources/esdm.py):

    - IDN_SUM: Sumatera (Aceh, North Sumatra, West Sumatra, Riau, Jambi,
      South Sumatra, Bengkulu, Bangka-Belitung, and Lampung);
    - IDN_BTM: Batam-Riau Islands (Riau Islands province);
    - IDN_JAW: Jawa (Banten, Jakarta, West Java, Central Java,
      Yogyakarta, East Java, and Bali);
    - IDN_KAL: Kalimantan (including North Kalimantan, which is part of
      East Kalimantan in the Natural Earth database);
    - IDN_SUL: Sulawesi (including Gorontalo);
    - IDN_NUS: Nusa Tenggara (West and East Nusa Tenggara);
    - IDN_MAL: Maluku (Maluku and North Maluku);
    - IDN_PAP: Papua (Papua and West Papua, which include the provinces
      created in 2022).

    The provinces are grouped as in the node mapping of the PLN sales
    file (retrievals/socio_economic_data_sources/manual_downloads/
    esdm_pusdastin), so that the shapes match the sales of the nodes.
    The provinces are identified by their ISO 3166-2 codes.

    Sources:
    - https://gatrik.esdm.go.id (Statistik Ketenagalistrikan)
    - https://www.naturalearthdata.com
"""

import os

import cartopy.io.shapereader
import geopandas

# Define the grid node of each province, by its ISO 3166-2 code.
codes_of_indonesian_provinces = {
    # IDN_SUM: 9 provinces.
    "ID-AC": "IDN_SUM",  # Aceh
    "ID-SU": "IDN_SUM",  # Sumatera Utara
    "ID-SB": "IDN_SUM",  # Sumatera Barat
    "ID-RI": "IDN_SUM",  # Riau
    "ID-JA": "IDN_SUM",  # Jambi
    "ID-SS": "IDN_SUM",  # Sumatera Selatan
    "ID-BE": "IDN_SUM",  # Bengkulu
    "ID-BB": "IDN_SUM",  # Bangka-Belitung
    "ID-LA": "IDN_SUM",  # Lampung
    # IDN_BTM: 1 province.
    "ID-KR": "IDN_BTM",  # Kepulauan Riau
    # IDN_JAW: 7 provinces.
    "ID-BT": "IDN_JAW",  # Banten
    "ID-JK": "IDN_JAW",  # Jakarta Raya
    "ID-JB": "IDN_JAW",  # Jawa Barat
    "ID-JT": "IDN_JAW",  # Jawa Tengah
    "ID-YO": "IDN_JAW",  # Yogyakarta
    "ID-JI": "IDN_JAW",  # Jawa Timur
    "ID-BA": "IDN_JAW",  # Bali
    # IDN_KAL: 4 provinces.
    "ID-KB": "IDN_KAL",  # Kalimantan Barat
    "ID-KT": "IDN_KAL",  # Kalimantan Tengah
    "ID-KS": "IDN_KAL",  # Kalimantan Selatan
    "ID-KI": "IDN_KAL",  # Kalimantan Timur (incl. Kalimantan Utara)
    # IDN_SUL: 6 provinces.
    "ID-SA": "IDN_SUL",  # Sulawesi Utara
    "ID-GO": "IDN_SUL",  # Gorontalo
    "ID-ST": "IDN_SUL",  # Sulawesi Tengah
    "ID-SR": "IDN_SUL",  # Sulawesi Barat
    "ID-SN": "IDN_SUL",  # Sulawesi Selatan
    "ID-SG": "IDN_SUL",  # Sulawesi Tenggara
    # IDN_NUS: 2 provinces.
    "ID-NB": "IDN_NUS",  # Nusa Tenggara Barat
    "ID-NT": "IDN_NUS",  # Nusa Tenggara Timur
    # IDN_MAL: 2 provinces.
    "ID-MA": "IDN_MAL",  # Maluku
    "ID-MU": "IDN_MAL",  # Maluku Utara
    # IDN_PAP: 2 provinces.
    "ID-PA": "IDN_PAP",  # Papua
    "ID-PB": "IDN_PAP",  # Papua Barat
}

# Define the names of the Indonesian grid nodes.
names_of_indonesian_subdivisions = {
    "IDN_SUM": "Indonesia Sumatera",
    "IDN_BTM": "Indonesia Batam-Riau Islands",
    "IDN_JAW": "Indonesia Jawa",
    "IDN_KAL": "Indonesia Kalimantan",
    "IDN_SUL": "Indonesia Sulawesi",
    "IDN_NUS": "Indonesia Nusa Tenggara",
    "IDN_MAL": "Indonesia Maluku",
    "IDN_PAP": "Indonesia Papua",
}

# Load the shapefile containing the subdivision shapes from the Natural
# Earth database. The 10m resolution is used because the 50m
# resolution does not include the provinces of Indonesia.
all_shapes = cartopy.io.shapereader.natural_earth(
    resolution="10m", category="cultural", name="admin_1_states_provinces"
)

# Define a reader for the shapefile.
reader = cartopy.io.shapereader.Reader(all_shapes)

# Read the shapes of all Indonesian provinces.
province_shapes = [
    shape
    for shape in list(reader.records())
    if shape.attributes["iso_a2"] == "ID"
]

# Check that all the provinces are mapped to a grid node, and that all
# the mapped provinces are in the Natural Earth database.
province_codes = {shape.attributes["iso_3166_2"] for shape in province_shapes}
unmapped_provinces = sorted(province_codes - set(codes_of_indonesian_provinces))
missing_provinces = sorted(set(codes_of_indonesian_provinces) - province_codes)
if unmapped_provinces or missing_provinces:
    raise ValueError(
        "Mismatch between the Natural Earth provinces and the mapping. "
        f"Unmapped: {unmapped_provinces}. Missing: {missing_provinces}."
    )

# Create a GeoDataFrame from the shapes of the provinces.
provinces = geopandas.GeoDataFrame(
    {
        "code": [
            codes_of_indonesian_provinces[shape.attributes["iso_3166_2"]]
            for shape in province_shapes
        ],
        "geometry": [shape.geometry for shape in province_shapes],
    },
    geometry="geometry",
    crs="EPSG:4326",
)

# Merge the provinces belonging to the same grid node.
subdivisions = provinces.dissolve(by="code").reset_index()

# Add the names of the grid nodes to the GeoDataFrame.
subdivisions["name"] = subdivisions["code"].map(
    names_of_indonesian_subdivisions
)
subdivisions = subdivisions[["name", "code", "geometry"]]

# Set the precision of the geometry to a grid size of 0.005 degrees.
# This is done to remove small spikes in the shapes that cause issues
# when plotting the shapes.
subdivisions["geometry"] = subdivisions["geometry"].set_precision(0.005)

# Save the shapes of the grid nodes to a shapefile.
shapes_dir = os.path.join(os.path.dirname(__file__), "esdm")
os.makedirs(shapes_dir, exist_ok=True)
subdivisions.to_file(
    os.path.join(shapes_dir, "esdm.shp"), driver="ESRI Shapefile"
)
