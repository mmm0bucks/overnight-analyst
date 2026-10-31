# Control group policy

## Size
The holdout is 10% of the eligible base, never smaller than 1 000 customers.

## Randomisation
Customers are assigned to treatment or control by a hash of customer_id and campaign_id,
so the split is reproducible and does not depend on the order of the list.

## No overlap
A customer must be in exactly one group per campaign. If a customer appears in both
treatment and control, the campaign readout is invalid until the overlap is removed.
