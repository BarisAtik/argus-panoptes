# Independent audit of the transformer comparison, plus why the blend works. Recomputes balanced
# accuracy from raw predictions in R, then asks how far the two kinds of model err on different
# passages, and whether that differs by author.
#
#   Rscript R/05_transformer_audit.R artifacts/transformer/predictions.parquet
suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(arrow)
  library(lme4)
})

args <- commandArgs(trailingOnly = TRUE)
path <- if (length(args)) args[1] else "artifacts/transformer/predictions.parquet"
preds <- read_parquet(path)

balanced <- function(truth, pred) mean(tapply(pred == truth, truth, mean))
long <- preds |>
  pivot_longer(starts_with("pred_"), names_to = "candidate", names_prefix = "pred_",
               values_to = "pred") |>
  mutate(hit = pred == model)
cat("Balanced accuracy, recomputed in R\n")
print(long |>
  group_by(seed, candidate) |>
  summarise(score = round(balanced(model, pred), 4), .groups = "drop") |>
  pivot_wider(names_from = seed, values_from = score))

cat("\nDo the models fail on the same passages? Sparse blend against tuned RoBERTa\n")
pair <- preds |>
  mutate(sparse = pred_sparse_blend == model, tuned = pred_tuned == model)
cross <- pair |> count(seed, sparse, tuned) |> group_by(seed) |> mutate(share = round(n / sum(n), 3))
print(cross)
agree <- pair |>
  group_by(seed) |>
  summarise(phi = round(cor(sparse, tuned), 3), both_wrong = round(mean(!sparse & !tuned), 3),
            only_one_right = round(mean(sparse != tuned), 3), .groups = "drop")
print(agree)

cat("\nRecall by author, mean over splits\n")
print(long |>
  filter(candidate %in% c("sparse_blend", "tuned", "tuned_plus_sparse")) |>
  group_by(model, candidate) |>
  summarise(recall = round(mean(hit), 3), .groups = "drop") |>
  pivot_wider(names_from = candidate, values_from = recall))

# Passages on one prompt share difficulty, so a plain test of the blend's gain would be overconfident.
cat("\nBlend against sparse: logistic mixed model with prompt and split effects\n")
two <- long |>
  filter(candidate %in% c("sparse_blend", "tuned_plus_sparse")) |>
  mutate(blend = as.numeric(candidate == "tuned_plus_sparse"), prompt = paste(seed, prompt_id))
rhs <- if (n_distinct(two$seed) > 1) "blend + factor(seed)" else "blend"
fit <- glmer(as.formula(paste("hit ~", rhs, "+ (1 | prompt) + (1 | model)")), data = two,
             family = binomial, control = glmerControl(optimizer = "bobyqa"))
print(round(summary(fit)$coefficients, 3))
