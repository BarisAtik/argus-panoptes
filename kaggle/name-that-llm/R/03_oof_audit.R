# Independent audit of Python's out-of-fold predictions: recompute the score from scratch in R,
# and bootstrap whole prompts for an interval. A second implementation catches metric bugs.
#   Rscript R/03_oof_audit.R artifacts/real/oof_blend.parquet
source("R/common.R")
suppressPackageStartupMessages(library(arrow))
set.seed(1)

path <- commandArgs(trailingOnly = TRUE)[1]
oof <- read_parquet(path)
meta <- c("id", "fold", "model", "prompt_id")
classes <- setdiff(names(oof), meta)
pred <- classes[max.col(as.matrix(oof[classes]), ties.method = "first")]
oof$pred <- pred

point <- balanced_accuracy(oof$model, oof$pred)
rows <- split(seq_len(nrow(oof)), oof$prompt_id)
boots <- replicate(1000, {
  pick <- unlist(sample(rows, length(rows), replace = TRUE), use.names = FALSE)
  balanced_accuracy(oof$model[pick], oof$pred[pick])
})
cat(sprintf("Balanced accuracy %.4f, 95%% prompt-bootstrap CI [%.4f, %.4f]\n",
            point, quantile(boots, .025), quantile(boots, .975)))

per_model <- oof %>%
  group_by(model) %>%
  summarise(recall = mean(model == pred), n = n(), .groups = "drop") %>%
  arrange(recall)
print(per_model, n = Inf)

heat <- oof %>% count(model, pred) %>% group_by(model) %>% mutate(share = n / sum(n)) %>% ungroup()
p <- ggplot(heat, aes(pred, model, fill = share)) +
  geom_tile() +
  scale_fill_gradient(low = "#f4f6f8", high = "#1f5f7a") +
  labs(title = "Out-of-fold confusion", x = "Predicted", y = "True") +
  theme_minimal(base_size = 10) +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))
ggsave(report_path("r_confusion.png"), p, width = 8, height = 7, dpi = 160)
