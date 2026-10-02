#| title: Statistics every remote sensing analyst needs (R)
#| description: The same sample and the same questions in base R and ggplot2: summaries by group, IQR and z-score outliers, the central limit theorem by simulation, a bootstrap confidence interval, t, Wilcoxon (Mann-Whitney) and Kolmogorov-Smirnov tests, and lm with its diagnostic plots.

# CHAPTER 70 | Statistics every remote sensing analyst needs  (R twin)
# Reads data/ch70_bandung_lst_sample.csv (drawn from Earth Engine by the Python twin).

library(dplyr)
library(ggplot2)

d <- read.csv(Sys.getenv("STATS_CSV", "data/ch70_bandung_lst_sample.csv"))
d$cover <- factor(d$cover, levels = c("trees", "grass", "crops", "built"))
set.seed(42)

# PART 2. Central tendency and spread ------------------------------------------------------
d |> group_by(cover) |>
  summarise(n = n(), mean = mean(lst), median = median(lst), sd = sd(lst),
            iqr = IQR(lst), mad = mad(lst), skew = mean((lst - mean(lst))^3) / sd(lst)^3) |>
  print()

ggplot(d, aes(lst, colour = cover)) + geom_density(linewidth = 1) +
  geom_vline(data = d |> group_by(cover) |> summarise(m = mean(lst), md = median(lst)),
             aes(xintercept = m, colour = cover)) +
  geom_vline(data = d |> group_by(cover) |> summarise(md = median(lst)),
             aes(xintercept = md, colour = cover), linetype = "dotted") +
  scale_colour_manual(values = c(trees = "#1b7837", grass = "#a6dba0", crops = "#e6ab02", built = "#d73027")) +
  labs(x = "dry-season land surface temperature (°C)", title = "LST by land cover: mean (solid), median (dotted)") +
  theme_minimal()

# PART 3. Outliers: IQR fences and z-scores ----------------------------------------------------
d |> group_by(cover) |>
  mutate(lo = quantile(lst, 0.25) - 1.5 * IQR(lst), hi = quantile(lst, 0.75) + 1.5 * IQR(lst),
         z = (lst - mean(lst)) / sd(lst)) |>
  summarise(outside_fences = sum(lst < lo | lst > hi), z_gt_3 = sum(abs(z) > 3), z_gt_2 = sum(abs(z) > 2)) |>
  print()
ggplot(d, aes(cover, lst)) + geom_boxplot(coef = 1.5, outlier.colour = "#d73027") + theme_minimal()

# PART 4. The central limit theorem: means of samples of population density -------------------------
x <- d$people_ha
clt <- do.call(rbind, lapply(c(2, 5, 30, 100), function(n) {
  m <- replicate(5000, mean(sample(x, n, replace = TRUE)))
  data.frame(n = n, sd_of_means = sd(m), sigma_over_sqrt_n = sd(x) / sqrt(n),
             skew_of_means = mean((m - mean(m))^3) / sd(m)^3)
}))
print(clt)

# PART 5. Built minus trees: a 95 % confidence interval, normal and bootstrap --------------------------
a <- d$lst[d$cover == "built"]; b <- d$lst[d$cover == "trees"]
diff <- mean(a) - mean(b); se <- sqrt(var(a) / length(a) + var(b) / length(b))
boot <- replicate(5000, mean(sample(a, replace = TRUE)) - mean(sample(b, replace = TRUE)))
cat(sprintf("built - trees: %.2f °C; normal CI %.2f to %.2f; bootstrap CI %.2f to %.2f\n",
            diff, diff - 1.96 * se, diff + 1.96 * se, quantile(boot, 0.025), quantile(boot, 0.975)))

# PART 6. Three tests for two groups --------------------------------------------------------------------
for (pair in list(c("built", "trees"), c("crops", "grass"), c("crops", "trees"))) {
  x1 <- d$lst[d$cover == pair[1]]; x2 <- d$lst[d$cover == pair[2]]
  cat(sprintf("%s vs %s: Welch t p = %.2g, Mann-Whitney p = %.2g, KS D = %.2f (p = %.2g)\n", pair[1], pair[2],
              t.test(x1, x2)$p.value, wilcox.test(x1, x2)$p.value,
              ks.test(x1, x2)$statistic, ks.test(x1, x2)$p.value))
}
ggplot(filter(d, cover %in% c("crops", "grass")), aes(lst, colour = cover)) + stat_ecdf(linewidth = 1) +
  labs(y = "share of pixels at or below", title = "ECDFs: KS D is the largest vertical gap") + theme_minimal()

# PART 7. Regression and its diagnostics ------------------------------------------------------------------
m1 <- lm(lst ~ greenery, data = d)
m2 <- lm(lst ~ greenery + log1p(people_ha), data = d)
print(summary(m1)$coefficients); print(confint(m1))
cat(sprintf("R2: %.3f and %.3f; RMSE: %.2f and %.2f °C\n", summary(m1)$r.squared, summary(m2)$r.squared,
            sigma(m1), sigma(m2)))
par(mfrow = c(1, 2)); plot(m1, which = 1:2)        # residuals vs fitted, and the normal Q-Q plot
