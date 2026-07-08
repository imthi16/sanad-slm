# Fixed fertility corpora

Three frozen text files (collected once at P4; committed so numbers stay comparable):

| File | Content | Size target | Source constraint |
|---|---|---|---|
| `msa_news.txt` | Modern Standard Arabic news prose | ~10,000 words | own-collected / CC-licensed only |
| `banking_ar.txt` | Arabic banking/compliance prose | ~5,000 words | own-authored / CC-licensed only |
| `english.txt` | General English prose | ~10,000 words | CC-licensed only |

Rules: plain UTF-8 text, NFC-normalized, no markup; once committed, **never edit** — a corpus
change invalidates every previously published fertility number (add a `_v2` file instead and
bump the consumers).
