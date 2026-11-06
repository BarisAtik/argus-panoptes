# How clustered are errors within prompts, and what does that do to the effective sample size?
# A binomial mixed model on out-of-fold hits, which also tests the choice to bootstrap prompts.
#   Rscript R/04_prompt_effects.R data/proxy/comp artifacts/proxy_comp/oof_tfidf_lr.parquet
source("R/common.R")
suppressPackageStartupMessages({library(arrow); library(lme4)})

args <- commandArgs(trailingOnly = TRUE)
train <- load_train(args[1])
oof <- read_parquet(args[2])
classes <- setdiff(names(oof), c("id", "fold", "model", "prompt_id"))
oof$pred <- classes[max.col(as.matrix(oof[classes]), ties.method = "first")]

d <- oof %>%
  select(id, model, prompt_id, pred) %>%
  inner_join(select(train, id, text), by = "id") %>%
  mutate(hit = as.integer(model == pred),
         words_z = as.numeric(scale(log(str_count(text, "\\S+")))),
         genre = str_remove(prompt_id, "_\\d+$"))

form <- if (n_distinct(d$genre) > 1 && n_distinct(d$genre) < 10) {
  hit ~ words_z + genre + (1 | prompt_id) + (1 | model)
} else {
  hit ~ words_z + (1 | prompt_id) + (1 | model)
}
fit <- glmer(form, data = d, family = binomial, control = glmerControl(optimizer = "bobyqa"))
print(round(summary(fit)$coefficients, 3))

v <- as.data.frame(VarCorr(fit))
tau_prompt <- v$vcov[v$grp == "prompt_id"]
tau_model <- v$vcov[v$grp == "model"]
# The latent-scale residual of a logistic model is pi^2 / 3.
icc <- tau_prompt / (tau_prompt + tau_model + pi^2 / 3)
m <- mean(table(d$prompt_id))
deff <- 1 + (m - 1) * icc
cat(sprintf(paste0("\nPrompt variance %.3f, model variance %.3f\n",
                   "Latent ICC for prompt %.3f, design effect %.2f at %.1f passages per prompt\n",
                   "%d rows behave roughly like %d independent rows\n"),
            tau_prompt, tau_model, icc, deff, m, nrow(d), round(nrow(d) / deff)))

# Compare with what the rows say directly: spread of prompt-level accuracy vs binomial expectation.
by_prompt <- d %>% group_by(prompt_id) %>% summarise(acc = mean(hit), n = n(), .groups = "drop")
p_bar <- mean(d$hit)
cat(sprintf("Observed SD of prompt accuracy %.3f, binomial expectation %.3f\n",
            sd(by_prompt$acc), sqrt(p_bar * (1 - p_bar) / mean(by_prompt$n))))
