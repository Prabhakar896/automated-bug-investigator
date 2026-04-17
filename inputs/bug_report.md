# Bug Report: Negative Payment Amount on 100% Promo Code

## Title
Customer charged negative amount when applying 100% promotional discount code

## Severity
**HIGH** — Financial impact, customer-facing, potential revenue leakage

## Environment
- **Application:** Antigravity Payment Service v2.4.1
- **Python:** 3.11.4
- **OS:** Ubuntu 22.04 LTS
- **Framework:** FastAPI 0.104.1
- **Deploy:** Kubernetes (GKE), deployed 2024-01-15 14:32 UTC
- **Dependencies:** See requirements.txt

## Description
Multiple customers have reported being "charged" a negative amount when applying the `PROMO100` promotional discount code (100% off) to their orders. The payment system is generating negative totals, which causes the payment processor to throw a `ValueError` and the order to fail with HTTP 500.

The issue first appeared after the v2.4.1 deploy on January 15th. Prior versions did not support percentage discounts above 50%, so this code path was never exercised before.

## Expected Behavior
When a 100% discount code is applied:
1. The discount should reduce the order subtotal to $0.00
2. Tax should be calculated on the discounted amount ($0.00)
3. The total should be $0.00
4. The order should complete successfully as a fully comped order (no payment needed)

## Actual Behavior
When `PROMO100` is applied to a $50.00 order:
1. The system calculates subtotal = $50.00, tax = $4.00, gross = $54.00
2. The discount is applied to the gross amount: $54.00 × 100% = $54.00
3. Total = $54.00 - $54.00 = $0.00 ... wait, that should be zero?

Actually, looking more carefully at reports, customers with different tax rates are seeing varying negative amounts. One test with a $43.75 subtotal showed a total of -$3.50.

**Error seen in logs:**
```
ValueError: Payment amount must be positive, got: -$3.50
```

## Steps to Reproduce (partial)
1. Create an order with items totaling any positive subtotal
2. Apply discount code `PROMO100` (type: percentage, value: 100)
3. POST to `/orders` endpoint
4. Observe HTTP 500 response

Note: I couldn't reproduce this consistently in my local dev environment. It might be related to the tax rate configuration or the specific combination of items. The tax rate might differ between environments.

## Impact
- ~47 failed orders in the last 24 hours
- 12 customer support tickets filed
- PROMO100 code was distributed to 500 VIP customers via email campaign
- Potential trust/brand impact

## Additional Context
- The `PROMO100` code was added as part of the VIP loyalty program in v2.4.1
- Previous discount codes were capped at 50%
- The `payment_service.py` module was refactored in v2.4.0 to support percentage discounts (before that, only fixed dollar discounts were supported)
- The intern who wrote the discount logic left the company last week
