#| title: Smoke from space: the 2019 haze, the analysis (R)
#| description: Reads the daily fire and CO series the Python twin drew from Earth Engine, then draws the three-panel season chart, the longitude-time (Hovmöller) diagram and the lag analysis of fires against downwind smoke with ggplot2.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

# CHAPTER 71 | Smoke from space  (R twin)
# Reads data/ch71_haze_daily.csv and data/ch71_haze_hovmoller.csv
# (the animations need Earth Engine, so they live in the JavaScript and Python tabs).

library(dplyr)
library(tidyr)
library(ggplot2)

d <- read.csv(Sys.getenv("HAZE_CSV", "data/ch71_haze_daily.csv")) |> mutate(date = as.Date(date), year = as.integer(format(date, "%Y")))
hov <- read.csv(Sys.getenv("HAZE_HOV", "data/ch71_haze_hovmoller.csv")) |> mutate(date = as.Date(date))
sources <- c("Sumatra", "Kalimantan")
cities <- c("Pekanbaru", "Palangka Raya", "Pontianak", "Singapore", "Kuching", "Kuala Lumpur")

# PART 1. The season in numbers: 2019 against 2020 ----------------------------------------
fires <- d |> filter(name %in% sources) |> group_by(name, year) |> summarise(fire_pixels = sum(fires), .groups = "drop")
smoky <- d |> filter(name %in% cities) |> group_by(name, year) |> summarise(days_co_over_50 = sum(co > 50, na.rm = TRUE), .groups = "drop")
print(pivot_wider(fires, names_from = year, values_from = fire_pixels))
print(pivot_wider(smoky, names_from = year, values_from = days_co_over_50))

# PART 2. Fires, smoke, baseline: one figure, three panels ------------------------------------
roll <- function(x, k) as.numeric(stats::filter(x, rep(1 / k, k), sides = 2))
p_fire <- d |> filter(year == 2019, name %in% sources) |>
  ggplot(aes(date, fires, fill = name)) + geom_col(width = 1) +
  scale_fill_manual(values = c(Sumatra = "#e08214", Kalimantan = "#b2182b")) +
  labs(title = "1. The fires: FIRMS detections in the six fire provinces, 2019", x = NULL, y = "fire pixels per day", fill = NULL)
p_co <- d |> filter(year == 2019, name %in% cities) |> group_by(name) |> mutate(co3 = roll(co, 3)) |>
  ggplot(aes(date, co3, colour = name)) + geom_line(linewidth = 0.6) +
  geom_hline(yintercept = 50, linetype = "dotted", colour = "grey50") +
  labs(title = "2. The smoke: Sentinel-5P CO over six cities (3-day mean)", x = NULL, y = "CO column (mmol/m²)", colour = NULL)
p_base <- d |> filter(name %in% c("Palangka Raya", "Singapore")) |> group_by(name, year) |>
  mutate(co7 = roll(co, 7), day = as.Date(format(date, "2019-%m-%d"))) |>
  ggplot(aes(day, co7, colour = name, linetype = factor(year))) + geom_line(linewidth = 0.7) +
  scale_colour_manual(values = c("Palangka Raya" = "#b2182b", Singapore = "#2166ac")) +
  labs(title = "3. The baseline: the same months in 2020, a wet year", x = NULL, y = "CO (7-day mean)", colour = NULL, linetype = NULL)
for (p in list(p_fire, p_co, p_base)) print(p + theme_minimal() + theme(legend.position = "top"))

# PART 3. Hovmöller: the season in one picture ----------------------------------------------------
ggplot(hov, aes(lon, date, fill = co)) + geom_tile() +
  scale_fill_distiller(palette = "YlOrBr", direction = 1, limits = c(25, 120), oob = scales::squish, name = "CO\n(mmol/m²)") +
  geom_vline(xintercept = c(101.45, 103.82, 109.33, 113.92), linetype = "dotted", linewidth = 0.3) +
  annotate("text", x = c(101.45, 103.82, 109.33, 113.92), y = min(hov$date), label = c("Pekanbaru", "Singapore", "Pontianak", "Palangka Raya"),
           angle = 90, hjust = 0, vjust = -0.3, size = 2.5) +
  labs(x = "longitude (°E), mean over 3° S to 3° N", y = "2019",
       title = "Longitude-time (Hovmöller) diagram of CO") + theme_minimal()

# PART 4. How long does the smoke take to arrive? ----------------------------------------------
# Both series rise through the dry season, so correlate anomalies from a 15-day running mean.
# A centred 15-day mean that skips missing days (cloud) and needs at least 5 values, like pandas' rolling(min_periods=5)
roll_na <- function(x, k = 15, min_n = 5) sapply(seq_along(x), function(i) {
  v <- x[max(1, i - k %/% 2):min(length(x), i + k %/% 2)]
  if (sum(!is.na(v)) >= min_n) mean(v, na.rm = TRUE) else NA })
anom <- function(x) x - roll_na(x)
w <- d |> filter(year == 2019) |> mutate(v = ifelse(name %in% sources, fires, co)) |>
  select(date, name, v) |> pivot_wider(names_from = name, values_from = v) |> arrange(date)
pairs <- list(c("Sumatra", "Pekanbaru"), c("Sumatra", "Singapore"), c("Sumatra", "Kuala Lumpur"),
              c("Kalimantan", "Palangka Raya"), c("Kalimantan", "Pontianak"), c("Kalimantan", "Kuching"))
lags <- do.call(rbind, lapply(pairs, function(p) {
  f <- anom(w[[p[1]]]); co <- anom(w[[p[2]]])
  data.frame(pair = paste(p[1], "→", p[2]), source = p[1], lag = 0:7,
             r = sapply(0:7, function(L) cor(f, dplyr::lead(co, L), use = "complete.obs")))
}))
print(lags |> group_by(pair) |> slice_max(r, n = 1))
ggplot(lags, aes(lag, r, colour = pair, linetype = source)) + geom_line() + geom_point(size = 1) +
  geom_hline(yintercept = 0, colour = "grey60") +
  labs(x = "CO measured this many days after the fires", y = "correlation of anomalies", colour = NULL, linetype = NULL,
       title = "How long the smoke takes to arrive") + theme_minimal()
