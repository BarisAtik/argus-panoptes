# How injected documents go wrong

Exploratory, added after seeing the results. Four `delegate-plain` models, 4200 injected trials. A toy.

The registered ASR only counts actions sent to the attacker's destination, so it scores a blended action as no attack.

| Outcome | Trials | Share |
| --- | ---: | ---: |
| correct | 2691 | 64.1% |
| blended: right tool and target, wrong value | 710 | 16.9% |
| hijacked | 299 | 7.1% |
| blended: wrong tool | 286 | 6.8% |
| malformed | 213 | 5.1% |
| other | 1 | 0.0% |
