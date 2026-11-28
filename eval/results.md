| | run 30 | run 31 | run 32 | run 33 | run 34 | run 35 | run 36 |
|---|---|---|---|---|---|---|---|
| Model | claude-sonnet-5-5 | claude-haiku-5-5 | claude-haiku-5-5 | claude-haiku-5-5 | claude-haiku-5-5 | verify | verify |
| Status | completed | completed | completed | completed | completed | completed | completed |
| Recall, cited in the summary | 3/10 | 1/10 | 2/10 | 4/10 | 4/10 | n/a | n/a |
| Recall, experiments that broke | 3/10 | 3/10 | 2/10 | 4/10 | 4/10 | 0/10 | 1/10 |
| Unknown findings (to review) | 4 | 5 | 1 | 7 | 4 | 0 | 0 |
| False positives, cited | 0 | 0 | 0 | 0 | 0 | n/a | n/a |
| False positives, broke | 0 | 1 | 1 | 1 | 0 | 0 | 0 |
| Experiments | 13 | 13 | 8 | 15 | 15 | 9 | 2 |
| Inconclusive | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| Broke when run, withstood by the current judge | 0 | 2 | 1 | 0 | 2 | 1 | 0 |
| Not run (never steady) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Model rounds | 13 | 15 | 11 | 19 | 21 | 0 | 0 |
| Tokens in / out | 263,482 / 6,445 | 368,458 / 17,122 | 293,408 / 8,901 | 706,472 / 15,565 | 859,058 / 19,549 | 0 / 0 | 0 / 0 |
| Cost (USD) | 0.15 | 0.02 | 0.01 | 0.02 | 0.03 | 0.00 | 0.00 |
| Duration (min) | 21.1 | 26.0 | 12.4 | 27.1 | 28.1 | 13.3 | 3.8 |
| Seconds broken | 295 | 370 | 170 | 292 | 340 | 2 | 31 |
| Denied calls | 0 | 1 | 0 | 0 | 1 | 0 | 0 |
| Pending undos (must be 0) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Experiments on known weaknesses / new | 5 / 8 | 4 / 9 | 1 / 7 | 4 / 11 | 4 / 11 | 2 / 7 | 2 / 0 |

### Run 30

- Found, cited: N1-checkoutservice, N1-shippingservice, W1
- Found, broke: N1-checkoutservice, N1-shippingservice, W1
- False positives: cited none; broke none
- Unverified entries shown: none
- Unknown, step 21 (cited): node_failure lost of chaos-lab-worker2, broke cart, checkout, home, product
- Unknown, step 37 (cited): patch productcatalogservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=20m, spec.template.spec.containers.resources.requests.cpu=20m), broke cart, checkout, product
- Unknown, step 48: delete_pod frontend, broke cart, checkout, home, product
- Unknown, step 59 (cited): patch productcatalogservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=20m, spec.template.spec.containers.resources.requests.cpu=20m), broke cart, checkout, home, product

### Run 31

- Found, cited: W1
- Found, broke: N1-checkoutservice, N1-paymentservice, W1
- False positives: cited none; broke S4-recommendationservice
- Unverified entries shown: none
- Unknown, step 37: node_failure lost of chaos-lab-worker2, broke cart, checkout
- Unknown, step 60: delete_pod cartservice, broke cart, checkout
- Unknown, step 67 (cited): patch productcatalogservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=50m, spec.template.spec.containers.resources.requests.cpu=50m), broke cart, checkout, home, product
- Unknown, step 75 (cited): patch productcatalogservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=50m, spec.template.spec.containers.resources.requests.cpu=50m), broke cart, checkout, product
- Unknown, step 82 (cited): patch recommendationservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=10m, spec.template.spec.containers.resources.requests.cpu=10m), broke cart, checkout, home, product

### Run 32

- Found, cited: N11, W1
- Found, broke: N11, W1
- False positives: cited none; broke S4-adservice
- Unverified entries shown: none
- Unknown, step 56 (cited): node_failure lost of chaos-lab-worker2, broke cart, checkout, product

### Run 33

- Found, cited: N1-paymentservice, N1-shippingservice, N11, W1
- Found, broke: N1-paymentservice, N1-shippingservice, N11, W1
- False positives: cited none; broke S4-adservice
- Unverified entries shown: N10
- Unknown, step 21: patch shippingservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=10m, spec.template.spec.containers.resources.requests.cpu=10m), broke cart, checkout
- Unknown, step 41: patch currencyservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=10m, spec.template.spec.containers.resources.requests.cpu=10m), broke cart, checkout, home, product
- Unknown, step 48 (cited): patch checkoutservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=10m, spec.template.spec.containers.resources.requests.cpu=10m), broke checkout
- Unknown, step 76 (cited): patch recommendationservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=10m, spec.template.spec.containers.resources.requests.cpu=10m), broke home
- Unknown, step 89 (cited): node_failure drain of chaos-lab-worker2, broke cart, checkout, product
- Unknown, step 105: patch frontend (spec.template.metadata.annotations.chaos-run=rollout-check), broke cart
- Unknown, step 136 (cited): patch checkoutservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=10m, spec.template.spec.containers.resources.requests.cpu=10m), broke checkout

### Run 34

- Found, cited: N1-checkoutservice, N1-shippingservice, N11, W1
- Found, broke: N1-checkoutservice, N1-shippingservice, N11, W1
- False positives: cited none; broke none
- Unverified entries shown: N10
- Unknown, step 30: node_failure lost of chaos-lab-worker2, broke checkout
- Unknown, step 48: patch currencyservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=10m, spec.template.spec.containers.resources.requests.cpu=10m), broke home
- Unknown, step 77 (cited): patch shippingservice (spec.template.spec.containers.name=server, spec.template.spec.containers.resources.limits.cpu=10m, spec.template.spec.containers.resources.requests.cpu=10m), broke cart, checkout
- Unknown, step 115: patch frontend (spec.template.metadata.annotations.chaos-rollout=1), broke checkout

### Run 35

- Found, cited: n/a
- Found, broke: none
- False positives: cited n/a; broke none
- Unverified entries shown: none

### Run 36

- Found, cited: n/a
- Found, broke: N11
- False positives: cited n/a; broke none
- Unverified entries shown: none
