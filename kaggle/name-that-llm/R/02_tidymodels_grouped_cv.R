# Interpretable multinomial model on style features, tuned with prompt-grouped folds.
# Also scores the same workflow under naive random folds, to show what the wrong scheme reports.
#   Rscript R/02_tidymodels_grouped_cv.R data/raw
source("R/common.R")
suppressPackageStartupMessages({library(tidymodels); library(glmnet)})
tidymodels_prefer(quiet = TRUE)
set.seed(42)

train <- load_train(data_dir()) %>%
  add_style() %>%
  mutate(model = factor(model)) %>%
  select(id, prompt_id, model, all_of(style_cols))

grouped <- group_vfold_cv(train, group = prompt_id, v = 5)
naive <- vfold_cv(train, v = 5, strata = model)

rec <- recipe(model ~ ., data = train) %>%
  update_role(id, prompt_id, new_role = "id") %>%
  step_zv(all_numeric_predictors()) %>%
  step_YeoJohnson(all_numeric_predictors()) %>%
  step_normalize(all_numeric_predictors())

spec <- multinom_reg(penalty = tune(), mixture = tune()) %>% set_engine("glmnet")
wf <- workflow() %>% add_recipe(rec) %>% add_model(spec)

# Macro sensitivity is the competition metric; see the note in common.R.
macro_recall <- metric_tweak("macro_recall", sens, estimator = "macro")
metrics <- metric_set(macro_recall, mn_log_loss)

grid <- crossing(penalty = 10^seq(-4, -1, length.out = 7), mixture = c(0, 0.5, 1))
res <- tune_grid(wf, resamples = grouped, grid = grid, metrics = metrics,
                 control = control_grid(save_pred = FALSE))
print(show_best(res, metric = "macro_recall", n = 5))
best <- select_best(res, metric = "macro_recall")

final_wf <- finalize_workflow(wf, best)
keep <- control_resamples(save_pred = TRUE)
group_fit <- fit_resamples(final_wf, grouped, metrics = metrics, control = keep)
naive_fit <- fit_resamples(final_wf, naive, metrics = metrics, control = keep)

score <- function(fit) {
  p <- collect_predictions(fit)
  balanced_accuracy(p$model, p$.pred_class)
}
comparison <- tibble(scheme = c("grouped by prompt", "naive random"),
                     balanced_accuracy = c(score(group_fit), score(naive_fit)))
print(comparison)

# Cross-check the hand-written metric against yardstick so the two cannot silently diverge.
p <- collect_predictions(group_fit)
stopifnot(abs(score(group_fit) - sens_vec(p$model, p$.pred_class, estimator = "macro")) < 1e-9)

coefs <- final_wf %>% fit(train) %>% extract_fit_engine() %>% coef(s = best$penalty)
top <- bind_rows(lapply(names(coefs), function(cl) {
  m <- as.matrix(coefs[[cl]])
  tibble(model = cl, feature = rownames(m), beta = m[, 1])
})) %>%
  filter(feature != "(Intercept)", beta != 0) %>%
  arrange(desc(abs(beta))) %>%
  slice_head(n = 15)
cat("\nLargest coefficients:\n"); print(top)

write_csv(comparison, report_path("r_cv_comparison.csv"))
write_csv(top, report_path("r_top_coefficients.csv"))
cat("\nWrote reports/generated/r_cv_comparison.csv and r_top_coefficients.csv\n")
