#| title: Out-of-home advertising placement in Sydney (R)
#| description: Predict weekday pedestrian counts from open urban data with a stacked caret ensemble, combine them with income, population and points of interest in a multi-criteria score for three advertiser types, and rank bus shelters, city banners and bus routes.

# Fullstack Remote Sensing | Code by Rifky Nauval Hendrawan, Remote Sensing Specialist
# MIT licence: free to use and adapt; please keep this credit line.

# CHAPTER 65 | Where should an advertiser buy a billboard?
#
# Three steps, the same three an out-of-home (OOH) media planner takes:
#   1. footfall   predict pedestrians at every candidate location from
#                 urban form (points of interest, roads, buildings, transit,
#                 night-time activity, employment), trained on the City of
#                 Sydney walking counts
#   2. audience   combine footfall with income, population by age and nearby
#                 businesses into a score for each kind of advertiser
#                 (financial services, fast food, education)
#   3. inventory  score the places an advertiser can actually buy: bus
#                 shelters, city banners and bus routes
#
# Data: all open, built by scripts/py/ch65_ooh_data.py into OOH_DATA - City of
# Sydney walking counts, employment survey, bus shelters and banners;
# OpenStreetMap points of interest, roads, stops and bus routes; GHSL building
# surface and volume, VIIRS night lights and WorldPop age structure (Earth
# Engine); ABS Census 2021 income.

library(sf)
library(terra)
library(exactextractr)
library(dplyr)
library(caret)
library(caretEnsemble)
library(gbm)
library(ggplot2)

DATA <- Sys.getenv("OOH_DATA", "data/ooh_sydney")
# The exact inputs used for the book (frozen 2 October 2026), downloaded once if not here
if (!file.exists(file.path(DATA, "counts.gpkg"))) {
  dir.create(DATA, FALSE, TRUE); tmp <- tempfile(fileext = ".zip")
  download.file("https://github.com/rifkynhsp-byte/Fullstack-Remote-Sensing/releases/download/data-v1/ch65_ooh_sydney_inputs.zip", tmp, mode = "wb"); unzip(tmp, exdir = DATA)
}
p <- function(...) file.path(DATA, ...)
set.seed(12345)

# PART 1. Training points and predictor surfaces --------------------------------
add_features <- function(x) {
  stopifnot(st_crs(x)$units == "m")         # buffers below are in metres
  # Mean of every surface within 100, 500 and 1000 m: the same place seen at a
  # street, a neighbourhood and a district scale.
  for (name in surfaces) {
    r <- rast(p("surfaces", paste0(name, ".tif")))
    for (d in c(100, 500, 1000)) {
      x[[paste0(name, "_", d, "m")]] <- exact_extract(r, st_buffer(x, d), "mean", progress = FALSE)
    }
  }
  # Employment survey: attributes of the nearest block. Count sites stand on
  # streets and streets lie between blocks, so "within" would match almost
  # nothing; st_intersection would also silently drop the unmatched sites.
  st_join(x, employment, join = st_nearest_feature)
}

surfaces <- c("poi", "road_density", "nighttime", "bus_station",
              "building_surface", "building_volume", "jobs")

counts <- st_read(p("counts.gpkg"), quiet = TRUE)
employment <- st_read(p("employment.gpkg"), quiet = TRUE) |>
  st_transform(st_crs(counts)) |> select(jobs_per_ha, floor_ratio, Businesses)
counts <- add_features(counts)

predictors <- setdiff(names(st_drop_geometry(counts)),
                      c("weekday_count", "n_surveys", "Site_ID", "OBJECTID"))
predictors <- predictors[sapply(st_drop_geometry(counts)[predictors], is.numeric)]

# PART 2. An honest split ---------------------------------------------------------
# Hold out 20 % of the counted sites BEFORE anything is learned from the data.
# Pre-processing (centre, scale, near-zero variance, Yeo-Johnson) is then fitted
# inside every resample, never on the test sites.
labelled <- counts[!is.na(counts$weekday_count), ]
df <- st_drop_geometry(labelled)[c("weekday_count", predictors)]
df[is.na(df)] <- 0
# Counts run from a few hundred to over 70,000 a day. Models learn log(1 + count),
# so a quiet laneway and a CBD corner are fitted on comparable terms;
# predictions are transformed back before any error is reported.
df$weekday_count <- log1p(df$weekday_count)
test_idx <- createDataPartition(df$weekday_count, p = 0.2, list = FALSE)
train <- df[-test_idx, ]
test  <- df[test_idx, ]

# Count sites a few hundred metres apart share their surroundings, so a random
# fold leaks the neighbourhood of every test site into training. Spatial folds:
# group the training sites into 5 clusters by location.
xy <- st_coordinates(labelled)[-test_idx, ]
cluster <- kmeans(xy, centers = 5, nstart = 20)$cluster

ctrl_random <- trainControl(method = "cv", number = 5, savePredictions = "final",
                            search = "random")
ctrl_spatial <- trainControl(method = "cv", index = groupKFold(cluster, k = 5),
                             savePredictions = "final", search = "random")

models <- list(
  glmnet  = caretModelSpec(method = "glmnet",    tuneLength = 50),
  ranger  = caretModelSpec(method = "ranger",    tuneLength = 10, importance = "impurity"),
  cubist  = caretModelSpec(method = "cubist",    tuneLength = 10),
  svmL    = caretModelSpec(method = "svmLinear", tuneLength = 10),
  # Boosted trees: caret's "xgbTree" fails with xgboost >= 3.0 (2025) ("ALTLIST
  # classes must provide a Set_elt method"). "gbm" is the boosted-tree learner caret
  # still supports; to keep xgbTree, install xgboost 1.7 from the CRAN archive.
  gbm     = caretModelSpec(method = "gbm",       tuneLength = 10, verbose = FALSE),
  nnet    = caretModelSpec(method = "nnet",      tuneLength = 30, linout = TRUE, trace = FALSE))

fit_all <- function(ctrl) {
  caretList(weekday_count ~ ., data = train, trControl = ctrl, metric = "MAE",
            # Yeo-Johnson, not Box-Cox: Box-Cox needs positive values, and a street
            # with zero of something the training sites all had turns into -Inf
            preProcess = c("center", "scale", "nzv", "YeoJohnson"), tuneList = models)
}
base_random  <- fit_all(ctrl_random)
base_spatial <- fit_all(ctrl_spatial)

# PART 3. Six learners, then a stack -------------------------------------------------
cv_mae <- function(lst) sapply(lst, function(m) getTrainPerf(m)$TrainMAE)
print(rbind(random = cv_mae(base_random), spatial = cv_mae(base_spatial)))
print(modelCor(resamples(base_spatial)))     # stacking helps only if errors differ

# Meta-learner: an elastic net. (A Cubist meta-learner over all six models
# crashed R inside caretStack in testing; the Python twin uses Cubist.)
stack <- caretStack(base_spatial, method = "glmnet", metric = "MAE", tuneLength = 10,
                    trControl = trainControl(method = "cv", index = groupKFold(cluster, k = 5)))

# PART 4. The test sites, which nothing above has seen ------------------------------
pred_test <- predict(stack, newdata = test)
pred_test <- expm1(if (is.data.frame(pred_test)) pred_test[[1]] else pred_test)
test$weekday_count <- expm1(test$weekday_count)
r2   <- cor(test$weekday_count, pred_test)^2
rmse <- sqrt(mean((test$weekday_count - pred_test)^2))
mape <- mean(abs(pred_test - test$weekday_count) / test$weekday_count)
cat(sprintf("test sites: n %d, R2 %.2f, RMSE %.0f, MAPE %.0f%%\n", nrow(test), r2, rmse, 100 * mape))

ggplot(data.frame(actual = test$weekday_count, predicted = pred_test), aes(actual, predicted)) +
  geom_abline(linetype = "dotted") +
  geom_point(size = 3, alpha = 0.7, colour = "dodgerblue4") +
  annotate("text", x = -Inf, y = Inf, hjust = -0.1, vjust = 1.3, fontface = "bold",
           label = sprintf("R² = %.2f\nRMSE = %.0f\nMAPE = %.0f%%", r2, rmse, 100 * mape)) +
  labs(title = "Held-out count sites: actual vs predicted",
       x = "Counted pedestrians (weekday)", y = "Predicted") +
  theme_bw()

# Predict footfall at every candidate location: a point every 100 m along the streets.
cand <- add_features(st_read(p("candidates.gpkg"), quiet = TRUE))
cand_df <- st_drop_geometry(cand)[predictors]; cand_df[is.na(cand_df)] <- 0
pred_all <- predict(stack, newdata = cand_df)
cand$walking_count <- expm1(if (is.data.frame(pred_all)) pred_all[[1]] else pred_all)

# PART 5. Audience: a multi-criteria score per advertiser ----------------------------
# SA2 areas: Census 2021 median weekly household income, WorldPop 2020 by age.
areas <- st_read(p("areas.gpkg"), quiet = TRUE) |> st_transform(st_crs(counts)) |>
  select(income_weekly, total_population, pop1545, pop2035, pop4065)

site <- cand["walking_count"] |> st_join(areas)
for (k in c("fastfood", "education", "financial")) {
  r <- rast(p("surfaces", paste0(k, "_poi.tif")))
  site[[paste0("poi_", k)]] <- exact_extract(r, st_buffer(site, 500), "mean", progress = FALSE)
}

# Rescale every criterion to 0-1, then weight. The weights encode a media
# planner's judgement of each advertiser's audience; change them and the map
# changes, which is the point of writing them down.
s <- st_drop_geometry(site); s[] <- lapply(s, function(v) (v - min(v, na.rm = TRUE)) / diff(range(v, na.rm = TRUE)))
wealth <- (s$income_weekly + s$total_population) / 2
site$MCDA_financial <- 0.50 * wealth + 0.20 * s$walking_count + 0.20 * s$poi_financial + 0.10 * s$pop4065
site$MCDA_fastfood  <- 0.15 * wealth + 0.40 * s$walking_count + 0.35 * s$poi_fastfood  + 0.10 * s$pop1545
site$MCDA_education <- 0.05 * wealth + 0.20 * s$walking_count + 0.35 * s$poi_education + 0.40 * s$pop2035

# PART 6. Inventory: what can actually be bought -------------------------------------
score_assets <- function(file) {
  a <- st_read(p(file), quiet = TRUE) |> st_transform(st_crs(site)) |>
    mutate(asset_id = row_number())
  # mean score of the scored locations within 50 m of each asset
  scores <- st_join(st_buffer(a, 50), site[c("MCDA_financial", "MCDA_fastfood", "MCDA_education")]) |>
    st_drop_geometry() |> group_by(asset_id) |>
    summarise(n_locations = sum(!is.na(MCDA_financial)),
              across(starts_with("MCDA"), \(v) mean(v, na.rm = TRUE)))
  left_join(a, scores, by = "asset_id")
}
shelters <- score_assets("shelters.gpkg")
banners  <- score_assets("banners.gpkg")

# Bus routes: a sum of scores along a route rewards long routes for being long.
# Use the mean score per scored location the route passes, and report length.
routes <- st_read(p("routes.gpkg"), quiet = TRUE) |> st_transform(st_crs(site))
route_scores <- st_join(st_buffer(site, 10), routes["route"]) |>
  st_drop_geometry() |> filter(!is.na(route)) |> group_by(route) |>
  summarise(n_locations = n(), across(starts_with("MCDA"), \(v) mean(v, na.rm = TRUE)))
routes$length_km <- as.numeric(st_length(routes)) / 1000
routes <- routes |> group_by(route) |> summarise(length_km = sum(length_km)) |>
  left_join(route_scores, by = "route")

for (k in c("financial", "fastfood", "education")) {
  col <- paste0("MCDA_", k)
  ok <- routes$n_locations >= 5              # enough scored locations for a mean to mean something
  cat(k, ": best route", routes$route[ok][which.max(routes[[col]][ok])],
      "| best shelter row", which.max(shelters[[col]]), "\n")
}
