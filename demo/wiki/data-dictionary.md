# Data dictionary

- `campaigns(campaign_id, name, channel, start_date, end_date)` — one row per campaign.
- `contacts(customer_id, campaign_id, grp, contact_date)` — who was targeted; `grp` is `treatment` or `control`. A customer must be in exactly one group per campaign.
- `responses(customer_id, campaign_id, response_date, revenue)` — a response is attributed to a campaign if it happens after the contact date and within the campaign window. One row per response.
