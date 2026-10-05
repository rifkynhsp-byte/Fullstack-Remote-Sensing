#| title: An urban planning toolkit for Surabaya: the analysis (R)
#| description: Reads the hexagon table and OpenStreetMap parks the Python twin built, then maps green cover, park access, heat and density on the H3 grid, fits the two regressions that show how 'green' flips sign, tests the residuals with Moran's I, and ranks greening priorities with a weight-sensitivity test.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

# CHAPTER 73 | An urban planning toolkit  (R twin)
# Reads data/ch73_surabaya_hex.csv and data/ch73_surabaya_parks.geojson.
# H3 polygons are rebuilt here with h3jsr if installed; otherwise points are used.

library(dplyr)
library(ggplot2)
library(sf)

DATA <- Sys.getenv("PLAN_DATA", "data")
UTM <- 32749; WALK <- 400; RTH_TARGET <- 30
hx <- read.csv(file.path(DATA, "ch73_surabaya_hex.csv")) |>
  mutate(people_ha = people / area_ha,
         park_access_pct = ifelse(people > 0, 100 * people_near_park / people, NA))
parks <- st_read(file.path(DATA, "ch73_surabaya_parks.geojson"), quiet = TRUE)

# Hexagon outlines: h3jsr if available, otherwise draw each cell as a point at its centre
if (requireNamespace("h3jsr", quietly = TRUE)) {
  hx_sf <- st_sf(hx, geometry = h3jsr::cell_to_polygon(hx$h3))
} else {
  hx_sf <- st_as_sf(hx, coords = c("lon", "lat"), crs = 4326, remove = FALSE)
}

# PART 1. Green open space and park access ---------------------------------------------------
w <- hx$area_ha
data.frame(
  measure = c("green cover, whole city (%)", "tree cover, whole city (%)", "hexagons meeting the 30 % target",
              "hexagons below 10 % green", "residents in hexagons below 10 % green (%)",
              "residents within 400 m of a park >= 0.5 ha (%)"),
  value = c(weighted.mean(hx$green_pct, w), weighted.mean(hx$tree_pct, w), sum(hx$green_pct >= RTH_TARGET),
            sum(hx$green_pct < 10), 100 * sum(hx$people[hx$green_pct < 10]) / sum(hx$people),
            100 * sum(hx$people_near_park) / sum(hx$people))) |> print()

# PART 2. Two regressions: the sign of 'green' depends on what it replaces ---------------------
g <- hx |> filter(!is.na(lst_c), people > 0) |> mutate(log_people_ha = log1p(people_ha))
mA <- lm(lst_c ~ green_pct, data = g)
mB <- lm(lst_c ~ green_pct + built_pct + log_people_ha, data = g)
print(summary(mA)$coefficients); print(summary(mB)$coefficients)
cat(sprintf("R2: A %.3f, B %.3f\n", summary(mA)$r.squared, summary(mB)$r.squared))

# Moran's I with H3 ring-1 neighbours, row-standardised, 999 permutations
if (requireNamespace("h3jsr", quietly = TRUE)) {
  ring <- h3jsr::get_ring(g$h3, ring_size = 1)
  nb <- lapply(seq_along(ring), function(i) setdiff(match(ring[[i]], g$h3), c(i, NA)))
} else {                                       # fallback: neighbours within 1.1 km of each centre
  xy <- st_coordinates(st_transform(st_as_sf(g, coords = c("lon", "lat"), crs = 4326), UTM))
  d <- as.matrix(dist(xy)); nb <- lapply(seq_len(nrow(d)), function(i) setdiff(which(d[i, ] < 1100), i))
}
moran <- function(x, nb, nperm = 999) {
  z <- x - mean(x)
  stat <- function(v) sum(v * sapply(nb, function(n) if (length(n)) mean(v[n]) else 0)) / sum(v^2)
  obs <- stat(z); set.seed(0); perm <- replicate(nperm, stat(sample(z)))
  c(I = obs, p = (1 + sum(perm >= obs)) / (nperm + 1))
}
print(rbind(LST = moran(g$lst_c, nb), residuals_B = moran(resid(mB), nb)))

ggplot(g, aes(green_pct, lst_c, colour = built_pct)) + geom_point(size = 1) +
  geom_abline(intercept = coef(mA)[1], slope = coef(mA)[2], colour = "#2166ac") +
  geom_abline(intercept = coef(mB)[1] + coef(mB)[3] * mean(g$built_pct) + coef(mB)[4] * mean(g$log_people_ha),
              slope = coef(mB)[2], linetype = "dashed") +
  scale_colour_distiller(palette = "RdPu", direction = 1, name = "built-up (%)") +
  labs(x = "green cover (%)", y = "land surface temperature (°C)",
       title = "Green only (solid) against built-up held fixed (dashed)") + theme_minimal()

# PART 3. Greening priority and its robustness to the weights -------------------------------------
crit <- c(lst_c = 1, people_ha = 1, green_pct = -1, park_access_pct = -1)
p <- hx |> filter(!is.na(lst_c), people >= 500)
Z <- sapply(names(crit), function(k) { v <- p[[k]]; v[is.na(v)] <- median(v, na.rm = TRUE); crit[k] * (v - mean(v)) / sd(v) })
p$score <- Z %*% rep(0.25, 4)
top <- order(-p$score)[1:10]
set.seed(42)
W <- matrix(rgamma(4000, 1), ncol = 4); W <- W / rowSums(W)          # 1,000 Dirichlet(1,1,1,1) weightings
hits <- tabulate(as.vector(apply(W, 1, function(wt) order(-(Z %*% wt))[1:10])), nbins = nrow(p))
p$robust_pct <- 100 * hits / 1000
print(p[top, c("h3", "lon", "lat", "lst_c", "people_ha", "green_pct", "park_access_pct", "score", "robust_pct")])

ggplot(st_transform(hx_sf, UTM)) + geom_sf(aes(fill = green_pct, colour = green_pct)) +
  geom_sf(data = st_transform(parks, UTM), fill = NA, colour = "#08306b", linewidth = 0.2) +
  scale_fill_distiller(palette = "Greens", direction = 1, limits = c(0, 60), oob = scales::squish, name = "green (%)") +
  scale_colour_distiller(palette = "Greens", direction = 1, limits = c(0, 60), oob = scales::squish, guide = "none") +
  coord_sf(datum = 4326) +                      # graticule in degrees on a UTM map
  labs(title = "Green cover per hexagon, with OpenStreetMap parks") + theme_minimal()

# PART 4. Building on low ground ---------------------------------------------------------------------
land_low <- weighted.mean(hx$low_pct, w); new_low <- 100 * sum(hx$new_bldg_low_m2) / sum(hx$new_bldg_m2)
cat(sprintf("land below 3 m: %.1f %%; new building there: %.1f %%; location quotient %.2f\n", land_low, new_low, new_low / land_low))
