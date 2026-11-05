# Mixed-effects view of the same question in R. Python's combinelink.run produces player_features.csv.
# Separation is noisy and repeated within player and game, so both get random intercepts.
# The tidymodels part scores out-of-player prediction, which is the honest test of transfer.
#   Rscript R/01_reliability_and_linkage.R data/raw artifacts/real/player_features.csv
suppressPackageStartupMessages({
  library(dplyr); library(readr); library(lme4); library(tidymodels); library(glmnet)
})
tidymodels_prefer(quiet = TRUE)
set.seed(11)

args <- commandArgs(trailingOnly = TRUE)
plays <- read_csv(file.path(args[1], "player_play.csv"), show_col_types = FALSE)
features <- read_csv(args[2], show_col_types = FALSE)

d <- plays %>%
  filter(!is.na(separation_at_pass_forward)) %>%
  inner_join(features, by = "nfl_id") %>%
  mutate(speed_z = as.numeric(scale(peak_speed)), lateral_z = as.numeric(scale(peak_lateral)))

fit <- lmer(separation_at_pass_forward ~ lined_up_position + speed_z + lateral_z +
              (1 | nfl_id) + (1 | game_id), data = d, REML = TRUE)
print(summary(fit)$coefficients)
ci <- suppressWarnings(suppressMessages(confint(fit, method = "Wald", parm = "beta_")))
print(ci)
v <- as.data.frame(VarCorr(fit))
cat("\nVariance by source:\n"); print(transmute(v, grp, share = round(vcov / sum(vcov), 3)))

# Out-of-player prediction with player-grouped folds.
folds <- group_vfold_cv(d, group = nfl_id, v = 5)
rec <- recipe(separation_at_pass_forward ~ lined_up_position + speed_z + lateral_z, data = d) %>%
  step_dummy(all_nominal_predictors()) %>%
  step_zv(all_predictors())
base_rec <- recipe(separation_at_pass_forward ~ lined_up_position, data = d) %>%
  step_dummy(all_nominal_predictors()) %>%
  step_zv(all_predictors())
spec <- linear_reg() %>% set_engine("lm")
scores <- bind_rows(
  fit_resamples(workflow(rec, spec), folds) %>% collect_metrics() %>% mutate(model = "combine + position"),
  fit_resamples(workflow(base_rec, spec), folds) %>% collect_metrics() %>% mutate(model = "position only")
)
print(scores %>% filter(.metric == "rmse") %>% select(model, mean, std_err))
