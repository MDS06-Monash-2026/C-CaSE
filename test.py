from google.cloud import bigquery
import os
import sys

sys.path.append('d:/C-CaSE/evaluation_suite')
from evaluate import get_bigquery_sql_result

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'd:/C-CaSE/evaluation_suite/bigquery_credential.json'

q1 = """
SELECT
  DATE(CAST(year AS INT64), CAST(mo AS INT64), CAST(da AS INT64)) AS date
FROM
  `bigquery-public-data.noaa_gsod.gsod2009`
WHERE
  stn = '723758'
  AND year = '2009'
  AND mo = '10'
  AND temp != 9999.9
ORDER BY
  temp DESC
LIMIT 3
"""

exe_flag, err = get_bigquery_sql_result(q1, False, None, None, 'bq392')
print("Baseline exe_flag:", exe_flag)
if not exe_flag:
    print("Baseline ERROR:", err)
