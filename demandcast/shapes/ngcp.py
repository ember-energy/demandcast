# -*- coding: utf-8 -*-
"""
License: AGPL-3.0.

Description:

    This script generates the shapes of the three main grids of the
    Philippines operated by the National Grid Corporation of the
    Philippines (NGCP): Luzon, Visayas, and Mindanao.

    The provinces are grouped by their administrative region. The
    MIMAROPA region (Region IV-B), which is largely off-grid, is
    included in Luzon so that its population is accounted for when the
    annual electricity demand includes off-grid generation.

    Source: https://www.ngcp.ph/operations#operations
"""

import os

import cartopy.io.shapereader
import geopandas
import pandas

# Define the administrative regions of the Philippines and their
# corresponding subdivisions, as named in the Natural Earth database.
codes_of_philippine_subdivisions = {
    "National Capital Region": "PHL_LU",
    "Cordillera Administrative Region (CAR)": "PHL_LU",
    "Ilocos (Region I)": "PHL_LU",
    "Cagayan Valley (Region II)": "PHL_LU",
    "Central Luzon (Region III)": "PHL_LU",
    "CALABARZON (Region IV-A)": "PHL_LU",
    "MIMAROPA (Region IV-B)": "PHL_LU",
    "Bicol (Region V)": "PHL_LU",
    "Western Visayas (Region VI)": "PHL_VI",
    "Central Visayas (Region VII)": "PHL_VI",
    "Eastern Visayas (Region VIII)": "PHL_VI",
    "Zamboanga Peninsula (Region IX)": "PHL_MI",
    "Northern Mindanao (Region X)": "PHL_MI",
    "Davao (Region XI)": "PHL_MI",
    "SOCCSKSARGEN (Region XII)": "PHL_MI",
    # Caraga (Region XIII) is labelled as "Dinagat Islands" in the
    # Natural Earth database.
    "Dinagat Islands (Region XIII)": "PHL_MI",
    "Autonomous Region in Muslim Mindanao (ARMM)": "PHL_MI",
}

# Define the names of the Philippine subdivisions.
names_of_philippine_subdivisions = {
    "PHL_LU": "Luzon",
    "PHL_VI": "Visayas",
    "PHL_MI": "Mindanao",
}

# Load the shapefile containing the subdivision shapes from the Natural
# Earth database. The 10m resolution is used because the 50m
# resolution does not include the provinces of the Philippines.
all_shapes = cartopy.io.shapereader.natural_earth(
    resolution="10m", category="cultural", name="admin_1_states_provinces"
)

# Define a reader for the shapefile.
reader = cartopy.io.shapereader.Reader(all_shapes)

# Read the shapefiles of all Philippine provinces.
province_shapes = [
    shape
    for shape in list(reader.records())
    if shape.attributes["iso_a2"] == "PH"
]

# Check that all the regions of the provinces are mapped to a
# subdivision.
unmapped_regions = {
    province_shape.attributes["region"]
    for province_shape in province_shapes
} - set(codes_of_philippine_subdivisions)
if unmapped_regions:
    raise ValueError(
        "The following regions are not mapped to a subdivision: "
        f"{', '.join(sorted(unmapped_regions))}."
    )

# Create a DataFrame from the shapes of the provinces.
provinces = pandas.DataFrame(columns=["name", "code", "parent", "geometry"])
for province_shape in province_shapes:
    province = pandas.Series(
        {
            "name": province_shape.attributes["name"],
            "code": province_shape.attributes["iso_3166_2"],
            "parent": codes_of_philippine_subdivisions[
                province_shape.attributes["region"]
            ],
            "geometry": province_shape.geometry,
        }
    )
    provinces = pandas.concat(
        [provinces, province.to_frame().T], ignore_index=True
    )

# Add the coordinate reference system to the GeoDataFrame.
provinces = geopandas.GeoDataFrame(
    provinces, geometry="geometry", crs="EPSG:4326"
)

# Merge the provinces belonging to the same subdivision.
subdivisions = provinces.dissolve(by="parent")

# Reset the index of the GeoDataFrame.
subdivisions = subdivisions.reset_index()

# Drop the columns that are not needed.
subdivisions = subdivisions[["name", "parent", "geometry"]]

# Rename the columns of the GeoDataFrame.
subdivisions = subdivisions.rename(columns={"parent": "code"})

# Add the names of the subdivisions to the GeoDataFrame.
for subdivision_code in subdivisions["code"]:
    subdivisions.loc[subdivisions["code"] == subdivision_code, "name"] = (
        names_of_philippine_subdivisions[subdivision_code]
    )

# Set the precision of the geometry to a grid size of 0.005 degrees.
# This is done to remove small spikes in the shapes that cause issues
# when plotting the shapes.
subdivisions["geometry"] = subdivisions["geometry"].set_precision(0.005)

# Add the coordinate reference system (CRS) to the shapefile.
subdivisions = subdivisions.set_crs(epsg=4326)

# Save the shapes of the subdivisions to a shapefile.
shapes_dir = os.path.join(os.path.dirname(__file__), "ngcp")
os.makedirs(shapes_dir, exist_ok=True)
subdivisions.to_file(
    os.path.join(shapes_dir, "ngcp.shp"), driver="ESRI Shapefile"
)
