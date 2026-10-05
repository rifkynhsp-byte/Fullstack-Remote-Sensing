#| title: Solar insight charts (R)
#| description: Ten years of hourly PVGIS-ERA5 irradiance for Kupang and Bandung turned into five insight charts with ggplot2 - a day-by-hour heatmap, a clearness-index scatter with physical limits, hourly ramp boxes with extreme events, monthly PV yield bars and monthly diurnal small multiples.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

# CHAPTER 66 | One chart, one question
#
#   Insight 1  heatmap (day x hour)       when is there sun, and when is it missing?
#   Insight 2  clearness scatter (k-space) is the data physically possible?
#   Insight 3  hourly ramp boxes          how fast does the resource change?
#   Insight 4  monthly yield bars         what will a PV system produce, and how
#                                         much does that vary from year to year?
#   Insight 5  small multiples            how do two climates differ, month by month?
#
# Data: PVGIS v5.3 hourly series (EU Joint Research Centre), free, no key.
# Kupang and Bandung, 2014-2023, PVGIS-ERA5. Timestamps are UTC.

library(jsonlite)
library(dplyr)
library(tidyr)
library(ggplot2)

API <- "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
CACHE <- Sys.getenv("SOLAR_CACHE", "data/solar_insight"); dir.create(CACHE, FALSE, TRUE)
SITES <- data.frame(site = c("Kupang", "Bandung"), lat = c(-10.17, -6.91), lon = c(123.61, 107.61), utc = c(8, 7))
YEARS <- c(2014, 2023)

pvgis <- function(site, pv = FALSE) {
  s <- SITES[SITES$site == site, ]
  f <- file.path(CACHE, paste0(site, if (pv) "_pv" else "_h", ".json"))
  if (!file.exists(f)) {
    q <- sprintf("%s?lat=%s&lon=%s&startyear=%d&endyear=%d&outputformat=json&raddatabase=PVGIS-ERA5",
                 API, s$lat, s$lon, YEARS[1], YEARS[2])
    # PVGIS aspect: 0 = south, 180 = north; south of the equator face north
    q <- paste0(q, if (pv) "&pvcalculation=1&peakpower=1&loss=14&angle=10&aspect=180" else "&components=1&angle=0")
    download.file(q, f, quiet = TRUE, mode = "wb")
  }
  d <- fromJSON(f)$outputs$hourly
  d$utc <- as.POSIXct(d$time, format = "%Y%m%d:%H%M", tz = "UTC")
  d$local <- d$utc + s$utc * 3600
  d$site <- site
  d
}

hourly <- function(site) {
  d <- pvgis(site)
  d$ghi <- d$`Gb(i)` + d$`Gd(i)`; d$dhi <- d$`Gd(i)`          # horizontal plane: beam + diffuse
  doy <- as.integer(format(d$utc, "%j"))
  g0 <- 1361 * (1 + 0.033 * cos(2 * pi * doy / 365)) * sin(pmax(d$H_sun, 0) * pi / 180)
  day <- d$H_sun > 5                                          # skip low sun, where ratios explode
  d$kt <- ifelse(day, d$ghi / g0, NA)                         # clearness index
  d$kd <- ifelse(day & d$ghi > 0, d$dhi / d$ghi, NA)          # diffuse fraction
  d$date <- as.Date(d$local); d$hour <- as.integer(format(d$local, "%H"))
  d$month <- as.integer(format(d$local, "%m"))
  d
}
H <- bind_rows(lapply(SITES$site, hourly))

# The house style: a headline that states the finding, a subtitle that says what is plotted.
insight <- theme_minimal(base_size = 10) +
  theme(plot.title = element_text(face = "bold", size = 11), plot.subtitle = element_text(colour = "grey30", size = 8),
        plot.title.position = "plot", panel.grid.minor = element_blank())

# Insight 1. Heatmap: when is there sun? --------------------------------------------------
p1 <- H |> filter(site == "Kupang", format(local, "%Y") == "2023") |>
  complete(date = seq(as.Date("2023-01-01"), as.Date("2023-12-31"), by = "day"), hour = 0:23) |>
  ggplot(aes(date, hour, fill = ghi)) + geom_raster() +
  scale_fill_viridis_c(option = "inferno", na.value = "grey25", limits = c(0, 1100), name = "GHI (W/m²)") +
  scale_y_continuous(breaks = c(0, 6, 12, 18, 24), expand = c(0, 0)) + scale_x_date(date_labels = "%b", expand = c(0, 0)) +
  labs(title = "Insight 1: Kupang's brightest weeks are September to November; the wet season shows as broken days",
       subtitle = "Hourly global horizontal irradiance, 2023. Each column is a day, each row a local hour; dark grey would mark missing hours.",
       x = NULL, y = "local hour") + insight
print(p1)

# Insight 2. k-space: is the data physically possible? -----------------------------------
k <- H |> filter(!is.na(kt), !is.na(kd))
print(k |> group_by(site) |> summarise(daylight_hours = n(), kt_above_1 = mean(kt > 1) * 100,
                                         kd_above_1 = mean(kd > 1) * 100, overcast = mean(kt < 0.3) * 100,
                                         clear = mean(kt > 0.65) * 100))
p2 <- ggplot(k, aes(kt, kd)) + geom_hex(bins = 60) + scale_fill_viridis_c(trans = "log10", name = "hours") +
  geom_hline(yintercept = 1, colour = "#d73027", linetype = "dashed") +
  geom_vline(xintercept = 1, colour = "#d73027", linetype = "dashed") +
  facet_wrap(~site) + coord_cartesian(xlim = c(0, 1.1), ylim = c(0, 1.05)) +
  labs(title = "Insight 2: no hour breaks the physical limits; Kupang crowds the clear-sky corner, Bandung spreads to overcast",
       subtitle = "Hourly clearness index against diffuse fraction, sun above 5°, 2014–2023. Points beyond a red line would be impossible.",
       x = "clearness index kt = GHI / extraterrestrial", y = "diffuse fraction kd = DHI / GHI") + insight
print(p2)

# Insight 3. Ramps: how fast does the resource change? -------------------------------------
r <- H |> filter(site == "Kupang") |> arrange(utc) |> mutate(ramp = ghi - lag(ghi)) |>
  filter(hour >= 6, hour <= 18, !is.na(ramp))
lim <- quantile(abs(r$ramp), 0.999)
p3 <- ggplot(r, aes(factor(hour), ramp)) +
  stat_summary(fun.data = function(v) data.frame(ymin = quantile(v, .05), lower = quantile(v, .25), middle = median(v),
                                                 upper = quantile(v, .75), ymax = quantile(v, .95)),
               geom = "boxplot", fill = "#c6dbef", colour = "#4292c6") +
  stat_summary(aes(group = 1), fun = mean, geom = "line", colour = "grey35") +
  geom_point(data = filter(r, abs(ramp) > lim), shape = 4, colour = "#cb181d") +
  geom_hline(yintercept = 0, colour = "grey60") +
  labs(title = "Insight 3: in Kupang the sharpest changes are sudden afternoon drops, at 13:00 and 14:00",
       subtitle = sprintf("Hour-to-hour change in GHI, 2014–2023. Boxes: middle half; whiskers: 5th–95th percentiles; crosses: |ramp| > %.0f W/m²/h (top 0.1 %%).", lim),
       x = "local hour", y = "GHI change (W/m² per hour)") + insight
print(p3)

# Insight 4. Monthly PV yield, and its year-to-year spread ---------------------------------
Y <- bind_rows(lapply(SITES$site, function(s) pvgis(s, pv = TRUE))) |>
  mutate(year = as.integer(format(local, "%Y")), month = as.integer(format(local, "%m"))) |>
  filter(year >= YEARS[1], year <= YEARS[2]) |>
  group_by(site, year, month) |> summarise(kwh = sum(P) / 1000, .groups = "drop") |>
  group_by(site, month) |> summarise(mean = mean(kwh), min = min(kwh), max = max(kwh), .groups = "drop")
print(Y |> group_by(site) |> summarise(annual_kWh_per_kWp = sum(mean)))
p4 <- ggplot(Y, aes(factor(month), mean, fill = site)) +
  geom_col(position = position_dodge(0.8), width = 0.75) +
  geom_errorbar(aes(ymin = min, ymax = max), position = position_dodge(0.8), width = 0.25, colour = "grey20") +
  scale_fill_manual(values = c(Kupang = "#e6550d", Bandung = "#3182bd")) +
  scale_x_discrete(labels = month.abb) +
  labs(title = "Insight 4: Kupang out-yields Bandung in every month, by the most in October and November",
       subtitle = "Mean monthly yield of a 1 kWp system (10° tilt towards the equator, 14 % losses); whiskers: lowest and highest year, 2014–2023.",
       x = NULL, y = "PV yield (kWh per kWp per month)", fill = NULL) + insight
print(p4)

# Insight 5. Small multiples: the average day, month by month -------------------------------
D <- H |> group_by(site, month, hour) |> summarise(mean = mean(ghi), p90 = quantile(ghi, 0.9), .groups = "drop") |>
  mutate(month = factor(month.abb[month], levels = month.abb))
p5 <- ggplot(D, aes(hour, colour = site, fill = site)) +
  geom_ribbon(aes(ymin = mean, ymax = p90), alpha = 0.15, colour = NA) + geom_line(aes(y = mean), linewidth = 0.8) +
  facet_wrap(~month, nrow = 2) + coord_cartesian(xlim = c(5, 19)) + scale_x_continuous(breaks = c(6, 12, 18)) +
  scale_colour_manual(values = c(Kupang = "#e6550d", Bandung = "#3182bd")) +
  scale_fill_manual(values = c(Kupang = "#e6550d", Bandung = "#3182bd")) +
  labs(title = "Insight 5: the two sites have almost the same day from June to August and part most from October to March",
       subtitle = "Mean hourly GHI by local hour (line) up to the 90th percentile (shading), one panel per month, 2014–2023.",
       x = "local hour", y = "GHI (W/m²)", colour = NULL, fill = NULL) + insight
print(p5)
