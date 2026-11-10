# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This script generates the shapes of the three regions of Malaysia
    used with the data of the Grid System Operator of Malaysia (GSO)
    (retrievals/electricity_demand_data_sources/gso.py):

    - MYS_PEN: Peninsula (the 11 states of Peninsular Malaysia and the
      Federal Territories of Kuala Lumpur and Putrajaya), served by the
      grid operated by GSO;
    - MYS_SAB: Sabah (Sabah and the Federal Territory of Labuan), served
      by Sabah Electricity Sdn. Bhd. (SESB);
    - MYS_SAR: Sarawak, served by Sarawak Energy.

    The states are identified by their ISO 3166-2 codes.

    Sources:
    - https://www.gso.org.my
    - https://www.naturalearthdata.com
"""

import os

import cartopy.io.shapereader
import geopandas

# Define the region of each state, by its ISO 3166-2 code.
codes_of_malaysian_states = {
    # MYS_PEN: 13 states and federal territories.
    "MY-01": "MYS_PEN",  # Johor
    "MY-02": "MYS_PEN",  # Kedah
    "MY-03": "MYS_PEN",  # Kelantan
    "MY-04": "MYS_PEN",  # Melaka
    "MY-05": "MYS_PEN",  # Negeri Sembilan
    "MY-06": "MYS_PEN",  # Pahang
    "MY-07": "MYS_PEN",  # Pulau Pinang
    "MY-08": "MYS_PEN",  # Perak
    "MY-09": "MYS_PEN",  # Perlis
    "MY-10": "MYS_PEN",  # Selangor
    "MY-11": "MYS_PEN",  # Terengganu
    "MY-14": "MYS_PEN",  # Kuala Lumpur
    "MY-16": "MYS_PEN",  # Putrajaya
    # MYS_SAB: 2 states and federal territories.
    "MY-12": "MYS_SAB",  # Sabah
    "MY-15": "MYS_SAB",  # Labuan
    # MYS_SAR: 1 state.
    "MY-13": "MYS_SAR",  # Sarawak
}

# Define the names of the Malaysian subdivisions.
names_of_malaysian_subdivisions = {
    "MYS_PEN": "Peninsula",
    "MYS_SAB": "Sabah",
    "MYS_SAR": "Sarawak",
}

# Load the shapefile containing the subdivision shapes from the Natural
# Earth database. The 10m resolution is used because the 50m
# resolution does not include the states of Malaysia.
all_shapes = cartopy.io.shapereader.natural_earth(
    resolution="10m", category="cultural", name="admin_1_states_provinces"
)

# Define a reader for the shapefile.
reader = cartopy.io.shapereader.Reader(all_shapes)

# Read the shapes of all Malaysian states.
state_shapes = [
    shape
    for shape in list(reader.records())
    if shape.attributes["iso_a2"] == "MY"
]

# Check that all the states are mapped to a region, and that all the
# mapped states are in the Natural Earth database.
state_codes = {shape.attributes["iso_3166_2"] for shape in state_shapes}
unmapped_states = sorted(state_codes - set(codes_of_malaysian_states))
missing_states = sorted(set(codes_of_malaysian_states) - state_codes)
if unmapped_states or missing_states:
    raise ValueError(
        "Mismatch between the Natural Earth states and the mapping. "
        f"Unmapped: {unmapped_states}. Missing: {missing_states}."
    )

# Create a GeoDataFrame from the shapes of the states.
states = geopandas.GeoDataFrame(
    {
        "code": [
            codes_of_malaysian_states[shape.attributes["iso_3166_2"]]
            for shape in state_shapes
        ],
        "geometry": [shape.geometry for shape in state_shapes],
    },
    geometry="geometry",
    crs="EPSG:4326",
)

# Merge the states belonging to the same region.
subdivisions = states.dissolve(by="code").reset_index()

# Add the names of the regions to the GeoDataFrame.
subdivisions["name"] = subdivisions["code"].map(
    names_of_malaysian_subdivisions
)
subdivisions = subdivisions[["name", "code", "geometry"]]

# Set the precision of the geometry to a grid size of 0.005 degrees.
# This is done to remove small spikes in the shapes that cause issues
# when plotting the shapes.
subdivisions["geometry"] = subdivisions["geometry"].set_precision(0.005)

# Save the shapes of the regions to a shapefile.
shapes_dir = os.path.join(os.path.dirname(__file__), "gso")
os.makedirs(shapes_dir, exist_ok=True)
subdivisions.to_file(
    os.path.join(shapes_dir, "gso.shp"), driver="ESRI Shapefile"
)
