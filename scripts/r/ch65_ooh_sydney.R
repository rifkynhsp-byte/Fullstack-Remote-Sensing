#| title: Out-of-home advertising placement in Sydney (R)
#| description: Predict weekday pedestrian counts from open urban data with a stacked caret ensemble, combine them with income, population and points of interest in a multi-criteria score for three advertiser types, and rank bus shelters, city banners and bus routes.

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
# Data (all open): City of Sydney walking count sites, floor space and
# employment survey, bus shelters and banner poles (data.cityofsydney.nsw.gov.au);
# Transport for NSW bus routes; ABS income and NSW population projections;
# POI, road and building density surfaces derived from OpenStreetMap.
# Set OOH_DATA to the folder that holds them (layout as in the chapter).

library(sf)
library(terra)
library(exactextractr)
library(dplyr)
library(caret)
library(caretEnsemble)
library(ggplot2)

DATA <- Sys.getenv("OOH_DATA", "data/ooh_sydney")
p <- function(...) file.path(DATA, ...)
set.seed(12345)

# PART 1. Training points and predictor surfaces --------------------------------
counts <- st_read(p("Walking_count", "WalkingCountTraining.shp"), quiet = TRUE)
stopifnot(st_crs(counts)$units == "m")      # buffers below are in metres

surfaces <- c(
  poi              = "Heatmap_POI.tif",
  road_density     = "Road_density.tif",
  nighttime        = "NightimeArea.tif",
  bus_station      = "Heatmap_busstation.tif",
  building_surface = "Heatmap_building_surface.tif",
  building_volume  = "Heatmap_building_volume.tif",
  economic         = "Heatmap_economic_potential.tif")

# Mean of every surface within 100, 500 and 1000 m: the same place seen at a
# street, a neighbourhood and a district scale.
for (name in names(surfaces)) {
  r <- rast(p("Walking_count", surfaces[[name]]))
  for (d in c(100, 500, 1000)) {
    counts[[paste0(name, "_", d, "m")]] <-
      exact_extract(r, st_buffer(counts, d), "mean", progress = FALSE)
  }
}

# Employment survey: attach the attributes of the zone each point falls in.
# st_join keeps every point; st_intersection would silently drop points outside
# the survey zones and duplicate points on a boundary.
employment <- st_read(p("Walking_count", "Employment_Survey.shp"), quiet = TRUE) |>
  st_transform(st_crs(counts))
counts <- st_join(counts, employment, largest = TRUE)

predictors <- setdiff(names(st_drop_geometry(counts)), c("Mon_Count", "site_id", "Site_ID"))
predictors <- predictors[sapply(st_drop_geometry(counts)[predictors], is.numeric)]

# PART 2. An honest split ---------------------------------------------------------
# Hold out 20 % of the counted sites BEFORE anything is learned from the data.
# Pre-processing (centre, scale, near-zero variance, Box-Cox) is then fitted
# inside every resample, never on the test sites.
labelled <- counts[!is.na(counts$Mon_Count), ]
df <- st_drop_geometry(labelled)[c("Mon_Count", predictors)]
df[is.na(df)] <- 0
test_idx <- createDataPartition(df$Mon_Count, p = 0.2, list = FALSE)
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
  xgbTree = caretModelSpec(method = "xgbTree",   tuneLength = 50),
  nnet    = caretModelSpec(method = "nnet",      tuneLength = 30, linout = TRUE, trace = FALSE))

fit_all <- function(ctrl) {
  caretList(Mon_Count ~ ., data = train, trControl = ctrl, metric = "MAE",
            preProcess = c("center", "scale", "nzv", "BoxCox"), tuneList = models)
}
base_random  <- fit_all(ctrl_random)
base_spatial <- fit_all(ctrl_spatial)

# PART 3. Six learners, then a stack -------------------------------------------------
cv_mae <- function(lst) sapply(lst, function(m) getTrainPerf(m)$TrainMAE)
print(rbind(random = cv_mae(base_random), spatial = cv_mae(base_spatial)))
print(modelCor(resamples(base_spatial)))     # stacking helps only if errors differ

stack <- caretStack(base_spatial, method = "cubist", metric = "MAE", tuneLength = 10,
                    trControl = trainControl(method = "cv", index = groupKFold(cluster, k = 5)))

# PART 4. The test sites, which nothing above has seen ------------------------------
pred_test <- predict(stack, newdata = test)
pred_test <- if (is.data.frame(pred_test)) pred_test[[1]] else pred_test
r2   <- cor(test$Mon_Count, pred_test)^2
rmse <- sqrt(mean((test$Mon_Count - pred_test)^2))
mape <- mean(abs(pred_test - test$Mon_Count) / test$Mon_Count)
cat(sprintf("test sites: n %d, R2 %.2f, RMSE %.0f, MAPE %.0f%%\n", nrow(test), r2, rmse, 100 * mape))

ggplot(data.frame(actual = test$Mon_Count, predicted = pred_test), aes(actual, predicted)) +
  geom_abline(linetype = "dotted") +
  geom_point(size = 3, alpha = 0.7, colour = "dodgerblue4") +
  annotate("text", x = -Inf, y = Inf, hjust = -0.1, vjust = 1.3, fontface = "bold",
           label = sprintf("R² = %.2f\nRMSE = %.0f\nMAPE = %.0f%%", r2, rmse, 100 * mape)) +
  labs(title = "Held-out count sites: actual vs predicted",
       x = "Counted pedestrians (weekday)", y = "Predicted") +
  theme_bw()

# Predict every candidate location (sites without a count included).
all_df <- st_drop_geometry(counts)[predictors]; all_df[is.na(all_df)] <- 0
pred_all <- predict(stack, newdata = all_df)
counts$walking_count <- if (is.data.frame(pred_all)) pred_all[[1]] else pred_all

# PART 5. Audience: a multi-criteria score per advertiser ----------------------------
income <- st_read(p("Buying Potential", "Income_Data.shp"), quiet = TRUE) |>
  transmute(income_weekly = equiv_2202) |> st_transform(st_crs(counts))
pop <- st_read(p("Buying Potential", "Population_Data.shp"), quiet = TRUE) |>
  st_transform(st_crs(counts))
band <- function(df, ages) Reduce(`+`, lapply(ages, function(a) df[[paste0("prj_m_", a)]] + df[[paste0("prj_f_", a)]]))
pop <- pop |> mutate(
  total_population = prj_person,
  pop1545 = band(pop, c("1519", "2024", "2529", "3034", "3539", "4044")),
  pop2035 = band(pop, c("2024", "2529", "3034")),
  pop4065 = band(pop, c("4044", "4549", "5054", "5559", "6064"))) |>
  select(total_population, pop1545, pop2035, pop4065)

site <- counts["walking_count"] |> st_join(income, largest = TRUE) |> st_join(pop, largest = TRUE)
for (k in c("fastfood", "education", "financial")) {
  r <- rast(p("POI", paste0(k, "_heatmap.tif")))
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
  a <- st_read(p("OOH places", file), quiet = TRUE) |> st_transform(st_crs(site)) |>
    mutate(asset_id = row_number())
  # mean score of the scored locations within 50 m of each asset
  scores <- st_join(st_buffer(a, 50), site[c("MCDA_financial", "MCDA_fastfood", "MCDA_education")]) |>
    st_drop_geometry() |> group_by(asset_id) |>
    summarise(n_locations = sum(!is.na(MCDA_financial)),
              across(starts_with("MCDA"), \(v) mean(v, na.rm = TRUE)))
  left_join(a, scores, by = "asset_id")
}
shelters <- score_assets("Bus Shelther.shp")
banners  <- score_assets("City_Banner.shp")

# Bus routes: a sum of scores along a route rewards long routes for being long.
# Use the mean score per scored location the route passes, and report length.
routes <- st_read(p("OOH places", "Bus Routes clipped.shp"), quiet = TRUE) |> st_transform(st_crs(site))
route_scores <- st_join(st_buffer(site, 10), routes["route"]) |>
  st_drop_geometry() |> filter(!is.na(route)) |> group_by(route) |>
  summarise(n_locations = n(), across(starts_with("MCDA"), \(v) mean(v, na.rm = TRUE)))
routes <- routes |> group_by(route) |> summarise(length_km = sum(as.numeric(st_length(geometry))) / 1000) |>
  left_join(route_scores, by = "route")

for (k in c("financial", "fastfood", "education")) {
  col <- paste0("MCDA_", k)
  cat(k, ": best route", routes$route[which.max(routes[[col]])],
      "| best shelter row", which.max(shelters[[col]]), "\n")
}
