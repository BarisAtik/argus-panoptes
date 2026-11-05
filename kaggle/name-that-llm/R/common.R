# Shared helpers. Style features mirror src/ntl/features.py closely but are not guaranteed identical,
# so compare the two languages on metrics, not on feature values.
suppressPackageStartupMessages({
  library(dplyr); library(tidyr); library(readr); library(stringr); library(ggplot2)
})

data_dir <- function(default = "data/raw") {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) >= 1) args[[1]] else default
}

load_train <- function(dir) {
  train <- read_csv(file.path(dir, "train.csv"), show_col_types = FALSE)
  stopifnot(all(c("id", "prompt_id", "text", "model") %in% names(train)))
  train
}

add_style <- function(df) {
  words <- str_extract_all(df$text, "[A-Za-z']+")
  n_w <- pmax(lengths(words), 1L)
  per100 <- function(x) x * 100 / n_w
  df %>%
    mutate(
      n_words = n_w,
      word_len = vapply(words, function(w) if (length(w)) mean(nchar(w)) else 0, numeric(1)),
      type_token = vapply(words, function(w) length(unique(tolower(w))), integer(1)) / n_w,
      words_per_sent = n_w / pmax(str_count(text, "[.!?;]+(\\s|$)"), 1L),
      comma = per100(str_count(text, ",")),
      semicolon = per100(str_count(text, ";")),
      colon = per100(str_count(text, ":")),
      em_dash = per100(str_count(text, "—")),
      paren = per100(str_count(text, "\\(")),
      question = per100(str_count(text, "\\?")),
      bullet = per100(str_count(text, "(^|\\n|\\s)[-*•]\\s")),
      contraction = per100(str_count(text, "[A-Za-z]'[a-z]")),
      digit = per100(str_count(text, "[0-9]"))
    )
}

style_cols <- c("n_words", "word_len", "type_token", "words_per_sent", "comma", "semicolon",
                "colon", "em_dash", "paren", "question", "bullet", "contraction", "digit")

# The competition metric: mean per-class recall. Equals yardstick::sens(estimator = "macro").
# yardstick::bal_accuracy is NOT this for multiclass: it averages (sensitivity + specificity) / 2.
balanced_accuracy <- function(truth, estimate) {
  mean(tapply(as.character(truth) == as.character(estimate), as.character(truth), mean))
}

report_path <- function(name) {
  dir.create("reports/generated", recursive = TRUE, showWarnings = FALSE)
  file.path("reports/generated", name)
}
