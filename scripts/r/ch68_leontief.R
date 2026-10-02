#| title: How a spending shock travels through Indonesia's economy (R)
#| description: Builds the Leontief input-output model for Indonesia from the open WIOD national table, computes output, value-added, employment and import multipliers and the backward and forward linkages of every sector, follows a construction shock round by round, and draws a radar chart of six sectors.

# CHAPTER 68 | How a spending shock travels through an economy  (R twin)
# Data: WIOD 2016 release (doi:10.34894/PJ2M1C), downloaded once into IO_DATA.

library(readxl)
library(dplyr)
library(tidyr)
library(ggplot2)

DATA <- Sys.getenv("IO_DATA", "data/io_indonesia"); dir.create(DATA, FALSE, TRUE)
fetch <- function(name, id) {
  f <- file.path(DATA, name)
  if (!file.exists(f)) download.file(paste0("https://dataverse.nl/api/access/datafile/", id), f, mode = "wb")
  f
}
YEAR <- 2014
FD <- c("CONS_h", "CONS_np", "CONS_g", "GFCF", "INVEN", "EXP")

# PART 1. Sectors: 56 WIOD industries grouped into 28 readable ones -----------------------
group <- function(code) {
  c <- gsub("_", "-", code); n <- suppressWarnings(as.integer(substr(c, 2, 3)))
  dplyr::case_when(
    startsWith(c, "A01") ~ "Crops & livestock", startsWith(c, "A02") ~ "Forestry", startsWith(c, "A03") ~ "Fishing",
    startsWith(c, "B") ~ "Mining",
    startsWith(c, "C") & n <= 12 ~ "Food & beverages", startsWith(c, "C") & n <= 15 ~ "Textiles & apparel",
    startsWith(c, "C") & n <= 18 ~ "Wood & paper", startsWith(c, "C") & n == 19 ~ "Petroleum refining",
    startsWith(c, "C") & n <= 21 ~ "Chemicals & pharma", startsWith(c, "C") & n <= 23 ~ "Rubber, plastic & minerals",
    startsWith(c, "C") & n <= 25 ~ "Metals", startsWith(c, "C") & n <= 28 ~ "Electronics & machinery",
    startsWith(c, "C") & n <= 30 ~ "Vehicles", startsWith(c, "C") ~ "Other manufacturing",
    startsWith(c, "D") ~ "Electricity & gas", startsWith(c, "E") ~ "Water & waste", startsWith(c, "F") ~ "Construction",
    startsWith(c, "G") ~ "Trade", startsWith(c, "H") ~ "Transport", startsWith(c, "I") ~ "Hotels & restaurants",
    startsWith(c, "J") ~ "Information & communication", startsWith(c, "K") ~ "Finance", startsWith(c, "L") ~ "Real estate",
    startsWith(c, "M") | startsWith(c, "N") ~ "Business services", startsWith(c, "O") ~ "Public administration",
    startsWith(c, "P") ~ "Education", startsWith(c, "Q") ~ "Health", TRUE ~ "Other services")
}

zipf <- fetch("NIOTS.zip", 199099); seaf <- fetch("SEA.xlsx", 199095)
xl <- unzip(zipf, "IDN_NIOT_nov16.xlsx", exdir = tempdir())
raw <- read_excel(xl, sheet = "National IO-tables")                 # first row holds descriptions:
num <- setdiff(names(raw), c("Code", "Description", "Origin"))       # make the numbers numeric again
raw[num] <- lapply(raw[num], function(v) suppressWarnings(as.numeric(v)))
raw <- filter(raw, !is.na(Year), Year == YEAR)
codes <- raw$Code[raw$Origin == "Domestic"]
g <- group(codes)
agg <- function(m) { m <- rowsum(m, g); t(rowsum(t(m), g)) }          # sum rows and columns by group
dom <- raw[raw$Origin == "Domestic", ]; imp <- raw[raw$Origin == "Imports", ]; tot <- raw[raw$Origin == "TOT", ]
Z <- agg(as.matrix(dom[, codes]))
f <- rowsum(rowSums(as.matrix(dom[, FD])), g)[, 1]
x <- rowsum(dom$GO, g)[, 1]
va <- rowsum(unlist(tot[tot$Code == "VA", codes]), g)[, 1]
m <- rowsum(colSums(as.matrix(imp[, codes])), g)[, 1]
sea <- read_excel(seaf, sheet = "DATA") |> filter(country == "IDN", variable == "EMP")
jobs <- rowsum(sea[[as.character(YEAR)]] * 1000, group(sea$code))[, 1][names(x)]

# PART 2. The Leontief model ------------------------------------------------------------------
A <- sweep(Z, 2, x, "/")                     # a_ij = z_ij / x_j
L <- solve(diag(length(x)) - A)              # Leontief inverse
B <- sweep(Z, 1, x, "/"); G <- solve(diag(length(x)) - B)   # Ghosh, for forward linkage
mult <- data.frame(sector = names(x),
                   output_multiplier = colSums(L),
                   va_multiplier = as.vector((va / x) %*% L),
                   jobs_per_musd = as.vector((jobs / x) %*% L),
                   import_leakage = as.vector((m / x) %*% L),
                   forward_linkage = rowSums(G) / mean(rowSums(G)),
                   output_busd = x / 1000)
mult$backward_linkage <- mult$output_multiplier / mean(mult$output_multiplier)
print(arrange(mult, desc(output_multiplier)), digits = 3)

# A USD 1 billion construction shock, round by round: f + Af + A^2 f + ...
shock <- setNames(rep(0, length(x)), names(x)); shock["Construction"] <- 1000
rounds <- Reduce(function(v, i) A %*% v, 1:6, accumulate = TRUE, init = shock)
cat(sprintf("rounds: %s; total %.0f (Leontief)\n",
            paste(round(sapply(rounds, sum)), collapse = ", "), sum(L %*% shock)))

# PART 3. The radar chart ----------------------------------------------------------------------
sectors <- c("Construction", "Food & beverages", "Crops & livestock", "Electronics & machinery", "Trade", "Mining")
radar <- mult |>
  mutate(domestic_content = 1 - import_leakage / output_multiplier, log_output = log10(output_busd)) |>
  select(sector, output_multiplier, va_multiplier, jobs_per_musd, log_output, forward_linkage, domestic_content) |>
  mutate(across(-sector, \(v) (v - min(v)) / (max(v) - min(v)))) |>
  filter(sector %in% sectors) |>
  pivot_longer(-sector, names_to = "indicator") |>
  mutate(indicator = factor(indicator, levels = unique(indicator)), sector = factor(sector, levels = sectors))
# coord_polar bends straight lines into spirals; a radar chart needs straight edges,
# so declare the polar coordinate system "linear" (no interpolation between points).
coord_radar <- function() ggproto("CoordRadar", CoordPolar, theta = "x", r = "y", start = 0, direction = 1,
                                  is_linear = function(coord) TRUE)
n_ax <- nlevels(radar$indicator)
closed <- bind_rows(mutate(radar, x = as.numeric(indicator)),           # close each polygon at position n + 1,
                    radar |> group_by(sector) |> slice(1) |> mutate(x = n_ax + 1))   # which sits on top of axis 1
ggplot(closed, aes(x, value, group = sector)) +
  geom_polygon(aes(fill = sector), alpha = 0.25, colour = NA) +
  geom_path(aes(colour = sector), linewidth = 1) +
  coord_radar() + facet_wrap(~ sector) +
  scale_y_continuous(limits = c(0, 1)) +
  scale_x_continuous(limits = c(1, n_ax + 1), breaks = seq_len(n_ax),
                     labels = c("output\nmultiplier", "value-added\nmultiplier", "jobs per\nUSD 1 m", "size\n(log output)",
                                "forward\nlinkage", "domestic\ncontent")) +
  labs(title = "Insight 5: no sector wins on every axis",
       subtitle = sprintf("Six indicators rescaled 0 (lowest of %d sectors) to 1 (highest), %d", nrow(mult), YEAR),
       x = NULL, y = NULL) +
  theme_minimal() + theme(legend.position = "none", axis.text.y = element_blank(), axis.text.x = element_text(size = 6))
