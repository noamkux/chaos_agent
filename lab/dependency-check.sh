#!/usr/bin/env bash
# Scales each boutique dependency to 0, one at a time, and records how the frontend responds.
# Requires: kubectl -n boutique port-forward svc/frontend 8080:80
set -euo pipefail

NS="boutique"
BASE_URL="http://localhost:8080"
PRODUCT_ID="OLJCESPC7Z"
SERVICES=(adservice cartservice checkoutservice currencyservice emailservice
          paymentservice productcatalogservice recommendationservice
          redis-cart shippingservice)

# Undo: if the script stops for any reason, bring the current service back
current=""
current_replicas=""
restore() {
  if [ -n "$current" ]; then
    echo "Restoring $current to $current_replicas replicas" >&2
    kubectl -n "$NS" scale deploy "$current" --replicas="$current_replicas" >/dev/null
  fi
}
trap restore EXIT

http_code() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$@" || true
}

# Pod Ready is not enough: the frontend may still be reconnecting to the restored service
wait_for_baseline() {
  for _ in $(seq 1 30); do
    if [ "$(http_code "$BASE_URL/")" = "200" ] && \
       [ "$(http_code "$BASE_URL/product/$PRODUCT_ID")" = "200" ]; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: system did not return to baseline within 60s" >&2
  exit 1
}

check_pages() {
  local label="$1" jar home product addcart cart checkout
  jar=$(mktemp)
  home=$(http_code -c "$jar" "$BASE_URL/")
  product=$(http_code -b "$jar" -c "$jar" "$BASE_URL/product/$PRODUCT_ID")
  addcart=$(http_code -b "$jar" -c "$jar" -X POST \
    -d "product_id=$PRODUCT_ID&quantity=1" "$BASE_URL/cart")
  cart=$(http_code -b "$jar" -c "$jar" "$BASE_URL/cart")
  checkout=$(http_code -b "$jar" -c "$jar" -X POST \
    -d "email=test@example.com&street_address=1+Main+St&zip_code=12345&city=Test&state=CA&country=US" \
    -d "credit_card_number=4432801561520454&credit_card_expiration_month=1" \
    -d "credit_card_expiration_year=2030&credit_card_cvv=672" \
    "$BASE_URL/cart/checkout")
  rm -f "$jar"
  printf '%-28s %-6s %-9s %-9s %-6s %-9s\n' "$label" "$home" "$product" "$addcart" "$cart" "$checkout"
}

wait_for_baseline
printf '%-28s %-6s %-9s %-9s %-6s %-9s\n' "SCENARIO" "HOME" "PRODUCT" "ADD_CART" "CART" "CHECKOUT"
check_pages "baseline"

for svc in "${SERVICES[@]}"; do
  current_replicas=$(kubectl -n "$NS" get deploy "$svc" -o jsonpath='{.spec.replicas}')
  current="$svc"
  kubectl -n "$NS" scale deploy "$svc" --replicas=0 >/dev/null
  kubectl -n "$NS" wait --for=delete pod -l app="$svc" --timeout=60s >/dev/null 2>&1 || true
  check_pages "$svc down"
  kubectl -n "$NS" scale deploy "$svc" --replicas="$current_replicas" >/dev/null
  kubectl -n "$NS" rollout status deploy "$svc" --timeout=120s >/dev/null
  current=""
  wait_for_baseline
done