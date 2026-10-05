#| title: LiDAR beyond the forest: the analysis (R)
#| description: Reads the Oso transect and slope statistics and the Rotterdam cell sample and totals that the Python twin drew from Earth Engine, then draws the terrain profile, the height distributions and the roof-slope histogram, and recomputes the city indicators.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

# CHAPTER 74 | LiDAR beyond the forest  (R twin)
# Reads data/ch74_oso_profile.csv, ch74_oso_slopes.csv, ch74_rotterdam_sample.csv and ch74_rotterdam_totals.csv.

library(dplyr)
library(tidyr)
library(ggplot2)

DATA <- Sys.getenv("LIDAR_DATA", "data")
rd <- function(f) read.csv(file.path(DATA, paste0("ch74_", f, ".csv")), check.names = FALSE)
SOLAR_KWH_M2 <- 1000; PANEL_EFF <- 0.20          # screening assumptions, as in the Python tab

# PART 1. Oso: one slope, three terrain models -------------------------------------------------
print(rd("oso_slopes"))
prof <- rd("oso_profile") |> pivot_longer(-distance_m, names_to = "DEM", values_to = "elev")
pr <- rd("oso_profile")
plat <- filter(pr, distance_m >= 700, distance_m < 1250)      # forested plateau
dep <- filter(pr, distance_m >= 1650, distance_m < 2000)       # the 2014 deposit on the valley floor
cat(sprintf("plateau: SRTM %.0f m and Copernicus %.0f m above the LiDAR ground (canopy)\n",
            mean(plat$`SRTM 30 m (2000)` - plat$`LiDAR 1 m (3DEP 2016)`), mean(plat$`Copernicus 30 m` - plat$`LiDAR 1 m (3DEP 2016)`)))
cat(sprintf("deposit: LiDAR %.0f m above the older DEMs\n",
            mean(dep$`LiDAR 1 m (3DEP 2016)` - (dep$`SRTM 30 m (2000)` + dep$`Copernicus 30 m`) / 2)))
ggplot(prof, aes(distance_m, elev, colour = DEM, linewidth = DEM)) + geom_line() +
  scale_colour_manual(values = c("LiDAR 1 m (3DEP 2016)" = "black", "SRTM 30 m (2000)" = "#d95f02", "Copernicus 30 m" = "#1b9e77")) +
  scale_linewidth_manual(values = c(0.5, 0.8, 0.8), guide = "none") +
  labs(x = "distance along the transect, north to south (m)", y = "elevation (m)", colour = NULL,
       title = "Across the Oso slide: LiDAR (2016) against two 30 m DEMs") + theme_minimal()

# PART 2. Rotterdam: a city from surface minus ground ---------------------------------------------
r <- rd("rotterdam_totals")
land <- r$total - r$water
data.frame(
  measure = c("area of the box (ha)", "open water (%)", "ground below sea level, share of land (%)",
              "building footprint, share of land (%)", "tree canopy, share of land (%)", "mean building height (m)",
              "built volume per ha of land (m3)", "roof area suitable for solar (% of roofs)", "screening solar yield (GWh/yr)"),
  value = c(r$total / 1e4, 100 * r$water / r$total, 100 * r$below_sea / land, 100 * r$building / land, 100 * r$tree / land,
            r$volume / r$building, r$volume / (land / 1e4), 100 * r$solar / r$roof,
            r$solar * SOLAR_KWH_M2 * PANEL_EFF / 1e6)) |> print()

d <- rd("rotterdam_sample")
h <- bind_rows(d |> filter(building == 1) |> transmute(class = "buildings", ndsm),
               d |> filter(tree == 1) |> transmute(class = "trees", ndsm))
print(h |> group_by(class) |> summarise(n = n(), median_height = median(ndsm), p90 = quantile(ndsm, 0.9)))
ggplot(h, aes(ndsm, fill = class)) + geom_histogram(binwidth = 1.5, boundary = 2.5, position = "identity", alpha = 0.7) +
  scale_fill_manual(values = c(buildings = "#636363", trees = "#1b7837")) + scale_y_log10() +
  coord_cartesian(xlim = c(2.5, 60)) +
  labs(x = "height above ground (m)", y = "0.5 m cells in the sample (log)", fill = NULL, title = "Heights: buildings against trees") +
  theme_minimal()
ggplot(filter(d, building == 1), aes(pmin(roof_slope, 70))) + geom_histogram(binwidth = 2, boundary = 0, fill = "#e6550d") +
  geom_vline(xintercept = 10, linetype = "dotted") +
  labs(x = "roof slope (°)", y = "cells", title = "Roof slopes in central Rotterdam") + theme_minimal()
