# Incident 2026-08: duplicate loads

## What happened
In August the nightly ETL job was restarted after a timeout and loaded the same responses file twice.
Response counts for two campaigns were inflated by about 1.5%.

## Detection
An analyst noticed that responders exceeded distinct customers for one campaign.

## Fix
The responses table got a uniqueness check on customer, campaign, date and revenue.
Duplicates are now removed before any readout, see [[data-quality-checklist]].
