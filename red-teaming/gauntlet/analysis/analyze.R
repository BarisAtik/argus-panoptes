#!/usr/bin/env Rscript
# Mixed-effects view of a gauntlet run. Trials from one scenario are correlated, so
# scenario is a random effect instead of being treated as independent evidence.
#
#   Rscript analysis/analyze.R runs/latest.jsonl
#
# Needs jsonlite and lme4. Falls back to a fixed-effects logit with a warning if
# lme4 is missing or the model cannot be fitted (common when outcomes are near 0 or 1).

args <- commandArgs(trailingOnly = TRUE)
path <- if (length(args) >= 1) args[1] else "runs/latest.jsonl"
if (!requireNamespace("jsonlite", quietly = TRUE)) stop("install.packages('jsonlite')")

rows <- lapply(readLines(path), function(l) {
  r <- jsonlite::fromJSON(l, simplifyVector = FALSE)
  data.frame(scenario = r$scenario, category = r$category, control = isTRUE(r$control), defense = r$defense,
             seed = r$seed, attack = as.integer(isTRUE(r$attack)), utility = as.integer(isTRUE(r$utility)))
})
d <- do.call(rbind, rows)
atk <- d[!d$control, ]

cat("Attack success by defense\n")
print(round(sort(tapply(atk$attack, atk$defense, mean), decreasing = TRUE), 3))

cat("\nAttack success by category and defense\n")
print(round(tapply(atk$attack, list(atk$category, atk$defense), mean), 2))

atk$defense <- relevel(factor(atk$defense), ref = levels(factor(atk$defense))[1])
varies <- tapply(atk$attack, atk$defense, function(x) mean(x) > 0 && mean(x) < 1)
fit_data <- droplevels(atk[atk$defense %in% names(varies)[varies], ])

if (nlevels(fit_data$defense) >= 2 && requireNamespace("lme4", quietly = TRUE)) {
  m <- tryCatch(
    suppressWarnings(lme4::glmer(attack ~ defense + (1 | scenario), data = fit_data, family = binomial)),
    error = function(e) NULL
  )
  if (!is.null(m)) {
    cat("\nglmer: attack ~ defense + (1 | scenario), defenses with non-degenerate rates only\n")
    print(round(summary(m)$coefficients, 3))
    cat("Scenario SD on the logit scale:", round(sqrt(unlist(lme4::VarCorr(m))), 2), "\n")
    if (!is.null(m@optinfo$conv$lme4$messages)) cat("Convergence notes:", m@optinfo$conv$lme4$messages, "\n")
    quit(save = "no")
  }
}
if (nlevels(fit_data$defense) >= 2) {
  warning("lme4 unavailable or failed: this fixed-effects fit ignores clustering, so its errors are too small")
  print(round(summary(glm(attack ~ defense, data = fit_data, family = binomial))$coefficients, 3))
}
