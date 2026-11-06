# Crossed random intercepts for model and test item. Each model answers each item once, greedily.
# Rscript analysis/talos.R data/all.csv.gz > data/glmm.txt
suppressPackageStartupMessages(library(lme4))
args <- commandArgs(TRUE)
d <- read.csv(gzfile(args[1]), colClasses = c(heldout = "character"))
ctrl <- glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
inj <- d[startsWith(d$cell, "inject/"), ]
inj$family <- sub("inject/", "", inj$cell)
inj$prov <- relevel(factor(inj$prov), "plain")
# glmer refuses a constant response, which is itself a result: nothing to model.
fit <- function(title, f, data) {
  if (length(unique(data$attack)) < 2) {
    cat("\n==", title, "\nnot fitted:", sum(data$attack), "successes in", nrow(data), "trials\n")
    return(invisible())
  }
  report(title, glmer(f, data, binomial, control = ctrl))
}
report <- function(title, m) {
  cat("\n==", title, "\n")
  s <- summary(m)
  print(round(s$coefficients, 3))
  print(VarCorr(m), comp = "Std.Dev.")
  cat("singular fit:", isSingular(m), "\n")
}
# T4: do marks matter with no attack training?
fit("T4, delegate regime: attack ~ provenance", attack ~ prov + (1 | model) + (1 | item), inj[inj$regime == "delegate", ])
# T3: known versus held-out family, adv regime
adv <- inj[inj$regime == "adv", ]
adv$heldout_family <- as.integer(adv$family == adv$heldout)
fit("T3, adv regime: attack ~ held-out + provenance", attack ~ heldout_family + prov + (1 | model) + (1 | item), adv)
# T5: forged closing delimiter, the held-out break models. Few models, so read with care.
brk <- adv[adv$family == "break" & adv$heldout == "break", ]
brk$prov <- relevel(factor(brk$prov), "segment")
fit("T5, break held out, reference segment", attack ~ prov + (1 | item), brk)
