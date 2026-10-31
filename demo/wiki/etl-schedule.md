# ETL schedule

## Nightly load
Contacts and responses are loaded every night at 03:00 by the Airflow DAG cvm_daily_load.
The load usually finishes by 05:30.

## Late data
If the source system is late, the DAG retries three times with a 30 minute pause.
Data that arrives after 08:00 is loaded the next night, so morning reports may miss yesterday's tail.
