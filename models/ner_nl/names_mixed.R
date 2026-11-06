# Cross-check of the name-swap gap with a logistic mixed model. Run from models/:
#   Rscript ner_nl/names_mixed.R runs/ner_nl/names.csv runs/ner_nl/names_mixed.json
# Article and name are random effects, so the interval also reflects which names were listed,
# something the article bootstrap ignores. Each model is fitted separately.
suppressPackageStartupMessages({library(lme4); library(jsonlite)})
args <- commandArgs(trailingOnly = TRUE)
d <- read.csv(args[1])
d$group <- relevel(factor(d$group), ref = "dutch")
out <- list()
for (m in unique(d$model)) {
  x <- d[d$model == m, ]
  # Identical mentions recur across five repeats, so collapse to a sensible grain.
  fit <- glmer(exact ~ group + (1 | doc) + (1 | name), data = x, family = binomial,
               control = glmerControl(optimizer = "bobyqa", calc.derivs = FALSE), nAGQ = 0)
  co <- summary(fit)$coefficients
  rows <- co[grepl("^group", rownames(co)), , drop = FALSE]
  vc <- as.data.frame(VarCorr(fit))
  out[[m]] <- list(
    term = sub("^group", "", rownames(rows)),
    odds_ratio = exp(rows[, 1]),
    low = exp(rows[, 1] - 1.96 * rows[, 2]),
    high = exp(rows[, 1] + 1.96 * rows[, 2]),
    p = rows[, 4],
    sd_doc = vc$sdcor[vc$grp == "doc"],
    sd_name = vc$sdcor[vc$grp == "name"]
  )
}
write_json(out, args[2], auto_unbox = TRUE, digits = 4, pretty = TRUE)
print(toJSON(out, auto_unbox = TRUE, digits = 3, pretty = TRUE))
