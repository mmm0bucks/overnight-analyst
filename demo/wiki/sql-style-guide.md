# SQL style guide

## Rules
- Use CTEs instead of nested subqueries.
- Never use SELECT * in shared notebooks; list the columns.
- Always add LIMIT when exploring a large table.
- Name aggregates explicitly: count(*) AS contacts, not just count(*).
