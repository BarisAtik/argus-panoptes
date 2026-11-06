#!/usr/bin/env Rscript
# Mixed-effects view of the rewriting experiment. Documents from one attack template are
# not independent, and neither are the rewrites, so both are random effects.
#
#   Rscript analysis/robustness.R reports/robustness_groups.json > reports/robustness-glmm.txt
#
# Pooled recall hides the shortcut noted in the README: on some rewrites the benign documents
# get flagged too. Read this next to the FPR table.
#
# Needs jsonlite and lme4. Only the trained detectors are modelled; the regex is deterministic.

args <- commandArgs(trailingOnly = TRUE)
path <- if (length(args) >= 1) args[1] else "reports/robustness_groups.json"
raw <- jsonlite::fromJSON(path, simplifyMatrix = TRUE)
d <- as.data.frame(raw$rows, stringsAsFactors = FALSE)
names(d) <- raw$columns
d$caught <- as.integer(d$caught)
d$n <- as.integer(d$n)
parts <- do.call(rbind, strsplit(d$model, "/", fixed = TRUE))
d$detector <- parts[, 1]
d$variant <- factor(parts[, 2], levels = c("plain", "normalised", "canonical", "augmented", "augmented+normalised"))
d$kind <- ifelse(d$transform == "none", "clean",
                 ifelse(d$transform %in% c("upper", "zero_width", "homoglyph"), "seen", "unseen"))
d$kind <- factor(d$kind, levels = c("clean", "seen", "unseen"))
d$template <- paste(d$seed, d$template)  # held-out sets differ by seed
m <- d[d$detector != "regex", ]

cat("Recall pooled over templates (documents weighted equally)\n")
print(round(with(m, tapply(caught, list(paste(detector, variant), kind), sum) /
                   tapply(n, list(paste(detector, variant), kind), sum)), 3))

fit <- lme4::glmer(cbind(caught, n - caught) ~ detector + variant * kind + (1 | template) + (1 | transform),
                   data = m, family = binomial, control = lme4::glmerControl(optimizer = "bobyqa"))
cat("\nglmer: caught ~ detector + variant * kind + (1 | template) + (1 | transform)\n")
co <- summary(fit)$coefficients
print(round(cbind(co[, 1:2], odds_ratio = exp(co[, 1]), p = co[, 4]), 3))
cat("\nRandom-effect SDs on the logit scale\n")
print(round(sqrt(unlist(lme4::VarCorr(fit))), 2))
if (!is.null(fit@optinfo$conv$lme4$messages)) cat("Convergence notes:", fit@optinfo$conv$lme4$messages, "\n")
cat("\nTerms are not corrected for multiple comparisons, and with only four unseen rewrites the\n")
cat("transform effect is poorly estimated. Treat the sign and rough size as the finding.\n")
