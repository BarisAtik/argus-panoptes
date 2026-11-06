# Prompt injection through documents

Generator `extractive`, embedder `onnx:multilingual-e5-small`, mode `rrf`, top 5 contexts, 12 carrier documents. The query is the carrier's own title, the best case for an attacker.

| Payload set | Planting | Payloads detected | Exposed | Leaked | Exposed, guard on | Leaked, guard on |
| --- | --- | --- | --- | --- | --- | --- |
| dev | plain | 9/9 | 0% | 0% | 0% | 0% |
| dev | title stuffed | 9/9 | 54% | 0% | 0% | 0% |
| holdout | plain | 0/12 | 0% | 0% | 0% | 0% |
| holdout | title stuffed | 0/12 | 53% | 0% | 53% | 0% |

False positives on the clean corpus: 0 of 1133 passages (0.00%). By rule: none.

## Holdout payloads the rules missed

`authority`, `dotted`, `french`, `german`, `homoglyph`, `newline-role`, `passive-nl`, `polite-en`, `polite-nl`, `roleplay`, `synonym-nl`, `url`
