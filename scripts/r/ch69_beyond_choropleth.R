#| title: Maps that answer questions, beyond the choropleth (R)
#| description: Indonesia's provinces with population and night lights, drawn as totals against rates, three classification schemes, a bivariate choropleth, a Dorling cartogram and a dot-density map, and Riau's land-cover change 2004-2024 as an alluvial (Sankey) diagram.

# CHAPTER 69 | Maps that answer questions  (R twin)
# Reads the layers the Python twin saved from Earth Engine to MAP_DATA.
# geom_sf draws a labelled lon/lat graticule by default: keep it.

library(sf)
library(terra)
library(dplyr)
library(ggplot2)
library(classInt)
library(cartogram)
library(ggalluvial)

DATA <- Sys.getenv("MAP_DATA", "data/maps_indonesia")
# The exact inputs used for the book (frozen 2 October 2026), downloaded once if not here
if (!file.exists(file.path(DATA, "provinces.gpkg"))) {
  dir.create(DATA, FALSE, TRUE); tmp <- tempfile(fileext = ".zip")
  download.file("https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/releases/download/data-v1/ch69_maps_indonesia_inputs.zip", tmp, mode = "wb"); unzip(tmp, exdir = DATA)
}
sf_use_s2(FALSE)
g <- st_read(file.path(DATA, "provinces.gpkg"), quiet = TRUE) |>
  st_collection_extract("POLYGON") |> group_by(province, population, light, area_km2) |> summarise(.groups = "drop") |>
  mutate(density = population / area_km2, light_per_1000 = 1000 * light / population)
box <- coord_sf(xlim = c(94.5, 141.5), ylim = c(-11.5, 6.5), expand = FALSE)

# Insight 1. Totals against rates ---------------------------------------------------------------
ggplot(g) + geom_sf(aes(fill = cut(population / 1e6, quantile(population / 1e6, 0:5 / 5), include.lowest = TRUE)),
                    colour = "white", linewidth = 0.1) +
  scale_fill_brewer(palette = "Blues", name = "population (million)") + box +
  labs(title = "Total: how many people live there") + theme_minimal()
ggplot(g) + geom_sf(aes(fill = cut(density, quantile(density, 0:5 / 5), include.lowest = TRUE)), colour = "white", linewidth = 0.1) +
  scale_fill_brewer(palette = "Purples", name = "people per km²") + box +
  labs(title = "Rate: how crowded it is") + theme_minimal()

# Insight 2. Three classification schemes ---------------------------------------------------------
for (style in c("equal", "quantile", "fisher")) {
  ci <- classIntervals(g$density, 5, style = style)
  cat(style, ": provinces per class", table(findCols(ci)), "| breaks", round(ci$brks), "\n")
  print(ggplot(g) + geom_sf(aes(fill = cut(density, ci$brks, include.lowest = TRUE, dig.lab = 6)), colour = "white", linewidth = 0.1) +
          scale_fill_brewer(palette = "YlOrRd", name = "people per km²") + box + labs(title = style) + theme_minimal())
}

# Insight 3. Bivariate choropleth (3 x 3) -----------------------------------------------------------
pal <- c("1-1" = "#e8e8e8", "1-2" = "#ace4e4", "1-3" = "#5ac8c8", "2-1" = "#dfb0d6", "2-2" = "#a5add3", "2-3" = "#5698b9",
         "3-1" = "#be64ac", "3-2" = "#8c62aa", "3-3" = "#3b4994")
g <- g |> mutate(bi = paste(ntile(density, 3), ntile(light_per_1000, 3), sep = "-"))
cat("crowded but dim:", sum(g$bi == "3-1"), "| sparse but bright:", sum(g$bi == "1-3"), "\n")
ggplot(g) + geom_sf(aes(fill = bi), colour = "white", linewidth = 0.1) + scale_fill_manual(values = pal, guide = "none") + box +
  labs(title = "Insight 3: Java is crowded but dim per person (pink)",
       subtitle = "rows: people per km² terciles; columns: night light per 1,000 residents terciles") + theme_minimal()

# Insight 4. Dorling cartogram (equal-area projection) --------------------------------------------------
dor <- cartogram_dorling(st_transform(g, 6933), "population", k = 0.6)
ggplot() + geom_sf(data = st_transform(g, 6933), fill = "grey95", colour = "grey80", linewidth = 0.1) +
  geom_sf(data = dor, aes(fill = log10(density)), colour = "white") +
  scale_fill_distiller(palette = "Purples", direction = 1, name = "log10 density") +
  labs(title = "Insight 4: drawn by people instead of land, Java dominates") + theme_minimal()

# Insight 5. Dot density: one dot per 20,000 people --------------------------------------------------------
pop <- rast(file.path(DATA, "worldpop_5km.tif"))
cells <- as.data.frame(pop, xy = TRUE, na.rm = TRUE) |> setNames(c("x", "y", "p")) |> filter(p > 0)
set.seed(1); n <- rpois(nrow(cells), cells$p / 20000)
dots <- data.frame(x = rep(cells$x, n) + runif(sum(n), -0.025, 0.025), y = rep(cells$y, n) + runif(sum(n), -0.025, 0.025)) |>
  st_as_sf(coords = c("x", "y"), crs = 4326) |> st_filter(g)             # Indonesia only
cat("dots:", nrow(dots), "\n")
ggplot() + geom_sf(data = g, fill = "grey95", colour = "grey80", linewidth = 0.1) +
  geom_sf(data = dots, size = 0.05, colour = "#08306b", alpha = 0.5) + box +
  labs(title = "Insight 5: one dot per 20,000 people") + theme_minimal()

# Insight 6. Riau land cover 2004 -> 2024 as an alluvial (Sankey) diagram --------------------------------------
simple <- c("Evergreen broadleaf forest" = "Forest", "Deciduous broadleaf forest" = "Forest", "Mixed forest" = "Forest",
            "Evergreen needleleaf forest" = "Forest", "Woody savanna" = "Savanna & shrub", "Savanna" = "Savanna & shrub",
            "Closed shrubland" = "Savanna & shrub", "Open shrubland" = "Savanna & shrub")
tr <- read.csv(file.path(DATA, "riau_landcover_2004_2024.csv")) |>
  mutate(from = coalesce(simple[from], "Other (wetland, crops, grass, urban, water)"),
         to = coalesce(simple[to], "Other (wetland, crops, grass, urban, water)")) |>
  group_by(from, to) |> summarise(km2 = sum(km2), .groups = "drop")
forest <- c(sum(tr$km2[tr$from == "Forest"]), sum(tr$km2[tr$to == "Forest"]))
cat(sprintf("Riau forest 2004 %.0f km2, 2024 %.0f km2, net change %.0f km2\n", forest[1], forest[2], forest[2] - forest[1]))
ggplot(tr, aes(axis1 = from, axis2 = to, y = km2)) +
  geom_alluvium(aes(fill = from), alpha = 0.5) + geom_stratum(width = 0.08) +
  geom_text(stat = "stratum", aes(label = after_stat(stratum)), size = 2.6, hjust = -0.1, nudge_x = 0.05) +
  scale_x_discrete(limits = c("2004", "2024")) +
  scale_fill_manual(values = c("Forest" = "#1b7837", "Savanna & shrub" = "#b8e186",
                               "Other (wetland, crops, grass, urban, water)" = "#bdbdbd"), guide = "none") +
  labs(title = "Insight 6: Riau's mapped forest, 2004 to 2024 (MODIS)", y = "km²") + theme_minimal()
