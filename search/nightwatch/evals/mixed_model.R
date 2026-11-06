# Cross-check of test B2 with a mixed model: rules and datasets as random effects.
#   Rscript evals/mixed_model.R data/pairs-test-keyword_lower.json reports/b2-mixed-model.txt
suppressPackageStartupMessages({library(lme4); library(jsonlite)})
args <- commandArgs(trailingOnly = TRUE)
pairs <- fromJSON(args[1])
pairs <- pairs[pairs$level %in% c("low", "medium", "high", "critical"), ]
pairs$severe <- as.integer(pairs$level %in% c("high", "critical"))
pairs$on_target <- as.integer(pairs$on_target)
fit <- glmer(on_target ~ severe + (1 | rule) + (1 | dataset), data = pairs, family = binomial,
             control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5)))
coefs <- summary(fit)$coefficients
wald <- confint(fit, parm = "beta_", method = "Wald")
out <- c(
  sprintf("%s, lme4 %s", R.version.string, packageVersion("lme4")),
  sprintf("pairs %d, rules %d, datasets %d", nrow(pairs), length(unique(pairs$rule)),
          length(unique(pairs$dataset))),
  sprintf("log-odds severe vs mild: %.3f (Wald 95%% %.3f to %.3f), one-sided p = %.4f",
          coefs["severe", "Estimate"], wald["severe", 1], wald["severe", 2],
          pnorm(coefs["severe", "z value"], lower.tail = FALSE)),
  sprintf("odds ratio: %.2f", exp(coefs["severe", "Estimate"])),
  sprintf("random effect sd: rule %.3f, dataset %.3f", sqrt(VarCorr(fit)$rule[1]),
          sqrt(VarCorr(fit)$dataset[1])),
  sprintf("singular fit: %s", isSingular(fit))
)
writeLines(out, args[2])
writeLines(out)
