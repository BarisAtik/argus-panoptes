# Second opinion on combinelink.public_proxy, in R. Reads its player-season table, so it is only as
# real as that table: fake with --synth, public stand-in otherwise (see reports/public_proxy_plan.md).
#
#   Rscript R/02_public_proxy_mixed.R artifacts/public/player_seasons.csv
suppressPackageStartupMessages({
  library(lme4)
  library(tidymodels)
})

args <- commandArgs(trailingOnly = TRUE)
path <- if (length(args)) args[1] else "artifacts/public/player_seasons.csv"
seasons <- readr::read_csv(path, show_col_types = FALSE) |>
  filter(!is.na(speed_power)) |>
  mutate(season = factor(season), position = factor(position),
         speed_power = as.numeric(scale(speed_power)))
cat(sprintf("%d player-seasons, %d players\n", nrow(seasons), n_distinct(seasons$gsis_id)))

# Random intercepts keep a five-season veteran from counting as five independent players.
fit <- lmer(avg_separation ~ speed_power + position + (1 | gsis_id) + (1 | season), data = seasons)
print(summary(fit)$coefficients)
ci <- confint(fit, parm = "speed_power", method = "Wald")
cat(sprintf("speed_power: %.3f yards per SD, 95%% CI %.3f to %.3f\n",
            fixef(fit)[["speed_power"]], ci[1], ci[2]))
vars <- as.data.frame(VarCorr(fit))
cat(sprintf("share of variance between players: %.2f\n",
            vars$vcov[vars$grp == "gsis_id"] / sum(vars$vcov)))

# Same question as grouped_skill: does it predict separation for players the model hasn't seen?
set.seed(42)
folds <- group_vfold_cv(seasons, group = gsis_id, v = 5)
recipe_base <- recipe(avg_separation ~ position, data = seasons) |> step_dummy(position)
recipe_full <- recipe(avg_separation ~ position + speed_power, data = seasons) |>
  step_dummy(position) |> step_normalize(all_numeric_predictors())
spec <- linear_reg() |> set_engine("lm")
score <- function(rec) {
  fit_resamples(workflow(rec, spec), folds, control = control_resamples(save_pred = TRUE)) |>
    collect_predictions()
}
base <- score(recipe_base)
full <- score(recipe_full)
sse <- function(p) sum((p$avg_separation - p$.pred)^2)
cat(sprintf("out-of-player R2 above position baseline: %.3f\n", 1 - sse(full) / sse(base)))
