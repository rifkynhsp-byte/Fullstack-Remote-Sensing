#| title: Transit service and access in Jakarta from GTFS (R)
#| description: Reads the public TransJakarta GTFS feed, turns its frequency-based timetable into buses per hour per route and per stop, and combines it with WorldPop to model what share of Jakarta's residents live within a walk of frequent service.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

# CHAPTER 67 | What a timetable says about a city  (R twin)
# Reads the GTFS zip and the WorldPop and city layers that the Python twin
# saved to TRANSIT_DATA (Earth Engine is easier from Python).

library(sf)
library(terra)
library(dplyr)
library(ggplot2)

DATA <- Sys.getenv("TRANSIT_DATA", "data/transit_jakarta")
# The exact inputs used for the book (frozen 2 October 2026), downloaded once if not here
if (!file.exists(file.path(DATA, "transjakarta_gtfs.zip"))) {
  dir.create(DATA, FALSE, TRUE); tmp <- tempfile(fileext = ".zip")
  download.file("https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/releases/download/data-v1/ch67_transit_jakarta_inputs.zip", tmp, mode = "wb"); unzip(tmp, exdir = DATA)
}
CRS <- 32748                       # UTM 48S, metres
HOUR <- 8 * 3600                   # 08:00
WALK <- 500                        # metres
zip <- file.path(DATA, "transjakarta_gtfs.zip")
rd <- function(f) read.csv(unz(zip, f), colClasses = "character")
routes <- rd("routes.txt"); trips <- rd("trips.txt"); freq <- rd("frequencies.txt")
stops <- rd("stops.txt"); stop_times <- rd("stop_times.txt"); cal <- rd("calendar.txt")
secs <- function(t) vapply(strsplit(t, ":"), function(x) sum(as.numeric(x) * c(3600, 60, 1)), 0)

# PART 1. Buses per hour on every trip pattern (frequency-based feed) ------------------
buses_per_hour <- function(day = "monday", at = HOUR) {
  services <- cal$service_id[cal[[day]] == "1"]
  freq |>
    mutate(start = secs(start_time), end = secs(end_time), bph = 3600 / as.numeric(headway_secs)) |>
    filter(start <= at, end > at) |>
    inner_join(filter(trips, service_id %in% services) |> select(trip_id, route_id, shape_id), by = "trip_id") |>
    inner_join(select(routes, route_id, route_short_name, route_desc), by = "route_id")
}
b <- buses_per_hour()

# PART 2. Buses per hour at every stop, and how unequal it is ---------------------------
stop_service <- distinct(stop_times, trip_id, stop_id) |>
  inner_join(select(b, trip_id, bph), by = "trip_id") |>
  group_by(stop_id) |> summarise(bph = sum(bph), n_patterns = n_distinct(trip_id)) |>
  inner_join(stops, by = "stop_id") |>
  st_as_sf(coords = c("stop_lon", "stop_lat"), crs = 4326) |> st_transform(CRS) |>
  mutate(headway_min = 60 / bph)

v <- sort(stop_service$bph); cs <- cumsum(v) / sum(v); x <- seq_along(v) / length(v)
gini <- 1 - 2 * sum(diff(c(0, x)) * (cs + c(0, head(cs, -1))) / 2)
top10 <- 1 - approx(x, cs, 0.9)$y
cat(sprintf("stops %d, Gini %.2f, busiest 10%% of stops get %.0f%% of calls\n", nrow(stop_service), gini, 100 * top10))
print(head(arrange(st_drop_geometry(stop_service), desc(bph))[c("stop_name", "bph", "n_patterns")], 10))

ggplot(data.frame(x, cs), aes(x, cs)) +
  geom_abline(linetype = "dotted", colour = "grey50") +
  geom_ribbon(aes(ymin = cs, ymax = x), fill = "#2166ac", alpha = 0.12) +
  geom_line(colour = "#2166ac", linewidth = 1) +
  labs(title = sprintf("Insight 2: the busiest tenth of stops gets %.0f %% of all bus calls", 100 * top10),
       subtitle = "Lorenz curve of buses per hour over stops, 08:00 on a weekday",
       x = "share of stops (least served first)", y = "share of all bus calls per hour") +
  theme_minimal()

# PART 3. Headways by service type (log axis) ------------------------------------------------
b |> mutate(headway_min = as.numeric(headway_secs) / 60) |>
  ggplot(aes(headway_min, reorder(route_desc, headway_min, median))) +
  geom_boxplot(outlier.shape = NA, fill = "grey95") +
  geom_jitter(height = 0.15, alpha = 0.6, size = 1) +
  scale_x_log10(breaks = c(2, 5, 10, 20, 30, 60)) +
  labs(title = "Insight 3: per trip pattern, Mikrotrans is scheduled every 6 minutes and a BRT pattern every 20",
       x = "scheduled headway on each trip pattern (minutes, log scale)", y = NULL) +
  theme_minimal()

# PART 4. Weekday against Sunday ----------------------------------------------------------------
weekend <- full_join(buses_per_hour("monday") |> group_by(route_desc) |> summarise(weekday = sum(bph)),
                     buses_per_hour("sunday") |> group_by(route_desc) |> summarise(sunday = sum(bph)),
                     by = "route_desc") |>
  mutate(across(c(weekday, sunday), \(v) coalesce(v, 0)), change_pct = 100 * (sunday / weekday - 1))
print(weekend)

# PART 5. A model of access: residents within WALK m of a frequent stop ------------------------
pop <- rast(file.path(DATA, "worldpop_jakarta.tif"))
kota <- st_read(file.path(DATA, "kota.gpkg"), quiet = TRUE)
cells <- as.data.frame(pop, xy = TRUE, na.rm = TRUE) |> setNames(c("x", "y", "people")) |> filter(people > 0)
cells <- st_as_sf(cells, coords = c("x", "y"), crs = 4326) |> st_join(kota, left = FALSE) |> st_transform(CRS)
access <- lapply(c(3, 5, 10, 15, 20, 30, 60), function(h) {
  f <- stop_service[stop_service$headway_min <= h, ]
  near <- lengths(st_is_within_distance(cells, f, WALK)) > 0
  cells |> st_drop_geometry() |> mutate(near = near) |> group_by(kota) |>
    summarise(share = 100 * sum(people[near]) / sum(people)) |> mutate(headway_max_min = h) |>
    bind_rows(data.frame(kota = "DKI Jakarta (5 cities)", headway_max_min = h,
                         share = 100 * sum(cells$people[near]) / sum(cells$people)))
}) |> bind_rows()
print(tidyr::pivot_wider(access, names_from = headway_max_min, values_from = share))

ggplot(access, aes(headway_max_min, share, colour = kota)) +
  geom_line(aes(linewidth = kota == "DKI Jakarta (5 cities)")) + geom_point() +
  scale_linewidth_manual(values = c(0.6, 1.8), guide = "none") +
  scale_x_log10(breaks = c(3, 5, 10, 15, 20, 30, 60)) + ylim(0, 100) +
  labs(title = "Insight 5: nine in ten residents live within 500 m of a stop served at least every 10 minutes",
       x = "a bus at least every ... minutes (combined headway at the stop)",
       y = "residents within 500 m of such a stop (%)", colour = NULL) +
  theme_minimal()
