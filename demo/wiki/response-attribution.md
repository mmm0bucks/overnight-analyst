# Response attribution

## Window
A response counts for a campaign if it happens within 14 days after the contact date.
Responses before the contact date are never attributed.

## Deduplication
One customer gives at most one response per campaign per day. Rows with the same
customer, campaign, date and revenue are duplicates of a single response.

## Overlapping campaigns
If a customer was contacted by two campaigns, the response goes to the most recent contact (last touch).
