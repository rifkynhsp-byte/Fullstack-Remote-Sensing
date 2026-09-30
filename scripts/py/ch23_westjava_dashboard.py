#| title: A district dashboard for West Java (Python)
#| description: The same indicators as the JavaScript tab, turned into an interactive web dashboard with plotly.

"""
CHAPTER 23 | Earth Engine computes; Python presents. The same four indicators
per West Java district, then an interactive map and chart saved as one HTML
file you can email, host or open offline.

    pip install earthengine-api plotly pandas
"""

import ee
import matplotlib.pyplot as plt

districts = (ee.FeatureCollection("FAO/GAUL/2025/level2")
             .filter(ee.Filter.eq("GAUL1_NAME", "Jawa Barat")))
YEAR = "2024"

ndvi = (ee.ImageCollection("MODIS/061/MOD13A2").filterDate(f"{YEAR}-01-01", "2025-01-01")
        .select("NDVI").mean().multiply(0.0001).rename("ndvi"))
lst = (ee.ImageCollection("MODIS/061/MOD11A2").filterDate(f"{YEAR}-01-01", "2025-01-01")
       .select("LST_Day_1km").mean().multiply(0.02).subtract(273.15).rename("lst_c"))
built = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(districts)
         .filterDate(f"{YEAR}-01-01", "2025-01-01").select("built").mean().gt(0.5)
         .rename("built"))
people = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IDN"))
          .filter(ee.Filter.eq("year", 2020)).mosaic().rename("people"))

means = ndvi.addBands(lst).addBands(built).reduceRegions(
    collection=districts, reducer=ee.Reducer.mean(), scale=1000, tileScale=4)
table = (people.reduceRegions(collection=means,
                              reducer=ee.Reducer.sum().setOutputs(["people"]),
                              scale=100, tileScale=8)
         .map(lambda f: f.set({"district": f.get("GAUL2_NAME"),
                               "built_pct": ee.Number(f.get("built")).multiply(100)})))


def dashboard_html(path):
    """Build the interactive dashboard: a choropleth you can switch, and a scatter."""
    import json
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    info = table.map(lambda f: f.simplify(300)).getInfo()
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": f["properties"]["district"], "geometry": f["geometry"],
         "properties": {}} for f in info["features"]]}
    rows = [f["properties"] for f in info["features"]]
    names = [r["district"] for r in rows]
    fields = {"lst_c": ("Daytime LST 2024 (°C)", "YlOrRd"),
              "ndvi": ("NDVI 2024", "YlGn"),
              "built_pct": ("Built-up share 2024 (%)", "Greys")}

    fig = make_subplots(rows=1, cols=2, column_widths=[0.58, 0.42],
                        specs=[[{"type": "choropleth"}, {"type": "xy"}]],
                        subplot_titles=("Pick an indicator", "Greener districts run cooler"))
    for i, (field, (label, scale)) in enumerate(fields.items()):
        fig.add_trace(go.Choropleth(
            geojson=geo, locations=names, z=[r[field] for r in rows], colorscale=scale,
            colorbar=dict(title=label, x=0.52, len=0.8), visible=(i == 0),
            hovertemplate="%{location}<br>" + label + ": %{z:.2f}<extra></extra>",
            marker_line_width=0.4), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=[r["ndvi"] for r in rows], y=[r["lst_c"] for r in rows], mode="markers",
        text=names, marker=dict(size=[max(6, (r["people"] / 1e6) ** 0.5 * 14) for r in rows],
                                color=[r["built_pct"] for r in rows], colorscale="Greys",
                                line=dict(width=0.5, color="#333")),
        hovertemplate="%{text}<br>NDVI %{x:.2f}, LST %{y:.1f} °C<extra></extra>"),
        row=1, col=2)
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_xaxes(title_text="NDVI", row=1, col=2)
    fig.update_yaxes(title_text="Daytime LST (°C)", row=1, col=2)
    buttons = [dict(label=label, method="update",
                    args=[{"visible": [j == i for j in range(3)] + [True]}])
               for i, (label, _) in enumerate(fields.values())]
    fig.update_layout(updatemenus=[dict(buttons=buttons, x=0, y=1.12, xanchor="left")],
                      height=520, margin=dict(l=10, r=10, t=70, b=10),
                      title="West Java districts, 2024 (bubble size = population)",
                      showlegend=False)
    fig.write_html(path, include_plotlyjs="cdn", full_html=True)


def plot_ndvi_lst(df):
    """The static version for print: NDVI against LST, bubble = population."""
    fig, ax = plt.subplots(figsize=(6.5, 4))
    sc = ax.scatter(df["ndvi"], df["lst_c"], s=df["people"] / 2e4, c=df["built_pct"],
                    cmap="Greys", edgecolor="#333", linewidth=0.5)
    for _, r in df.nlargest(5, "lst_c").iterrows():
        ax.annotate(r["district"], (r["ndvi"], r["lst_c"]), fontsize=7,
                    xytext=(4, 2), textcoords="offset points")
    fig.colorbar(sc, ax=ax, label="Built-up share (%)")
    ax.set_xlabel("NDVI, 2024 mean")
    ax.set_ylabel("Daytime LST, 2024 mean (°C)")
    ax.set_title("Greener districts run cooler", loc="left")
    return fig


def products():
    return [
        {"kind": "html", "name": "ch23-dashboard", "build": dashboard_html, "height": 540,
         "caption": "Interactive: switch the indicator, hover a district, compare in "
                    "the scatter. One HTML file, built from one Earth Engine table."},
        {"kind": "chart", "name": "ch23-ndvi-lst", "data": table.select(
            ["district", "ndvi", "lst_c", "built_pct", "people"], retainGeometry=False),
         "plot": plot_ndvi_lst,
         "caption": "Each bubble is a district, sized by population and shaded by "
                    "built-up share."},
        {"kind": "table", "name": "ch23-table", "data": table.select(
            ["district", "ndvi", "lst_c", "built_pct", "people"], retainGeometry=False),
         "columns": ["district", "ndvi", "lst_c", "built_pct", "people"],
         "floatfmt": ("", ".2f", ".1f", ".1f", ",.0f"),
         "caption": "The exported table behind the app and the dashboard."},
    ]


if __name__ == "__main__":
    ee.Initialize()
    dashboard_html("westjava_dashboard.html")
