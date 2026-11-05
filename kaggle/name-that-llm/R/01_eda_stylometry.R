# EDA in one question: for each style feature, is the variance about WHO wrote it or WHAT was asked?
# Prompts are unseen at test time, so a feature dominated by prompt variance will not transfer.
#   Rscript R/01_eda_stylometry.R data/raw
# Uses a crossed random-effects model: feature ~ 1 + (1 | model) + (1 | prompt_id)
source("R/common.R")
suppressPackageStartupMessages(library(lme4))

train <- load_train(data_dir()) %>% add_style()

shape <- train %>% count(prompt_id, name = "rows") %>% count(rows, name = "prompts")
cat("Rows per prompt:\n"); print(shape)

decompose <- function(feature) {
  y <- train[[feature]]
  if (var(y) == 0) {
    return(tibble(feature = feature, model = NA_real_, prompt = NA_real_, residual = NA_real_))
  }
  d <- transmute(train, y = as.numeric(scale(y)), model, prompt_id)
  fit <- suppressWarnings(suppressMessages(
    lmer(y ~ 1 + (1 | model) + (1 | prompt_id), data = d, REML = TRUE)
  ))
  v <- as.data.frame(VarCorr(fit))
  share <- setNames(v$vcov / sum(v$vcov), v$grp)
  tibble(feature = feature, model = share[["model"]], prompt = share[["prompt_id"]],
         residual = share[["Residual"]])
}

shares <- bind_rows(lapply(style_cols, decompose)) %>% arrange(desc(model))
cat("\nShare of variance by source (higher `model` = better authorship signal):\n")
print(shares %>% mutate(across(where(is.numeric), ~ round(.x, 3))), n = Inf)
write_csv(shares, report_path("r_variance_shares.csv"))

plot_df <- shares %>%
  filter(!is.na(model)) %>%
  pivot_longer(c(model, prompt, residual), names_to = "source", values_to = "share") %>%
  mutate(feature = factor(feature, levels = rev(shares$feature)))
p <- ggplot(plot_df, aes(share, feature, fill = source)) +
  geom_col(width = 0.7) +
  scale_fill_manual(values = c(model = "#2a7f9e", prompt = "#d98c2b", residual = "#c9ced6")) +
  labs(title = "Where does style variance come from?", x = "Share of variance", y = NULL) +
  theme_minimal(base_size = 12)
ggsave(report_path("r_variance_shares.png"), p, width = 7, height = 4.5, dpi = 160)

by_model <- train %>%
  group_by(model) %>%
  summarise(across(all_of(style_cols), mean), n = n(), .groups = "drop")
write_csv(by_model, report_path("r_style_by_model.csv"))
cat("\nWrote reports/generated/r_variance_shares.{csv,png} and r_style_by_model.csv\n")
