#| title: Urban growth and population: the analysis (R)
#| description: Reads the GHSL tables and the growth sample the Python twin drew from Earth Engine, then draws the urbanisation chart, the radial sprawl profile and the SDG 11.3.1 scatter, and fits the urban growth model (glm and ranger) with spatially blocked cross-validation.

# CHAPTER 72 | Urban growth  (R twin)
# Reads data/ch72_urbanisation.csv, ch72_radial.csv, ch72_sdg11.csv and ch72_growth_sample.csv.

library(dplyr)
library(tidyr)
library(ggplot2)
library(ranger)
library(pROC)

DATA <- Sys.getenv("URBAN_DATA", "data")
rd <- function(f) read.csv(file.path(DATA, paste0("ch72_", f, ".csv")))

# PART 1. How urban is Indonesia? ---------------------------------------------------------
urb <- rd("urbanisation") |>
  mutate(class = case_when(smod == 30 ~ "city (urban centre)", smod >= 21 ~ "town and suburb (urban cluster)", TRUE ~ "rural")) |>
  group_by(year, class) |> summarise(people = sum(people), .groups = "drop") |>
  group_by(year) |> mutate(share = 100 * people / sum(people))
print(pivot_wider(select(urb, -people), names_from = class, values_from = share))
ggplot(urb, aes(year, share, fill = factor(class, levels = c("rural", "town and suburb (urban cluster)", "city (urban centre)")))) +
  geom_area(alpha = 0.9) + annotate("rect", xmin = 2020, xmax = 2030, ymin = 0, ymax = 100, fill = "white", alpha = 0.45) +
  scale_fill_manual(values = c("#a6d96a", "#f4a582", "#b2182b")) +
  labs(y = "share of population (%)", x = NULL, fill = NULL, title = "Degree of urbanisation, Indonesia (2025-2030 projected)") +
  theme_minimal() + theme(legend.position = "top")

# PART 2. The radial profile: the edge moving out -------------------------------------------
rad <- rd("radial") |> pivot_longer(-km, names_to = "year", values_to = "built") |> mutate(year = as.integer(sub("y", "", year)))
rad |> group_by(year) |> summarise(edge_km_10pct = max(km[built >= 0.10])) |> print()
ggplot(rad, aes(km, 100 * built, colour = year, group = year)) + geom_line() + scale_colour_viridis_c() +
  labs(x = "distance from Monas (km)", y = "built-up share of land (%)", title = "Jabodetabek: built-up share in 2 km rings") +
  theme_minimal()

# PART 3. SDG 11.3.1 ----------------------------------------------------------------------------
sdg <- rd("sdg11") |> distinct(GAUL2_NAME, .keep_all = TRUE) |>
  mutate(city = sub("Kota ", "", GAUL2_NAME),
         lcr = 100 * log(built2020 / built2000) / 20, pgr = 100 * log(pop2020 / pop2000) / 20, lcrpgr = lcr / pgr,
         m2_per_person_2000 = built2000 / pop2000, m2_per_person_2020 = built2020 / pop2020) |>
  arrange(desc(lcrpgr))
print(select(sdg, city, lcr, pgr, lcrpgr, m2_per_person_2000, m2_per_person_2020))
lim <- max(c(sdg$lcr, sdg$pgr)) * 1.1
ggplot(sdg, aes(pgr, lcr)) +
  annotate("polygon", x = c(0, lim, 0), y = c(0, lim, lim), fill = "#fddbc7", alpha = 0.5) +
  geom_abline(colour = "grey50") + geom_point(colour = "#b2182b", size = 2) +
  geom_text(aes(label = city), size = 3, hjust = -0.1, vjust = -0.3) +
  coord_cartesian(xlim = c(0, lim), ylim = c(0, lim)) +
  labs(x = "population growth rate, 2000-2020 (%/yr)", y = "land consumption rate, 2000-2020 (%/yr)",
       title = "SDG 11.3.1: above the line, land is built on faster than people arrive") + theme_minimal()

# PART 4. Where does the city grow? A model -----------------------------------------------------
d <- rd("growth_sample") |> na.omit() |> mutate(people_ha = log1p(pmax(people_ha, 0)))
preds <- c("km_to_centre", "km_to_urban", "built_1km", "people_ha", "slope_deg", "elev_m")
d[preds] <- scale(d[preds])                                # odds ratios per 1 SD, as in Python
f <- reformulate(preds, "urbanised")
m <- glm(f, data = d, family = binomial)
print(round(cbind(odds_ratio = exp(coef(m)), exp(confint.default(m)))[-1, ], 3))

# Spatially blocked 5-fold cross-validation (~11 km blocks): nearby cells never sit in train and test at once
block <- floor(d$lon / 0.1) * 100 + floor(d$lat / 0.1)
set.seed(42); fold <- sample(rep(1:5, length.out = length(unique(block))))[match(block, unique(block))]
oof <- data.frame(logistic = NA_real_, forest = NA_real_)[rep(1, nrow(d)), ]
for (k in 1:5) {
  tr <- fold != k
  oof$logistic[!tr] <- predict(glm(f, data = d[tr, ], family = binomial), d[!tr, ], type = "response")
  oof$forest[!tr] <- predict(ranger(f, data = d[tr, ], num.trees = 300, min.node.size = 5, probability = FALSE,
                                    classification = FALSE, seed = 0), d[!tr, ])$predictions
}
cat(sprintf("AUC, spatially blocked: logistic %.2f, random forest %.2f\n",
            auc(d$urbanised, oof$logistic, quiet = TRUE), auc(d$urbanised, oof$forest, quiet = TRUE)))
