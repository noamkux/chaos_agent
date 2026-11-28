| | run 30 | run 31 | run 32 | run 33 | run 34 | run 35 | run 36 | run 37 | run 38 |
|---|---|---|---|---|---|---|---|---|---|
| Model | claude-sonnet-5-5 | claude-haiku-5-5 | claude-haiku-5-5 | claude-haiku-5-5 | claude-haiku-5-5 | verify | verify | baseline | claude-sonnet-5-5 |
| Status | completed | completed | completed | completed | completed | completed | completed | completed | completed |
| Weaknesses tested at all | 3/10 | 3/10 | 2/10 | 4/10 | 4/10 | 1/10 | 1/10 | 2/10 | 1/10 |
| Recall, cited in the summary | 3/10 | 1/10 | 2/10 | 4/10 | 4/10 | n/a | n/a | n/a | 1/10 |
| Recall, experiments that broke | 3/10 | 3/10 | 2/10 | 4/10 | 4/10 | 0/10 | 1/10 | 2/10 | 1/10 |
| Unknown findings (to review) | 2 | 2 | 1 | 2 | 2 | 0 | 0 | 1 | 6 |
| Trivial experiments (break by design) | 2 | 5 | 1 | 6 | 7 | 2 | 0 | 0 | 4 |
| False positives, cited | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | 0 |
| False positives, broke | 0 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| Experiments | 13 | 13 | 8 | 15 | 15 | 9 | 2 | 9 | 15 |
| Inconclusive | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 3 |
| Broke when run, withstood by the current judge | 0 | 2 | 1 | 0 | 2 | 1 | 0 | 0 | 0 |
| Not run (never steady) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 1 |
| Model rounds | 13 | 15 | 11 | 19 | 21 | 0 | 0 | 0 | 20 |
| Tokens in / out | 263,482 / 6,445 | 368,458 / 17,122 | 293,408 / 8,901 | 706,472 / 15,565 | 859,058 / 19,549 | 0 / 0 | 0 / 0 | 0 / 0 | 539,608 / 9,022 |
| Cost (USD) | 0.15 | 0.02 | 0.01 | 0.02 | 0.03 | 0.00 | 0.00 | 0.00 | 0.23 |
| Duration (min) | 21.1 | 26.0 | 12.4 | 27.1 | 28.1 | 13.3 | 3.8 | 20.6 | 27.8 |
| Seconds broken | 295 | 370 | 170 | 292 | 340 | 2 | 31 | 51 | 197 |
| Denied calls | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| Pending undos (must be 0) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Experiments on known weaknesses / new | 5 / 8 | 4 / 9 | 1 / 7 | 4 / 11 | 4 / 11 | 2 / 7 | 2 / 0 | 3 / 6 | 2 / 13 |

### Run 30

- Tested: N1-checkoutservice, N1-shippingservice, W1
- Found, cited: N1-checkoutservice, N1-shippingservice, W1
- Found, broke: N1-checkoutservice, N1-shippingservice, W1
- False positives: cited none; broke none
- Unverified entries shown: none
- Trivial experiments: step 37, step 59
- Unknown, step 21 (cited): node_failure lost of chaos-lab-worker2, broke cart, checkout, home, product
- Unknown, step 48: delete_pod frontend, broke cart, checkout, home, product

### Run 31

- Tested: N1-checkoutservice, N1-paymentservice, W1
- Found, cited: W1
- Found, broke: N1-checkoutservice, N1-paymentservice, W1
- False positives: cited none; broke S4-recommendationservice
- Unverified entries shown: none
- Trivial experiments: step 67, step 75, step 82, step 89, step 113
- Unknown, step 37: node_failure lost of chaos-lab-worker2, broke cart, checkout
- Unknown, step 60: delete_pod cartservice, broke cart, checkout

### Run 32

- Tested: N11, W1
- Found, cited: N11, W1
- Found, broke: N11, W1
- False positives: cited none; broke S4-adservice
- Unverified entries shown: none
- Trivial experiments: step 32
- Unknown, step 56 (cited): node_failure lost of chaos-lab-worker2, broke cart, checkout, product

### Run 33

- Tested: N1-paymentservice, N1-shippingservice, N11, W1
- Found, cited: N1-paymentservice, N1-shippingservice, N11, W1
- Found, broke: N1-paymentservice, N1-shippingservice, N11, W1
- False positives: cited none; broke S4-adservice
- Unverified entries shown: N10
- Trivial experiments: step 21, step 28, step 41, step 48, step 76, step 136
- Unknown, step 89 (cited): node_failure drain of chaos-lab-worker2, broke cart, checkout, product
- Unknown, step 105: patch frontend (spec.template.metadata.annotations.chaos-run=rollout-check), broke cart

### Run 34

- Tested: N1-checkoutservice, N1-shippingservice, N11, W1
- Found, cited: N1-checkoutservice, N1-shippingservice, N11, W1
- Found, broke: N1-checkoutservice, N1-shippingservice, N11, W1
- False positives: cited none; broke none
- Unverified entries shown: N10
- Trivial experiments: step 48, step 60, step 70, step 77, step 85, step 92, step 99
- Unknown, step 30: node_failure lost of chaos-lab-worker2, broke checkout
- Unknown, step 115: patch frontend (spec.template.metadata.annotations.chaos-rollout=1), broke checkout

### Run 35

- Tested: N11
- Found, cited: n/a
- Found, broke: none
- False positives: cited n/a; broke none
- Unverified entries shown: none
- Trivial experiments: step 21, step 27

### Run 36

- Tested: N11
- Found, cited: n/a
- Found, broke: N11
- False positives: cited n/a; broke none
- Unverified entries shown: none
- Trivial experiments: none

### Run 37

- Tested: N1-checkoutservice, N1-paymentservice
- Found, cited: n/a
- Found, broke: N1-checkoutservice, N1-paymentservice
- False positives: cited n/a; broke none
- Unverified entries shown: none
- Trivial experiments: none
- Unknown, step 20: delete_pod currencyservice, broke home

### Run 38

- Tested: W1
- Found, cited: W1
- Found, broke: W1
- False positives: cited none; broke S4-adservice
- Unverified entries shown: N10
- Trivial experiments: step 50, step 64, step 72, step 79
- Unknown, step 11: delete_pod currencyservice, broke home
- Unknown, step 21: delete_pod frontend, broke home
- Unknown, step 40: delete_pod emailservice, broke home
- Unknown, step 45: delete_pod recommendationservice, broke checkout, home
- Unknown, step 59: delete_pod productcatalogservice, broke home
- Unknown, step 119: node_failure lost of chaos-lab-worker2, broke cart, checkout, product
