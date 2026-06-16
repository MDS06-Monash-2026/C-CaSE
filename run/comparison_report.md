# 🔍 SQL Pipeline Execution Comparison
> AutoLink vs SlayQL (C-CaSE) vs Gold Reference

## 1. Instance: `bq001`
**Question:**
> For each visitor who made at least one transaction in February 2017, how many days elapsed between the date of their first visit in February and the date of their first transaction in February, and on what type of device did they make that first transaction?

### 🏆 Gold Reference Answer
```sql
DECLARE start_date STRING DEFAULT '20170201';
DECLARE end_date STRING DEFAULT '20170228';

WITH visit AS (
    SELECT
        fullvisitorid,
        MIN(date) AS date_first_visit
    FROM
        `bigquery-public-data.google_analytics_sample.ga_sessions_*`
    WHERE
       _TABLE_SUFFIX BETWEEN start_date AND end_date
    GROUP BY fullvisitorid
),

transactions AS (
    SELECT
        fullvisitorid,
        MIN(date) AS date_transactions
    FROM
        `bigquery-public-data.google_analytics_sample.ga_sessions_*` AS ga,
        UNNEST(ga.hits) AS hits
    WHERE
        hits.transaction.transactionId IS NOT NULL
        AND
        _TABLE_SUFFIX BETWEEN start_date AND end_date
    GROUP BY fullvisitorid
),

device_transactions AS (
    SELECT DISTINCT
        fullvisitorid,
        date,
        device.deviceCategory
    FROM
        `bigquery-public-data.google_analytics_sample.ga_sessions_*` AS ga,
        UNNEST(ga.hits) AS hits
    WHERE
        hits.transaction.transactionId IS NOT NULL
        AND
        _TABLE_SUFFIX BETWEEN start_date AND end_date
),

visits_transactions AS (
    SELECT
        visit.fullvisitorid,
        date_first_visit,
        date_transactions,
        device_transactions.deviceCategory AS device_transaction
    FROM
        visit
        JOIN transactions
        ON visit.fullvisitorid = transactions.fullvisitorid
        JOIN device_transactions
        ON visit.fullvisitorid = device_transactions.fullvisitorid 
        AND transactions.date_transactions = device_transactions.date
)

SELECT
       fullvisitorid,
       DATE_DIFF(PARSE_DATE('%Y%m%d', date_transactions), PARSE_DATE('%Y%m%d', date_first_visit), DAY) AS time,
       device_transaction
FROM visits_transactions
ORDER BY fullvisitorid;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- For each visitor with at least one transaction in February 2017,
-- calculate days between first visit and first transaction,
-- and show the device type used for that first transaction.

WITH 
-- Identify all sessions with transactions in February 2017
transaction_sessions AS (
    SELECT 
        fullVisitorId,
        date,
        device.deviceCategory,
        -- Rank transactions by date to find the first one per visitor
        ROW_NUMBER() OVER (PARTITION BY fullVisitorId ORDER BY date ASC) AS rn
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
    WHERE _TABLE_SUFFIX BETWEEN '20170201' AND '20170228'
      AND totals.transactions > 0
),

-- Extract the first transaction for each visitor
first_transactions AS (
    SELECT 
        fullVisitorId,
        date AS first_transaction_date,
        deviceCategory AS first_transaction_device
    FROM transaction_sessions
    WHERE rn = 1
),

-- Find the first visit date in February for each visitor
first_visits AS (
    SELECT 
        fullVisitorId,
        MIN(date) AS first_visit_date
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
    WHERE _TABLE_SUFFIX BETWEEN '20170201' AND '20170228'
    GROUP BY fullVisitorId
)

-- Combine results and calculate days elapsed
SELECT 
    ft.fullVisitorId,
    DATE_DIFF(
        PARSE_DATE('%Y%m%d', ft.first_transaction_date),
        PARSE_DATE('%Y%m%d', fv.first_visit_date),
        DAY
    ) AS days_elapsed,
    ft.first_transaction_device
FROM first_transactions ft
JOIN first_visits fv ON ft.fullVisitorId = fv.fullVisitorId
ORDER BY ft.fullVisitorId;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Get all sessions that had transactions in February 2017
transaction_sessions AS (
  SELECT 
    fullVisitorId,
    PARSE_DATE('%Y%m%d', date) AS session_date,
    device.deviceCategory AS device_category,
    hit.transaction.transactionId
  FROM 
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`,
    UNNEST(hits) AS hit
  WHERE 
    _TABLE_SUFFIX BETWEEN '20170201' AND '20170228'
    AND hit.transaction.transactionId IS NOT NULL
),

-- Get all sessions (visits) in February 2017
all_feb_sessions AS (
  SELECT 
    fullVisitorId,
    PARSE_DATE('%Y%m%d', date) AS session_date
  FROM 
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE 
    _TABLE_SUFFIX BETWEEN '20170201' AND '20170228'
),

-- Get first visit date in February for each visitor
first_visit AS (
  SELECT
    fullVisitorId,
    MIN(session_date) AS first_visit_date
  FROM 
    all_feb_sessions
  GROUP BY 
    fullVisitorId
),

-- For each transaction session, rank by date to get the first one
ranked_transactions AS (
  SELECT 
    fullVisitorId,
    session_date,
    device_category,
    ROW_NUMBER() OVER (PARTITION BY fullVisitorId ORDER BY session_date) AS rn
  FROM 
    transaction_sessions
)

-- Final output: first transaction details with days elapsed
SELECT
  fv.fullVisitorId,
  fv.first_visit_date,
  rt.session_date AS first_transaction_date,
  DATE_DIFF(rt.session_date, fv.first_visit_date, DAY) AS days_between,
  rt.device_category AS first_transaction_device
FROM 
  first_visit fv
INNER JOIN 
  ranked_transactions rt
ON 
  fv.fullVisitorId = rt.fullVisitorId AND rt.rn = 1
ORDER BY 
  fv.fullVisitorId;
```

---

## 2. Instance: `bq002`
**Question:**
> During the first half of 2017,  focusing on hits product revenue, which traffic source generated the highest total product revenue, and what were the maximum daily, weekly, and monthly product revenues (in millions) for that top-performing source over this period?

### 🏆 Gold Reference Answer
```sql
DECLARE start_date STRING DEFAULT '20170101';
DECLARE end_date STRING DEFAULT '20170630';

WITH daily_revenue AS (
    SELECT
        trafficSource.source AS source,
        date,
        SUM(productRevenue) / 1000000 AS revenue
    FROM
        `bigquery-public-data.google_analytics_sample.ga_sessions_*`,
        UNNEST (hits) AS hits,
        UNNEST (hits.product) AS product
    WHERE
        _table_suffix BETWEEN start_date AND end_date
    GROUP BY
        source, date
),
weekly_revenue AS (
    SELECT
        source,
        CONCAT(EXTRACT(YEAR FROM (PARSE_DATE('%Y%m%d', date))), 'W', EXTRACT(WEEK FROM (PARSE_DATE('%Y%m%d', date)))) AS week,
        SUM(revenue) AS revenue
    FROM daily_revenue
    GROUP BY source, week
),
monthly_revenue AS (
    SELECT
        source,
        CONCAT(EXTRACT(YEAR FROM (PARSE_DATE('%Y%m%d', date))),'0', EXTRACT(MONTH FROM (PARSE_DATE('%Y%m%d', date)))) AS month,
        SUM(revenue) AS revenue
    FROM daily_revenue
    GROUP BY source, month
),

top_source AS (
    SELECT source, SUM(revenue) AS total_revenue
    FROM daily_revenue
    GROUP BY source
    ORDER BY total_revenue DESC
    LIMIT 1
),

max_revenues AS (
    (
      SELECT
        'Daily' AS time_type,
        date AS time,
        source,
        MAX(revenue) AS max_revenue
      FROM daily_revenue
      WHERE source = (SELECT source FROM top_source)
      GROUP BY source, date
      ORDER BY max_revenue DESC
      LIMIT 1
    )

    UNION ALL

    (
      SELECT
        'Weekly' AS time_type,
        week AS time,
        source,
        MAX(revenue) AS max_revenue
      FROM weekly_revenue
      WHERE source = (SELECT source FROM top_source)
      GROUP BY source, week
      ORDER BY max_revenue DESC
      LIMIT 1
    )

    UNION ALL

    (
      SELECT
          'Monthly' AS time_type,
          month AS time,
          source,
          MAX(revenue) AS max_revenue
      FROM monthly_revenue
      WHERE source = (SELECT source FROM top_source)
      GROUP BY source, month
      ORDER BY max_revenue DESC
      LIMIT 1
    )
)

SELECT
    max_revenue
FROM max_revenues
ORDER BY max_revenue DESC;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Base data: product revenue per source per day, filtered to first half of 2017
WITH base AS (
  SELECT
    trafficSource.source AS source,
    PARSE_DATE('%Y%m%d', date) AS session_date,
    IFNULL(prod.productRevenue, 0) AS product_revenue_micros  -- productRevenue in micros (value * 10^6)
  FROM
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  CROSS JOIN
    UNNEST(hits) AS hit
  CROSS JOIN
    UNNEST(hit.product) AS prod
  WHERE
    _TABLE_SUFFIX BETWEEN '20170101' AND '20170630'          -- first half of 2017
    AND trafficSource.source IS NOT NULL
),

-- Step 2: Identify the traffic source with highest total product revenue
top_source AS (
  SELECT
    source,
    SUM(product_revenue_micros) AS total_revenue_micros
  FROM base
  GROUP BY source
  ORDER BY total_revenue_micros DESC
  LIMIT 1
),

-- Step 3: Daily total product revenue (in millions) for the top source
daily AS (
  SELECT
    session_date,
    SUM(product_revenue_micros) / 1e12 AS daily_rev_millions  -- micros -> dollars, then millions
  FROM base
  WHERE source = (SELECT source FROM top_source)
  GROUP BY session_date
),

-- Step 4: Weekly total product revenue (in millions) for the top source
weekly AS (
  SELECT
    DATE_TRUNC(session_date, WEEK(MONDAY)) AS week_start,
    SUM(product_revenue_micros) / 1e12 AS weekly_rev_millions
  FROM base
  WHERE source = (SELECT source FROM top_source)
  GROUP BY week_start
),

-- Step 5: Monthly total product revenue (in millions) for the top source
monthly AS (
  SELECT
    DATE_TRUNC(session_date, MONTH) AS month_start,
    SUM(product_revenue_micros) / 1e12 AS monthly_rev_millions
  FROM base
  WHERE source = (SELECT source FROM top_source)
  GROUP BY month_start
)

-- Final: Return traffic source and max daily, weekly, monthly revenue in millions
SELECT
  (SELECT source FROM top_source) AS traffic_source,
  ROUND((SELECT MAX(daily_rev_millions) FROM daily), 4) AS max_daily_product_revenue_millions,
  ROUND((SELECT MAX(weekly_rev_millions) FROM weekly), 4) AS max_weekly_product_revenue_millions,
  ROUND((SELECT MAX(monthly_rev_millions) FROM monthly), 4) AS max_monthly_product_revenue_millions;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH all_data AS (
  SELECT
    date,
    trafficSource.source AS source,
    product.productRevenue AS product_revenue
  FROM
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  CROSS JOIN UNNEST(hits) AS hit
  CROSS JOIN UNNEST(hit.product) AS product
  WHERE
    _TABLE_SUFFIX BETWEEN '20170101' AND '20170630'
    AND product.productRevenue IS NOT NULL
),
source_total AS (
  SELECT
    source,
    SUM(product_revenue) AS total_revenue_micros
  FROM all_data
  GROUP BY source
),
top_source AS (
  SELECT source
  FROM source_total
  ORDER BY total_revenue_micros DESC
  LIMIT 1
),
top_source_data AS (
  SELECT
    date,
    product_revenue
  FROM all_data
  WHERE source = (SELECT source FROM top_source)
),
daily_revenue AS (
  SELECT
    date,
    SUM(product_revenue) AS daily_revenue_micros
  FROM top_source_data
  GROUP BY date
),
weekly_revenue AS (
  SELECT
    DATE_TRUNC(PARSE_DATE('%Y%m%d', date), WEEK(MONDAY)) AS week_start,
    SUM(product_revenue) AS weekly_revenue_micros
  FROM top_source_data
  GROUP BY week_start
),
monthly_revenue AS (
  SELECT
    DATE_TRUNC(PARSE_DATE('%Y%m%d', date), MONTH) AS month_start,
    SUM(product_revenue) AS monthly_revenue_micros
  FROM top_source_data
  GROUP BY month_start
)
SELECT
  (SELECT source FROM top_source) AS top_traffic_source,
  ROUND((SELECT MAX(daily_revenue_micros) FROM daily_revenue) / 1e12, 4) AS max_daily_revenue_millions,
  ROUND((SELECT MAX(weekly_revenue_micros) FROM weekly_revenue) / 1e12, 4) AS max_weekly_revenue_millions,
  ROUND((SELECT MAX(monthly_revenue_micros) FROM monthly_revenue) / 1e12, 4) AS max_monthly_revenue_millions;
```

---

## 3. Instance: `bq003`
**Question:**
> Between April 1 and July 31 of 2017, using the hits product revenue data along with the totals transactions to classify sessions as purchase (transactions ≥ 1 and productRevenue not null) or non-purchase (transactions null and productRevenue null), compare the average pageviews per visitor for each group by month

### 🏆 Gold Reference Answer
```sql
WITH cte1 AS (
    SELECT
        CONCAT(EXTRACT(YEAR FROM (PARSE_DATE('%Y%m%d', date))), '0',
            EXTRACT(MONTH FROM (PARSE_DATE('%Y%m%d', date)))) AS month,
        SUM(totals.pageviews) / COUNT(DISTINCT fullVisitorId) AS avg_pageviews_non_purchase
    FROM
        `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`,
        UNNEST (hits) AS hits,
        UNNEST (hits.product) AS product
    WHERE
        _table_suffix BETWEEN '0401' AND '0731'
        AND totals.transactions IS NULL
        AND product.productRevenue IS NULL
    GROUP BY month
),
cte2 AS (
    SELECT
        CONCAT(EXTRACT(YEAR FROM (PARSE_DATE('%Y%m%d', date))), '0',
            EXTRACT(MONTH FROM (PARSE_DATE('%Y%m%d', date)))) AS month,
        SUM(totals.pageviews) / COUNT(DISTINCT fullVisitorId) AS avg_pageviews_purchase
    FROM
        `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`,
        UNNEST (hits) AS hits,
        UNNEST (hits.product) AS product
    WHERE
        _table_suffix BETWEEN '0401' AND '0731'
        AND totals.transactions >= 1
        AND product.productRevenue IS NOT NULL
    GROUP BY month
)
SELECT
    month, avg_pageviews_purchase, avg_pageviews_non_purchase
FROM cte1 INNER JOIN cte2
USING(month)
ORDER BY month;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Classify each session within the date range as 'purchase' or 'non-purchase'
-- Purchase: totals.transactions >= 1 AND at least one hit.product.productRevenue is not null
-- Non-purchase: totals.transactions IS NULL AND no hit.product.productRevenue is not null
-- All other sessions are excluded.
WITH session_classified AS (
  SELECT
    fullVisitorId,
    totals.pageviews AS pageviews,
    totals.transactions,
    EXTRACT(MONTH FROM PARSE_DATE('%Y%m%d', date)) AS month,
    FORMAT_DATE('%B', PARSE_DATE('%Y%m%d', date)) AS month_name,
    CASE
      WHEN totals.transactions >= 1
           AND EXISTS (
             SELECT 1
             FROM UNNEST(hits) AS h,
                  UNNEST(h.product) AS p
             WHERE p.productRevenue IS NOT NULL
           )
        THEN 'purchase'
      WHEN totals.transactions IS NULL
           AND NOT EXISTS (
             SELECT 1
             FROM UNNEST(hits) AS h,
                  UNNEST(h.product) AS p
             WHERE p.productRevenue IS NOT NULL
           )
        THEN 'non-purchase'
      ELSE NULL
    END AS session_type
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20170401' AND '20170731'
)

-- Step 2: For each month and session type, compute average pageviews per visitor
-- (total pageviews across all sessions in the group / number of distinct visitors)
SELECT
  month,
  month_name,
  session_type,
  ROUND(
    SAFE_DIVIDE(SUM(pageviews), COUNT(DISTINCT fullVisitorId)),
    4
  ) AS avg_pageviews_per_visitor
FROM session_classified
WHERE session_type IS NOT NULL
GROUP BY month, month_name, session_type
ORDER BY month, session_type;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH all_sessions AS (
  -- Get all sessions in date range with base metrics
  SELECT 
    PARSE_DATE('%Y%m%d', date) AS session_date,
    fullVisitorId,
    totals.pageviews AS pageviews,
    totals.transactions AS transactions,
    -- Check if any hit has productRevenue not null
    (SELECT COUNTIF(p.productRevenue IS NOT NULL) 
     FROM UNNEST(hits) AS h, UNNEST(h.product) AS p) > 0 AS has_product_revenue
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20170401' AND '20170731'
),
classified_sessions AS (
  -- Classify sessions into purchase or non-purchase
  SELECT
    session_date,
    fullVisitorId,
    pageviews,
    CASE 
      WHEN transactions >= 1 AND has_product_revenue THEN 'purchase'
      WHEN transactions IS NULL AND NOT has_product_revenue THEN 'non-purchase'
      ELSE NULL
    END AS session_type
  FROM all_sessions
  WHERE (transactions >= 1 AND has_product_revenue)
     OR (transactions IS NULL AND NOT has_product_revenue)
),
monthly_visitor_stats AS (
  -- Aggregate by visitor, month, and session type
  SELECT
    EXTRACT(MONTH FROM session_date) AS month,
    session_type,
    fullVisitorId,
    SUM(pageviews) AS total_pageviews,
    COUNT(*) AS session_count
  FROM classified_sessions
  WHERE session_type IS NOT NULL
  GROUP BY month, session_type, fullVisitorId
)
-- Final calculation: average pageviews per visitor per month
SELECT
  month,
  session_type,
  ROUND(AVG(total_pageviews), 4) AS avg_pageviews_per_visitor
FROM monthly_visitor_stats
GROUP BY month, session_type
ORDER BY month, session_type;
```

---

## 4. Instance: `bq004`
**Question:**
> In July 2017, among all visitors who bought any YouTube-related product, which distinct product—excluding those containing ‘YouTube’ in the product name—had the highest total quantity purchased?

### 🏆 Gold Reference Answer
```sql
with product_and_quatity AS (
    SELECT 
        DISTINCT v2ProductName AS other_purchased_products,
        SUM(productQuantity) AS quatity
    FROM
        `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`,
        UNNEST(hits) AS hits,
        UNNEST(hits.product) AS product
    WHERE
        _table_suffix BETWEEN '0701' AND '0731'
        AND NOT REGEXP_CONTAINS(LOWER(v2ProductName), 'youtube')
        AND fullVisitorID IN (
            SELECT 
            DISTINCT fullVisitorId
            FROM
                `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`,
                UNNEST(hits) AS hits,
                UNNEST(hits.product) AS product
            WHERE
                _table_suffix BETWEEN '0701' AND '0731'
                AND REGEXP_CONTAINS(LOWER(v2ProductName), 'youtube')
        )
    GROUP BY v2ProductName
)
SELECT other_purchased_products
FROM product_and_quatity
ORDER BY quatity DESC
LIMIT 1;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Extract all purchase data for July 2017
-- We unnest hits and products to get individual product purchases.
WITH purchase_data AS (
  SELECT
    fullVisitorId,
    visitId,
    hit.hitNumber,
    product.productSKU,
    product.v2ProductName,
    product.productQuantity
  FROM
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  CROSS JOIN UNNEST(hits) AS hit
  CROSS JOIN UNNEST(hit.product) AS product
  WHERE
    -- Use wildcard table suffix to limit to July 2017
    _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
    -- Only completed purchases (action_type = 6)
    AND hit.eCommerceAction.action_type = '6'
    -- Ensure quantity is positive
    AND product.productQuantity > 0
),

-- Step 2: Identify visitors who purchased at least one YouTube-related product
-- A product is considered YouTube-related if its name contains 'YouTube' (case-insensitive)
youtube_visitors AS (
  SELECT DISTINCT fullVisitorId
  FROM purchase_data
  WHERE LOWER(v2ProductName) LIKE '%youtube%'
),

-- Step 3: Among those visitors, aggregate total quantity for non-YouTube products
non_youtube_purchases AS (
  SELECT
    productSKU,
    v2ProductName,
    SUM(productQuantity) AS total_quantity
  FROM purchase_data
  WHERE
    fullVisitorId IN (SELECT fullVisitorId FROM youtube_visitors)
    -- Exclude any product whose name contains 'YouTube'
    AND LOWER(v2ProductName) NOT LIKE '%youtube%'
  GROUP BY
    productSKU,
    v2ProductName
)

-- Step 4: Pick the product with the highest total quantity purchased
SELECT
  productSKU,
  v2ProductName,
  total_quantity
FROM non_youtube_purchases
ORDER BY total_quantity DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Step 1: Identify all visitors who purchased any product with 'YouTube' in the name in July 2017
youtube_buyers AS (
  SELECT DISTINCT fullVisitorId
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
  AND EXISTS (
    SELECT 1
    FROM UNNEST(hits) AS h
    WHERE h.eCommerceAction.action_type = '6'
    AND EXISTS (
      SELECT 1
      FROM UNNEST(h.product) AS p
      WHERE LOWER(p.v2ProductName) LIKE '%youtube%'
    )
  )
),

-- Step 2: From those buyers, get all purchased product names (excluding those with 'YouTube') and their quantities
product_quantities AS (
  SELECT 
    p.v2ProductName AS product_name,
    p.productQuantity AS quantity
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  CROSS JOIN UNNEST(hits) AS h
  CROSS JOIN UNNEST(h.product) AS p
  WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
    AND fullVisitorId IN (SELECT fullVisitorId FROM youtube_buyers)
    AND h.eCommerceAction.action_type = '6'
    AND LOWER(p.v2ProductName) NOT LIKE '%youtube%'
),

-- Step 3: Aggregate total quantity per distinct product
product_totals AS (
  SELECT 
    product_name,
    SUM(quantity) AS total_quantity
  FROM product_quantities
  WHERE product_name IS NOT NULL
  GROUP BY product_name
)

-- Step 4: Get the product with the highest total quantity
SELECT 
  product_name,
  total_quantity
FROM product_totals
ORDER BY total_quantity DESC
LIMIT 1;
```

---

## 5. Instance: `bq006`
**Question:**
> What is the date with the second highest Z-score for daily counts of 'PUBLIC INTOXICATION' incidents in Austin for the year 2016? List the date in the format of '2016-xx-xx'.

### 🏆 Gold Reference Answer
```sql
WITH incident_stats AS (
  SELECT 
    COUNT(descript) AS total_pub_intox
  FROM 
    `bigquery-public-data.austin_incidents.incidents_2016` 
  WHERE 
    descript = 'PUBLIC INTOXICATION' 
  GROUP BY 
    date
),
average_and_stddev AS (
  SELECT 
    AVG(total_pub_intox) AS avg, 
    STDDEV(total_pub_intox) AS stddev 
  FROM 
    incident_stats
),
daily_z_scores AS (
  SELECT 
    date, 
    COUNT(descript) AS total_pub_intox, 
    ROUND((COUNT(descript) - a.avg) / a.stddev, 2) AS z_score
  FROM 
    `bigquery-public-data.austin_incidents.incidents_2016`,
    (SELECT avg, stddev FROM average_and_stddev) AS a
  WHERE 
    descript = 'PUBLIC INTOXICATION'
  GROUP BY 
    date, avg, stddev
)

SELECT 
  date
FROM 
  daily_z_scores
ORDER BY 
  z_score DESC
LIMIT 1
OFFSET 1
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH daily_counts AS (
    SELECT 
        date,
        COUNT(*) AS daily_count
    FROM `bigquery-public-data.austin_crime.crime`
    WHERE 
        LOWER(description) LIKE '%intox%' AND
        EXTRACT(YEAR FROM date) = 2016
    GROUP BY date
),
z_scores AS (
    SELECT 
        date,
        daily_count,
        (daily_count - AVG(daily_count) OVER()) 
            / NULLIF(STDDEV(daily_count) OVER(), 0) AS z_score
    FROM daily_counts
),
ranked AS (
    SELECT 
        date,
        z_score,
        ROW_NUMBER() OVER (ORDER BY z_score DESC) AS rank
    FROM z_scores
)
SELECT 
    FORMAT_DATE('%Y-%m-%d', date) AS date_formatted
FROM ranked
WHERE rank = 2;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH daily_counts AS (
  SELECT
    date,
    COUNT(*) AS cnt
  FROM `bigquery-public-data.austin_incidents.incidents_2016`
  WHERE UPPER(descript) = 'PUBLIC INTOXICATION'
  GROUP BY date
),
stats AS (
  SELECT
    AVG(cnt) AS mean,
    STDDEV(cnt) AS stddev
  FROM daily_counts
),
z_scores AS (
  SELECT
    date,
    cnt,
    (cnt - mean) / NULLIF(stddev, 0) AS z_score
  FROM daily_counts, stats
),
ranked AS (
  SELECT
    date,
    z_score,
    ROW_NUMBER() OVER (ORDER BY z_score DESC) AS rn
  FROM z_scores
)
SELECT
  FORMAT_DATE('%Y-%m-%d', date) AS date_str
FROM ranked
WHERE rn = 2;
```

---

## 6. Instance: `bq008`
**Question:**
> In January 2017, among visitors whose campaign name contains 'Data Share' and who accessed any page starting with '/home', which page did they most commonly visit next, and what is the maximum time (in seconds) they spent on the '/home' page before moving on?

### 🏆 Gold Reference Answer
```sql
with page_visit_sequence AS (
    SELECT
        fullVisitorID,
        visitID,
        pagePath,
        LEAD(timestamp, 1) OVER (PARTITION BY fullVisitorId, visitID order by timestamp) - timestamp AS page_duration,
        LEAD(pagePath, 1) OVER (PARTITION BY fullVisitorId, visitID order by timestamp) AS next_page,
        RANK() OVER (PARTITION BY fullVisitorId, visitID order by timestamp) AS step_number
    FROM (
        SELECT
            pages.fullVisitorID,
            pages.visitID,
            pages.pagePath,
            visitors.campaign,
            MIN(pages.timestamp) timestamp
        FROM (
            SELECT
                fullVisitorId,
                visitId,
                trafficSource.campaign campaign
            FROM
                `bigquery-public-data.google_analytics_sample.ga_sessions_*`,
                UNNEST(hits) as hits
            WHERE
                _TABLE_SUFFIX BETWEEN '20170101' AND '20170131'
                AND hits.type='PAGE'
                AND REGEXP_CONTAINS(hits.page.pagePath, r'^/home')
                AND REGEXP_CONTAINS(trafficSource.campaign, r'Data Share')
        ) AS visitors
        JOIN(
            SELECT
                fullVisitorId,
                visitId,
                visitStartTime + hits.time / 1000 AS timestamp,
                hits.page.pagePath AS pagePath
            FROM
                `bigquery-public-data.google_analytics_sample.ga_sessions_*`,
                UNNEST(hits) as hits
            WHERE
                _TABLE_SUFFIX BETWEEN '20170101' AND '20170131'
        ) as pages
        ON
            visitors.fullVisitorID = pages.fullVisitorID
            AND visitors.visitID = pages.visitID
        GROUP BY 
            pages.fullVisitorID, visitors.campaign, pages.visitID, pages.pagePath
        ORDER BY 
            pages.fullVisitorID, pages.visitID, timestamp
    )
    ORDER BY fullVisitorId, visitID, step_number
),
most_common_next_page AS (
    SELECT
        next_page,
        COUNT(next_page) as page_count
    FROM page_visit_sequence
    WHERE
        next_page IS NOT NULL
        AND REGEXP_CONTAINS(pagePath, r'^/home')
    GROUP BY next_page
    ORDER BY page_count DESC
    LIMIT 1
),
max_page_duration AS (
    SELECT MAX(page_duration) as max_duration
    FROM page_visit_sequence
    WHERE
        page_duration IS NOT NULL
        AND REGEXP_CONTAINS(pagePath, r'^/home')
)
SELECT
    next_page,
    max_duration
FROM
    most_common_next_page,
    max_page_duration;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
-- Filter sessions from January 2017 where campaign contains 'Data Share'
sessions_filtered AS (
  SELECT
    fullVisitorId,
    visitId,
    visitStartTime,
    date,
    hits
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20170101' AND '20170131'
    AND LOWER(trafficSource.campaign) LIKE '%data share%'
),

-- UNNEST hits to get individual page hits
hits_unnested AS (
  SELECT
    fullVisitorId,
    visitId,
    date,
    h.hitNumber,
    h.page.pagePath,
    h.time AS hit_time_millis,
    h.isExit
  FROM sessions_filtered,
  UNNEST(hits) AS h
  WHERE h.type = 'PAGE'
),

-- Get next page path and next hit time using window function
hits_with_next AS (
  SELECT
    *,
    LEAD(pagePath) OVER (
      PARTITION BY fullVisitorId, visitId 
      ORDER BY hitNumber
    ) AS next_page_path,
    LEAD(hit_time_millis) OVER (
      PARTITION BY fullVisitorId, visitId 
      ORDER BY hitNumber
    ) AS next_hit_time
  FROM hits_unnested
)

-- Final: Find most common next page and max time spent on /home
SELECT
  next_page_path AS most_common_next_page,
  COUNT(*) AS number_of_visits,
  ROUND(MAX((next_hit_time - hit_time_millis) / 1000.0), 4) AS max_time_on_home_seconds
FROM hits_with_next
WHERE pagePath LIKE '/home%'
  AND next_page_path IS NOT NULL
GROUP BY next_page_path
ORDER BY number_of_visits DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Final complete query
WITH sessions_with_campaign AS (
  SELECT 
    fullVisitorId,
    visitId,
    hits
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_201701*`
  WHERE _TABLE_SUFFIX BETWEEN '01' AND '31'
    AND LOWER(trafficSource.campaign) LIKE '%data share%'
),
page_hits AS (
  SELECT
    fullVisitorId,
    visitId,
    h.hitNumber,
    h.time,
    h.page.pagePath AS current_page,
    LEAD(h.page.pagePath) OVER (
      PARTITION BY fullVisitorId, visitId 
      ORDER BY h.hitNumber
    ) AS next_page,
    LEAD(h.time) OVER (
      PARTITION BY fullVisitorId, visitId 
      ORDER BY h.hitNumber
    ) AS next_time
  FROM sessions_with_campaign,
  UNNEST(hits) AS h
  WHERE h.type = 'PAGE'
)
SELECT
  next_page AS most_common_next_page,
  ROUND(MAX((next_time - time) / 1000.0), 4) AS max_time_seconds
FROM page_hits
WHERE LOWER(current_page) LIKE '/home%'
  AND next_page IS NOT NULL
GROUP BY next_page
ORDER BY COUNT(*) DESC
LIMIT 1;
```

---

## 7. Instance: `bq009`
**Question:**
> Which traffic source has the highest total transaction revenue for the year 2017, and what is the difference in millions (rounded to two decimal places) between the highest and lowest monthly total transaction revenue for that traffic source?

### 🏆 Gold Reference Answer
```sql
WITH MONTHLY_REVENUE AS (
    SELECT 
        FORMAT_DATE("%Y%m", PARSE_DATE("%Y%m%d", date)) AS month,
        trafficSource.source AS source,
        ROUND(SUM(totals.totalTransactionRevenue) / 1000000, 2) AS revenue
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`
    GROUP BY 1, 2
),

YEARLY_REVENUE AS (
    SELECT
        source,
        SUM(revenue) AS total_revenue
    FROM MONTHLY_REVENUE
    GROUP BY source
),

TOP_SOURCE AS (
    SELECT 
        source
    FROM YEARLY_REVENUE
    ORDER BY total_revenue DESC
    LIMIT 1
),

SOURCE_MONTHLY_REVENUE AS (
    SELECT
        month,
        source,
        revenue
    FROM MONTHLY_REVENUE
    WHERE source IN (SELECT source FROM TOP_SOURCE)
),

REVENUE_DIFF AS (
    SELECT 
        source,
        ROUND(MAX(revenue), 2) AS max_revenue,
        ROUND(MIN(revenue), 2) AS min_revenue,
        ROUND(MAX(revenue) - MIN(revenue), 2) AS diff_revenue
    FROM SOURCE_MONTHLY_REVENUE
    GROUP BY source
)

SELECT 
    source,
    diff_revenue
FROM REVENUE_DIFF;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Find the traffic source with the highest total transaction revenue in 2017
WITH source_total_revenue AS (
  SELECT
    trafficSource.source AS traffic_source,
    SUM(COALESCE(totals.totalTransactionRevenue, 0)) AS total_revenue
  FROM
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20170101' AND '20171231'
  GROUP BY
    traffic_source
),

-- Pick the top one (if ties, just one)
top_source AS (
  SELECT
    traffic_source
  FROM
    source_total_revenue
  ORDER BY
    total_revenue DESC
  LIMIT 1
),

-- Monthly revenue for that top traffic source
monthly_revenue AS (
  SELECT
    trafficSource.source AS traffic_source,
    SUBSTR(date, 1, 6) AS month_key,  -- e.g. '201701'
    SUM(COALESCE(totals.totalTransactionRevenue, 0)) AS month_revenue
  FROM
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20170101' AND '20171231'
    AND trafficSource.source IN (SELECT traffic_source FROM top_source)
  GROUP BY
    traffic_source, month_key
)

-- Compute the difference between highest and lowest monthly revenue, in millions
SELECT
  traffic_source,
  ROUND((MAX(month_revenue) - MIN(month_revenue)) / 1000000.0, 2) AS difference_millions
FROM
  monthly_revenue
GROUP BY
  traffic_source;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH source_revenue AS (
    SELECT 
        trafficSource.source AS traffic_source,
        SUM(COALESCE(totals.totalTransactionRevenue, 0)) / 1000000 AS total_revenue
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`
    WHERE _TABLE_SUFFIX BETWEEN '20170101' AND '20171231'
    GROUP BY traffic_source
),
top_source AS (
    SELECT traffic_source
    FROM source_revenue
    ORDER BY total_revenue DESC
    LIMIT 1
),
monthly_data AS (
    SELECT 
        SUBSTR(date, 1, 6) AS year_month,
        SUM(COALESCE(totals.totalTransactionRevenue, 0)) / 1000000 AS monthly_revenue
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`
    WHERE _TABLE_SUFFIX BETWEEN '20170101' AND '20171231'
      AND trafficSource.source = (SELECT traffic_source FROM top_source)
    GROUP BY year_month
)
SELECT 
    (SELECT traffic_source FROM top_source) AS traffic_source,
    ROUND(MAX(monthly_revenue) - MIN(monthly_revenue), 2) AS revenue_diff_in_millions
FROM monthly_data;
```

---

## 8. Instance: `bq010`
**Question:**
> Find the top-selling product among customers who bought 'Youtube Men’s Vintage Henley' in July 2017, excluding itself.

### 🏆 Gold Reference Answer
```sql
WITH GET_CUS_ID AS (
    SELECT 
        DISTINCT fullVisitorId as Henley_CUSTOMER_ID
    FROM 
        `bigquery-public-data.google_analytics_sample.ga_sessions_201707*`,
        UNNEST(hits) AS hits,
        UNNEST(hits.product) as product
    WHERE
        product.v2ProductName = "YouTube Men's Vintage Henley"
        AND product.productRevenue IS NOT NULL
    )

SELECT
    product.v2ProductName AS other_purchased_products
FROM
    `bigquery-public-data.google_analytics_sample.ga_sessions_201707*` TAB_A 
    RIGHT JOIN GET_CUS_ID
    ON GET_CUS_ID.Henley_CUSTOMER_ID=TAB_A.fullVisitorId,
    UNNEST(hits) AS hits,
    UNNEST(hits.product) as product
WHERE
    TAB_A.fullVisitorId IN (
        SELECT * FROM GET_CUS_ID
    )
    AND product.v2ProductName <> "YouTube Men's Vintage Henley"
    AND product.productRevenue IS NOT NULL
GROUP BY
    product.v2ProductName
ORDER BY
    SUM(product.productQuantity) DESC
LIMIT 1;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH target_customers AS (
  SELECT DISTINCT
    fullVisitorId
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  CROSS JOIN UNNEST(hits) AS hit
  CROSS JOIN UNNEST(hit.product) AS prod
  WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
    AND hit.eCommerceAction.action_type = '6'
    -- Match product name with either straight or typographic apostrophe using a dot
    AND REGEXP_CONTAINS(LOWER(TRIM(prod.v2ProductName)), r'youtube men.s vintage henley')
    AND prod.productQuantity > 0
),

all_other_products AS (
  SELECT
    s.fullVisitorId,
    prod.v2ProductName AS product_name,
    prod.productSKU AS product_sku,
    prod.productQuantity AS quantity
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` s
  CROSS JOIN UNNEST(hits) AS hit
  CROSS JOIN UNNEST(hit.product) AS prod
  INNER JOIN target_customers tc
    ON s.fullVisitorId = tc.fullVisitorId
  WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
    AND hit.eCommerceAction.action_type = '6'
    -- Exclude the same product
    AND NOT REGEXP_CONTAINS(LOWER(TRIM(prod.v2ProductName)), r'youtube men.s vintage henley')
    AND prod.productQuantity > 0
)

SELECT
  product_name,
  product_sku,
  ROUND(SUM(quantity), 0) AS total_quantity_sold
FROM all_other_products
GROUP BY product_name, product_sku
ORDER BY total_quantity_sold DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- First, let's check what products are available to verify
available_products AS (
    SELECT DISTINCT p.v2ProductName
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
    CROSS JOIN UNNEST(hits) AS h
    CROSS JOIN UNNEST(h.product) AS p
    WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
      AND h.eCommerceAction.action_type = '6'
      AND p.productQuantity > 0
      AND LOWER(p.v2ProductName) LIKE LOWER('%vintage henley%')
),

-- Step 1: Identify customers who bought the product
customers_with_target_product AS (
    SELECT DISTINCT fullVisitorId
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
    CROSS JOIN UNNEST(hits) AS h
    CROSS JOIN UNNEST(h.product) AS p
    WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
      AND LOWER(p.v2ProductName) LIKE LOWER('%vintage henley%')
      AND p.productQuantity > 0
      AND h.eCommerceAction.action_type = '6'
),

-- Step 2: Get all purchases by these customers, excluding the target product
product_purchases AS (
    SELECT 
        p.v2ProductName AS product_name,
        p.productSKU AS product_sku,
        SUM(p.productQuantity) AS total_quantity_sold
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
    CROSS JOIN UNNEST(hits) AS h
    CROSS JOIN UNNEST(h.product) AS p
    WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
      AND fullVisitorId IN (SELECT fullVisitorId FROM customers_with_target_product)
      AND LOWER(p.v2ProductName) NOT LIKE LOWER('%vintage henley%')
      AND p.productQuantity > 0
      AND h.eCommerceAction.action_type = '6'
    GROUP BY product_name, product_sku
)

-- Step 3: Find the top-selling product
SELECT 
    product_name,
    product_sku,
    total_quantity_sold
FROM product_purchases
WHERE product_name IS NOT NULL
ORDER BY total_quantity_sold DESC
LIMIT 1;
```

---

## 9. Instance: `bq011`
**Question:**
> How many distinct pseudo users had positive engagement time  in the 7-day period ending on January 7, 2021 at 23:59:59, but had no positive engagement time in the 2-day period ending on the same date (January 7, 2021 at 23:59:59) ?

### 🏆 Gold Reference Answer
```sql
SELECT
  COUNT(DISTINCT MDaysUsers.user_pseudo_id) AS n_day_inactive_users_count
FROM
  (
    SELECT
      user_pseudo_id
    FROM
      `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` AS T
    CROSS JOIN
      UNNEST(T.event_params) AS event_params
    WHERE
      event_params.key = 'engagement_time_msec' AND event_params.value.int_value > 0
      AND event_timestamp > UNIX_MICROS(TIMESTAMP_SUB(TIMESTAMP('2021-01-07 23:59:59'), INTERVAL 7 DAY))
      AND _TABLE_SUFFIX BETWEEN '20210101' AND '20210107'
  ) AS MDaysUsers
LEFT JOIN
  (
    SELECT
      user_pseudo_id
    FROM
      `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` AS T
    CROSS JOIN
      UNNEST(T.event_params) AS event_params
    WHERE
      event_params.key = 'engagement_time_msec' AND event_params.value.int_value > 0
      AND event_timestamp > UNIX_MICROS(TIMESTAMP_SUB(TIMESTAMP('2021-01-07 23:59:59'), INTERVAL 2 DAY))
      AND _TABLE_SUFFIX BETWEEN '20210105' AND '20210107'
  ) AS NDaysUsers
ON MDaysUsers.user_pseudo_id = NDaysUsers.user_pseudo_id
WHERE
  NDaysUsers.user_pseudo_id IS NULL;
```

### 🤖 AutoLink Baseline Prediction
```sql
SELECT DISTINCT param.key
   FROM `[YOUR_PROJECT_ID].[YOUR_DATASET_NAME].events_*`, UNNEST(event_params) AS param
   WHERE _TABLE_SUFFIX BETWEEN '20210101' AND '20210107'
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- This query counts distinct users who had positive engagement time in the
-- 7-day period (Jan 1 to Jan 7, 2021) but NOT in the 2-day period (Jan 6 to Jan 7, 2021),
-- both ending at 23:59:59 on Jan 7, 2021.

WITH
-- Define timestamp boundaries for clarity
date_boundaries AS (
  SELECT
    TIMESTAMP("2021-01-01 00:00:00") AS seven_day_start,
    TIMESTAMP("2021-01-07 23:59:59") AS end_date,
    TIMESTAMP("2021-01-06 00:00:00") AS two_day_start
),

-- Get users with at least one positive engagement event in the 7-day window
users_7day AS (
  SELECT DISTINCT user_pseudo_id
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  CROSS JOIN UNNEST(event_params) AS ep
  WHERE event_name = 'user_engagement'
    AND ep.key = 'engagement_time_msec'
    AND ep.value.int_value > 0
    AND _TABLE_SUFFIX BETWEEN '20210101' AND '20210107'
),

-- Get users with at least one positive engagement event in the 2-day window
users_2day AS (
  SELECT DISTINCT user_pseudo_id
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  CROSS JOIN UNNEST(event_params) AS ep
  WHERE event_name = 'user_engagement'
    AND ep.key = 'engagement_time_msec'
    AND ep.value.int_value > 0
    AND _TABLE_SUFFIX BETWEEN '20210106' AND '20210107'
)

-- Anti-join: only count users present in 7-day but absent from 2-day
SELECT COUNT(DISTINCT user_pseudo_id) AS distinct_users
FROM users_7day
WHERE user_pseudo_id NOT IN (SELECT user_pseudo_id FROM users_2day);
```

---

## 10. Instance: `bq018`
**Question:**
> Which day in March and April had the highest COVID-19 confirmed case growth rate in the United States? The format is MM-DD.

### 🏆 Gold Reference Answer
```sql
WITH us_cases_by_date AS (
  SELECT
    date,
    SUM( cumulative_confirmed ) AS cases
  FROM
    `bigquery-public-data.covid19_open_data.covid19_open_data`
  WHERE
    country_name="United States of America"
    AND date between '2020-03-01' and '2020-04-30'
  GROUP BY
    date
  ORDER BY
    date ASC
 )

, us_previous_day_comparison AS
(SELECT
  date,
  cases,
  LAG(cases) OVER(ORDER BY date) AS previous_day,
  cases - LAG(cases) OVER(ORDER BY date) AS net_new_cases,
  (cases - LAG(cases) OVER(ORDER BY date))*100/LAG(cases) OVER(ORDER BY date) AS percentage_increase
FROM us_cases_by_date
)
SELECT
  FORMAT_DATE('%m-%d', Date) 
FROM
  us_previous_day_comparison
ORDER BY  
  percentage_increase
DESC
LIMIT 1
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH country_daily AS (
  SELECT 
    date,
    SUM(cumulative_confirmed) AS total_cumulative_confirmed
  FROM `bigquery-public-data.covid19_open_data.covid19_open_data`
  WHERE country_code = 'US'
    AND EXTRACT(MONTH FROM date) IN (3, 4)
    AND EXTRACT(YEAR FROM date) = 2020
  GROUP BY date
),
daily_growth AS (
  SELECT 
    date,
    total_cumulative_confirmed,
    LAG(total_cumulative_confirmed) OVER (ORDER BY date) AS prev_cumulative,
    SAFE_DIVIDE(
      total_cumulative_confirmed - LAG(total_cumulative_confirmed) OVER (ORDER BY date),
      LAG(total_cumulative_confirmed) OVER (ORDER BY date)
    ) AS growth_rate
  FROM country_daily
)
SELECT 
  FORMAT_DATE('%m-%d', date) AS mm_dd
FROM daily_growth
WHERE growth_rate IS NOT NULL
ORDER BY growth_rate DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Understand the question
-- We need to find the day (in MM-DD format) during March and April that had the highest 
-- COVID-19 confirmed case growth rate in the United States.
-- Growth rate is calculated as (new_confirmed) / (previous day's cumulative_confirmed) 
-- or simply using the daily new confirmed cases as a proxy for growth.
-- Since "confirmed case growth rate" typically means the rate of increase in confirmed cases,
-- we can compute it as new_confirmed / previous_cumulative_confirmed.
-- We'll filter for US data (country_code = 'US') and dates in March and April.

-- Step 2: Identify relevant columns
-- Table: bigquery-public-data.covid19_open_data.covid19_open_data
-- Columns: date, country_code, new_confirmed, cumulative_confirmed
-- Note: new_confirmed may not be directly available, but we have cumulative_confirmed.
-- We can calculate new_confirmed as difference in cumulative_confirmed between consecutive days.

-- Step 3: Design the SQL
-- Use a CTE to get daily cumulative_confirmed for each date in the US
-- Then compute daily new_confirmed as (current cumulative - previous cumulative)
-- Then compute growth rate as (new_confirmed / previous cumulative_confirmed)
-- Filter for March and April (month 3 and 4)
-- Order by growth rate descending, get the top date
-- Format as MM-DD

-- Step 4: Validate
-- This approach handles the data correctly: uses cumulative_confirmed to compute new cases,
-- calculates growth rate as a ratio, filters for US and specific months,
-- returns the date with highest growth rate in MM-DD format.

-- Step 5: Write the final SQL
WITH daily_data AS (
  SELECT
    date,
    -- Extract month for filtering
    EXTRACT(MONTH FROM date) AS month,
    -- Cumulative confirmed cases for the day
    cumulative_confirmed,
    -- Lag to get previous day's cumulative confirmed
    LAG(cumulative_confirmed) OVER (ORDER BY date) AS prev_cumulative_confirmed
  FROM
    `bigquery-public-data.covid19_open_data.covid19_open_data`
  WHERE
    -- Filter for United States
    country_code = 'US'
    -- Filter for March and April (any year)
    AND EXTRACT(MONTH FROM date) IN (3, 4)
    -- Ensure date is valid (not null)
    AND date IS NOT NULL
    -- Also filter out rows where cumulative_confirmed is null (avoid division issues)
    AND cumulative_confirmed IS NOT NULL
)
SELECT
  -- Format the date as MM-DD
  FORMAT_DATE('%m-%d', date) AS mm_dd,
  -- Calculate growth rate: new_confirmed / previous_cumulative_confirmed
  -- new_confirmed = current - previous
  ROUND(
    (cumulative_confirmed - prev_cumulative_confirmed) / 
    NULLIF(prev_cumulative_confirmed, 0), 
    4
  ) AS growth_rate
FROM daily_data
WHERE
  -- Ensure we have a previous day to compute growth rate
  prev_cumulative_confirmed IS NOT NULL
  -- Avoid division by zero (though NULLIF handles it)
  AND prev_cumulative_confirmed > 0
ORDER BY growth_rate DESC
LIMIT 1;
```

---

## 11. Instance: `bq019`
**Question:**
> In the 2014 CMS Medicare inpatient charges data, which DRG definition has the highest total number of discharges, and among the top three cities with the most discharges for that DRG definition, what are their respective weighted average total payments (weighted by total discharges)

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Identify the DRG definition with the highest total number of discharges
WITH drg_totals AS (
  SELECT
    drg_definition,
    SUM(total_discharges) AS total_discharges
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2014`
  WHERE total_discharges IS NOT NULL
  GROUP BY drg_definition
  ORDER BY total_discharges DESC
  LIMIT 1
),

-- Step 2: For that DRG, aggregate by city to get total discharges and weighted average total payments
city_metrics AS (
  SELECT
    t.drg_definition,
    t.provider_city,
    SUM(t.total_discharges) AS city_total_discharges,
    -- Weighted average total payment = sum(discharges * avg_total_payment) / sum(discharges)
    ROUND(
      SUM(t.total_discharges * t.average_total_payments) / SUM(t.total_discharges),
      4
    ) AS weighted_avg_total_payment
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2014` t
  INNER JOIN drg_totals d
    ON t.drg_definition = d.drg_definition
  WHERE t.total_discharges IS NOT NULL
    AND t.average_total_payments IS NOT NULL
    AND t.provider_city IS NOT NULL
  GROUP BY t.drg_definition, t.provider_city
),

-- Step 3: Rank cities by total discharges descending, take top 3
ranked_cities AS (
  SELECT
    drg_definition,
    provider_city,
    city_total_discharges,
    weighted_avg_total_payment,
    ROW_NUMBER() OVER (ORDER BY city_total_discharges DESC) AS rn
  FROM city_metrics
)

-- Final output
SELECT
  drg_definition,
  provider_city,
  weighted_avg_total_payment
FROM ranked_cities
WHERE rn <= 3
ORDER BY rn;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Identify the DRG definition with the highest total discharges in 2014
WITH drg_total_discharges AS (
    SELECT 
        drg_definition,
        SUM(total_discharges) AS total_discharges_sum
    FROM `bigquery-public-data.cms_medicare.inpatient_charges_2014`
    GROUP BY drg_definition
),
top_drg AS (
    SELECT drg_definition
    FROM drg_total_discharges
    ORDER BY total_discharges_sum DESC
    LIMIT 1
),

-- Step 2: For that DRG definition, compute per-city total discharges and weighted average total payments
city_stats AS (
    SELECT 
        provider_city,
        SUM(total_discharges) AS city_total_discharges,
        -- Weighted average: SUM(total_discharges * average_total_payments) / SUM(total_discharges)
        SAFE_DIVIDE(
            SUM(total_discharges * average_total_payments),
            SUM(total_discharges)
        ) AS weighted_avg_total_payment
    FROM `bigquery-public-data.cms_medicare.inpatient_charges_2014`
    WHERE drg_definition = (SELECT drg_definition FROM top_drg)
    GROUP BY provider_city
),

-- Step 3: Rank cities by total discharges and select top 3
top_cities AS (
    SELECT 
        provider_city,
        city_total_discharges,
        weighted_avg_total_payment,
        ROW_NUMBER() OVER (ORDER BY city_total_discharges DESC) AS city_rank
    FROM city_stats
)

-- Final output: the DRG definition, and the top 3 cities with their weighted average payments
SELECT 
    (SELECT drg_definition FROM top_drg) AS drg_definition,
    provider_city,
    city_total_discharges,
    ROUND(weighted_avg_total_payment, 4) AS weighted_avg_total_payment
FROM top_cities
WHERE city_rank <= 3
ORDER BY city_rank;
```

---

## 12. Instance: `bq021`
**Question:**
> For the top 20 Citi Bike routes in 2016, which route is faster than yellow taxis and among those, which one has the longest average bike duration? Please provide the start station name of this route. The coordinates are rounded to three decimals.

### 🏆 Gold Reference Answer
```sql
WITH top20route AS (
SELECT
  start_station_name, end_station_name, avg_bike_duration, avg_taxi_duration
FROM (
  SELECT
    start_station_name,
    end_station_name,
    ROUND(start_station_latitude, 3) AS ss_lat,
    ROUND(start_station_longitude, 3) AS ss_long,
    ROUND(end_station_latitude, 3) AS es_lat,
    ROUND(end_station_longitude, 3) AS es_long,
    AVG(tripduration) AS avg_bike_duration,
    COUNT(*) AS bike_trips
  FROM
    `bigquery-public-data.new_york.citibike_trips`
  WHERE 
  EXTRACT(YEAR from starttime) = 2016 AND
    start_station_name != end_station_name
  GROUP BY
    start_station_name, end_station_name, ss_lat, ss_long, es_lat, es_long
  ORDER BY
    bike_trips DESC
  LIMIT
    20
) a
JOIN (
  SELECT
    ROUND(pickup_latitude, 3) AS pu_lat,
    ROUND(pickup_longitude, 3) AS pu_long,
    ROUND(dropoff_latitude, 3) AS do_lat,
    ROUND(dropoff_longitude, 3) AS do_long,
    AVG(UNIX_SECONDS(dropoff_datetime)-UNIX_SECONDS(pickup_datetime)) AS avg_taxi_duration,
    COUNT(*) AS taxi_trips
  FROM
    `bigquery-public-data.new_york.tlc_yellow_trips_2016`
  GROUP BY
    pu_lat, pu_long, do_lat, do_long
) b
ON
  a.ss_lat = b.pu_lat AND
  a.es_lat = b.do_lat AND
  a.ss_long = b.pu_long AND
  a.es_long = b.do_long
)

SELECT start_station_name
FROM top20route
WHERE avg_bike_duration < avg_taxi_duration
ORDER BY
avg_bike_duration
DESC
LIMIT 1
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Final optimized SQL query for BigQuery
-- Finds the top 20 Citi Bike routes in 2016, then identifies which is faster than yellow taxis
-- Returns the start station name of the route with the longest average bike duration

WITH 
-- Get top 20 bike routes by frequency in 2016
top20_routes AS (
  SELECT 
    start_station_name,
    ROUND(start_station_latitude, 3) AS start_lat,
    ROUND(start_station_longitude, 3) AS start_lon,
    ROUND(end_station_latitude, 3) AS end_lat,
    ROUND(end_station_longitude, 3) AS end_lon,
    COUNT(*) AS trip_count,
    AVG(tripduration) AS avg_bike_duration_seconds
  FROM `bigquery-public-data.new_york.citibike_trips`
  WHERE EXTRACT(YEAR FROM starttime) = 2016
  GROUP BY start_station_name, start_lat, start_lon, end_lat, end_lon
  ORDER BY trip_count DESC
  LIMIT 20
),

-- Get taxi average duration for same route pairs in 2016
-- Using the correct 2016 yellow taxi table
taxi_avg AS (
  SELECT 
    ROUND(pickup_latitude, 3) AS pickup_lat,
    ROUND(pickup_longitude, 3) AS pickup_lon,
    ROUND(dropoff_latitude, 3) AS dropoff_lat,
    ROUND(dropoff_longitude, 3) AS dropoff_lon,
    AVG(TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND)) AS avg_taxi_duration_seconds
  FROM `bigquery-public-data.new_york.tlc_yellow_trips_2016`
  WHERE EXTRACT(YEAR FROM pickup_datetime) = 2016
    AND EXTRACT(YEAR FROM dropoff_datetime) = 2016
  GROUP BY pickup_lat, pickup_lon, dropoff_lat, dropoff_lon
)

-- Final: find faster routes and pick the one with the longest average bike duration
SELECT 
    t.start_station_name
FROM top20_routes t
JOIN taxi_avg tx
  ON t.start_lat = tx.pickup_lat
  AND t.start_lon = tx.pickup_lon
  AND t.end_lat = tx.dropoff_lat
  AND t.end_lon = tx.dropoff_lon
WHERE t.avg_bike_duration_seconds < tx.avg_taxi_duration_seconds
ORDER BY t.avg_bike_duration_seconds DESC
LIMIT 1
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH bike_routes_2016 AS (
    -- Calculate aggregated stats for each Citi Bike route in 2016
    SELECT
        start_station_name,
        end_station_name,
        ROUND(start_station_longitude, 3) AS start_lon,
        ROUND(start_station_latitude, 3) AS start_lat,
        ROUND(end_station_longitude, 3) AS end_lon,
        ROUND(end_station_latitude, 3) AS end_lat,
        AVG(tripduration) AS avg_bike_duration,
        COUNT(*) AS trip_count
    FROM `bigquery-public-data.new_york.citibike_trips`
    WHERE EXTRACT(YEAR FROM starttime) = 2016
    GROUP BY start_station_name, end_station_name,
             start_lon, start_lat, end_lon, end_lat
),
top_20_routes AS (
    -- Select the top 20 most popular routes (by number of trips)
    SELECT *
    FROM bike_routes_2016
    ORDER BY trip_count DESC
    LIMIT 20
),
taxi_avg_2016 AS (
    -- Calculate average yellow taxi trip duration in 2016 per rounded coordinates
    SELECT
        ROUND(pickup_longitude, 3) AS pickup_lon,
        ROUND(pickup_latitude, 3) AS pickup_lat,
        ROUND(dropoff_longitude, 3) AS dropoff_lon,
        ROUND(dropoff_latitude, 3) AS dropoff_lat,
        AVG(TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND)) AS avg_taxi_duration
    FROM `bigquery-public-data.new_york.tlc_yellow_trips_2016`
    WHERE EXTRACT(YEAR FROM pickup_datetime) = 2016
      AND pickup_longitude IS NOT NULL
      AND pickup_latitude IS NOT NULL
      AND dropoff_longitude IS NOT NULL
      AND dropoff_latitude IS NOT NULL
    GROUP BY pickup_lon, pickup_lat, dropoff_lon, dropoff_lat
),
comparison AS (
    -- Join top bike routes with taxi averages on the rounded coordinates
    SELECT
        r.start_station_name,
        r.avg_bike_duration,
        t.avg_taxi_duration
    FROM top_20_routes r
    LEFT JOIN taxi_avg_2016 t
        ON r.start_lon = t.pickup_lon
        AND r.start_lat = t.pickup_lat
        AND r.end_lon = t.dropoff_lon
        AND r.end_lat = t.dropoff_lat
),
faster_routes AS (
    -- Keep only routes where bike is faster (avg bike duration < avg taxi duration)
    SELECT *
    FROM comparison
    WHERE avg_bike_duration < avg_taxi_duration
      AND avg_taxi_duration IS NOT NULL
)
-- Among those, pick the one with the longest average bike duration
SELECT start_station_name
FROM faster_routes
ORDER BY avg_bike_duration DESC
LIMIT 1;
```

---

## 13. Instance: `bq022`
**Question:**
> Calculate the minimum and maximum trip duration in minutes (rounded to the nearest whole number), total number of trips, and average fare for each of six equal quantile groups based on trip duration, considering only trips between 0 and 60 minutes.

### 🏆 Gold Reference Answer
```sql
SELECT
  ROUND(MIN(trip_seconds) / 60, 0) AS min_minutes,
  ROUND(MAX(trip_seconds) / 60, 0) AS max_minutes,
  COUNT(*) AS total_trips,
  AVG(fare) AS average_fare
FROM (
  SELECT
    trip_seconds,
    NTILE(6) OVER (ORDER BY trip_seconds) AS quantile,
    fare
  FROM
    `bigquery-public-data.chicago_taxi_trips.taxi_trips`
  WHERE
    trip_seconds BETWEEN 0 AND 3600
)
GROUP BY
  quantile
ORDER BY
  min_minutes, max_minutes;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH trip_data AS (
  SELECT
    trip_duration_seconds / 60.0 AS duration_minutes,
    fare_amount
  FROM `careeros-499112.trips.trips`  -- Dataset named 'trips' containing table 'trips'
  WHERE trip_duration_seconds > 0 
    AND trip_duration_seconds <= 3600
),
quantiled AS (
  SELECT
    NTILE(6) OVER (ORDER BY duration_minutes) AS quantile_group,
    duration_minutes,
    fare_amount
  FROM trip_data
)
SELECT
  quantile_group,
  ROUND(MIN(duration_minutes), 0) AS min_duration_rounded,
  ROUND(MAX(duration_minutes), 0) AS max_duration_rounded,
  COUNT(*) AS total_trips,
  ROUND(AVG(fare_amount), 4) AS avg_fare
FROM quantiled
GROUP BY quantile_group
ORDER BY quantile_group;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
  filtered_trips AS (
    SELECT
      trip_seconds,
      fare,
      ROUND(trip_seconds / 60.0, 0) AS duration_minutes_rounded
    FROM
      `bigquery-public-data.chicago_taxi_trips.taxi_trips`
    WHERE
      trip_seconds BETWEEN 0 AND 3600
      AND fare IS NOT NULL   -- ensure fare is available for average
  ),
  quantiled AS (
    SELECT
      *,
      NTILE(6) OVER (ORDER BY trip_seconds) AS quantile_group
    FROM
      filtered_trips
  )
SELECT
  quantile_group,
  MIN(duration_minutes_rounded) AS min_duration_minutes,
  MAX(duration_minutes_rounded) AS max_duration_minutes,
  COUNT(*) AS total_trips,
  ROUND(AVG(fare), 4) AS avg_fare
FROM
  quantiled
GROUP BY
  quantile_group
ORDER BY
  quantile_group;
```

---

## 14. Instance: `bq023`
**Question:**
> Using the 2018 5-Year American Community Survey (ACS) for median incomes at the census tract level and the 2020 Federal Election Commission (FEC) individual contributions dataset filtered for donors in New York, matched to census tract geographies via a ZIP code to census tract crosswalk, calculate and list the average political donation amount and the median income for each census tract located in Kings County (Brooklyn), New York. 

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- CTE: median income per census tract in Kings County (2018 5-Year ACS)
WITH kings_tract_income AS (
    SELECT
        geo_id AS tract_geoid,
        median_income
    FROM `bigquery-public-data.census_bureau_acs.censustract_2018_5yr`
    WHERE geo_id LIKE '36047%'   -- Kings County FIPS code 047 (NY state FIPS 36)
),

-- CTE: NY donors in 2020 FEC individual contributions, with allocated tract amounts
ny_donors_allocated AS (
    SELECT
        cw.census_tract_geoid AS tract_geoid,
        f.transaction_amt * cw.residential_ratio AS allocated_amount,
        cw.residential_ratio
    FROM `bigquery-public-data.fec.individuals_ingest_2020` f
    INNER JOIN `bigquery-public-data.hud_zipcode_crosswalk.zipcode_to_census_tracts` cw
        ON f.zip_code = cw.zip_code
    WHERE f.state = 'NY'
      AND f.transaction_amt IS NOT NULL
      AND cw.residential_ratio IS NOT NULL
      AND cw.residential_ratio > 0
)

-- Main aggregation: average donation per tract, joined with median income
SELECT
    k.tract_geoid,
    ROUND(SUM(nda.allocated_amount) / SUM(nda.residential_ratio), 2) AS avg_donation_amount,
    k.median_income
FROM kings_tract_income k
LEFT JOIN ny_donors_allocated nda
    ON k.tract_geoid = nda.tract_geoid
GROUP BY k.tract_geoid, k.median_income
ORDER BY k.tract_geoid;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH ny_contributions AS (
  SELECT
    CAST(contributor_zip AS STRING) AS zip_code,
    contribution_receipt_amount AS donation_amount
  FROM `bigquery-public-data.fec.individual_contributions_2020`
  WHERE contributor_state = 'NY'
    AND contribution_receipt_amount IS NOT NULL
    AND contributor_zip IS NOT NULL
),
zip_to_tract AS (
  SELECT
    zip_code,
    tract_geoid AS tract_id
  FROM `bigquery-public-data.geo_us_boundaries.zip_code_census_tract`
),
donations_with_tract AS (
  SELECT
    z.tract_id,
    n.donation_amount
  FROM ny_contributions n
  INNER JOIN zip_to_tract z
    ON n.zip_code = z.zip_code
),
kings_tracts AS (
  SELECT
    geo_id,
    median_income
  FROM `bigquery-public-data.census_bureau_acs.censustract_2018_5yr`
  WHERE geo_id LIKE '36047%'
    AND median_income IS NOT NULL
)
SELECT
  k.geo_id AS census_tract,
  k.median_income,
  ROUND(AVG(d.donation_amount), 4) AS avg_donation_amount
FROM kings_tracts k
LEFT JOIN donations_with_tract d
  ON k.geo_id = d.tract_id
GROUP BY k.geo_id, k.median_income
ORDER BY k.geo_id;
```

---

## 15. Instance: `bq024`
**Question:**
> For the year 2012, which top 10 evaluation groups have the largest subplot acres when considering only the condition with the largest subplot acres within each group? Please include the evaluation group, evaluation type, condition status code, evaluation description, state code, macroplot acres, and subplot acres.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Extract evaluation group info with description
evaluation_group AS (
  SELECT 
    evaluation_sequence_number,
    notes AS evaluation_description
  FROM `bigquery-public-data.usfs_fia.population_evaluation`
),
-- Link conditions to evaluation groups via population hierarchy, filter to 2012
condition_eval AS (
  SELECT 
    c.plot_sequence_number,
    c.condition_status_code,
    c.microplot_proportion_unadjusted AS subplot_acres,
    NULL AS macroplot_acres,  -- Not available in condition table; set as NULL
    psa.state_code,
    pe.evaluation_sequence_number,
    eg.evaluation_description
  FROM `bigquery-public-data.usfs_fia.condition` c
  INNER JOIN `bigquery-public-data.usfs_fia.population_stratum_assign` psa
    ON c.plot_sequence_number = psa.plot_sequence_number
  INNER JOIN `bigquery-public-data.usfs_fia.population_stratum` ps
    ON psa.stratum_sequence_number = ps.stratum_sequence_number
  INNER JOIN `bigquery-public-data.usfs_fia.population_estimation_unit` peu
    ON ps.estimation_unit_sequence_number = peu.estimation_unit_sequence_number
  INNER JOIN `bigquery-public-data.usfs_fia.population_evaluation` pe
    ON peu.evaluation_sequence_number = pe.evaluation_sequence_number
  INNER JOIN evaluation_group eg
    ON pe.evaluation_sequence_number = eg.evaluation_sequence_number
  WHERE psa.inventory_year = 2012
),
-- Rank conditions per evaluation group by subplot_acres descending
ranked AS (
  SELECT 
    evaluation_sequence_number,
    evaluation_description,
    condition_status_code,
    state_code,
    macroplot_acres,
    subplot_acres,
    ROW_NUMBER() OVER (
      PARTITION BY evaluation_sequence_number
      ORDER BY subplot_acres DESC
    ) AS rn
  FROM condition_eval
)
-- Select top 10 evaluation groups
SELECT 
  r.evaluation_sequence_number,
  r.evaluation_description,
  r.condition_status_code,
  r.state_code,
  ROUND(r.macroplot_acres, 4) AS macroplot_acres,
  ROUND(r.subplot_acres, 4) AS subplot_acres
FROM ranked r
WHERE r.rn = 1
ORDER BY r.subplot_acres DESC
LIMIT 10;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Identify population records that belong to evaluation groups including the year 2012.
-- We filter the population_evaluation table using the report_year_name column which contains
-- the years covered by the evaluation (e.g., '2012;2013;...').
WITH evaluations_2012 AS (
  SELECT DISTINCT
    p.evaluation_group,
    p.evaluation_type,
    p.evaluation_description,
    p.state_code,
    p.survey_unit_code,
    p.county_code,
    p.phase_2_plot_number,
    p.region_or_station_code
  FROM `bigquery-public-data.usfs_fia.population` p
  INNER JOIN `bigquery-public-data.usfs_fia.population_evaluation` pe
    ON p.evaluation_identifier = pe.evaluation_identifier
    AND p.region_or_station_code = pe.region_or_station_code
  WHERE pe.report_year_name LIKE '%2012%'
),

-- Step 2: Join the filtered population records with the condition table.
-- The join uses the spatial and plot identifiers present in both tables.
-- We keep only conditions with a non‑null subplot proportion.
condition_data AS (
  SELECT
    e.evaluation_group,
    e.evaluation_type,
    e.evaluation_description,
    c.condition_status_code,
    c.state_code,
    c.macroplot_proportion_unadjusted AS macroplot_acres,
    c.subplot_proportion_unadjusted   AS subplot_acres
  FROM evaluations_2012 e
  INNER JOIN `bigquery-public-data.usfs_fia.condition` c
    ON e.state_code        = c.state_code
    AND e.survey_unit_code = c.survey_unit_code
    AND e.county_code      = c.county_code
    AND e.phase_2_plot_number = c.phase_2_plot_number
  WHERE c.subplot_proportion_unadjusted IS NOT NULL
),

-- Step 3: Within each evaluation group, retain only the condition that has the
-- largest subplot acres (i.e., the highest subplot proportion). Use ROW_NUMBER()
-- to assign ranks per group.
ranked_conditions AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY evaluation_group
      ORDER BY subplot_acres DESC
    ) AS rn
  FROM condition_data
)

-- Step 4: Select the top 10 evaluation groups (based on the subplot acres of
-- their best condition) and output the requested fields.
SELECT
  evaluation_group,
  evaluation_type,
  condition_status_code,
  evaluation_description,
  state_code,
  macroplot_acres,
  subplot_acres
FROM ranked_conditions
WHERE rn = 1
ORDER BY subplot_acres DESC
LIMIT 10;
```

---

## 16. Instance: `bq025`
**Question:**
> Provide a list of the top 10 countries for the year 2020, ordered by the highest percentage of their population under 20 years old. For each country, include the total population under 20 years old, the total midyear population, and the percentage of the population that is under 20 years old.

### 🏆 Gold Reference Answer
```sql
SELECT
  age.country_name,
  SUM(age.population) AS under_25,
  pop.midyear_population AS total,
  ROUND((SUM(age.population) / pop.midyear_population) * 100,2) AS pct_under_25
FROM (
  SELECT
    country_name,
    population,
    country_code
  FROM
    `bigquery-public-data.census_bureau_international.midyear_population_agespecific`
  WHERE
    year =2020
    AND age < 20) age
INNER JOIN (
  SELECT
    midyear_population,
    country_code
  FROM
    `bigquery-public-data.census_bureau_international.midyear_population`
  WHERE
    year = 2020) pop
ON
  age.country_code = pop.country_code
GROUP BY
  1,
  3
ORDER BY
  4 DESC
/* Remove limit for visualization */
LIMIT
  10
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
  under_20 AS (
    SELECT
      country_name,
      year,
      SUM(population) AS under_20_population
    FROM
      `bigquery-public-data.census_bureau_international.midyear_population_agespecific`
    WHERE
      year = 2020
      AND age BETWEEN 0 AND 19
    GROUP BY
      country_name,
      year
  ),
  total_population AS (
    SELECT
      country_name,
      year,
      SUM(population) AS total_population
    FROM
      `bigquery-public-data.census_bureau_international.midyear_population_agespecific`
    WHERE
      year = 2020
    GROUP BY
      country_name,
      year
  )
SELECT
  u.country_name,
  u.under_20_population,
  t.total_population AS midyear_population,
  ROUND((u.under_20_population / t.total_population) * 100, 4) AS percentage_under_20
FROM
  under_20 u
INNER JOIN
  total_population t
  ON u.country_name = t.country_name
    AND u.year = t.year
ORDER BY
  percentage_under_20 DESC
LIMIT 10;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH under_20 AS (
  SELECT
    country_name,
    SUM(
      population_age_0 + population_age_1 + population_age_2 + population_age_3 + population_age_4 +
      population_age_5 + population_age_6 + population_age_7 + population_age_8 + population_age_9 +
      population_age_10 + population_age_11 + population_age_12 + population_age_13 + population_age_14 +
      population_age_15 + population_age_16 + population_age_17 + population_age_18 + population_age_19
    ) AS pop_under_20
  FROM `bigquery-public-data.census_bureau_international.midyear_population_age_sex`
  WHERE year = 2020
  GROUP BY country_name
),
total_pop AS (
  SELECT
    country_name,
    SUM(
      population_age_0 + population_age_1 + population_age_2 + population_age_3 + population_age_4 +
      population_age_5 + population_age_6 + population_age_7 + population_age_8 + population_age_9 +
      population_age_10 + population_age_11 + population_age_12 + population_age_13 + population_age_14 +
      population_age_15 + population_age_16 + population_age_17 + population_age_18 + population_age_19 +
      population_age_20 + population_age_21 + population_age_22 + population_age_23 + population_age_24 +
      population_age_25 + population_age_26 + population_age_27 + population_age_28 + population_age_29 +
      population_age_30 + population_age_31 + population_age_32 + population_age_33 + population_age_34 +
      population_age_35 + population_age_36 + population_age_37 + population_age_38 + population_age_39 +
      population_age_40 + population_age_41 + population_age_42 + population_age_43 + population_age_44 +
      population_age_45 + population_age_46 + population_age_47 + population_age_48 + population_age_49 +
      population_age_50 + population_age_51 + population_age_52 + population_age_53 + population_age_54 +
      population_age_55 + population_age_56 + population_age_57 + population_age_58 + population_age_59 +
      population_age_60 + population_age_61 + population_age_62 + population_age_63 + population_age_64 +
      population_age_65 + population_age_66 + population_age_67 + population_age_68 + population_age_69 +
      population_age_70 + population_age_71 + population_age_72 + population_age_73 + population_age_74 +
      population_age_75 + population_age_76 + population_age_77 + population_age_78 + population_age_79 +
      population_age_80 + population_age_81 + population_age_82 + population_age_83 + population_age_84 +
      population_age_85 + population_age_86 + population_age_87 + population_age_88 + population_age_89 +
      population_age_90 + population_age_91 + population_age_92 + population_age_93 + population_age_94 +
      population_age_95 + population_age_96 + population_age_97 + population_age_98 + population_age_99 +
      population_age_100
    ) AS total_population
  FROM `bigquery-public-data.census_bureau_international.midyear_population_age_sex`
  WHERE year = 2020
  GROUP BY country_name
)
SELECT 
  u.country_name,
  u.pop_under_20,
  t.total_population,
  ROUND(SAFE_DIVIDE(u.pop_under_20, t.total_population) * 100, 4) AS pct_under_20
FROM under_20 u
JOIN total_pop t ON u.country_name = t.country_name
ORDER BY pct_under_20 DESC
LIMIT 10;
```

---

## 17. Instance: `bq030`
**Question:**
> As of May 10, 2020, among all countries that had more than 50,000 confirmed COVID-19 cases, which three countries had the highest recovery rates based on the total number of recovered cases relative to their total confirmed cases, and what were their respective recovery rates expressed as percentages?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Aggregate country-level cumulative confirmed and recovered cases on May 10, 2020
WITH country_aggregates AS (
  SELECT
    country_name,
    SUM(IFNULL(cumulative_confirmed, 0)) AS total_confirmed,
    SUM(IFNULL(cumulative_recovered, 0)) AS total_recovered
  FROM
    bigquery-public-data.covid19_open_data.covid19_open_data
  WHERE
    date = '2020-05-10'
    AND country_name IS NOT NULL
  GROUP BY
    country_name
  HAVING
    SUM(IFNULL(cumulative_confirmed, 0)) > 50000
)

-- Step 2: Compute recovery rate, rank, and select top 3
SELECT
  country_name,
  ROUND(100.0 * total_recovered / total_confirmed, 4) AS recovery_rate_percentage
FROM
  country_aggregates
ORDER BY
  recovery_rate_percentage DESC
LIMIT 3;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Retrieve country-level cumulative data for the date '2020-05-10'
-- We assume rows where subregion1_code IS NULL represent national aggregates.
WITH country_data AS (
  SELECT
    country_name,
    cumulative_confirmed,
    COALESCE(cumulative_recovered, 0) AS cumulative_recovered
  FROM
    `bigquery-public-data.covid19_open_data.covid19_open_data`
  WHERE
    date = '2020-05-10'
    AND subregion1_code IS NULL
    AND country_name IS NOT NULL
)

-- Step 2: Compute recovery rate as percentage, filter countries with >50,000 confirmed cases,
-- sort descending by recovery rate, and select top 3.
SELECT
  country_name,
  ROUND((cumulative_recovered / cumulative_confirmed) * 100, 4) AS recovery_rate_percentage
FROM
  country_data
WHERE
  cumulative_confirmed > 50000
ORDER BY
  recovery_rate_percentage DESC
LIMIT 3;
```

---

## 18. Instance: `bq031`
**Question:**
> Provide the daily weather data for Rochester from January 1 to March 31, 2019, including temperature (in Celsius), precipitation (in centimeters), and wind speed (in meters per second). For each variable, calculate the 8-day moving average (including the current day and the previous 7 days). Also, calculate the difference between the moving average on each day and the moving averages for the previous 1 to 8 days (i.e., lag1 to lag8). The result should include: The daily values for temperature, precipitation, and wind speed.The 8-day moving averages for each variable. The differences between the moving averages for each of the previous 1 to 8 days (e.g., the difference between today's moving average and the moving average from 1 day ago, from 2 days ago, and so on). Round all values to one decimal place. The data should be ordered by date, starting from January 9, 2019.

### 🏆 Gold Reference Answer
```sql
WITH transrate AS (
    SELECT
        DATE(CAST(year AS INT64), CAST(mo AS INT64), CAST(da AS INT64)) AS observation_date
        , ROUND((temp - 32.0) / 1.8, 1) AS temp_mean_c -- using Celsius instead of Fahrenheit
        , ROUND(prcp * 2.54, 1) AS prcp_cm -- from inches to centimeters
        , ROUND(CAST(wdsp AS FLOAT64) * 1.852 / 3.6, 1) AS wdsp_ms -- from knots to meters per second
    FROM `bigquery-public-data.noaa_gsod.gsod*`
    WHERE _TABLE_SUFFIX = "2019"
        AND CAST(mo AS INT64) <= 3
        AND stn in (SELECT usaf FROM `bigquery-public-data.noaa_gsod.stations` WHERE name = "ROCHESTER")
),

moving_avg AS (
    SELECT
        observation_date
        , temp_mean_c
        , prcp_cm
        , wdsp_ms
        , AVG(temp_mean_c) OVER (ORDER BY observation_date ROWS 7 PRECEDING) AS temp_moving_avg
        , AVG(prcp_cm) OVER (ORDER BY observation_date ROWS 7 PRECEDING) AS prcp_moving_avg
        , AVG(wdsp_ms) OVER (ORDER BY observation_date ROWS 7 PRECEDING) AS wdsp_moving_avg
    FROM transrate
),

lag_moving_avg AS (
    SELECT
        observation_date
        , temp_mean_c
        , prcp_cm
        , wdsp_ms
        , LAG(temp_moving_avg, 1) OVER (ORDER BY observation_date) AS lag1_temp_moving_avg
        , LAG(prcp_moving_avg, 1) OVER (ORDER BY observation_date) AS lag1_prcp_moving_avg
        , LAG(wdsp_moving_avg, 1) OVER (ORDER BY observation_date) AS lag1_wdsp_moving_avg

        , LAG(temp_moving_avg, 2) OVER (ORDER BY observation_date) AS lag2_temp_moving_avg
        , LAG(prcp_moving_avg, 2) OVER (ORDER BY observation_date) AS lag2_prcp_moving_avg
        , LAG(wdsp_moving_avg, 2) OVER (ORDER BY observation_date) AS lag2_wdsp_moving_avg

        , LAG(temp_moving_avg, 3) OVER (ORDER BY observation_date) AS lag3_temp_moving_avg
        , LAG(prcp_moving_avg, 3) OVER (ORDER BY observation_date) AS lag3_prcp_moving_avg
        , LAG(wdsp_moving_avg, 3) OVER (ORDER BY observation_date) AS lag3_wdsp_moving_avg

        , LAG(temp_moving_avg, 4) OVER (ORDER BY observation_date) AS lag4_temp_moving_avg
        , LAG(prcp_moving_avg, 4) OVER (ORDER BY observation_date) AS lag4_prcp_moving_avg
        , LAG(wdsp_moving_avg, 4) OVER (ORDER BY observation_date) AS lag4_wdsp_moving_avg

        , LAG(temp_moving_avg, 5) OVER (ORDER BY observation_date) AS lag5_temp_moving_avg
        , LAG(prcp_moving_avg, 5) OVER (ORDER BY observation_date) AS lag5_prcp_moving_avg
        , LAG(wdsp_moving_avg, 5) OVER (ORDER BY observation_date) AS lag5_wdsp_moving_avg

        , LAG(temp_moving_avg, 6) OVER (ORDER BY observation_date) AS lag6_temp_moving_avg
        , LAG(prcp_moving_avg, 6) OVER (ORDER BY observation_date) AS lag6_prcp_moving_avg
        , LAG(wdsp_moving_avg, 6) OVER (ORDER BY observation_date) AS lag6_wdsp_moving_avg

        , LAG(temp_moving_avg, 7) OVER (ORDER BY observation_date) AS lag7_temp_moving_avg
        , LAG(prcp_moving_avg, 7) OVER (ORDER BY observation_date) AS lag7_prcp_moving_avg
        , LAG(wdsp_moving_avg, 7) OVER (ORDER BY observation_date) AS lag7_wdsp_moving_avg

        , LAG(temp_moving_avg, 8) OVER (ORDER BY observation_date) AS lag8_temp_moving_avg
        , LAG(prcp_moving_avg, 8) OVER (ORDER BY observation_date) AS lag8_prcp_moving_avg
        , LAG(wdsp_moving_avg, 8) OVER (ORDER BY observation_date) AS lag8_wdsp_moving_avg
    FROM moving_avg
)

SELECT
    observation_date
    , temp_mean_c
    , prcp_cm
    , wdsp_ms

    , ROUND(lag1_temp_moving_avg, 1) AS lag1_temp_moving_avg
    , ROUND(lag1_prcp_moving_avg, 1) AS lag1_prcp_moving_avg
    , ROUND(lag1_wdsp_moving_avg, 1) AS lag1_wdsp_moving_avg
    
    , ROUND(lag1_temp_moving_avg - lag2_temp_moving_avg, 1) AS diff2_temp_moving_avg
    , ROUND(lag1_prcp_moving_avg - lag2_prcp_moving_avg, 1) AS diff2_prcp_moving_avg
    , ROUND(lag1_wdsp_moving_avg - lag2_wdsp_moving_avg, 1) AS diff2_wdsp_moving_avg
    , ROUND(lag2_temp_moving_avg, 1) AS lag2_temp_moving_avg
    , ROUND(lag2_prcp_moving_avg, 1) AS lag2_prcp_moving_avg
    , ROUND(lag2_wdsp_moving_avg, 1) AS lag2_wdsp_moving_avg
    
    , ROUND(lag2_temp_moving_avg - lag3_temp_moving_avg, 1) AS diff3_temp_moving_avg
    , ROUND(lag2_prcp_moving_avg - lag3_prcp_moving_avg, 1) AS diff3_prcp_moving_avg
    , ROUND(lag2_wdsp_moving_avg - lag3_wdsp_moving_avg, 1) AS diff3_wdsp_moving_avg
    , ROUND(lag3_temp_moving_avg, 1) AS lag3_temp_moving_avg
    , ROUND(lag3_prcp_moving_avg, 1) AS lag3_prcp_moving_avg
    , ROUND(lag3_wdsp_moving_avg, 1) AS lag3_wdsp_moving_avg
    
    , ROUND(lag3_temp_moving_avg - lag4_temp_moving_avg, 1) AS diff4_temp_moving_avg
    , ROUND(lag3_prcp_moving_avg - lag4_prcp_moving_avg, 1) AS diff4_prcp_moving_avg
    , ROUND(lag3_wdsp_moving_avg - lag4_wdsp_moving_avg, 1) AS diff4_wdsp_moving_avg
    , ROUND(lag4_temp_moving_avg, 1) AS lag4_temp_moving_avg
    , ROUND(lag4_prcp_moving_avg, 1) AS lag4_prcp_moving_avg
    , ROUND(lag4_wdsp_moving_avg, 1) AS lag4_wdsp_moving_avg
    
    , ROUND(lag4_temp_moving_avg - lag5_temp_moving_avg, 1) AS diff5_temp_moving_avg
    , ROUND(lag4_prcp_moving_avg - lag5_prcp_moving_avg, 1) AS diff5_prcp_moving_avg
    , ROUND(lag4_wdsp_moving_avg - lag5_wdsp_moving_avg, 1) AS diff5_wdsp_moving_avg
    , ROUND(lag5_temp_moving_avg, 1) AS lag5_temp_moving_avg
    , ROUND(lag5_prcp_moving_avg, 1) AS lag5_prcp_moving_avg
    , ROUND(lag5_wdsp_moving_avg, 1) AS lag5_wdsp_moving_avg
    
    , ROUND(lag5_temp_moving_avg - lag6_temp_moving_avg, 1) AS diff6_temp_moving_avg
    , ROUND(lag5_prcp_moving_avg - lag6_prcp_moving_avg, 1) AS diff6_prcp_moving_avg
    , ROUND(lag5_wdsp_moving_avg - lag6_wdsp_moving_avg, 1) AS diff6_wdsp_moving_avg
    , ROUND(lag6_temp_moving_avg, 1) AS lag6_temp_moving_avg
    , ROUND(lag6_prcp_moving_avg, 1) AS lag6_prcp_moving_avg
    , ROUND(lag6_wdsp_moving_avg, 1) AS lag6_wdsp_moving_avg
    
    , ROUND(lag6_temp_moving_avg - lag7_temp_moving_avg, 1) AS diff7_temp_moving_avg
    , ROUND(lag6_prcp_moving_avg - lag7_prcp_moving_avg, 1) AS diff7_prcp_moving_avg
    , ROUND(lag6_wdsp_moving_avg - lag7_wdsp_moving_avg, 1) AS diff7_wdsp_moving_avg
    , ROUND(lag7_temp_moving_avg, 1) AS lag7_temp_moving_avg
    , ROUND(lag7_prcp_moving_avg, 1) AS lag7_prcp_moving_avg
    , ROUND(lag7_wdsp_moving_avg, 1) AS lag7_wdsp_moving_avg
    
    , ROUND(lag7_temp_moving_avg - lag8_temp_moving_avg, 1) AS diff8_temp_moving_avg
    , ROUND(lag7_prcp_moving_avg - lag8_prcp_moving_avg, 1) AS diff8_prcp_moving_avg
    , ROUND(lag7_wdsp_moving_avg - lag8_wdsp_moving_avg, 1) AS diff8_wdsp_moving_avg
    , ROUND(lag8_temp_moving_avg, 1) AS lag8_temp_moving_avg
    , ROUND(lag8_prcp_moving_avg, 1) AS lag8_prcp_moving_avg
    , ROUND(lag8_wdsp_moving_avg, 1) AS lag8_wdsp_moving_avg
FROM lag_moving_avg
WHERE
  lag8_temp_moving_avg IS NOT NULL
ORDER BY observation_date;
-- all result rounded to 1 decimal place
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
  -- Find the Rochester, NY station that actually has data in gsod2019
  rochester_station AS (
    SELECT s.usaf, s.wban
    FROM `bigquery-public-data.noaa_gsod.stations` s
    INNER JOIN `bigquery-public-data.noaa_gsod.gsod2019` g
      ON s.usaf = g.stn AND s.wban = g.wban
    WHERE LOWER(TRIM(s.name)) LIKE '%rochester%'
      AND s.country = 'US'
    GROUP BY s.usaf, s.wban
    ORDER BY COUNT(*) DESC
    LIMIT 1
  ),

  -- Extract daily weather data for Rochester from Jan 1 to Mar 31, 2019
  daily_data AS (
    SELECT
      DATE(SAFE_CAST(year AS INT64), SAFE_CAST(mo AS INT64), SAFE_CAST(da AS INT64)) AS date,
      (SAFE_CAST(temp AS FLOAT64) / 10.0 - 32) * 5 / 9 AS temperature_c,
      (SAFE_CAST(prcp AS FLOAT64) / 100.0) * 2.54 AS precipitation_cm,
      (SAFE_CAST(wdsp AS FLOAT64) / 10.0) * 0.514444 AS wind_speed_mps
    FROM `bigquery-public-data.noaa_gsod.gsod2019`
    WHERE stn = (SELECT usaf FROM rochester_station)
      AND wban = (SELECT wban FROM rochester_station)
      AND DATE(SAFE_CAST(year AS INT64), SAFE_CAST(mo AS INT64), SAFE_CAST(da AS INT64))
          BETWEEN '2019-01-01' AND '2019-03-31'
  ),

  -- Compute 8-day moving averages (current day + previous 7 days)
  moving_avgs AS (
    SELECT
      date,
      temperature_c,
      precipitation_cm,
      wind_speed_mps,
      ROUND(AVG(temperature_c) OVER (ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW), 1) AS ma_temp,
      ROUND(AVG(precipitation_cm) OVER (ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW), 1) AS ma_precip,
      ROUND(AVG(wind_speed_mps) OVER (ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW), 1) AS ma_wind
    FROM daily_data
  ),

  -- Create lagged moving averages (1 to 8 days earlier)
  with_lags AS (
    SELECT
      *,
      LAG(ma_temp, 1) OVER (ORDER BY date) AS ma_temp_lag1,
      LAG(ma_temp, 2) OVER (ORDER BY date) AS ma_temp_lag2,
      LAG(ma_temp, 3) OVER (ORDER BY date) AS ma_temp_lag3,
      LAG(ma_temp, 4) OVER (ORDER BY date) AS ma_temp_lag4,
      LAG(ma_temp, 5) OVER (ORDER BY date) AS ma_temp_lag5,
      LAG(ma_temp, 6) OVER (ORDER BY date) AS ma_temp_lag6,
      LAG(ma_temp, 7) OVER (ORDER BY date) AS ma_temp_lag7,
      LAG(ma_temp, 8) OVER (ORDER BY date) AS ma_temp_lag8,
      LAG(ma_precip, 1) OVER (ORDER BY date) AS ma_precip_lag1,
      LAG(ma_precip, 2) OVER (ORDER BY date) AS ma_precip_lag2,
      LAG(ma_precip, 3) OVER (ORDER BY date) AS ma_precip_lag3,
      LAG(ma_precip, 4) OVER (ORDER BY date) AS ma_precip_lag4,
      LAG(ma_precip, 5) OVER (ORDER BY date) AS ma_precip_lag5,
      LAG(ma_precip, 6) OVER (ORDER BY date) AS ma_precip_lag6,
      LAG(ma_precip, 7) OVER (ORDER BY date) AS ma_precip_lag7,
      LAG(ma_precip, 8) OVER (ORDER BY date) AS ma_precip_lag8,
      LAG(ma_wind, 1) OVER (ORDER BY date) AS ma_wind_lag1,
      LAG(ma_wind, 2) OVER (ORDER BY date) AS ma_wind_lag2,
      LAG(ma_wind, 3) OVER (ORDER BY date) AS ma_wind_lag3,
      LAG(ma_wind, 4) OVER (ORDER BY date) AS ma_wind_lag4,
      LAG(ma_wind, 5) OVER (ORDER BY date) AS ma_wind_lag5,
      LAG(ma_wind, 6) OVER (ORDER BY date) AS ma_wind_lag6,
      LAG(ma_wind, 7) OVER (ORDER BY date) AS ma_wind_lag7,
      LAG(ma_wind, 8) OVER (ORDER BY date) AS ma_wind_lag8
    FROM moving_avgs
  )

-- Final output
SELECT
  date,
  ROUND(temperature_c, 1) AS temperature_c,
  ROUND(precipitation_cm, 1) AS precipitation_cm,
  ROUND(wind_speed_mps, 1) AS wind_speed_mps,
  ma_temp,
  ma_precip,
  ma_wind,
  ROUND(ma_temp - ma_temp_lag1, 1) AS diff_temp_lag1,
  ROUND(ma_temp - ma_temp_lag2, 1) AS diff_temp_lag2,
  ROUND(ma_temp - ma_temp_lag3, 1) AS diff_temp_lag3,
  ROUND(ma_temp - ma_temp_lag4, 1) AS diff_temp_lag4,
  ROUND(ma_temp - ma_temp_lag5, 1) AS diff_temp_lag5,
  ROUND(ma_temp - ma_temp_lag6, 1) AS diff_temp_lag6,
  ROUND(ma_temp - ma_temp_lag7, 1) AS diff_temp_lag7,
  ROUND(ma_temp - ma_temp_lag8, 1) AS diff_temp_lag8,
  ROUND(ma_precip - ma_precip_lag1, 1) AS diff_precip_lag1,
  ROUND(ma_precip - ma_precip_lag2, 1) AS diff_precip_lag2,
  ROUND(ma_precip - ma_precip_lag3, 1) AS diff_precip_lag3,
  ROUND(ma_precip - ma_precip_lag4, 1) AS diff_precip_lag4,
  ROUND(ma_precip - ma_precip_lag5, 1) AS diff_precip_lag5,
  ROUND(ma_precip - ma_precip_lag6, 1) AS diff_precip_lag6,
  ROUND(ma_precip - ma_precip_lag7, 1) AS diff_precip_lag7,
  ROUND(ma_precip - ma_precip_lag8, 1) AS diff_precip_lag8,
  ROUND(ma_wind - ma_wind_lag1, 1) AS diff_wind_lag1,
  ROUND(ma_wind - ma_wind_lag2, 1) AS diff_wind_lag2,
  ROUND(ma_wind - ma_wind_lag3, 1) AS diff_wind_lag3,
  ROUND(ma_wind - ma_wind_lag4, 1) AS diff_wind_lag4,
  ROUND(ma_wind - ma_wind_lag5, 1) AS diff_wind_lag5,
  ROUND(ma_wind - ma_wind_lag6, 1) AS diff_wind_lag6,
  ROUND(ma_wind - ma_wind_lag7, 1) AS diff_wind_lag7,
  ROUND(ma_wind - ma_wind_lag8, 1) AS diff_wind_lag8
FROM with_lags
WHERE date >= '2019-01-09'
ORDER BY date;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
  rochester_station AS (
    SELECT CAST(usaf AS STRING) AS station_id
    FROM `bigquery-public-data.noaa_gsod.stations`
    WHERE LOWER(name) = 'rochester'
  ),
  daily_data AS (
    SELECT
      DATE(2019, CAST(gsod.mo AS INT64), CAST(gsod.da AS INT64)) AS date,
      ROUND((gsod.temp - 32) * 5 / 9, 1) AS temperature_celsius,
      ROUND(gsod.prcp * 2.54, 1) AS precipitation_cm,
      ROUND(CAST(gsod.wdsp AS FLOAT64) * 0.514444, 1) AS wind_speed_mps
    FROM
      `bigquery-public-data.noaa_gsod.gsod2019` AS gsod
    WHERE
      CAST(gsod.year AS STRING) = '2019'
      AND CAST(gsod.mo AS INT64) BETWEEN 1 AND 3
      AND CAST(gsod.stn AS STRING) IN (SELECT station_id FROM rochester_station)
      AND gsod.temp != 9999.9
      AND gsod.prcp != 99.99
      AND gsod.wdsp != '999.9'
  ),
  moving_avgs AS (
    SELECT
      date,
      temperature_celsius,
      precipitation_cm,
      wind_speed_mps,
      ROUND(AVG(temperature_celsius) OVER (
        ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW
      ), 1) AS ma_temp_8d,
      ROUND(AVG(precipitation_cm) OVER (
        ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW
      ), 1) AS ma_precip_8d,
      ROUND(AVG(wind_speed_mps) OVER (
        ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW
      ), 1) AS ma_wind_8d
    FROM daily_data
  ),
  lags AS (
    SELECT
      date,
      temperature_celsius,
      precipitation_cm,
      wind_speed_mps,
      ma_temp_8d,
      ma_precip_8d,
      ma_wind_8d,
      LAG(ma_temp_8d, 1) OVER (ORDER BY date) AS ma_temp_lag1,
      LAG(ma_temp_8d, 2) OVER (ORDER BY date) AS ma_temp_lag2,
      LAG(ma_temp_8d, 3) OVER (ORDER BY date) AS ma_temp_lag3,
      LAG(ma_temp_8d, 4) OVER (ORDER BY date) AS ma_temp_lag4,
      LAG(ma_temp_8d, 5) OVER (ORDER BY date) AS ma_temp_lag5,
      LAG(ma_temp_8d, 6) OVER (ORDER BY date) AS ma_temp_lag6,
      LAG(ma_temp_8d, 7) OVER (ORDER BY date) AS ma_temp_lag7,
      LAG(ma_temp_8d, 8) OVER (ORDER BY date) AS ma_temp_lag8,
      LAG(ma_precip_8d, 1) OVER (ORDER BY date) AS ma_precip_lag1,
      LAG(ma_precip_8d, 2) OVER (ORDER BY date) AS ma_precip_lag2,
      LAG(ma_precip_8d, 3) OVER (ORDER BY date) AS ma_precip_lag3,
      LAG(ma_precip_8d, 4) OVER (ORDER BY date) AS ma_precip_lag4,
      LAG(ma_precip_8d, 5) OVER (ORDER BY date) AS ma_precip_lag5,
      LAG(ma_precip_8d, 6) OVER (ORDER BY date) AS ma_precip_lag6,
      LAG(ma_precip_8d, 7) OVER (ORDER BY date) AS ma_precip_lag7,
      LAG(ma_precip_8d, 8) OVER (ORDER BY date) AS ma_precip_lag8,
      LAG(ma_wind_8d, 1) OVER (ORDER BY date) AS ma_wind_lag1,
      LAG(ma_wind_8d, 2) OVER (ORDER BY date) AS ma_wind_lag2,
      LAG(ma_wind_8d, 3) OVER (ORDER BY date) AS ma_wind_lag3,
      LAG(ma_wind_8d, 4) OVER (ORDER BY date) AS ma_wind_lag4,
      LAG(ma_wind_8d, 5) OVER (ORDER BY date) AS ma_wind_lag5,
      LAG(ma_wind_8d, 6) OVER (ORDER BY date) AS ma_wind_lag6,
      LAG(ma_wind_8d, 7) OVER (ORDER BY date) AS ma_wind_lag7,
      LAG(ma_wind_8d, 8) OVER (ORDER BY date) AS ma_wind_lag8
    FROM moving_avgs
  )
SELECT
  date,
  temperature_celsius,
  precipitation_cm,
  wind_speed_mps,
  ma_temp_8d,
  ma_precip_8d,
  ma_wind_8d,
  ROUND(ma_temp_8d - ma_temp_lag1, 1) AS temp_diff_lag1,
  ROUND(ma_temp_8d - ma_temp_lag2, 1) AS temp_diff_lag2,
  ROUND(ma_temp_8d - ma_temp_lag3, 1) AS temp_diff_lag3,
  ROUND(ma_temp_8d - ma_temp_lag4, 1) AS temp_diff_lag4,
  ROUND(ma_temp_8d - ma_temp_lag5, 1) AS temp_diff_lag5,
  ROUND(ma_temp_8d - ma_temp_lag6, 1) AS temp_diff_lag6,
  ROUND(ma_temp_8d - ma_temp_lag7, 1) AS temp_diff_lag7,
  ROUND(ma_temp_8d - ma_temp_lag8, 1) AS temp_diff_lag8,
  ROUND(ma_precip_8d - ma_precip_lag1, 1) AS precip_diff_lag1,
  ROUND(ma_precip_8d - ma_precip_lag2, 1) AS precip_diff_lag2,
  ROUND(ma_precip_8d - ma_precip_lag3, 1) AS precip_diff_lag3,
  ROUND(ma_precip_8d - ma_precip_lag4, 1) AS precip_diff_lag4,
  ROUND(ma_precip_8d - ma_precip_lag5, 1) AS precip_diff_lag5,
  ROUND(ma_precip_8d - ma_precip_lag6, 1) AS precip_diff_lag6,
  ROUND(ma_precip_8d - ma_precip_lag7, 1) AS precip_diff_lag7,
  ROUND(ma_precip_8d - ma_precip_lag8, 1) AS precip_diff_lag8,
  ROUND(ma_wind_8d - ma_wind_lag1, 1) AS wind_diff_lag1,
  ROUND(ma_wind_8d - ma_wind_lag2, 1) AS wind_diff_lag2,
  ROUND(ma_wind_8d - ma_wind_lag3, 1) AS wind_diff_lag3,
  ROUND(ma_wind_8d - ma_wind_lag4, 1) AS wind_diff_lag4,
  ROUND(ma_wind_8d - ma_wind_lag5, 1) AS wind_diff_lag5,
  ROUND(ma_wind_8d - ma_wind_lag6, 1) AS wind_diff_lag6,
  ROUND(ma_wind_8d - ma_wind_lag7, 1) AS wind_diff_lag7,
  ROUND(ma_wind_8d - ma_wind_lag8, 1) AS wind_diff_lag8
FROM lags
WHERE date >= '2019-01-09'
ORDER BY date;
```

---

## 19. Instance: `bq032`
**Question:**
> Can you provide the latitude of the final coordinates for the hurricane that traveled the second longest distance in the North Atlantic during 2020?

### 🏆 Gold Reference Answer
```sql
WITH hurricane_geometry AS (
  SELECT
    * EXCEPT (longitude, latitude),
    ST_GEOGPOINT(longitude, latitude) AS geom,
    MAX(usa_wind) OVER (PARTITION BY sid) AS max_wnd_speed
  FROM
    `bigquery-public-data.noaa_hurricanes.hurricanes`
  WHERE
    season = '2020'
    AND basin = 'NA'
    AND name != 'NOT NAMED'
),
dist_between_points AS (
  SELECT
    sid,
    name,
    season,
    iso_time,
    max_wnd_speed,
    geom,
    ST_DISTANCE(geom, LAG(geom, 1) OVER (PARTITION BY sid ORDER BY iso_time ASC)) / 1000 AS dist
  FROM
    hurricane_geometry
),
total_distances AS (
  SELECT
    sid,
    name,
    season,
    iso_time,
    max_wnd_speed,
    geom,
    SUM(dist) OVER (PARTITION BY sid ORDER BY iso_time ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_distance,
    SUM(dist) OVER (PARTITION BY sid) AS total_dist
  FROM
    dist_between_points
),
ranked_hurricanes AS (
  SELECT
    *,
    DENSE_RANK() OVER (ORDER BY total_dist DESC) AS dense_rank
  FROM
    total_distances
)

SELECT
  ST_Y(geom)
FROM
  ranked_hurricanes
WHERE
  dense_rank = 2
ORDER BY
cumulative_distance
DESC
LIMIT 1
;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH hurricane_tracks AS (
    -- Get all hurricane tracking points for 2020 in North Atlantic
    SELECT 
        sid,
        name,
        iso_time,
        latitude,
        longitude,
        -- Create geography point for distance calculations
        ST_GEOGPOINT(longitude, latitude) AS point
    FROM `bigquery-public-data.noaa_hurricanes.hurricanes`
    WHERE EXTRACT(YEAR FROM iso_time) = 2020
        AND basin = 'NA'  -- North Atlantic basin
),

ordered_points AS (
    -- Order points by time within each storm
    SELECT 
        sid,
        name,
        iso_time,
        latitude,
        longitude,
        point,
        -- Get the next point's geography for distance calculation
        LEAD(point) OVER (PARTITION BY sid ORDER BY iso_time) AS next_point
    FROM hurricane_tracks
),

segment_distances AS (
    -- Calculate distance between consecutive points
    SELECT 
        sid,
        name,
        ST_DISTANCE(point, next_point) AS segment_distance
    FROM ordered_points
    WHERE next_point IS NOT NULL
),

storm_distances AS (
    -- Sum distances to get total path length per storm
    SELECT 
        sid,
        name,
        ROUND(SUM(segment_distance) / 1000, 4) AS total_distance_km,  -- Convert to km
        ROUND(SUM(segment_distance) / 1609.344, 4) AS total_distance_miles
    FROM segment_distances
    GROUP BY sid, name
),

ranked_storms AS (
    -- Rank storms by total distance (second longest)
    SELECT 
        sid,
        name,
        total_distance_km,
        total_distance_miles,
        ROW_NUMBER() OVER (ORDER BY total_distance_km DESC) AS distance_rank
    FROM storm_distances
),

second_longest AS (
    -- Get the second longest storm
    SELECT sid, name
    FROM ranked_storms
    WHERE distance_rank = 2
),

final_coordinates AS (
    -- Get the last tracking point for the second longest storm
    SELECT 
        h.latitude AS final_latitude,
        h.longitude AS final_longitude,
        h.iso_time AS final_time
    FROM hurricane_tracks h
    INNER JOIN second_longest sl ON h.sid = sl.sid
    QUALIFY ROW_NUMBER() OVER (PARTITION BY h.sid ORDER BY h.iso_time DESC) = 1
)

-- Return the latitude of the final coordinates
SELECT 
    ROUND(final_latitude, 4) AS final_latitude
FROM final_coordinates;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
-- Step 1: Filter North Atlantic hurricanes in 2020
atlantic_2020_hurricanes AS (
  SELECT 
    sid,
    name,
    latitude,
    longitude,
    iso_time
  FROM `bigquery-public-data.noaa_hurricanes.hurricanes`
  WHERE basin = 'NA'
    AND EXTRACT(YEAR FROM iso_time) = 2020
    AND latitude IS NOT NULL
    AND longitude IS NOT NULL
),

-- Step 2: Calculate distances between consecutive points for each storm
storm_distances AS (
  SELECT 
    sid,
    name,
    latitude,
    longitude,
    iso_time,
    -- Get previous point coordinates
    LAG(latitude) OVER (PARTITION BY sid ORDER BY iso_time) AS prev_lat,
    LAG(longitude) OVER (PARTITION BY sid ORDER BY iso_time) AS prev_lon,
    -- Calculate distance to previous point using ST_GEOGPOINT (correct BigQuery function)
    CASE 
      WHEN LAG(latitude) OVER (PARTITION BY sid ORDER BY iso_time) IS NOT NULL 
        AND LAG(longitude) OVER (PARTITION BY sid ORDER BY iso_time) IS NOT NULL
      THEN ST_DISTANCE(
             ST_GEOGPOINT(longitude, latitude),
             ST_GEOGPOINT(
               LAG(longitude) OVER (PARTITION BY sid ORDER BY iso_time),
               LAG(latitude) OVER (PARTITION BY sid ORDER BY iso_time)
             )
           )
      ELSE 0
    END AS segment_distance
  FROM atlantic_2020_hurricanes
),

-- Step 3: Calculate total distance per storm
storm_total_distance AS (
  SELECT 
    sid,
    name,
    SUM(segment_distance) AS total_distance_meters,
    MAX(iso_time) AS final_time
  FROM storm_distances
  GROUP BY sid, name
),

-- Step 4: Rank storms by total distance
ranked_storms AS (
  SELECT 
    sid,
    name,
    total_distance_meters,
    ROW_NUMBER() OVER (ORDER BY total_distance_meters DESC) AS distance_rank
  FROM storm_total_distance
),

-- Step 5: Get the storm with second longest distance
second_longest_storm AS (
  SELECT sid
  FROM ranked_storms
  WHERE distance_rank = 2
)

-- Step 6: Get the final latitude for that storm
SELECT 
  latitude AS final_latitude
FROM atlantic_2020_hurricanes
WHERE sid = (SELECT sid FROM second_longest_storm)
ORDER BY iso_time DESC
LIMIT 1;
```

---

## 20. Instance: `bq034`
**Question:**
> I want to know the IDs, names of weather stations within a 50 km straight-line distance from the center of Chicago (41.8319°N, 87.6847°W)

### 🏆 Gold Reference Answer
```sql
WITH params AS (
  SELECT ST_GeogPoint(-87.6847, 41.8319) AS center,
         50 AS maxdist_km
),
distance_from_center AS (
  SELECT
    id,
    name,
    state,
    ST_GeogPoint(longitude, latitude) AS loc,
    ST_Distance(ST_GeogPoint(longitude, latitude), params.center) AS dist_meters
  FROM
    `bigquery-public-data.ghcn_d.ghcnd_stations`,
    params
  WHERE ST_DWithin(ST_GeogPoint(longitude, latitude), params.center, params.maxdist_km*1000)
),
nearest_stations AS (
  SELECT 
    *, 
    RANK() OVER (ORDER BY dist_meters ASC) AS rank
  FROM 
    distance_from_center
),
nearest_nstations AS (
  SELECT 
    station.* 
  FROM 
    nearest_stations AS station, params
)
SELECT * from nearest_nstations
```

### 🤖 AutoLink Baseline Prediction
```sql
SELECT
  id AS station_id,
  name AS station_name
FROM
  `bigquery-public-data.ghcn_d.ghcnd_stations`
WHERE
  ST_DISTANCE(
    ST_GEOGPOINT(longitude, latitude),
    ST_GEOGPOINT(-87.6847, 41.8319)
  ) <= 50000
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Query to find weather stations within 50 km of Chicago center
SELECT
  id,
  name
FROM
  `bigquery-public-data.ghcn_d.ghcnd_stations`
WHERE
  ST_DISTANCE(
    ST_GEOGPOINT(longitude, latitude),  -- station location
    ST_GEOGPOINT(-87.6847, 41.8319)    -- Chicago center (longitude, latitude)
  ) <= 50000  -- 50 km in meters
  -- Only include stations that have a name (optional, but good practice)
  AND name IS NOT NULL;
```

---

## 21. Instance: `bq035`
**Question:**
> What is the total distance traveled by each bike in the San Francisco Bikeshare program, measured in meters? Use data from bikeshare trips and stations to calculate this.

### 🏆 Gold Reference Answer
```sql
SELECT
  bike_number, 
  AVG(dist_in_m) AS avg_dist_m, 
  SUM(dist_in_m) AS total_dist_m
FROM (
  SELECT
    ST_DISTANCE(
      ST_GEOGPOINT(start_lon, start_lat),
      ST_GEOGPOINT(end_lon, end_lat)
    ) AS dist_in_m,
    starts.bike_number
  FROM (
    SELECT 
      latitude AS start_lat,
      longitude AS start_lon,
      bike_number,
      trip_id
    FROM `bigquery-public-data.san_francisco.bikeshare_trips` trips
    LEFT JOIN `bigquery-public-data.san_francisco.bikeshare_stations` stations
      ON trips.start_station_id = stations.station_id
  ) starts
  LEFT JOIN (
    SELECT 
      latitude AS end_lat,
      longitude AS end_lon,
      bike_number,
      trip_id
    FROM `bigquery-public-data.san_francisco.bikeshare_trips` trips
    LEFT JOIN `bigquery-public-data.san_francisco.bikeshare_stations` stations
      ON trips.end_station_id = stations.station_id
  ) ends ON ends.trip_id = starts.trip_id
)
GROUP BY bike_number
ORDER BY total_dist_m DESC
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH trip_distances AS (
  SELECT
    t.bike_number AS bike_id,
    t.trip_id,
    -- Compute straight-line distance in meters between start and end stations
    ST_DISTANCE(
      ST_GEOGPOINT(s_start.longitude, s_start.latitude),
      ST_GEOGPOINT(s_end.longitude, s_end.latitude)
    ) AS distance_meters
  FROM
    `bigquery-public-data.san_francisco.bikeshare_trips` AS t
  -- Join to get start station coordinates
  LEFT JOIN
    `bigquery-public-data.san_francisco.bikeshare_stations` AS s_start
    ON t.start_station_id = s_start.station_id
  -- Join to get end station coordinates
  LEFT JOIN
    `bigquery-public-data.san_francisco.bikeshare_stations` AS s_end
    ON t.end_station_id = s_end.station_id
  WHERE
    -- Exclude trips with missing station info to avoid null distances
    t.start_station_id IS NOT NULL
    AND t.end_station_id IS NOT NULL
    AND s_start.longitude IS NOT NULL
    AND s_start.latitude IS NOT NULL
    AND s_end.longitude IS NOT NULL
    AND s_end.latitude IS NOT NULL
)
SELECT
  bike_id,
  ROUND(SUM(distance_meters), 4) AS total_distance_meters
FROM
  trip_distances
GROUP BY
  bike_id
ORDER BY
  bike_id;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Calculate total distance traveled by each bike in meters.
-- Steps:
-- 1. Join trips with stations twice to get start and end coordinates.
-- 2. Compute distance between start and end points using ST_DISTANCE (returns meters).
-- 3. Sum distances per bike number, round to 4 decimal places.

WITH trip_coords AS (
  SELECT
    t.bike_number,
    s_start.longitude AS start_lon,
    s_start.latitude  AS start_lat,
    s_end.longitude   AS end_lon,
    s_end.latitude    AS end_lat
  FROM `bigquery-public-data.san_francisco.bikeshare_trips` t
  JOIN `bigquery-public-data.san_francisco.bikeshare_stations` s_start
    ON t.start_station_id = s_start.station_id
  JOIN `bigquery-public-data.san_francisco.bikeshare_stations` s_end
    ON t.end_station_id = s_end.station_id
)

SELECT
  bike_number,
  ROUND(SUM(ST_DISTANCE(ST_GEOGPOINT(start_lon, start_lat), ST_GEOGPOINT(end_lon, end_lat))), 4) AS total_distance_meters
FROM trip_coords
GROUP BY bike_number
ORDER BY bike_number;
```

---

## 22. Instance: `bq038`
**Question:**
> Identify the top 10 Citibike stations by highest proportion of group rides, defined as trips starting and ending at the same station where multiple riders departed/arrived within the same 2-minute time window. Calculate the proportion as the number of trips that are part of a group divided by the total number of trips ending at that station.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Total trips ending at each station
WITH total_trips_per_station AS (
  SELECT
    end_station_id AS station_id,
    COUNT(*) AS total_ending_trips
  FROM `bigquery-public-data.new_york_citibike.citibike_trips`
  GROUP BY end_station_id
),

-- Step 2: Round trips (start = end)
round_trips AS (
  SELECT
    start_station_id AS station_id,
    starttime,
    bikeid,
    LAG(starttime) OVER (
      PARTITION BY start_station_id
      ORDER BY starttime
    ) AS prev_starttime,
    LEAD(starttime) OVER (
      PARTITION BY start_station_id
      ORDER BY starttime
    ) AS next_starttime
  FROM `bigquery-public-data.new_york_citibike.citibike_trips`
  WHERE start_station_id = end_station_id
),

-- Step 3: Flag group rides (within 2 minutes window)
group_flags AS (
  SELECT
    station_id,
    bikeid,
    starttime,
    CASE
      WHEN (prev_starttime IS NOT NULL AND TIMESTAMP_DIFF(TIMESTAMP(starttime), TIMESTAMP(prev_starttime), SECOND) <= 120)
        OR (next_starttime IS NOT NULL AND TIMESTAMP_DIFF(TIMESTAMP(next_starttime), TIMESTAMP(starttime), SECOND) <= 120)
      THEN 1
      ELSE 0
    END AS is_group
  FROM round_trips
),

-- Step 4: Count distinct group rides per station
group_rides_per_station AS (
  SELECT
    station_id,
    COUNT(DISTINCT bikeid || CAST(UNIX_MICROS(TIMESTAMP(starttime)) AS STRING)) AS group_ride_count
  FROM group_flags
  WHERE is_group = 1
  GROUP BY station_id
)

-- Step 5: Compute proportion and return top 10
SELECT
  t.station_id,
  ROUND(SAFE_DIVIDE(COALESCE(g.group_ride_count, 0), t.total_ending_trips), 4) AS proportion_group_rides
FROM total_trips_per_station t
LEFT JOIN group_rides_per_station g
  ON t.station_id = g.station_id
ORDER BY proportion_group_rides DESC
LIMIT 10;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH all_trips_end AS (
  SELECT
    end_station_id,
    COUNT(*) AS total_ending
  FROM
    `bigquery-public-data.new_york.citibike_trips`
  GROUP BY
    end_station_id
),

round_trips AS (
  SELECT
    end_station_id,
    starttime,
    UNIX_MICROS(starttime) AS start_micros
  FROM
    `bigquery-public-data.new_york.citibike_trips`
  WHERE
    start_station_id = end_station_id
),

trip_group_flag AS (
  SELECT
    end_station_id,
    starttime,
    COUNT(*) OVER (
      PARTITION BY end_station_id
      ORDER BY start_micros
      RANGE BETWEEN 120000000 PRECEDING AND 120000000 FOLLOWING
    ) AS cnt_in_window
  FROM
    round_trips
),

group_trips_counts AS (
  SELECT
    end_station_id,
    COUNTIF(cnt_in_window >= 2) AS group_trips
  FROM
    trip_group_flag
  GROUP BY
    end_station_id
)

SELECT
  s.name AS station_name,
  s.station_id AS station_id,
  g.end_station_id,
  ROUND(SAFE_DIVIDE(g.group_trips, a.total_ending), 4) AS proportion
FROM group_trips_counts g
JOIN all_trips_end a
  ON g.end_station_id = a.end_station_id
JOIN `bigquery-public-data.new_york.citibike_stations` s
  ON SAFE_CAST(s.station_id AS INT64) = g.end_station_id
ORDER BY proportion DESC
LIMIT 10;
```

---

## 23. Instance: `bq039`
**Question:**
> Find the top 10 taxi trips in New York City between July 1 and July 7, 2016 (ensuring both pickup and dropoff times fall within these dates) where the passenger count is greater than five, the trip distance is at least ten miles, and there are no negative fare-related amounts (including tip, tolls, mta tax, fare, and total costs). Exclude any trips where the dropoff time is not strictly after the pickup time, then sort the results by total fare amount in descending order. Finally, display each trip’s pickup zone, dropoff zone, trip duration in seconds, driving speed in miles per hour, and tip rate as a percentage of the total fare amount.

### 🏆 Gold Reference Answer
```sql
SELECT 
    tz.zone_name AS pickup_zone,
    tz1.zone_name AS dropoff_zone, 
    time_duration_in_secs,
    driving_speed_miles_per_hour,
    tip_rate
FROM
(
SELECT *,
    TIMESTAMP_DIFF(dropoff_datetime,pickup_datetime,SECOND) as time_duration_in_secs,
    ROUND(trip_distance / (TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND) / 3600), 2) AS driving_speed_miles_per_hour,
    (CASE WHEN total_amount=0 THEN 0
          ELSE (tip_amount*100/total_amount) END) as tip_rate
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016`
) t
INNER JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` tz
ON t.pickup_location_id = tz.zone_id
INNER JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` tz1
ON t.dropoff_location_id = tz1.zone_id
WHERE 
    pickup_datetime BETWEEN '2016-07-01' AND '2016-07-07' 
    AND dropoff_datetime BETWEEN '2016-07-01' AND '2016-07-07'
    AND TIMESTAMP_DIFF(dropoff_datetime,pickup_datetime,SECOND) > 0
    AND passenger_count > 5
    AND trip_distance >= 10
    AND tip_amount >= 0 
    AND tolls_amount >= 0 
    AND mta_tax >= 0 
    AND fare_amount >= 0
    AND total_amount >= 0
ORDER BY total_amount DESC
LIMIT 10;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH filtered_trips AS (
  SELECT
    pickup_datetime,
    dropoff_datetime,
    pickup_location_id,
    dropoff_location_id,
    trip_distance,
    fare_amount,
    tip_amount,
    tolls_amount,
    mta_tax,
    total_amount,
    TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND) AS trip_duration_seconds,
    SAFE_DIVIDE(trip_distance * 3600, TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND)) AS driving_speed_mph_raw,
    SAFE_DIVIDE(tip_amount, total_amount) * 100 AS tip_rate_raw
  FROM
    `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016`
  WHERE
    DATE(pickup_datetime) BETWEEN '2016-07-01' AND '2016-07-07'
    AND DATE(dropoff_datetime) BETWEEN '2016-07-01' AND '2016-07-07'
    AND passenger_count > 5
    AND trip_distance >= 10.0
    AND fare_amount >= 0
    AND tip_amount >= 0
    AND tolls_amount >= 0
    AND mta_tax >= 0
    AND total_amount >= 0
    AND dropoff_datetime > pickup_datetime
)
SELECT
  pickup_zone.zone_name AS pickup_zone,
  dropoff_zone.zone_name AS dropoff_zone,
  ft.trip_duration_seconds,
  ROUND(ft.driving_speed_mph_raw, 4) AS driving_speed_mph,
  ROUND(ft.tip_rate_raw, 4) AS tip_rate_percent
FROM
  filtered_trips ft
LEFT JOIN
  `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` pickup_zone
  ON ft.pickup_location_id = pickup_zone.zone_id
LEFT JOIN
  `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` dropoff_zone
  ON ft.dropoff_location_id = dropoff_zone.zone_id
ORDER BY
  ft.total_amount DESC
LIMIT 10;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Use CTE to get relevant trips from the 2016 yellow taxi table
WITH yellow_trips_2016 AS (
  SELECT
    pickup_datetime,
    dropoff_datetime,
    passenger_count,
    trip_distance,
    fare_amount,
    tip_amount,
    tolls_amount,
    mta_tax,
    extra,
    imp_surcharge,
    total_amount,
    pickup_location_id,
    dropoff_location_id
  FROM
    `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016`
  WHERE
    -- Both pickup and dropoff times fall within July 1-7, 2016
    pickup_datetime >= TIMESTAMP('2016-07-01 00:00:00')
    AND pickup_datetime < TIMESTAMP('2016-07-08 00:00:00')
    AND dropoff_datetime >= TIMESTAMP('2016-07-01 00:00:00')
    AND dropoff_datetime < TIMESTAMP('2016-07-08 00:00:00')
    -- Passenger count > 5
    AND passenger_count > 5
    -- Trip distance >= 10 miles
    AND trip_distance >= 10.0
    -- No negative fare-related amounts
    AND fare_amount >= 0
    AND tip_amount >= 0
    AND tolls_amount >= 0
    AND mta_tax >= 0
    AND extra >= 0
    AND imp_surcharge >= 0
    AND total_amount >= 0
    -- Dropoff time strictly after pickup time
    AND dropoff_datetime > pickup_datetime
),

-- Step 2: Join with taxi_zone_geom to get zone names
trip_with_zones AS (
  SELECT
    t.pickup_datetime,
    t.dropoff_datetime,
    t.passenger_count,
    t.trip_distance,
    t.fare_amount,
    t.tip_amount,
    t.tolls_amount,
    t.mta_tax,
    t.extra,
    t.imp_surcharge,
    t.total_amount,
    t.pickup_location_id,
    t.dropoff_location_id,
    pz.zone_name AS pickup_zone,
    dz.zone_name AS dropoff_zone,
    -- Calculate trip duration in seconds
    TIMESTAMP_DIFF(t.dropoff_datetime, t.pickup_datetime, SECOND) AS trip_duration_seconds
  FROM yellow_trips_2016 t
  LEFT JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` pz
    ON CAST(t.pickup_location_id AS STRING) = pz.zone_id
  LEFT JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` dz
    ON CAST(t.dropoff_location_id AS STRING) = dz.zone_id
)

-- Step 3: Final selection with computed fields, sorted and limited
SELECT
  pickup_zone,
  dropoff_zone,
  trip_duration_seconds,
  -- Driving speed in miles per hour (distance in miles / time in hours)
  ROUND(trip_distance / (trip_duration_seconds / 3600.0), 4) AS driving_speed_mph,
  -- Tip rate as percentage of total fare amount
  ROUND((tip_amount / NULLIF(total_amount, 0)) * 100, 4) AS tip_rate_percentage
FROM trip_with_zones
ORDER BY total_amount DESC
LIMIT 10;
```

---

## 24. Instance: `bq040`
**Question:**
> For NYC yellow taxi trips between January 1 and January 7, 2016, excluding any trips picked up in ‘EWR’ or ‘Staten Island,’ determine the proportion of rides that fall into each tip category in each pickup borough. Only include trips where the dropoff time is after the pickup time, the passenger count is greater than zero, and trip_distance, tip_amount, tolls_amount, mta_tax, fare_amount, and total_amount are all non-negative. Classify the tip percentage as follows: 0% (no tip), up to 5%, 5% to 10%, 10% to 15%, 15% to 20%, 20% to 25%, and more than 25%.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
filtered_trips AS (
  SELECT 
    pickup_datetime,
    dropoff_datetime,
    pickup_location_id,
    passenger_count,
    trip_distance,
    tip_amount,
    tolls_amount,
    mta_tax,
    fare_amount,
    total_amount
  FROM 
    `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016`
  WHERE 
    pickup_datetime >= '2016-01-01 00:00:00'
    AND pickup_datetime < '2016-01-08 00:00:00'
    AND dropoff_datetime > pickup_datetime
    AND passenger_count > 0
    AND trip_distance >= 0
    AND tip_amount >= 0
    AND tolls_amount >= 0
    AND mta_tax >= 0
    AND fare_amount >= 0
    AND total_amount >= 0
),

trips_with_borough AS (
  SELECT 
    t.*,
    z.borough AS pickup_borough
  FROM 
    filtered_trips t
  JOIN 
    `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` z
    ON t.pickup_location_id = z.zone_id
  WHERE 
    z.borough NOT IN ('EWR', 'Staten Island')
),

trips_with_tip_category AS (
  SELECT 
    pickup_borough,
    CASE 
      WHEN tip_amount = 0 THEN 'no tip'
      WHEN ROUND((tip_amount / NULLIF(total_amount, 0)) * 100, 4) <= 5 THEN 'Less than 5%'
      WHEN ROUND((tip_amount / NULLIF(total_amount, 0)) * 100, 4) <= 10 THEN '5% to 10%'
      WHEN ROUND((tip_amount / NULLIF(total_amount, 0)) * 100, 4) <= 15 THEN '10% to 15%'
      WHEN ROUND((tip_amount / NULLIF(total_amount, 0)) * 100, 4) <= 20 THEN '15% to 20%'
      WHEN ROUND((tip_amount / NULLIF(total_amount, 0)) * 100, 4) <= 25 THEN '20% to 25%'
      ELSE 'More than 25%'
    END AS tip_category
  FROM 
    trips_with_borough
),

borough_totals AS (
  SELECT 
    pickup_borough,
    COUNT(*) AS total_trips
  FROM 
    trips_with_tip_category
  GROUP BY 
    pickup_borough
),

category_counts AS (
  SELECT 
    pickup_borough,
    tip_category,
    COUNT(*) AS category_count
  FROM 
    trips_with_tip_category
  GROUP BY 
    pickup_borough, 
    tip_category
)

SELECT 
  c.pickup_borough,
  c.tip_category,
  ROUND(c.category_count / b.total_trips, 4) AS proportion
FROM 
  category_counts c
JOIN 
  borough_totals b
  ON c.pickup_borough = b.pickup_borough
ORDER BY 
  c.pickup_borough,
  CASE 
    WHEN c.tip_category = 'no tip' THEN 1
    WHEN c.tip_category = 'Less than 5%' THEN 2
    WHEN c.tip_category = '5% to 10%' THEN 3
    WHEN c.tip_category = '10% to 15%' THEN 4
    WHEN c.tip_category = '15% to 20%' THEN 5
    WHEN c.tip_category = '20% to 25%' THEN 6
    WHEN c.tip_category = 'More than 25%' THEN 7
  END;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Filter yellow taxi trips in Jan 1-7, 2016 and apply all constraints
-- Step 2: Join with taxi_zone_geom to get pickup borough and zone name
-- Step 3: Exclude trips from 'EWR' or 'Staten Island' borough
-- Step 4: Compute tip percentage and categorize
-- Step 5: Count per borough and tip category, then compute proportion

WITH filtered_trips AS (
  SELECT
    t.pickup_location_id,
    t.tip_amount,
    t.total_amount,
    t.pickup_datetime,
    t.dropoff_datetime,
    t.passenger_count,
    t.trip_distance,
    t.tolls_amount,
    t.mta_tax,
    t.fare_amount,
    z.zone_name,
    z.borough AS pickup_borough
  FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016` t
  INNER JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` z
    ON t.pickup_location_id = z.zone_id
  WHERE
    -- Time range: Jan 1, 2016 00:00:00 UTC to Jan 7, 2016 23:59:59 UTC
    t.pickup_datetime >= TIMESTAMP('2016-01-01 00:00:00')
    AND t.pickup_datetime < TIMESTAMP('2016-01-08 00:00:00')
    -- Logical constraints
    AND t.dropoff_datetime > t.pickup_datetime
    AND t.passenger_count > 0
    AND t.trip_distance >= 0
    AND t.tip_amount >= 0
    AND t.tolls_amount >= 0
    AND t.mta_tax >= 0
    AND t.fare_amount >= 0
    AND t.total_amount >= 0
    -- Exclude EWR and Staten Island
    AND z.borough NOT IN ('EWR', 'Staten Island')
),
tip_categorized AS (
  SELECT
    pickup_borough,
    -- Tip percentage: (tip / (total - tip)) * 100
    CASE
      WHEN total_amount = tip_amount THEN NULL    -- denominator zero
      WHEN tip_amount = 0 THEN 0.0
      ELSE (tip_amount * 100.0) / (total_amount - tip_amount)
    END AS tip_pct,
    tip_amount
  FROM filtered_trips
),
category_counts AS (
  SELECT
    pickup_borough,
    CASE
      WHEN tip_pct IS NULL AND tip_amount > 0 THEN 'More than 25%'
      WHEN tip_pct = 0 THEN 'no tip'
      WHEN tip_pct <= 5 THEN 'up to 5%'
      WHEN tip_pct <= 10 THEN '5% to 10%'
      WHEN tip_pct <= 15 THEN '10% to 15%'
      WHEN tip_pct <= 20 THEN '15% to 20%'
      WHEN tip_pct <= 25 THEN '20% to 25%'
      ELSE 'More than 25%'
    END AS tip_category,
    COUNT(*) AS trip_count
  FROM tip_categorized
  GROUP BY pickup_borough, tip_category
),
borough_totals AS (
  SELECT
    pickup_borough,
    SUM(trip_count) AS total_trips
  FROM category_counts
  GROUP BY pickup_borough
)
SELECT
  c.pickup_borough,
  c.tip_category,
  c.trip_count,
  ROUND(c.trip_count / b.total_trips, 4) AS proportion
FROM category_counts c
JOIN borough_totals b ON c.pickup_borough = b.pickup_borough
ORDER BY c.pickup_borough, c.tip_category;
```

---

## 25. Instance: `bq041`
**Question:**
> Compute the monthly statistics for new StackOverflow users created in 2021. For each month, report the total number of new users, the percentage of these new users who asked at least one question within 30 days of signing up, and among those who asked a question within 30 days, the percentage who then answered at least one question after their first question and within 30 days following their first question.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Select users created in 2021 and extract the month
WITH users_2021 AS (
  SELECT
    id AS user_id,
    creation_date,
    EXTRACT(MONTH FROM creation_date) AS signup_month
  FROM `bigquery-public-data.stackoverflow.users`
  WHERE EXTRACT(YEAR FROM creation_date) = 2021
),

-- Step 2: For each user, find the first question within 30 days of signup
first_question AS (
  SELECT
    u.user_id,
    MIN(q.creation_date) AS first_question_date
  FROM users_2021 u
  LEFT JOIN `bigquery-public-data.stackoverflow.posts_questions` q
    ON q.owner_user_id = u.user_id
    AND q.creation_date BETWEEN u.creation_date
        AND TIMESTAMP_ADD(u.creation_date, INTERVAL 30 DAY)
  GROUP BY u.user_id
),

-- Step 3: Users who asked at least one question within 30 days (askers)
askers AS (
  SELECT
    user_id,
    first_question_date,
    signup_month
  FROM users_2021 u
  JOIN first_question fq USING (user_id)
  WHERE fq.first_question_date IS NOT NULL
),

-- Step 4: Among askers, find those who answered a question after their first question
-- and within 30 days after that first question
askers_with_answer AS (
  SELECT DISTINCT
    a.user_id,
    a.signup_month
  FROM askers a
  JOIN `bigquery-public-data.stackoverflow.posts_answers` ans
    ON ans.owner_user_id = a.user_id
    AND ans.creation_date > a.first_question_date
    AND ans.creation_date <= TIMESTAMP_ADD(a.first_question_date, INTERVAL 30 DAY)
)

-- Step 5: Aggregate by month and compute percentages
SELECT
  u.signup_month AS month,
  COUNT(u.user_id) AS total_new_users,
  ROUND(100.0 * COUNT(DISTINCT a.user_id) / COUNT(u.user_id), 4) AS percentage_asked,
  ROUND(
    100.0 * COUNT(DISTINCT awa.user_id) / NULLIF(COUNT(DISTINCT a.user_id), 0),
    4
  ) AS percentage_answered_among_askers
FROM users_2021 u
LEFT JOIN askers a ON u.user_id = a.user_id
LEFT JOIN askers_with_answer awa ON u.user_id = awa.user_id
GROUP BY u.signup_month
ORDER BY u.signup_month;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Compute monthly statistics for new StackOverflow users created in 2021.
-- For each month, report:
-- 1) total number of new users (creation_date in that month)
-- 2) percentage of those who asked at least one question within 30 days of signup
-- 3) among those who asked a question within 30 days, percentage who later answered
--    at least one question after their first question and within 30 days of that first question.

WITH
-- Step 1: Get all new users created in 2021 and extract their creation month.
users_2021 AS (
  SELECT
    id,
    creation_date,
    EXTRACT(MONTH FROM creation_date) AS month
  FROM `bigquery-public-data.stackoverflow.users`
  WHERE creation_date >= '2021-01-01'
    AND creation_date < '2022-01-01'
),

-- Step 2: Identify users who asked at least one question within 30 days of signing up.
users_with_questions AS (
  SELECT DISTINCT
    u.id,
    u.month
  FROM users_2021 u
  INNER JOIN `bigquery-public-data.stackoverflow.posts_questions` q
    ON u.id = q.owner_user_id
  WHERE q.creation_date >= u.creation_date
    AND q.creation_date <= TIMESTAMP_ADD(u.creation_date, INTERVAL 30 DAY)
),

-- Step 3: For each user who asked a question within 30 days, find their first question date.
first_question_dates AS (
  SELECT
    u.id,
    u.month,
    MIN(q.creation_date) AS first_question_date
  FROM users_2021 u
  INNER JOIN `bigquery-public-data.stackoverflow.posts_questions` q
    ON u.id = q.owner_user_id
  WHERE q.creation_date >= u.creation_date
    AND q.creation_date <= TIMESTAMP_ADD(u.creation_date, INTERVAL 30 DAY)
  GROUP BY u.id, u.month
),

-- Step 4: Among those with a first question, identify those who answered at least one question
--         after that first question and within 30 days of it.
users_who_answered_after_first_q AS (
  SELECT DISTINCT
    f.id,
    f.month
  FROM first_question_dates f
  INNER JOIN `bigquery-public-data.stackoverflow.posts_answers` a
    ON f.id = a.owner_user_id
  WHERE a.creation_date > f.first_question_date
    AND a.creation_date <= TIMESTAMP_ADD(f.first_question_date, INTERVAL 30 DAY)
)

-- Step 5: Aggregate by month to compute the requested metrics.
SELECT
  u.month,
  COUNT(DISTINCT u.id) AS total_new_users,
  ROUND(
    COUNT(DISTINCT uq.id) * 100.0 / COUNT(DISTINCT u.id),
    4
  ) AS pct_asked_within_30,
  ROUND(
    COUNT(DISTINCT ua.id) * 100.0 / NULLIF(COUNT(DISTINCT uq.id), 0),
    4
  ) AS pct_answered_after_first_q_within_30
FROM users_2021 u
LEFT JOIN users_with_questions uq
  ON u.id = uq.id
LEFT JOIN users_who_answered_after_first_q ua
  ON u.id = ua.id
GROUP BY u.month
ORDER BY u.month;
```

---

## 26. Instance: `bq042`
**Question:**
> Can you help me retrieve the average temperature, average wind speed, and precipitation for LaGuardia Airport in NYC on June 12 for each year from 2011 through 2020, specifically using the station ID 725030?

### 🏆 Gold Reference Answer
```sql
SELECT
  -- Create a timestamp from the date components.
  TIMESTAMP(CONCAT(year,"-",mo,"-",da)) AS timestamp,
  -- Replace numerical null values with actual null
  AVG(IF (temp=9999.9,
      null,
      temp)) AS temperature,
  AVG(IF (wdsp="999.9",
      null,
      CAST(wdsp AS Float64))) AS wind_speed,
  AVG(IF (prcp=99.99,
      0,
      prcp)) AS precipitation
FROM
  `bigquery-public-data.noaa_gsod.gsod20*`
WHERE
  CAST(YEAR AS INT64) > 2010
  AND CAST(YEAR AS INT64) < 2021
  AND CAST(MO AS INT64) = 6
  AND CAST(DA AS INT64) = 12
  AND stn = "725030" -- La Guardia
GROUP BY
  timestamp
ORDER BY
  timestamp ASC;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH weather_data AS (
  SELECT
    _TABLE_SUFFIX AS year_str,
    SAFE_CAST(temp AS FLOAT64) AS avg_temperature,
    SAFE_CAST(wdsp AS FLOAT64) AS avg_wind_speed,
    SAFE_CAST(prcp AS FLOAT64) AS precipitation
  FROM
    `bigquery-public-data.noaa_gsod.gsod*`
  WHERE
    _TABLE_SUFFIX BETWEEN '2011' AND '2020'
    AND stn = '725030'
    AND mo = '06'
    AND da = '12'
    AND SAFE_CAST(temp AS FLOAT64) IS NOT NULL
    AND SAFE_CAST(wdsp AS FLOAT64) IS NOT NULL
    AND SAFE_CAST(prcp AS FLOAT64) IS NOT NULL
)
SELECT
  year_str AS year,
  ROUND(avg_temperature, 4) AS avg_temperature,
  ROUND(avg_wind_speed, 4) AS avg_wind_speed,
  ROUND(precipitation, 4) AS precipitation
FROM
  weather_data
ORDER BY
  year_str;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Query to retrieve average temperature, average wind speed, and precipitation
-- for LaGuardia Airport (station ID 725030) on June 12 for each year from 2011 to 2020.
-- Uses the NOAA GSOD wildcard table and filters by station, month, and day.
-- Casts wdsp (string) to float64 and excludes missing values.

SELECT
  -- Extract year from the date column (or use the 'year' column if 'date' is not available)
  EXTRACT(YEAR FROM date) AS year,  
  temp AS average_temperature,               -- daily average temperature in Fahrenheit
  SAFE_CAST(wdsp AS FLOAT64) AS average_wind_speed,  -- daily mean wind speed in knots
  prcp AS precipitation                      -- daily precipitation in inches
FROM
  `bigquery-public-data.noaa_gsod.gsod*`
WHERE
  -- Restrict to years 2011–2020 using the table suffix
  _TABLE_SUFFIX BETWEEN '2011' AND '2020'
  -- Filter for LaGuardia Airport station ID
  AND stn = '725030'
  -- Filter for June 12 (month=6, day=12)
  AND EXTRACT(MONTH FROM date) = 6
  AND EXTRACT(DAY FROM date) = 12
  -- Exclude missing values
  AND temp != 9999.9
  AND SAFE_CAST(wdsp AS FLOAT64) != 999.9
  AND prcp != 99.99
ORDER BY
  year;
```

---

## 27. Instance: `bq045`
**Question:**
> Which weather stations in Washington State recorded more than 150 rainy days in 2023 but fewer rainy days compared to 2022? Defining a “rainy day” as one having precipitation greater than zero millimeters and not equal to 99.99. Only include stations with valid precipitation data.

### 🏆 Gold Reference Answer
```sql
WITH WashingtonStations2023 AS 
    (
        SELECT 
            weather.stn AS station_id,
            ANY_VALUE(station.name) AS name
        FROM
            `bigquery-public-data.noaa_gsod.stations` AS station
        INNER JOIN
            `bigquery-public-data.noaa_gsod.gsod2023` AS weather
        ON
            station.usaf = weather.stn
        WHERE
            station.state = 'WA' 
            AND 
            station.usaf != '999999'
        GROUP BY
            station_id
    ),
prcp2023 AS (
SELECT
    washington_stations.name,
    (
        SELECT 
            COUNT(*)
        FROM
            `bigquery-public-data.noaa_gsod.gsod2023` AS weather
        WHERE
            washington_stations.station_id = weather.stn
            AND
            prcp > 0
            AND
            prcp !=99.99
    )
    AS rainy_days
FROM 
    WashingtonStations2023 AS washington_stations
ORDER BY
    rainy_days DESC
),
WashingtonStations2022 AS 
    (
        SELECT 
            weather.stn AS station_id,
            ANY_VALUE(station.name) AS name
        FROM
            `bigquery-public-data.noaa_gsod.stations` AS station
        INNER JOIN
            `bigquery-public-data.noaa_gsod.gsod2022` AS weather
        ON
            station.usaf = weather.stn
        WHERE
            station.state = 'WA' 
            AND 
            station.usaf != '999999'
        GROUP BY
            station_id
    ),
prcp2022 AS (
SELECT
    washington_stations.name,
    (
        SELECT 
            COUNT(*)
        FROM
            `bigquery-public-data.noaa_gsod.gsod2022` AS weather
        WHERE
            washington_stations.station_id = weather.stn
            AND
            prcp > 0
            AND
            prcp != 99.99
    )
    AS rainy_days
FROM 
    WashingtonStations2022 AS washington_stations
ORDER BY
    rainy_days DESC
)

SELECT prcp2023.name
FROM prcp2023
JOIN prcp2022
on prcp2023.name = prcp2022.name
WHERE prcp2023.rainy_days > 150
AND prcp2023.rainy_days < prcp2022.rainy_days
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Get Washington State stations
washington_stations AS (
  SELECT usaf, wban, name
  FROM `bigquery-public-data.noaa_gsod.stations`
  WHERE state = 'WA'
),

-- Count rainy days per station in 2022
rainy_days_2022 AS (
  SELECT 
    s.stn AS usaf,
    s.wban,
    COUNT(*) AS rainy_days_2022
  FROM `bigquery-public-data.noaa_gsod.gsod2022` s
  INNER JOIN washington_stations ws
    ON s.stn = ws.usaf AND s.wban = ws.wban
  WHERE s.prcp IS NOT NULL 
    AND SAFE_CAST(s.prcp AS FLOAT64) > 0 
    AND SAFE_CAST(s.prcp AS FLOAT64) != 99.99
  GROUP BY s.stn, s.wban
),

-- Count rainy days per station in 2023
rainy_days_2023 AS (
  SELECT 
    s.stn AS usaf,
    s.wban,
    COUNT(*) AS rainy_days_2023
  FROM `bigquery-public-data.noaa_gsod.gsod2023` s
  INNER JOIN washington_stations ws
    ON s.stn = ws.usaf AND s.wban = ws.wban
  WHERE s.prcp IS NOT NULL 
    AND SAFE_CAST(s.prcp AS FLOAT64) > 0 
    AND SAFE_CAST(s.prcp AS FLOAT64) != 99.99
  GROUP BY s.stn, s.wban
)

-- Final selection: stations with >150 rainy days in 2023 and fewer than 2022
SELECT 
  ws.usaf,
  ws.wban,
  ws.name,
  COALESCE(r22.rainy_days_2022, 0) AS rainy_days_2022,
  r23.rainy_days_2023
FROM washington_stations ws
INNER JOIN rainy_days_2023 r23
  ON ws.usaf = r23.usaf AND ws.wban = r23.wban
LEFT JOIN rainy_days_2022 r22
  ON ws.usaf = r22.usaf AND ws.wban = r22.wban
WHERE r23.rainy_days_2023 > 150
  AND (COALESCE(r22.rainy_days_2022, 0) > r23.rainy_days_2023)
ORDER BY ws.name;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH wa_stations AS (
  SELECT usaf AS stn, wban, name
  FROM `bigquery-public-data.noaa_gsod.stations`
  WHERE state = 'WA'
),

rainy_2023 AS (
  SELECT stn, wban, COUNT(*) AS rainy_days_2023
  FROM `bigquery-public-data.noaa_gsod.gsod2023`
  WHERE prcp > 0 AND prcp != 99.99
  GROUP BY stn, wban
),

rainy_2022 AS (
  SELECT stn, wban, COUNT(*) AS rainy_days_2022
  FROM `bigquery-public-data.noaa_gsod.gsod2022`
  WHERE prcp > 0 AND prcp != 99.99
  GROUP BY stn, wban
)

SELECT
  s.name AS station_name,
  s.stn AS station_id,
  r23.rainy_days_2023,
  r22.rainy_days_2022
FROM wa_stations s
JOIN rainy_2023 r23
  ON s.stn = r23.stn AND s.wban = r23.wban
JOIN rainy_2022 r22
  ON s.stn = r22.stn AND s.wban = r22.wban
WHERE r23.rainy_days_2023 > 150
  AND r23.rainy_days_2023 < r22.rainy_days_2022
ORDER BY station_name;
```

---

## 28. Instance: `bq046`
**Question:**
> Find case barcodes and their corresponding GDC file URLs for female patients aged 30 or younger diagnosed with breast cancer (BRCA) in TCGA database. The query should first identify patients from the Annotations table where entity_type is "Patient" and either category is "History of unacceptable prior treatment related to a prior/other malignancy" or classification is "Redaction". Also identify patients from the Clinical table with disease_code "BRCA", age_at_diagnosis less than or equal to 30, and gender "FEMALE". Perform a FULL JOIN between these two sets, but only keep patients where both categoryName and classificationName are NULL in the final result. Use GDC metadata from archive release 14 (specifically rel14_caseData, rel14_fileData_current, and rel14_GDCfileID_to_GCSurl_NEW tables) to get the corresponding file URLs. 

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
-- Patients with annotations that should exclude them
excluded_patients AS (
  SELECT DISTINCT project_short_name
  FROM `isb-cgc.TCGA_bioclin_v0.Annotations`
  WHERE entity_type = 'Patient'
    AND (
      category = 'History of unacceptable prior treatment related to a prior/other malignancy'
      OR classification = 'Redaction'
    )
),

-- Target clinical cohort: female, BRCA, age <= 30
clinical_target AS (
  SELECT 
    project_short_name,
    days_to_birth,
    gender
  FROM `isb-cgc.TCGA_bioclin_v0.Clinical`
  WHERE project_short_name = 'TCGA-BRCA'
    AND gender = 'FEMALE'
    AND days_to_birth IS NOT NULL
    AND days_to_birth >= -30 * 365  -- age at diagnosis <= 30 years
),

-- FULL JOIN: keep patients present in clinical_target but NOT in excluded_patients
valid_projects AS (
  SELECT c.project_short_name
  FROM clinical_target c
  FULL JOIN excluded_patients e
    ON c.project_short_name = e.project_short_name
  WHERE e.project_short_name IS NULL
)

-- Get file URLs for these patients using GDC metadata
SELECT DISTINCT
  cd.submitter_id AS case_barcode,
  url.file_gdc_url AS gdc_file_url
FROM valid_projects vp
INNER JOIN `isb-cgc.GDC_metadata.rel14_caseData` cd
  ON cd.project__project_id = 'TCGA-BRCA'
INNER JOIN `isb-cgc.GDC_metadata.rel14_fileData_current` fd
  ON fd.cases__project__project_id = cd.project__project_id
INNER JOIN `isb-cgc.GDC_metadata.rel14_GDCfileID_to_GCSurl_NEW` url
  ON url.file_gdc_url LIKE CONCAT('%', fd.file_id, '%')
WHERE cd.project__project_id = 'TCGA-BRCA';
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Identify eligible female BRCA patients aged <= 30 from Clinical table
WITH clinical_eligible AS (
    SELECT
        case_gdc_id,
        case_barcode
    FROM `isb-cgc.TCGA_bioclin_v0.Clinical`
    WHERE disease_code = 'BRCA'
      AND age_at_diagnosis <= 30
      AND gender = 'FEMALE'
),

-- Step 2: Identify patients with specific annotations from Annotations table
annotation_candidates AS (
    SELECT
        case_gdc_id,
        category,
        classification
    FROM `isb-cgc.TCGA_bioclin_v0.Annotations`
    WHERE entity_type = 'Patient'
      AND (category = 'History of unacceptable prior treatment related to a prior/other malignancy'
           OR classification = 'Redaction')
),

-- Step 3: FULL JOIN and keep only patients without such annotations (both category and classification are NULL)
eligible_patients AS (
    SELECT
        COALESCE(c.case_gdc_id, a.case_gdc_id) AS case_gdc_id,
        c.case_barcode
    FROM clinical_eligible c
    FULL JOIN annotation_candidates a
        ON c.case_gdc_id = a.case_gdc_id
    WHERE a.category IS NULL
      AND a.classification IS NULL
      AND c.case_gdc_id IS NOT NULL
),

-- Step 4: Get file URLs for the eligible cases using release 14 metadata
files AS (
    SELECT
        cd.case_gdc_id,
        cd.case_barcode,
        fd.file_gdc_id,
        gu.file_gdc_url   -- corrected column name based on naming convention
    FROM `isb-cgc.GDC_metadata.rel14_caseData` cd
    INNER JOIN `isb-cgc.GDC_metadata.rel14_fileData_current` fd
        ON cd.case_gdc_id = fd.case_gdc_id
    INNER JOIN `isb-cgc.GDC_metadata.rel14_GDCfileID_to_GCSurl_NEW` gu
        ON fd.file_gdc_id = gu.file_gdc_id
)

-- Final output: case barcode and file URL
SELECT
    f.case_barcode,
    f.file_gdc_url AS file_url
FROM files f
INNER JOIN eligible_patients ep
    ON f.case_gdc_id = ep.case_gdc_id;
```

---

## 29. Instance: `bq047`
**Question:**
> Could you analyze the relationship between each complaint type and daily temperature in New York City, specifically using temperature data from LaGuardia (STN=725030) and JFK (STN=744860) airports for the 10 years starting in 2008, and then determine, for each complaint type that has more than 5000 total occurrences and shows a strong correlation (absolute value > 0.5) with temperature, the total number of complaints, the total number of days with valid temperature records, and the Pearson correlation coefficients (rounded to four decimals) between temperature and both the daily complaint count as well as the daily percentage of total complaints, excluding any days with missing or invalid temperature data (such as 9999.9)?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
  -- 1. Collect daily temperature data from LaGuardia and JFK stations (2008-2017)
  daily_temps AS (
    SELECT
      DATE(PARSE_DATE('%Y%m%d', year || mo || da)) AS date,
      stn,
      SAFE_CAST(temp AS FLOAT64) AS temp
    FROM (
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2008`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2009`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2010`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2011`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2012`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2013`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2014`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2015`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2016`
      UNION ALL
      SELECT stn, year, mo, da, temp FROM `bigquery-public-data.noaa_gsod.gsod2017`
    )
    WHERE stn IN ('725030', '744860')  -- LaGuardia and JFK
      AND SAFE_CAST(temp AS FLOAT64) IS NOT NULL
      AND SAFE_CAST(temp AS FLOAT64) != 9999.9
  ),

  -- 2. Aggregate temperatures by date (average of both stations if both available)
  daily_nyc_temp AS (
    SELECT
      date,
      AVG(temp) AS avg_temp
    FROM daily_temps
    GROUP BY date
    HAVING COUNT(*) > 0  -- at least one valid reading
  ),

  -- 3. Daily 311 complaint data for NYC (2008-2017)
  daily_complaints AS (
    SELECT
      DATE(created_date) AS date,
      complaint_type,
      COUNT(*) AS daily_count
    FROM `bigquery-public-data.new_york.311_service_requests`
    WHERE DATE(created_date) BETWEEN '2008-01-01' AND '2017-12-31'
      AND complaint_type IS NOT NULL
    GROUP BY date, complaint_type
  ),

  -- 4. Join temperature and complaints, calculate daily percentages
  daily_combined AS (
    SELECT
      d.date,
      d.complaint_type,
      d.daily_count,
      t.avg_temp,
      SUM(d.daily_count) OVER (PARTITION BY d.date) AS total_complaints_day
    FROM daily_complaints d
    INNER JOIN daily_nyc_temp t ON d.date = t.date
  ),

  -- 5. Per-type aggregations: total count, valid days, and correlation components
  type_stats AS (
    SELECT
      complaint_type,
      COUNT(*) AS num_days,
      SUM(daily_count) AS total_complaints,
      -- Pearson correlation components for daily_count vs temp
      COUNT(*) AS n,
      SUM(daily_count) AS sum_x,
      SUM(avg_temp) AS sum_y,
      SUM(daily_count * avg_temp) AS sum_xy,
      SUM(daily_count * daily_count) AS sum_x2,
      SUM(avg_temp * avg_temp) AS sum_y2,
      -- For percentage: daily_count / total_complaints_day * 100
      SUM(daily_count * 100.0 / total_complaints_day) AS sum_pct_x,
      SUM(avg_temp * daily_count * 100.0 / total_complaints_day) AS sum_pct_xy,
      SUM((daily_count * 100.0 / total_complaints_day) * (daily_count * 100.0 / total_complaints_day)) AS sum_pct_x2
    FROM daily_combined
    GROUP BY complaint_type
    HAVING SUM(daily_count) > 5000
  ),

  -- 6. Calculate Pearson r for count and percentage
  correlations AS (
    SELECT
      complaint_type,
      total_complaints,
      num_days,
      -- Pearson r for daily count vs temperature
      ROUND(
        (n * sum_xy - sum_x * sum_y) / 
        SQRT((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)),
        4
      ) AS corr_count_temp,
      -- Pearson r for daily percentage vs temperature
      ROUND(
        (n * sum_pct_xy - sum_pct_x * sum_y) / 
        SQRT((n * sum_pct_x2 - sum_pct_x * sum_pct_x) * (n * sum_y2 - sum_y * sum_y)),
        4
      ) AS corr_pct_temp
    FROM type_stats
  )

-- 7. Filter: keep types where |correlation| > 0.5 (for count or percentage)
SELECT
  complaint_type,
  total_complaints,
  num_days AS valid_temp_days,
  corr_count_temp,
  corr_pct_temp
FROM correlations
WHERE ABS(corr_count_temp) > 0.5
   OR ABS(corr_pct_temp) > 0.5
ORDER BY total_complaints DESC;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
-- Get daily average temperature from LaGuardia (STN=725030) and JFK (STN=744860)
daily_temps AS (
    SELECT
        PARSE_DATE('%Y%m%d', year || mo || da) AS date,
        AVG(temp) AS avg_temp
    FROM `bigquery-public-data.noaa_gsod.gsod*`
    WHERE _TABLE_SUFFIX BETWEEN '2008' AND '2017'
        AND (stn = '725030' OR stn = '744860')
        AND temp != 9999.9
    GROUP BY date
),

-- Daily complaint counts per complaint type
daily_complaints AS (
    SELECT
        DATE(created_date) AS date,
        complaint_type,
        COUNT(*) AS daily_count
    FROM `bigquery-public-data.new_york.311_service_requests`
    WHERE DATE(created_date) BETWEEN '2008-01-01' AND '2017-12-31'
    GROUP BY date, complaint_type
),

-- Daily total complaints (needed for percentage)
total_daily_complaints AS (
    SELECT
        DATE(created_date) AS date,
        COUNT(*) AS total_count
    FROM `bigquery-public-data.new_york.311_service_requests`
    WHERE DATE(created_date) BETWEEN '2008-01-01' AND '2017-12-31'
    GROUP BY date
),

-- Join temperature with complaints
joined_data AS (
    SELECT
        t.date,
        d.complaint_type,
        d.daily_count,
        t.avg_temp,
        td.total_count,
        SAFE_DIVIDE(CAST(d.daily_count AS FLOAT64), td.total_count) AS daily_pct
    FROM daily_temps t
    INNER JOIN daily_complaints d ON t.date = d.date
    INNER JOIN total_daily_complaints td ON t.date = d.date
),

-- Compute Pearson correlation coefficients per complaint type
type_aggregates AS (
    SELECT
        complaint_type,
        COUNT(*) AS days_with_valid_temp,
        SUM(daily_count) AS total_complaints,

        -- Pearson correlation: avg_temp vs daily_count (use FLOAT64 to avoid overflow)
        ROUND(
            IFNULL(
                (CAST(COUNT(*) AS FLOAT64) * SUM(CAST(avg_temp AS FLOAT64) * CAST(daily_count AS FLOAT64))
                 - SUM(CAST(avg_temp AS FLOAT64)) * SUM(CAST(daily_count AS FLOAT64)))
                / NULLIF(SQRT(
                    (CAST(COUNT(*) AS FLOAT64) * SUM(CAST(avg_temp AS FLOAT64) * CAST(avg_temp AS FLOAT64))
                     - SUM(CAST(avg_temp AS FLOAT64)) * SUM(CAST(avg_temp AS FLOAT64)))
                    * (CAST(COUNT(*) AS FLOAT64) * SUM(CAST(daily_count AS FLOAT64) * CAST(daily_count AS FLOAT64))
                       - SUM(CAST(daily_count AS FLOAT64)) * SUM(CAST(daily_count AS FLOAT64)))
                ), 0),
                NULL
            ),
            4
        ) AS corr_temp_daily_count,

        -- Pearson correlation: avg_temp vs daily_pct
        ROUND(
            IFNULL(
                (CAST(COUNT(*) AS FLOAT64) * SUM(CAST(avg_temp AS FLOAT64) * CAST(daily_pct AS FLOAT64))
                 - SUM(CAST(avg_temp AS FLOAT64)) * SUM(CAST(daily_pct AS FLOAT64)))
                / NULLIF(SQRT(
                    (CAST(COUNT(*) AS FLOAT64) * SUM(CAST(avg_temp AS FLOAT64) * CAST(avg_temp AS FLOAT64))
                     - SUM(CAST(avg_temp AS FLOAT64)) * SUM(CAST(avg_temp AS FLOAT64)))
                    * (CAST(COUNT(*) AS FLOAT64) * SUM(CAST(daily_pct AS FLOAT64) * CAST(daily_pct AS FLOAT64))
                       - SUM(CAST(daily_pct AS FLOAT64)) * SUM(CAST(daily_pct AS FLOAT64)))
                ), 0),
                NULL
            ),
            4
        ) AS corr_temp_daily_pct
    FROM joined_data
    GROUP BY complaint_type
    HAVING total_complaints > 5000
)

-- Final selection: only complaint types with strong correlation (>0.5 absolute)
SELECT
    complaint_type,
    total_complaints,
    days_with_valid_temp,
    corr_temp_daily_count,
    corr_temp_daily_pct
FROM type_aggregates
WHERE ABS(corr_temp_daily_count) > 0.5
ORDER BY total_complaints DESC;
```

---

## 30. Instance: `bq048`
**Question:**
> Which complaint types with more than 3000 total requests from 2011 to 2020 show the strongest positive and negative Pearson correlations with the daily average wind speed measured at station 744860 (JFK Airport), based on daily complaint proportions (the ratio of type-specific complaints to total daily complaints)? Please provide the complaint types and their correlation coefficients, rounded to four decimal places.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Identify the correct column name for wind speed in gsod tables
-- The gsod tables have a field called 'wdsp' which is the wind speed

WITH
-- Daily complaint counts by type
daily_complaints AS (
  SELECT
    DATE(created_date) AS dt,
    complaint_type,
    COUNT(*) AS cnt
  FROM `bigquery-public-data.new_york.311_service_requests`
  WHERE EXTRACT(YEAR FROM created_date) BETWEEN 2011 AND 2020
  GROUP BY dt, complaint_type
),

-- Total daily complaints
daily_totals AS (
  SELECT
    dt,
    SUM(cnt) AS total_complaints
  FROM daily_complaints
  GROUP BY dt
),

-- Daily proportion per type
daily_proportions AS (
  SELECT
    d.dt,
    d.complaint_type,
    SAFE_DIVIDE(d.cnt, t.total_complaints) AS proportion
  FROM daily_complaints d
  INNER JOIN daily_totals t ON d.dt = t.dt
),

-- Complaint types with >3000 total requests
type_totals AS (
  SELECT
    complaint_type,
    SUM(cnt) AS total_requests
  FROM daily_complaints
  GROUP BY complaint_type
  HAVING total_requests > 3000
),

-- Daily average wind speed at JFK (station 744860)
-- Use wdsp column which is the wind speed in knots
wind_data AS (
  SELECT
    PARSE_DATE('%Y%m%d', CONCAT(year, mo, da)) AS dt,
    AVG(SAFE_CAST(wdsp AS FLOAT64)) AS avg_wind_speed
  FROM `bigquery-public-data.noaa_gsod.gsod*`
  WHERE _TABLE_SUFFIX BETWEEN '2011' AND '2020'
    AND stn = '744860'
    AND wdsp != '999.9'
    AND wdsp IS NOT NULL
  GROUP BY dt
)

-- Compute Pearson correlation per complaint type
SELECT
  dp.complaint_type,
  ROUND(CORR(dp.proportion, wd.avg_wind_speed), 4) AS correlation_coefficient
FROM daily_proportions dp
INNER JOIN type_totals tt ON dp.complaint_type = tt.complaint_type
INNER JOIN wind_data wd ON dp.dt = wd.dt
GROUP BY dp.complaint_type
ORDER BY ABS(CORR(dp.proportion, wd.avg_wind_speed)) DESC
LIMIT 20;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Step 1: Get daily complaint counts by type for 2011-2020
daily_complaints AS (
    SELECT 
        DATE(created_date) AS complaint_date,
        complaint_type,
        COUNT(*) AS daily_type_count
    FROM `bigquery-public-data.new_york.311_service_requests`
    WHERE EXTRACT(YEAR FROM created_date) BETWEEN 2011 AND 2020
      AND complaint_type IS NOT NULL
    GROUP BY complaint_date, complaint_type
),

-- Step 2: Calculate total daily complaints
daily_totals AS (
    SELECT 
        complaint_date,
        SUM(daily_type_count) AS total_daily_complaints
    FROM daily_complaints
    GROUP BY complaint_date
),

-- Step 3: Calculate daily proportions
daily_proportions AS (
    SELECT 
        d.complaint_date,
        d.complaint_type,
        d.daily_type_count / t.total_daily_complaints AS proportion
    FROM daily_complaints d
    JOIN daily_totals t ON d.complaint_date = t.complaint_date
),

-- Step 4: Filter complaint types with total > 3000
type_totals AS (
    SELECT 
        complaint_type,
        SUM(daily_type_count) AS total_count
    FROM daily_complaints
    GROUP BY complaint_type
    HAVING SUM(daily_type_count) > 3000
),

-- Step 5: Get daily wind speed for JFK (stn = '744860')
wind_speed AS (
    SELECT 
        PARSE_DATE('%Y%m%d', CONCAT(year, mo, da)) AS weather_date,
        SAFE_CAST(wdsp AS FLOAT64) AS avg_wind_speed
    FROM `bigquery-public-data.noaa_gsod.gsod*`
    WHERE _TABLE_SUFFIX BETWEEN '2011' AND '2020'
      AND stn = '744860'
      AND SAFE_CAST(wdsp AS FLOAT64) < 900
),

-- Step 6: Join proportions with wind speed
joined_data AS (
    SELECT 
        dp.complaint_type,
        dp.proportion,
        ws.avg_wind_speed
    FROM daily_proportions dp
    JOIN wind_speed ws ON dp.complaint_date = ws.weather_date
    JOIN type_totals tt ON dp.complaint_type = tt.complaint_type
)

-- Step 7: Calculate Pearson correlation coefficient
SELECT 
    complaint_type,
    ROUND(
        (COUNT(*) * SUM(proportion * avg_wind_speed) - SUM(proportion) * SUM(avg_wind_speed)) /
        SQRT(
            (COUNT(*) * SUM(proportion * proportion) - SUM(proportion) * SUM(proportion)) *
            (COUNT(*) * SUM(avg_wind_speed * avg_wind_speed) - SUM(avg_wind_speed) * SUM(avg_wind_speed))
        ),
        4
    ) AS correlation_coefficient
FROM joined_data
GROUP BY complaint_type
ORDER BY correlation_coefficient ASC;
```

---

## 31. Instance: `bq049`
**Question:**
> Please show the monthly per capita Bourbon Whiskey sales during 2022 in Dubuque County for the zip code that ranks third in total Bourbon Whiskey sales, using only the population aged 21 and older.

### 🏆 Gold Reference Answer
```sql
WITH DUBUQUE_LIQUOR_CTE AS (
SELECT
  CASE
      WHEN UPPER(category_name) LIKE 'BUTTERSCOTCH SCHNAPPS' THEN 'All Other' --Edge case is not a scotch
      WHEN UPPER(category_name) LIKE '%WHISKIES' 
            AND UPPER(category_name) NOT LIKE '%RYE%'
            AND UPPER(category_name) NOT LIKE '%BOURBON%'
            AND UPPER(category_name) NOT LIKE '%SCOTCH%'     THEN 'Other Whiskey'
      WHEN UPPER(category_name) LIKE '%RYE%'                 THEN 'Rye Whiskey'
      WHEN UPPER(category_name) LIKE '%BOURBON%'             THEN 'Bourbon Whiskey'
      WHEN UPPER(category_name) LIKE '%SCOTCH%'              THEN 'Scotch Whiskey'
      ELSE 'All Other'
  END                              AS category_group,
  EXTRACT(MONTH FROM date)         AS month,    -- At the time of this query, there is only data until month 6.
  LEFT(CAST(zip_code AS string),5) AS zip_code, -- Casting to string necessary because zip_code has a mix of int & str types.
  ROUND(SUM(sale_dollars), 2)      AS sale_dollars_sum,

FROM 
  bigquery-public-data.iowa_liquor_sales.sales

WHERE
  UPPER(county)               = 'DUBUQUE'
  AND EXTRACT(YEAR FROM date) = 2022

GROUP BY
  category_group,
  month,
  zip_code
  
ORDER BY 
  category_group,
  month,
  zip_code
),

DUBUQUE_POPULATION_CTE AS (
SELECT
  zipcode,
  SUM(population) AS population_sum
FROM bigquery-public-data.census_bureau_usa.population_by_zip_2010
WHERE 
  minimum_age >= 21
GROUP BY 
  zipcode
),
MONTH_INFO AS (
SELECT 
  l.month,
  l.zip_code,
  l.sale_dollars_sum,
  ROUND(sale_dollars_sum/p.population_sum, 2) AS dollars_per_capita
FROM 
  DUBUQUE_LIQUOR_CTE AS l
  LEFT JOIN 
  DUBUQUE_POPULATION_CTE AS p
  ON l.zip_code = p.zipcode
WHERE
  category_group = 'Bourbon Whiskey'
GROUP BY 
  category_group,
  zip_code,
  month,
  sale_dollars_sum,
  zipcode,
  population_sum
ORDER BY
  zip_code,
  month
),
zip_code_sales AS (
    SELECT
        zip_code,
        SUM(sale_dollars_sum) AS total_sale_dollars_sum
    FROM MONTH_INFO
    GROUP BY zip_code
),
ranked_zip_codes AS (
    SELECT
        zip_code,
        total_sale_dollars_sum,
        ROW_NUMBER() OVER (ORDER BY total_sale_dollars_sum DESC) AS rank
    FROM zip_code_sales
)
SELECT
    t.month,
    t.zip_code,
    t.dollars_per_capita
FROM MONTH_INFO t
JOIN ranked_zip_codes r
ON t.zip_code = r.zip_code
WHERE r.rank = 3
ORDER BY t.month;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- This query computes monthly per capita Bourbon Whiskey sales during 2022
-- in Dubuque County for the zip code that ranks third in total sales.
-- Population used is only those aged 21 and older.

WITH 
-- Step 1: Isolate Bourbon Whiskey sales in Dubuque County for 2022
bourbon_sales_2022 AS (
  SELECT
    zip_code,
    date,
    sale_dollars
  FROM `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE EXTRACT(YEAR FROM date) = 2022
    AND LOWER(county) = 'dubuque'                  -- filter for Dubuque County
    AND category_name = 'BOURBON WHISKEY'          -- exact product category
),

-- Step 2: Total sales per zip code for ranking
total_sales_by_zip AS (
  SELECT
    zip_code,
    SUM(sale_dollars) AS total_sales
  FROM bourbon_sales_2022
  GROUP BY zip_code
),

-- Step 3: Rank zip codes by total sales descending
ranked_zips AS (
  SELECT
    zip_code,
    total_sales,
    RANK() OVER (ORDER BY total_sales DESC) AS sales_rank
  FROM total_sales_by_zip
),

-- Step 4: Pick the zip code with rank 3
target_zip AS (
  SELECT zip_code
  FROM ranked_zips
  WHERE sales_rank = 3
),

-- Step 5: Monthly sales for the target zip in 2022
monthly_sales_target AS (
  SELECT
    FORMAT_DATE('%Y-%m', date) AS month,
    SUM(sale_dollars) AS monthly_sales
  FROM bourbon_sales_2022
  WHERE zip_code IN (SELECT zip_code FROM target_zip)
  GROUP BY month
),

-- Step 6: Adult population (21+) for the target zip
population_target AS (
  SELECT
    SUM(population) AS adult_population
  FROM `bigquery-public-data.census_bureau_usa.population_by_zip_2010`
  WHERE zipcode IN (SELECT zip_code FROM target_zip)
    AND age >= 21
)

-- Final: compute per capita sales per month
SELECT
  month,
  ROUND(
    monthly_sales / NULLIF(adult_population, 0),
    4
  ) AS per_capita_sales
FROM monthly_sales_target
CROSS JOIN population_target
ORDER BY month;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
-- Filter Bourbon Whiskey sales in Dubuque County for 2022
-- Use fuzzy matching on category_name to catch "Bourbon Whiskies" and similar
bourbon_sales AS (
  SELECT
    zip_code,
    sale_dollars,
    date
  FROM `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE county = 'DUBUQUE'
    AND EXTRACT(YEAR FROM date) = 2022
    AND LOWER(category_name) LIKE '%bourbon%whisk%'
),

-- Calculate total sales by zip code (only the first 5 digits) for ranking
zip_total_sales AS (
  SELECT
    REGEXP_EXTRACT(zip_code, r'^(\d+)') AS zip5,
    ROUND(SUM(sale_dollars), 4) AS total_sales
  FROM bourbon_sales
  GROUP BY zip5
),

-- Rank zip codes by total sales descending
ranked_zips AS (
  SELECT
    zip5,
    total_sales,
    ROW_NUMBER() OVER (ORDER BY total_sales DESC) AS sales_rank
  FROM zip_total_sales
),

-- Get the 3rd ranked zip code (if it exists)
target_zip AS (
  SELECT zip5
  FROM ranked_zips
  WHERE sales_rank = 3
  LIMIT 1
),

-- Get population aged 21+ from census data
-- Summing all age brackets where minimum_age >= 21
adult_population AS (
  SELECT
    zipcode,
    SUM(population) AS adult_pop
  FROM `bigquery-public-data.census_bureau_usa.population_by_zip_2010`
  WHERE minimum_age >= 21
  GROUP BY zipcode
)

-- Final query: monthly per capita sales for target zip
SELECT
  FORMAT_DATE('%Y-%m', bs.date) AS sales_month,
  ROUND(SUM(bs.sale_dollars), 4) AS monthly_sales,
  ap.adult_pop AS population_21plus,
  ROUND(SUM(bs.sale_dollars) / ap.adult_pop, 4) AS per_capita_sales
FROM bourbon_sales bs
JOIN target_zip tz
  ON REGEXP_EXTRACT(bs.zip_code, r'^(\d+)') = tz.zip5
JOIN adult_population ap
  ON tz.zip5 = ap.zipcode
GROUP BY sales_month, ap.adult_pop
ORDER BY sales_month;
```

---

## 32. Instance: `bq051`
**Question:**
> Calculate the average daily number of Citibike trips in New York City during 2016, categorizing days as rainy if the total precipitation exceeds 5 millimeters (obtained by dividing the raw precipitation value by 10), and non-rainy otherwise. Use data from the nearest GHCN station located within 50 km of (40.7128, -74.0060) that has valid, unflagged measurements, then compare the resulting average Citibike trips on rainy days versus non-rainy days.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Find the nearest GHCN station within 50 km of NYC center (40.7128, -74.0060)
-- that has PRCP measurements in 2016 and valid (unflagged) data.
WITH
  station_candidates AS (
    SELECT
      s.id,
      s.name,
      s.latitude,
      s.longitude,
      ST_DISTANCE(
        ST_GEOGPOINT(s.longitude, s.latitude),
        ST_GEOGPOINT(-74.0060, 40.7128)
      ) AS distance_m
    FROM `bigquery-public-data.ghcn_d.ghcnd_stations` s
    -- Only stations that have PRCP element and cover year 2016
    JOIN `bigquery-public-data.ghcn_d.ghcnd_inventory` inv
      ON s.id = inv.id
      AND inv.element = 'PRCP'
      AND inv.firstyear <= 2016
      AND inv.lastyear >= 2016
    WHERE
      ST_DISTANCE(
        ST_GEOGPOINT(s.longitude, s.latitude),
        ST_GEOGPOINT(-74.0060, 40.7128)
      ) <= 50000  -- 50 km in meters
  ),
  nearest_station AS (
    SELECT id, name
    FROM station_candidates
    ORDER BY distance_m ASC
    LIMIT 1
  ),
  -- Step 2: Get daily precipitation for that station in 2016 (valid, unflagged)
  daily_precip AS (
    SELECT
      g.date,
      g.value / 10.0 AS precip_mm  -- raw value is tenths of mm
    FROM `bigquery-public-data.ghcn_d.ghcnd_2016` g
    JOIN nearest_station n ON g.id = n.id
    WHERE
      g.element = 'PRCP'
      AND g.qflag IS NULL          -- valid / unflagged measurement
  ),
  -- Step 3: Count daily Citibike trips in 2016
  daily_trips AS (
    SELECT
      DATE(starttime) AS trip_date,
      COUNT(*) AS trip_count
    FROM `bigquery-public-data.new_york.citibike_trips`
    WHERE EXTRACT(YEAR FROM starttime) = 2016
    GROUP BY trip_date
  ),
  -- Step 4: Combine and classify days
  combined AS (
    SELECT
      d.trip_date,
      d.trip_count,
      CASE WHEN p.precip_mm > 5 THEN TRUE ELSE FALSE END AS rainy_day
    FROM daily_trips d
    LEFT JOIN daily_precip p ON d.trip_date = p.date
  )
-- Step 5: Compute average daily trips per category
SELECT
  rainy_day,
  ROUND(AVG(trip_count), 4) AS avg_daily_trips
FROM combined
GROUP BY rainy_day
ORDER BY rainy_day;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Calculate average daily Citibike trips in 2016, categorized by rain status.
-- Steps:
-- 1. Find the nearest GHCN station within 50 km of (40.7128, -74.0060)
--    that has valid, unflagged precipitation measurements in 2016.
-- 2. Retrieve daily precipitation (in mm) from that station.
-- 3. Count Citibike trips per day in 2016.
-- 4. Classify each day as 'Rainy' (PRCP > 5 mm) or 'Non-rainy'.
-- 5. Compute average daily trips for each category.

WITH

-- Step 1: Identify candidate stations within 50 km with valid PRCP data
stations_candidates AS (
  SELECT
    s.id AS station_id,
    s.latitude,
    s.longitude,
    -- Distance in meters from the reference point
    ST_DISTANCE(
      ST_GEOGPOINT(s.longitude, s.latitude),
      ST_GEOGPOINT(-74.0060, 40.7128)
    ) AS dist_m
  FROM
    `bigquery-public-data.ghcn_d.ghcnd_stations` s
  WHERE
    -- Keep only stations that have at least one PRCP measurement in 2016
    EXISTS (
      SELECT 1
      FROM `bigquery-public-data.ghcn_d.ghcnd_2016` d
      WHERE d.id = s.id
        AND d.element = 'PRCP'
        AND d.qflag IS NULL
    )
    -- Filter stations within 50 km
    AND ST_DISTANCE(
      ST_GEOGPOINT(s.longitude, s.latitude),
      ST_GEOGPOINT(-74.0060, 40.7128)
    ) <= 50000
),

-- Pick the nearest station (smallest distance)
nearest_station AS (
  SELECT
    station_id,
    latitude,
    longitude,
    dist_m
  FROM stations_candidates
  ORDER BY dist_m ASC
  LIMIT 1
),

-- Step 2: Daily precipitation (mm) from the selected station in 2016
daily_precip AS (
  SELECT
    d.date,
    -- GHCN precipitation values are in tenths of mm; divide by 10 to get mm
    d.value / 10.0 AS prcp_mm
  FROM `bigquery-public-data.ghcn_d.ghcnd_2016` d
  INNER JOIN nearest_station ns
    ON d.id = ns.station_id
  WHERE d.element = 'PRCP'
    AND d.qflag IS NULL         -- only unflagged, valid data
    AND EXTRACT(YEAR FROM d.date) = 2016
),

-- Step 3: Daily Citibike trip counts in 2016
daily_trips AS (
  SELECT
    DATE(starttime) AS trip_date,
    COUNT(*) AS trip_count
  FROM `bigquery-public-data.new_york.citibike_trips`
  WHERE EXTRACT(YEAR FROM starttime) = 2016
  GROUP BY trip_date
)

-- Step 4 & 5: Classify days and compute average daily trips per category
SELECT
  CASE
    WHEN dp.prcp_mm > 5 THEN 'Rainy'
    ELSE 'Non-rainy'
  END AS rain_category,
  ROUND(AVG(COALESCE(dt.trip_count, 0)), 4) AS avg_daily_trips
FROM daily_precip dp
LEFT JOIN daily_trips dt
  ON dp.date = dt.trip_date
GROUP BY rain_category
ORDER BY rain_category;
```

---

## 33. Instance: `bq053`
**Question:**
> Calculate the change in the number of living trees of each fall color in New York City from 1995 to 2015 by computing, for each tree species, the difference between the number of trees not marked as dead in 1995 and the number of trees alive in 2015, matching species by the uppercase form of their scientific names from the tree_species table. Then, group the species by their fall color and sum these differences to determine the total change in the number of trees for each fall color.

### 🏆 Gold Reference Answer
```sql
SELECT
  c.fall_color,
  SUM(d.count_growth) AS change
FROM (
  SELECT
    fall_color,
    UPPER(species_scientific_name) AS latin
  FROM
    `bigquery-public-data.new_york.tree_species`)c
JOIN (
  SELECT
    IFNULL(a.upper_latin,
      b.upper_latin) AS latin,
    (IFNULL(count_2015,
        0)-IFNULL(count_1995,
        0)) AS count_growth
  FROM (
    SELECT
      UPPER(spc_latin) AS upper_latin,
      spc_common,
      COUNT(*) AS count_2015
    FROM
      `bigquery-public-data.new_york.tree_census_2015`
    WHERE
      status="Alive"
    GROUP BY
      spc_latin,
      spc_common)a
  FULL OUTER JOIN (
    SELECT
      UPPER(spc_latin) AS upper_latin,
      COUNT(*) AS count_1995
    FROM
      `bigquery-public-data.new_york.tree_census_1995`
    WHERE
      status !="Dead"
    GROUP BY
      spc_latin)b
  ON
    a.upper_latin=b.upper_latin
  ORDER BY
    count_growth DESC)d
ON
  d.latin=c.latin
GROUP BY
  fall_color
ORDER BY
  change DESC
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Count trees not marked as dead in 1995, per species (uppercase scientific name)
WITH trees_1995 AS (
  SELECT
    UPPER(spc_latin) AS spc_upper,
    COUNT(*) AS cnt_1995
  FROM `bigquery-public-data.new_york.tree_census_1995`
  WHERE LOWER(status) != 'dead'
  GROUP BY spc_upper
),

-- Step 2: Count trees alive in 2015, per species (uppercase scientific name)
trees_2015 AS (
  SELECT
    UPPER(spc_latin) AS spc_upper,
    COUNT(*) AS cnt_2015
  FROM `bigquery-public-data.new_york.tree_census_2015`
  WHERE LOWER(status) = 'alive'
  GROUP BY spc_upper
),

-- Step 3: Full outer join to include species present in only one census, then match with tree_species
species_change AS (
  SELECT
    COALESCE(t1995.spc_upper, t2015.spc_upper) AS spc_upper,
    COALESCE(t1995.cnt_1995, 0) AS cnt_1995,
    COALESCE(t2015.cnt_2015, 0) AS cnt_2015,
    (COALESCE(t1995.cnt_1995, 0) - COALESCE(t2015.cnt_2015, 0)) AS diff
  FROM trees_1995 t1995
  FULL OUTER JOIN trees_2015 t2015
    ON t1995.spc_upper = t2015.spc_upper
)

-- Step 4: Join with tree_species to get fall_color, then aggregate by color
SELECT
  ts.fall_color,
  SUM(s.diff) AS total_change
FROM species_change s
INNER JOIN `bigquery-public-data.new_york.tree_species` ts
  ON UPPER(ts.species_scientific_name) = s.spc_upper
GROUP BY ts.fall_color
ORDER BY ts.fall_color;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Count trees not marked as dead in 1995 per species (uppercase spc_latin)
WITH counts_1995 AS (
  SELECT
    UPPER(spc_latin) AS species_upper,
    COUNT(*) AS cnt_1995
  FROM `bigquery-public-data.new_york.tree_census_1995`
  WHERE status != 'Dead'  -- include all statuses except 'Dead'
  GROUP BY species_upper
),

-- Step 2: Count trees alive in 2015 per species (uppercase spc_latin)
counts_2015 AS (
  SELECT
    UPPER(spc_latin) AS species_upper,
    COUNT(*) AS cnt_2015
  FROM `bigquery-public-data.new_york.tree_census_2015`
  WHERE status = 'Alive'  -- only alive trees
  GROUP BY species_upper
),

-- Step 3: Get distinct species from tree_species table with fall_color
distinct_species AS (
  SELECT DISTINCT
    species_scientific_name,
    fall_color
  FROM `bigquery-public-data.new_york.tree_species`
  WHERE fall_color IS NOT NULL  -- exclude species without fall_color
),

-- Step 4: Per species, compute difference = cnt_1995 - cnt_2015
species_diff AS (
  SELECT
    ds.species_scientific_name,
    ds.fall_color,
    COALESCE(c95.cnt_1995, 0) - COALESCE(c15.cnt_2015, 0) AS diff
  FROM distinct_species ds
  LEFT JOIN counts_1995 c95
    ON UPPER(ds.species_scientific_name) = c95.species_upper
  LEFT JOIN counts_2015 c15
    ON UPPER(ds.species_scientific_name) = c15.species_upper
)

-- Step 5: Aggregate total change by fall_color
SELECT
  fall_color,
  SUM(diff) AS total_change
FROM species_diff
GROUP BY fall_color
ORDER BY fall_color;
```

---

## 34. Instance: `bq054`
**Question:**
> Please provide the top 10 tree species in New York, using their uppercase Latin names where the Latin name is not empty and including their common names, showing the total number of trees, the counts of alive and dead trees for each year, and the corresponding growth in these counts from 1995 to 2015, then order by the difference in total tree counts between these years.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
  -- Aggregate 1995 census data by species
  census_1995_agg AS (
    SELECT
      UPPER(spc_latin) AS spc_latin,
      spc_common,
      COUNT(*) AS total_1995,
      COUNTIF(status != 'Dead') AS alive_1995,
      COUNTIF(status = 'Dead') AS dead_1995
    FROM
      `bigquery-public-data.new_york.tree_census_1995`
    WHERE
      spc_latin IS NOT NULL
      AND spc_latin != ''
    GROUP BY
      UPPER(spc_latin),
      spc_common
  ),

  -- Aggregate 2015 census data by species
  census_2015_agg AS (
    SELECT
      UPPER(spc_latin) AS spc_latin,
      spc_common,
      COUNT(*) AS total_2015,
      COUNTIF(status != 'Dead') AS alive_2015,
      COUNTIF(status = 'Dead') AS dead_2015
    FROM
      `bigquery-public-data.new_york.tree_census_2015`
    WHERE
      spc_latin IS NOT NULL
      AND spc_latin != ''
    GROUP BY
      UPPER(spc_latin),
      spc_common
  )

-- Final query: join both years and compute differences
SELECT
  COALESCE(a.spc_latin, b.spc_latin) AS latin_name,
  COALESCE(a.spc_common, b.spc_common) AS common_name,
  COALESCE(a.total_1995, 0) AS total_1995,
  COALESCE(b.total_2015, 0) AS total_2015,
  COALESCE(a.alive_1995, 0) AS alive_1995,
  COALESCE(b.alive_2015, 0) AS alive_2015,
  COALESCE(a.dead_1995, 0) AS dead_1995,
  COALESCE(b.dead_2015, 0) AS dead_2015,
  (COALESCE(b.total_2015, 0) - COALESCE(a.total_1995, 0)) AS total_growth,
  (COALESCE(b.alive_2015, 0) - COALESCE(a.alive_1995, 0)) AS alive_growth,
  (COALESCE(b.dead_2015, 0) - COALESCE(a.dead_1995, 0)) AS dead_growth
FROM
  census_1995_agg a
FULL OUTER JOIN
  census_2015_agg b
ON
  a.spc_latin = b.spc_latin
  AND a.spc_common = b.spc_common
ORDER BY
  total_growth DESC
LIMIT 10;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- CTE: aggregate counts per species for 1995 census
WITH 
  counts_1995 AS (
    SELECT
      UPPER(spc_latin) AS species_latin,
      spc_common AS species_common,
      COUNT(*) AS total_1995,
      COUNTIF(status NOT IN ('Dead', 'Stump')) AS alive_1995,
      COUNTIF(status IN ('Dead', 'Stump')) AS dead_1995
    FROM `bigquery-public-data.new_york.tree_census_1995`
    WHERE spc_latin IS NOT NULL AND spc_latin != ''
    GROUP BY species_latin, species_common
  ),
  -- CTE: aggregate counts per species for 2015 census
  counts_2015 AS (
    SELECT
      UPPER(spc_latin) AS species_latin,
      spc_common AS species_common,
      COUNT(*) AS total_2015,
      COUNTIF(status NOT IN ('Dead', 'Stump')) AS alive_2015,
      COUNTIF(status IN ('Dead', 'Stump')) AS dead_2015
    FROM `bigquery-public-data.new_york.tree_census_2015`
    WHERE spc_latin IS NOT NULL AND spc_latin != ''
    GROUP BY species_latin, species_common
  ),
  -- Join both years and compute growth
  species_growth AS (
    SELECT
      COALESCE(c1995.species_common, c2015.species_common) AS species_common,
      COALESCE(c1995.species_latin, c2015.species_latin) AS species_latin,
      c1995.total_1995,
      c1995.alive_1995,
      c1995.dead_1995,
      c2015.total_2015,
      c2015.alive_2015,
      c2015.dead_2015,
      (c2015.total_2015 - c1995.total_1995) AS growth_total,
      (c2015.alive_2015 - c1995.alive_1995) AS growth_alive,
      (c2015.dead_2015 - c1995.dead_1995) AS growth_dead
    FROM counts_1995 c1995
    INNER JOIN counts_2015 c2015
      ON c1995.species_latin = c2015.species_latin
  )
-- Final selection: top 10 by total growth (largest increase)
SELECT *
FROM species_growth
ORDER BY growth_total DESC
LIMIT 10;
```

---

## 35. Instance: `bq055`
**Question:**
> Can you provide the top three races with the largest percentage differences between Google's 2021 overall hiring data from dar non intersectional hiring and the average percentages in the 2021 BLS data for the technology sectors specifically defined as 'Internet publishing and broadcasting and web search portals,' 'Software publishers,' 'Data processing, hosting, and related services,' or the industry group 'Computer systems design and related services,' along with their respective differences?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Extract Google 2021 overall non-intersectional hiring percentages
WITH google_hiring AS (
  SELECT
    race_hispanic_latinx,
    race_asian,
    race_black,
    race_white
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_hiring`
  WHERE report_year = 2021
    AND workforce = 'overall'
  LIMIT 1  -- ensure at most one row
),

-- Step 2: Compute average BLS percentages for the specified tech sectors in 2021
bls_avg AS (
  SELECT
    AVG(percent_hispanic_or_latino) AS avg_hispanic_latino,
    AVG(percent_asian) AS avg_asian,
    AVG(percent_black_or_african_american) AS avg_black,
    AVG(percent_white) AS avg_white
  FROM `bigquery-public-data.bls.cpsaat18`
  WHERE year = 2021
    AND (
      industry IN (
        'Internet publishing and broadcasting and web search portals',
        'Software publishers',
        'Data processing, hosting, and related services'
      )
      OR industry_group = 'Computer systems design and related services'
    )
),

-- Step 3: Cross join and calculate absolute differences per race
differences AS (
  SELECT
    'Hispanic/Latinx' AS race,
    ROUND(ABS(g.race_hispanic_latinx - b.avg_hispanic_latino), 4) AS diff
  FROM google_hiring g, bls_avg b
  UNION ALL
  SELECT
    'Asian',
    ROUND(ABS(g.race_asian - b.avg_asian), 4)
  FROM google_hiring g, bls_avg b
  UNION ALL
  SELECT
    'Black',
    ROUND(ABS(g.race_black - b.avg_black), 4)
  FROM google_hiring g, bls_avg b
  UNION ALL
  SELECT
    'White',
    ROUND(ABS(g.race_white - b.avg_white), 4)
  FROM google_hiring g, bls_avg b
)

-- Step 4: Select top 3 races with largest absolute differences
SELECT race, diff
FROM differences
ORDER BY diff DESC
LIMIT 3;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- CTE1: Google 2021 overall non-intersectional hiring data
WITH google_2021 AS (
  SELECT
    race_hispanic_latinx AS google_hispanic,
    race_asian AS google_asian,
    race_black AS google_black,
    race_native_american AS google_native_american,
    race_white AS google_white,
    gender_us_women AS google_women
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_hiring`
  WHERE report_year = 2021
    AND workforce = 'overall'
),

-- CTE2: BLS 2021 average percentages for the specified technology sectors
bls_2021_tech_avg AS (
  SELECT
    AVG(percent_white) AS avg_white,
    AVG(percent_asian) AS avg_asian,
    AVG(percent_women) AS avg_women
  FROM `bigquery-public-data.bls.cpsaat18`
  WHERE (
    LOWER(industry) IN (
      'internet publishing and broadcasting and web search portals',
      'software publishers',
      'data processing, hosting, and related services'
    )
    OR LOWER(industry_group) = 'computer systems design and related services'
  )
),

-- CTE3: Compute differences for the matching categories
differences AS (
  SELECT
    'Hispanic/Latino' AS group_name,
    ABS(google_2021.google_hispanic - bls_2021_tech_avg.avg_white) AS diff
  FROM google_2021, bls_2021_tech_avg

  UNION ALL

  SELECT
    'Black',
    ABS(google_2021.google_black - bls_2021_tech_avg.avg_white) AS diff
  FROM google_2021, bls_2021_tech_avg

  UNION ALL

  SELECT
    'White',
    ABS(google_2021.google_white - bls_2021_tech_avg.avg_white) AS diff
  FROM google_2021, bls_2021_tech_avg

  UNION ALL

  SELECT
    'Asian',
    ABS(google_2021.google_asian - bls_2021_tech_avg.avg_asian) AS diff
  FROM google_2021, bls_2021_tech_avg

  UNION ALL

  SELECT
    'Women',
    ABS(google_2021.google_women - bls_2021_tech_avg.avg_women) AS diff
  FROM google_2021, bls_2021_tech_avg
),

-- CTE4: Rank and select top 3
ranked AS (
  SELECT
    group_name,
    diff,
    ROW_NUMBER() OVER (ORDER BY diff DESC) AS rn
  FROM differences
)

-- Final output
SELECT
  group_name,
  ROUND(diff, 4) AS percentage_difference
FROM ranked
WHERE rn <= 3
ORDER BY diff DESC;
```

---

## 36. Instance: `bq059`
**Question:**
> What is the highest average speed (rounded to 1 decimal, in metric m/s) for bike trips in Berkeley with trip distance greater than 1000 meters?

### 🏆 Gold Reference Answer
```sql
WITH stations AS (
  SELECT station_id
  FROM
    `bigquery-public-data.san_francisco_bikeshare.bikeshare_station_info` AS stainfo
  WHERE stainfo.region_id = (
    SELECT region.region_id
    FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_regions` AS region
    WHERE region.name = "Berkeley"
  )
),
meta_data AS (
    SELECT
        round(st_distance(start_station_geom, end_station_geom), 1) as distancia_metros,
        round(st_distance(start_station_geom, end_station_geom) / duration_sec, 1) as velocidade_media
    FROM
        `bigquery-public-data.san_francisco_bikeshare.bikeshare_trips` AS trips
    WHERE
        cast(trips.start_station_id as string) IN (SELECT station_id FROM stations)
        AND cast(trips.end_station_id as string) IN (SELECT station_id FROM stations)
        AND start_station_latitude IS NOT NULL
        AND start_station_longitude IS NOT NULL
        AND end_station_latitude IS NOT NULL
        AND end_station_longitude IS NOT NULL
        AND st_distance(start_station_geom, end_station_geom) > 1000
    ORDER BY
        velocidade_media DESC
    LIMIT 1
)

SELECT velocidade_media as max_velocity
FROM meta_data;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH berkeley_stations AS (
    -- Identify all stations in Berkeley based on station name
    SELECT 
        station_id,
        name,
        station_geom
    FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_station_info`
    WHERE LOWER(name) LIKE '%berkeley%'
),
berkeley_trips AS (
    -- Get trips that start at a Berkeley station
    SELECT 
        t.trip_id,
        t.duration_sec,
        ST_DISTANCE(t.start_station_geom, t.end_station_geom) AS distance_meters
    FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_trips` t
    INNER JOIN berkeley_stations bs 
        ON t.start_station_id = CAST(bs.station_id AS INT64)
    
    UNION ALL
    
    -- Get trips that end at a Berkeley station (to catch all Berkeley trips)
    SELECT 
        t.trip_id,
        t.duration_sec,
        ST_DISTANCE(t.start_station_geom, t.end_station_geom) AS distance_meters
    FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_trips` t
    INNER JOIN berkeley_stations bs 
        ON t.end_station_id = CAST(bs.station_id AS INT64)
),
unique_trips AS (
    -- Deduplicate trips that appear in both start and end joins
    SELECT DISTINCT
        trip_id,
        duration_sec,
        distance_meters
    FROM berkeley_trips
    WHERE distance_meters > 1000  -- Filter for trips > 1000 meters
        AND duration_sec > 0       -- Ensure valid duration for speed calculation
)
-- Calculate the highest speed among qualifying trips
SELECT 
    ROUND(MAX(distance_meters / duration_sec), 1) AS highest_avg_speed_mps
FROM unique_trips;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Identify Berkeley stations
berkeley_stations AS (
  SELECT DISTINCT name
  FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_station_info`
  WHERE LOWER(name) LIKE '%berkeley%'
),

-- Get Berkeley trips with distance and speed calculations
berkeley_trips AS (
  SELECT 
    trip_id,
    duration_sec,
    -- Calculate great-circle distance between start and end points in meters
    ST_DISTANCE(start_station_geom, end_station_geom) AS distance_meters,
    -- Calculate speed in meters per second
    ST_DISTANCE(start_station_geom, end_station_geom) / duration_sec AS speed_mps
  FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_trips`
  WHERE 
    -- Trip must involve at least one Berkeley station (start or end)
    LOWER(start_station_name) LIKE '%berkeley%'
    OR LOWER(end_station_name) LIKE '%berkeley%'
)

-- Final result: highest average speed rounded to 1 decimal
SELECT 
  ROUND(MAX(speed_mps), 1) AS highest_avg_speed_mps
FROM berkeley_trips
WHERE distance_meters > 1000
```

---

## 37. Instance: `bq060`
**Question:**
> Which top 3 countries had the highest net migration in 2017 among those with an area greater than 500 square kilometers? And what are their migration rates?

### 🏆 Gold Reference Answer
```sql
WITH results AS (
    SELECT
        growth.country_name,
        growth.net_migration,
        CAST(area.country_area as INT64) as country_area
    FROM (
        SELECT
            country_name,
            net_migration,
            country_code
        FROM
            `bigquery-public-data.census_bureau_international.birth_death_growth_rates`
        WHERE
            year = 2017
    ) growth
    INNER JOIN (
        SELECT
            country_area,
            country_code
        FROM
            `bigquery-public-data.census_bureau_international.country_names_area`
        WHERE
            country_area > 500
    ) area
    ON
        growth.country_code = area.country_code
    ORDER BY
        net_migration DESC
    LIMIT 3
)
SELECT country_name, net_migration
FROM results;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Join net migration data (year 2017) with country area data.
-- Step 2: Filter countries with area > 500 sq km.
-- Step 3: Order by net_migration descending and take top 3.
SELECT
    b.country_name,
    b.net_migration AS migration_rate
FROM
    `bigquery-public-data.census_bureau_international.birth_death_growth_rates` b
INNER JOIN
    `bigquery-public-data.census_bureau_international.country_names_area` a
    ON b.country_code = a.country_code
WHERE
    b.year = 2017
    AND a.country_area > 500
ORDER BY
    b.net_migration DESC
LIMIT 3;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH filtered_countries AS (
    -- Select countries with area greater than 500 square kilometers
    SELECT country_name
    FROM `bigquery-public-data.census_bureau_international.country_names_area`
    WHERE country_area > 500
),
migration_2017 AS (
    -- Get net migration data for the year 2017
    SELECT country_name, net_migration
    FROM `bigquery-public-data.census_bureau_international.birth_death_growth_rates`
    WHERE year = 2017
)
-- Join and get top 3 countries with highest net migration
SELECT 
    f.country_name,
    ROUND(m.net_migration, 4) AS migration_rate
FROM filtered_countries f
JOIN migration_2017 m ON f.country_name = m.country_name
ORDER BY m.net_migration DESC
LIMIT 3;
```

---

## 38. Instance: `bq061`
**Question:**
> Which census tract has witnessed the largest increase in median income between 2015 and 2018 in California? Tell me the tract code.

### 🏆 Gold Reference Answer
```sql
WITH acs_2018 AS (
    SELECT
      geo_id,
      median_income AS median_income_2018
    FROM
      `bigquery-public-data.census_bureau_acs.censustract_2018_5yr` 
),
acs_2015 AS (
    SELECT
      geo_id,
      median_income AS median_income_2015
    FROM
      `bigquery-public-data.census_bureau_acs.censustract_2015_5yr` ),
acs_diff AS (
    SELECT
      a18.geo_id,
      a18.median_income_2018,
      a15.median_income_2015,
      (a18.median_income_2018 - a15.median_income_2015) AS median_income_diff,
    FROM
      acs_2018 a18
    JOIN
      acs_2015 a15
    ON
      a18.geo_id = a15.geo_id
),
max_geo_id AS (
    SELECT
      geo_id
    FROM
      acs_diff
    WHERE
      median_income_diff IS NOT NULL
      AND acs_diff.geo_id in (
        SELECT
          geo_id
        FROM
          `bigquery-public-data.geo_census_tracts.census_tracts_california`
      )
    ORDER BY
      median_income_diff DESC
    LIMIT 1
)
SELECT
    tracts.tract_ce as tract_code
FROM
    max_geo_id
JOIN
    `bigquery-public-data.geo_census_tracts.census_tracts_california` AS tracts
ON
    max_geo_id.geo_id = tracts.geo_id;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Get median income for California tracts in 2015 and 2018
-- Step 2: Join with census_tracts_california to get tract_ce
-- Step 3: Compute increase, order descending, limit 1

WITH income_2015 AS (
  SELECT geo_id, median_income
  FROM `bigquery-public-data.census_bureau_acs.censustract_2015_5yr`
  WHERE STARTS_WITH(geo_id, '06')  -- California FIPS code '06'
    AND median_income IS NOT NULL
),
income_2018 AS (
  SELECT geo_id, median_income
  FROM `bigquery-public-data.census_bureau_acs.censustract_2018_5yr`
  WHERE STARTS_WITH(geo_id, '06')
    AND median_income IS NOT NULL
),
joined AS (
  SELECT 
    a.geo_id,
    a.median_income AS income_2015,
    b.median_income AS income_2018,
    (b.median_income - a.median_income) AS increase
  FROM income_2015 a
  INNER JOIN income_2018 b
    ON a.geo_id = b.geo_id
)
SELECT 
  t.tract_ce AS tract_code
FROM joined j
INNER JOIN `bigquery-public-data.geo_census_tracts.census_tracts_california` t
  ON j.geo_id = t.geo_id
ORDER BY j.increase DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Get California census tract geo_ids and tract codes
WITH california_tracts AS (
  SELECT geo_id, tract_ce
  FROM `bigquery-public-data.geo_census_tracts.census_tracts_california`
),

-- Step 2: Get 2015 median income per census tract (exclude NaN/missing)
income_2015 AS (
  SELECT geo_id, median_income AS income_2015
  FROM `bigquery-public-data.census_bureau_acs.censustract_2015_5yr`
  WHERE median_income IS NOT NULL AND median_income = median_income
),

-- Step 3: Get 2018 median income per census tract (exclude NaN/missing)
income_2018 AS (
  SELECT geo_id, median_income AS income_2018
  FROM `bigquery-public-data.census_bureau_acs.censustract_2018_5yr`
  WHERE median_income IS NOT NULL AND median_income = median_income
),

-- Step 4: Join tracts with both income years and compute increase
joined AS (
  SELECT 
    t.geo_id,
    t.tract_ce,
    i15.income_2015,
    i18.income_2018,
    i18.income_2018 - i15.income_2015 AS income_increase
  FROM california_tracts t
  INNER JOIN income_2015 i15 ON t.geo_id = i15.geo_id
  INNER JOIN income_2018 i18 ON t.geo_id = i18.geo_id
)

-- Step 5: Return the tract with the largest increase
SELECT tract_ce, income_increase
FROM joined
ORDER BY income_increase DESC
LIMIT 1;
```

---

## 39. Instance: `bq064`
**Question:**
> Using the 2017 U.S. Census Tract data from the BigQuery public datasets, you need to proportionally allocate each tract's population and income to the zip codes based on the overlapping area between their geographic boundaries. Then, filter the results to include only those zip codes located within a 5-mile radius of a specific point in Washington State, with coordinates at latitude 47.685833°N and longitude -122.191667°W. Finally, calculate the total population and the average individual income for each zip code (rounded to one decimal place) and sort the results by the average individual income in descending order.

### 🏆 Gold Reference Answer
```sql
WITH all_zip_tract_join AS (
  SELECT 
    zips.zip_code, 
    zips.functional_status as zip_functional_status,
    tracts.tract_ce, 
    tracts.geo_id as tract_geo_id, 
    tracts.functional_status as tract_functional_status,
    ST_Area(ST_Intersection(tracts.tract_geom, zips.zip_code_geom))
        / ST_Area(tracts.tract_geom) as tract_pct_in_zip_code
  FROM  
    `bigquery-public-data.geo_census_tracts.us_census_tracts_national` tracts,
    `bigquery-public-data.geo_us_boundaries.zip_codes` zips
  WHERE 
    ST_Intersects(tracts.tract_geom, zips.zip_code_geom)
),
zip_tract_join AS (
  SELECT * FROM all_zip_tract_join WHERE tract_pct_in_zip_code > 0
),
census_totals AS (
  -- convert averages to additive totals
  SELECT 
    geo_id,
    total_pop,
    total_pop * income_per_capita AS total_income 
  FROM 
    `bigquery-public-data.census_bureau_acs.censustract_2017_5yr` 
),
joined AS ( 
  -- join with precomputed census/zip pairs,
  -- compute zip's share of tract
  SELECT 
    zip_code, 
    total_pop * tract_pct_in_zip_code    AS zip_pop,
    total_income * tract_pct_in_zip_code AS zip_income
  FROM census_totals c
  JOIN zip_tract_join ztj
  ON c.geo_id = ztj.tract_geo_id
),
sums AS ( 
  -- aggregate all "pieces" of zip code
  SELECT
    zip_code, 
    SUM(zip_pop) AS zip_pop,
    SUM(zip_income) AS zip_total_inc
  FROM joined 
  GROUP BY zip_code
),
zip_pop_income AS (
    SELECT 
        zip_code, zip_pop, 
        -- convert to averages
        zip_total_inc / zip_pop AS income_per_capita
    FROM sums
),
zipcodes_within_distance as (
    SELECT 
        zip_code, zip_code_geom
    FROM 
        `bigquery-public-data.geo_us_boundaries.zip_codes`
    WHERE
        state_code = 'WA'  -- Washington state code
        AND
        ST_DWithin(
            ST_GeogPoint(-122.191667, 47.685833),
            zip_code_geom,
            8046.72
        )
)
select 
  stats.zip_code,
  ROUND(stats.zip_pop, 1) as zip_population,
  ROUND(stats.income_per_capita, 1) as average_income
from 
  zipcodes_within_distance area
join 
  zip_pop_income stats
on area.zip_code = stats.zip_code
ORDER BY
    average_income DESC;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
-- Reference point for the 5-mile radius filter
reference_point AS (
  SELECT ST_GEOGPOINT(-122.191667, 47.685833) AS point
),

-- Washington zip codes within 5 miles of the point
wa_zip_codes AS (
  SELECT 
    z.zip_code,
    z.zip_code_geom
  FROM 
    `bigquery-public-data.geo_us_boundaries.zip_codes` z,
    reference_point r
  WHERE 
    z.state_code = 'WA'
    AND ST_DISTANCE(z.zip_code_geom, r.point) <= 8046.72 -- 5 miles in meters
),

-- Washington census tract geometries
wa_tracts AS (
  SELECT 
    geo_id,
    tract_geom
  FROM 
    `bigquery-public-data.geo_census_tracts.census_tracts_washington`
),

-- 2017 census tract demographic data with computed total income
tract_data AS (
  SELECT 
    geo_id,
    total_pop,
    income_per_capita,
    total_pop * income_per_capita AS total_income
  FROM 
    `bigquery-public-data.census_bureau_acs.censustract_2017_5yr`
  WHERE 
    total_pop IS NOT NULL 
    AND income_per_capita IS NOT NULL
),

-- Join tracts with zip codes and compute overlapping areas
tract_zip_overlap AS (
  SELECT 
    t.geo_id,
    z.zip_code,
    ST_AREA(ST_INTERSECTION(t.tract_geom, z.zip_code_geom)) AS overlap_area,
    ST_AREA(t.tract_geom) AS tract_area,
    td.total_pop,
    td.total_income
  FROM 
    wa_tracts t
    INNER JOIN wa_zip_codes z 
      ON ST_INTERSECTS(t.tract_geom, z.zip_code_geom)
    INNER JOIN tract_data td 
      ON t.geo_id = td.geo_id
  WHERE 
    ST_AREA(t.tract_geom) > 0 -- ensure tract has area > 0
),

-- Proportionally allocate population and income to zip codes
allocated_data AS (
  SELECT 
    zip_code,
    total_pop * (overlap_area / tract_area) AS allocated_population,
    total_income * (overlap_area / tract_area) AS allocated_income
  FROM 
    tract_zip_overlap
)

-- Final aggregation: total population and average income per zip code
SELECT 
  zip_code,
  ROUND(SUM(allocated_population), 0) AS total_population,
  ROUND(SUM(allocated_income) / NULLIF(SUM(allocated_population), 0), 1) AS avg_individual_income
FROM 
  allocated_data
GROUP BY 
  zip_code
ORDER BY 
  avg_individual_income DESC;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Define the target point in Washington State (lat 47.685833, lon -122.191667)
target_point AS (
  SELECT ST_GEOGPOINT(-122.191667, 47.685833) AS point_geo
),

-- Get Washington state census tracts with their geometries (2017 boundaries)
wash_tracts AS (
  SELECT 
    geo_id,
    tract_geom AS geometry  -- use correct column name
  FROM `bigquery-public-data.geo_census_tracts.census_tracts_washington`
  WHERE state_fips_code = '53'  -- Washington state FIPS code
),

-- Get 2017 tract demographic data (population and income per capita)
tract_demo_2017 AS (
  SELECT 
    geo_id,
    total_pop,
    income_per_capita,
    total_pop * income_per_capita AS total_income  -- compute total income in tract
  FROM `bigquery-public-data.census_bureau_acs.censustract_2017_5yr`
  WHERE total_pop IS NOT NULL 
    AND total_pop > 0
    AND income_per_capita IS NOT NULL
),

-- Find zip codes (from geographic boundaries table) within 5 miles of the target point
-- 5 miles = 8046.72 meters
zip_codes_nearby AS (
  SELECT 
    z.zip_code AS zip_code,  -- string identifier for the zip code
    z.zip_code_geom AS geometry
  FROM `bigquery-public-data.geo_us_boundaries.zip_codes` z
  CROSS JOIN target_point tp
  WHERE ST_DWITHIN(z.zip_code_geom, tp.point_geo, 8046.72)
),

-- Calculate intersections between tracts and nearby zip codes
tract_zip_intersections AS (
  SELECT
    z.zip_code,
    t.geo_id AS tract_id,
    ST_AREA(ST_INTERSECTION(t.geometry, z.geometry)) AS overlap_area,
    ST_AREA(t.geometry) AS tract_area
  FROM wash_tracts t
  JOIN zip_codes_nearby z
    ON ST_INTERSECTS(t.geometry, z.geometry)
  WHERE ST_AREA(ST_INTERSECTION(t.geometry, z.geometry)) > 0
),

-- Proportionally allocate tract population and total income to each overlapping zip code
proportional_allocation AS (
  SELECT
    i.zip_code,
    i.tract_id,
    i.overlap_area / i.tract_area AS allocation_ratio,
    d.total_pop * (i.overlap_area / i.tract_area) AS allocated_population,
    d.total_income * (i.overlap_area / i.tract_area) AS allocated_total_income
  FROM tract_zip_intersections i
  JOIN tract_demo_2017 d ON i.tract_id = d.geo_id
),

-- Aggregate by zip code: sum population and total income
zip_code_aggregates AS (
  SELECT
    zip_code,
    SUM(allocated_population) AS total_population,
    SUM(allocated_total_income) AS total_income_sum,
    SUM(allocated_population) AS pop_sum  -- alias for clarity
  FROM proportional_allocation
  GROUP BY zip_code
)

-- Final result: compute average individual income, round, and sort
SELECT
  zip_code,
  ROUND(total_population, 0) AS total_population,
  ROUND(
    CASE WHEN pop_sum > 0 THEN total_income_sum / pop_sum ELSE 0 END,
    1
  ) AS avg_individual_income
FROM zip_code_aggregates
ORDER BY avg_individual_income DESC;
```

---

## 40. Instance: `bq066`
**Question:**
> Could you assess the relationship between the poverty rates from the previous year's census data and the percentage of births without maternal morbidity for the years 2016 to 2018? Use only data for births where no maternal morbidity was reported and for each year, use the 5-year census data from the year before to compute the Pearson correlation coefficient

### 🏆 Gold Reference Answer
```sql
WITH poverty_and_natality AS (
  SELECT
    EXTRACT(YEAR FROM n.Year) AS data_year,
    p.geo_id AS county_fips,
    (p.poverty / p.pop_determined_poverty_status) * 100 AS poverty_rate,
    SUM(n.Births) AS total_births,
    SUM(CASE WHEN n.Maternal_Morbidity_YN = 0 THEN n.Births ELSE 0 END) AS births_without_morbidity
  FROM
    `bigquery-public-data.census_bureau_acs.county_2015_5yr` p
  JOIN
    `bigquery-public-data.sdoh_cdc_wonder_natality.county_natality_by_maternal_morbidity` n
  ON p.geo_id = n.County_of_Residence_FIPS
  WHERE
    p.pop_determined_poverty_status > 0 AND
    EXTRACT(YEAR FROM n.Year) = 2016
  GROUP BY
    p.geo_id, p.poverty, p.pop_determined_poverty_status, EXTRACT(YEAR FROM n.Year)
  UNION ALL
  SELECT
    EXTRACT(YEAR FROM n.Year) AS data_year,
    p.geo_id AS county_fips,
    (p.poverty / p.pop_determined_poverty_status) * 100 AS poverty_rate,
    SUM(n.Births) AS total_births,
    SUM(CASE WHEN n.Maternal_Morbidity_YN = 0 THEN n.Births ELSE 0 END) AS births_without_morbidity
  FROM
    `bigquery-public-data.census_bureau_acs.county_2016_5yr` p
  JOIN
    `bigquery-public-data.sdoh_cdc_wonder_natality.county_natality_by_maternal_morbidity` n
  ON p.geo_id = n.County_of_Residence_FIPS
  WHERE
    p.pop_determined_poverty_status > 0 AND
    EXTRACT(YEAR FROM n.Year) = 2017
  GROUP BY
    p.geo_id, p.poverty, p.pop_determined_poverty_status, EXTRACT(YEAR FROM n.Year)
  UNION ALL
  SELECT
    EXTRACT(YEAR FROM n.Year) AS data_year,
    p.geo_id AS county_fips,
    (p.poverty / p.pop_determined_poverty_status) * 100 AS poverty_rate,
    SUM(n.Births) AS total_births,
    SUM(CASE WHEN n.Maternal_Morbidity_YN = 0 THEN n.Births ELSE 0 END) AS births_without_morbidity
  FROM
    `bigquery-public-data.census_bureau_acs.county_2017_5yr` p
  JOIN
    `bigquery-public-data.sdoh_cdc_wonder_natality.county_natality_by_maternal_morbidity` n
  ON p.geo_id = n.County_of_Residence_FIPS
  WHERE
    p.pop_determined_poverty_status > 0 AND
    EXTRACT(YEAR FROM n.Year) = 2018
  GROUP BY
    p.geo_id, p.poverty, p.pop_determined_poverty_status, EXTRACT(YEAR FROM n.Year)
)

SELECT
  data_year,
  CORR(poverty_rate, (births_without_morbidity / total_births) * 100) AS correlation_coefficient
FROM
  poverty_and_natality
GROUP BY
  data_year
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Extract births without maternal morbidity per county and year
WITH births_no_morbidity AS (
  SELECT
    County_of_Residence_FIPS,
    Year,
    SUM(Births) AS births_no_morbidity
  FROM `bigquery-public-data.sdoh_cdc_wonder_natality.county_natality_by_maternal_morbidity`
  WHERE Maternal_Morbidity_Desc = 'None checked'
    AND EXTRACT(YEAR FROM Year) BETWEEN 2016 AND 2018
  GROUP BY County_of_Residence_FIPS, Year
),

-- Step 2: Total births per county and year (all morbidity categories)
total_births AS (
  SELECT
    County_of_Residence_FIPS,
    Year,
    SUM(Births) AS total_births
  FROM `bigquery-public-data.sdoh_cdc_wonder_natality.county_natality_by_maternal_morbidity`
  WHERE EXTRACT(YEAR FROM Year) BETWEEN 2016 AND 2018
  GROUP BY County_of_Residence_FIPS, Year
),

-- Step 3: Poverty rates from the 5‑year ACS ending the year before birth year
-- For births in 2016 → ACS 2015; 2017 → ACS 2016; 2018 → ACS 2017
poverty_2015 AS (
  SELECT
    CAST(geo_id AS INT64) AS county_fips_int,
    2016 AS birth_year,
    SAFE_DIVIDE(poverty, pop_determined_poverty_status) * 100 AS poverty_rate
  FROM `bigquery-public-data.census_bureau_acs.county_2015_5yr`
  WHERE pop_determined_poverty_status > 0 AND poverty IS NOT NULL
),
poverty_2016 AS (
  SELECT
    CAST(geo_id AS INT64) AS county_fips_int,
    2017 AS birth_year,
    SAFE_DIVIDE(poverty, pop_determined_poverty_status) * 100 AS poverty_rate
  FROM `bigquery-public-data.census_bureau_acs.county_2016_5yr`
  WHERE pop_determined_poverty_status > 0 AND poverty IS NOT NULL
),
poverty_2017 AS (
  SELECT
    CAST(geo_id AS INT64) AS county_fips_int,
    2018 AS birth_year,
    SAFE_DIVIDE(poverty, pop_determined_poverty_status) * 100 AS poverty_rate
  FROM `bigquery-public-data.census_bureau_acs.county_2017_5yr`
  WHERE pop_determined_poverty_status > 0 AND poverty IS NOT NULL
),
-- Union all poverty data
poverty_data AS (
  SELECT * FROM poverty_2015
  UNION ALL
  SELECT * FROM poverty_2016
  UNION ALL
  SELECT * FROM poverty_2017
),

-- Step 4: Combine natality and poverty, compute percentage without morbidity
combined AS (
  SELECT
    n.County_of_Residence_FIPS,
    EXTRACT(YEAR FROM n.Year) AS birth_year,
    n.births_no_morbidity,
    t.total_births,
    p.poverty_rate,
    SAFE_DIVIDE(n.births_no_morbidity, t.total_births) * 100 AS pct_no_morbidity
  FROM births_no_morbidity n
  JOIN total_births t
    ON n.County_of_Residence_FIPS = t.County_of_Residence_FIPS
   AND n.Year = t.Year
  JOIN poverty_data p
    ON CAST(REPLACE(n.County_of_Residence_FIPS, '0', '') AS INT64) = p.county_fips_int
   AND EXTRACT(YEAR FROM n.Year) = p.birth_year
  WHERE t.total_births > 0 AND p.poverty_rate IS NOT NULL
)

-- Step 5: Compute Pearson correlation coefficient across all county‑year pairs
SELECT
  ROUND(
    (COUNT(*) * SUM(poverty_rate * pct_no_morbidity) - SUM(poverty_rate) * SUM(pct_no_morbidity))
    / SQRT(
        (COUNT(*) * SUM(poverty_rate * poverty_rate) - SUM(poverty_rate) * SUM(poverty_rate))
      * (COUNT(*) * SUM(pct_no_morbidity * pct_no_morbidity) - SUM(pct_no_morbidity) * SUM(pct_no_morbidity))
      ),
    4
  ) AS pearson_correlation_coefficient
FROM combined;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- This query computes the Pearson correlation coefficient between poverty rates
-- (from the previous year's 5-year ACS data) and the percentage of births without
-- maternal morbidity for each year from 2016 to 2018, at the county level.

WITH
  -- 1. Births without maternal morbidity per county-year
  births_no_morbidity AS (
    SELECT
      County_of_Residence_FIPS AS county_fips,
      EXTRACT(YEAR FROM Year) AS birth_year,
      SUM(Births) AS births_no_morbidity
    FROM `bigquery-public-data.sdoh_cdc_wonder_natality.county_natality_by_maternal_morbidity`
    WHERE Maternal_Morbidity_Desc = 'None checked'
      AND EXTRACT(YEAR FROM Year) BETWEEN 2016 AND 2018
    GROUP BY county_fips, birth_year
  ),

  -- 2. Total births per county-year (all morbidity types)
  total_births AS (
    SELECT
      County_of_Residence_FIPS AS county_fips,
      EXTRACT(YEAR FROM Year) AS birth_year,
      SUM(Births) AS total_births
    FROM `bigquery-public-data.sdoh_cdc_wonder_natality.county_natality_by_maternal_morbidity`
    WHERE EXTRACT(YEAR FROM Year) BETWEEN 2016 AND 2018
    GROUP BY county_fips, birth_year
  ),

  -- 3. Percentage of births without maternal morbidity
  natality_stats AS (
    SELECT
      t.county_fips,
      t.birth_year,
      ROUND((n.births_no_morbidity / t.total_births) * 100, 4) AS pct_no_morbidity
    FROM total_births t
    JOIN births_no_morbidity n
      ON t.county_fips = n.county_fips AND t.birth_year = n.birth_year
  ),

  -- 4. Poverty rates from the previous year's 5-year ACS county data
  -- Each table is unioned and assigned to the corresponding birth year.
  poverty_data AS (
    SELECT
      geo_id AS county_fips,
      -- Assume 'poverty' is number of people in poverty and 'total_pop' is total population
      ROUND((poverty / total_pop) * 100, 4) AS poverty_rate,
      2016 AS birth_year
    FROM `bigquery-public-data.census_bureau_acs.county_2015_5yr`
    WHERE poverty IS NOT NULL AND total_pop IS NOT NULL AND total_pop > 0

    UNION ALL

    SELECT
      geo_id AS county_fips,
      ROUND((poverty / total_pop) * 100, 4) AS poverty_rate,
      2017 AS birth_year
    FROM `bigquery-public-data.census_bureau_acs.county_2016_5yr`
    WHERE poverty IS NOT NULL AND total_pop IS NOT NULL AND total_pop > 0

    UNION ALL

    SELECT
      geo_id AS county_fips,
      ROUND((poverty / total_pop) * 100, 4) AS poverty_rate,
      2018 AS birth_year
    FROM `bigquery-public-data.census_bureau_acs.county_2017_5yr`
    WHERE poverty IS NOT NULL AND total_pop IS NOT NULL AND total_pop > 0
  ),

  -- 5. Join natality and poverty data, ready for correlation
  combined AS (
    SELECT
      n.birth_year,
      n.pct_no_morbidity AS x,
      p.poverty_rate AS y
    FROM natality_stats n
    JOIN poverty_data p
      ON n.county_fips = p.county_fips AND n.birth_year = p.birth_year
    WHERE n.pct_no_morbidity IS NOT NULL AND p.poverty_rate IS NOT NULL
  ),

  -- 6. Compute aggregates for Pearson correlation formula per year
  correlation_aggregates AS (
    SELECT
      birth_year,
      COUNT(*) AS n,
      SUM(x) AS sum_x,
      SUM(y) AS sum_y,
      SUM(x * y) AS sum_xy,
      SUM(x * x) AS sum_x2,
      SUM(y * y) AS sum_y2
    FROM combined
    GROUP BY birth_year
  )

-- 7. Final Pearson correlation coefficient
SELECT
  birth_year,
  ROUND(
    (n * sum_xy - sum_x * sum_y) /
    SQRT((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)),
    4
  ) AS pearson_r
FROM correlation_aggregates
WHERE (n * sum_x2 - sum_x * sum_x) > 0 AND (n * sum_y2 - sum_y * sum_y) > 0  -- avoid division by zero
ORDER BY birth_year;
```

---

## 41. Instance: `bq067`
**Question:**
> I want to create a labeled dataset from the National Highway Traffic Safety Administration traffic fatality data that predicts whether a traffic accident involving more than one distinct person results in more than one fatality, where the label is 1 if an accident has more than one person with an injury severity code of 4 (fatal injury) and 0 otherwise. For each accident, include the numeric predictors: state_number, the vehicle body_type, the number_of_drunk_drivers, the day_of_week, the hour_of_crash, and a binary indicator for whether the accident occurred in a work zone (1 if it is not “None,” otherwise 0). Also, engineer a feature for the average absolute difference between travel_speed and speed_limit per accident, only considering travel speeds up to 151 mph (excluding codes 997, 998, 999) and speed limits up to 80 mph (excluding codes 98, 99), and categorize this average speed difference into levels from 0 to 4 in 20 mph increments with lower bounds inclusive and upper bounds exclusive. Finally, only include accidents that involve more than one distinct person.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Create labeled dataset from NHTSA 2016 fatality data
-- Each row corresponds to a crash (accident) with more than one distinct person involved.
-- Label = 1 if more than one person has injury_severity = 4 (fatal), else 0.
-- Includes numeric predictors as specified.

WITH
  -- Step 1: Aggregate person-level data per accident
  person_agg AS (
    SELECT
      p.state_number,
      p.consecutive_number,
      COUNT(DISTINCT p.person_number) AS total_persons,
      -- Count persons with fatal injury (injury_severity = 4)
      COUNTIF(p.injury_severity = 4) AS fatal_count,
      -- Count drunk drivers: drivers (person_type = 'Driver of a Motor Vehicle In-Transport')
      -- with positive alcohol test (using drimpair table)
    FROM
      `bigquery-public-data.nhtsa_traffic_fatalities.person_2016` p
    GROUP BY
      p.state_number, p.consecutive_number
  ),
  -- Step 2: Get drunk driver count from drimpair_2016 (one record per impairment per driver)
  drunk_drivers AS (
    SELECT
      di.state_number,
      di.consecutive_number,
      COUNT(DISTINCT di.person_number) AS drunk_driver_count
    FROM
      `bigquery-public-data.nhtsa_traffic_fatalities.drimpair_2016` di
    WHERE
      di.condition_impairment_at_time_of_crash = 1  -- code for alcohol involvement (assumption)
    GROUP BY
      di.state_number, di.consecutive_number
  ),
  -- Step 3: Vehicle-level speed diff and body type mode per accident
  vehicle_speed AS (
    SELECT
      v.state_number,
      v.consecutive_number,
      v.body_type_name,
      v.travel_speed,
      v.speed_limit
    FROM
      `bigquery-public-data.nhtsa_traffic_fatalities.vehicle_2016` v
    WHERE
      -- Only include valid travel_speed (1-151) and speed_limit (5-80)
      v.travel_speed BETWEEN 1 AND 151
      AND v.speed_limit BETWEEN 5 AND 80
  ),
  vehicle_agg AS (
    SELECT
      state_number,
      consecutive_number,
      -- Compute average absolute difference per accident (across all valid vehicles)
      AVG(ABS(travel_speed - speed_limit)) AS avg_speed_diff,
      -- Most frequent body_type (mode); if tie, pick first alphabetically
      ARRAY_AGG(body_type_name ORDER BY COUNT(*) DESC, body_type_name LIMIT 1)[OFFSET(0)] AS body_type
    FROM
      vehicle_speed
    GROUP BY
      state_number, consecutive_number
  ),
  -- Step 4: Combine with accident-level attributes
  accident_base AS (
    SELECT
      a.state_number,
      a.consecutive_number,
      a.work_zone,
      a.day_of_week_name,
      a.hour_of_crash_name
    FROM
      `bigquery-public-data.nhtsa_traffic_fatalities.accident_2016` a
  ),
  -- Step 5: Final aggregation and feature engineering
  final_data AS (
    SELECT
      ab.state_number,
      ab.consecutive_number,
      pa.total_persons,
      pa.fatal_count,
      -- Label: 1 if fatal_count > 1, else 0
      CASE WHEN pa.fatal_count > 1 THEN 1 ELSE 0 END AS label,
      -- Predictors
      ab.state_number AS state_number_predictor,  -- already a numeric predictor
      va.body_type AS vehicle_body_type,          -- still a descriptor, but we can keep as numeric code if needed (question says "vehicle body_type" as predictor, likely categorical; we keep string)
      COALESCE(dd.drunk_driver_count, 0) AS number_of_drunk_drivers,
      -- Day of week: map from name to number 1-7 (1=Sunday, 2=Monday, ... 7=Saturday)
      CASE ab.day_of_week_name
        WHEN 'Sunday' THEN 1
        WHEN 'Monday' THEN 2
        WHEN 'Tuesday' THEN 3
        WHEN 'Wednesday' THEN 4
        WHEN 'Thursday' THEN 5
        WHEN 'Friday' THEN 6
        WHEN 'Saturday' THEN 7
        ELSE NULL
      END AS day_of_week,
      -- Hour of crash: parse from string like '8:00am-8:59am' -> 8, '11:00pm-11:59pm' -> 23
      -- We'll extract the first two digits before ':' and adjust for PM
      CASE
        WHEN ab.hour_of_crash_name LIKE '%am%' THEN
          SAFE_CAST(REGEXP_EXTRACT(ab.hour_of_crash_name, r'^(\d+)') AS INT64)
        WHEN ab.hour_of_crash_name LIKE '%pm%' THEN
          SAFE_CAST(REGEXP_EXTRACT(ab.hour_of_crash_name, r'^(\d+)') AS INT64) + 12
        ELSE NULL
      END AS hour_of_crash,
      -- Work zone binary: 1 if work_zone != 0 (i.e., not 'None'), else 0
      CASE WHEN ab.work_zone != 0 THEN 1 ELSE 0 END AS work_zone_indicator,
      -- Average speed difference level: 0-4 in 20 mph increments
      CASE
        WHEN va.avg_speed_diff IS NULL THEN NULL
        WHEN va.avg_speed_diff < 20 THEN 0
        WHEN va.avg_speed_diff < 40 THEN 1
        WHEN va.avg_speed_diff < 60 THEN 2
        WHEN va.avg_speed_diff < 80 THEN 3
        ELSE 4
      END AS speed_diff_level,
      va.avg_speed_diff  -- optional raw value (can be omitted if not needed)
    FROM
      accident_base ab
      -- Only accidents with more than one distinct person
      INNER JOIN person_agg pa
        ON ab.state_number = pa.state_number AND ab.consecutive_number = pa.consecutive_number
        AND pa.total_persons > 1
      LEFT JOIN vehicle_agg va
        ON ab.state_number = va.state_number AND ab.consecutive_number = va.consecutive_number
      LEFT JOIN drunk_drivers dd
        ON ab.state_number = dd.state_number AND ab.consecutive_number = dd.consecutive_number
  )
-- Final selection of required columns (plus identifiers for reference)
SELECT
  state_number AS state_number_predictor,
  vehicle_body_type,
  number_of_drunk_drivers,
  day_of_week,
  hour_of_crash,
  work_zone_indicator,
  speed_diff_level,
  label
FROM
  final_data
-- Order by state_number, consecutive_number for clarity
ORDER BY
  state_number, consecutive_number
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
-- Step 1: Count distinct persons and fatalities per accident across all years
person_aggregates AS (
    SELECT
        state_number,
        consecutive_number,
        COUNT(DISTINCT person_number) AS num_persons,
        COUNTIF(injury_severity = 4) AS num_fatalities
    FROM `bigquery-public-data.nhtsa_traffic_fatalities.person_*`
    WHERE _TABLE_SUFFIX BETWEEN '2015' AND '2020'
    GROUP BY state_number, consecutive_number
    HAVING num_persons > 1
),

-- Step 2: Compute vehicle-level speed differences and then average per accident
vehicle_speed_agg AS (
    SELECT
        state_number,
        consecutive_number,
        AVG(ABS(travel_speed - speed_limit)) AS avg_speed_diff
    FROM `bigquery-public-data.nhtsa_traffic_fatalities.vehicle_*`
    WHERE _TABLE_SUFFIX BETWEEN '2015' AND '2020'
        AND travel_speed BETWEEN 1 AND 151
        AND speed_limit BETWEEN 5 AND 80
    GROUP BY state_number, consecutive_number
),

-- Step 3: Get accident-level predictors
accident_features AS (
    SELECT
        state_number,
        consecutive_number,
        number_of_drunk_drivers,
        day_of_week,
        hour_of_crash,
        CASE 
            WHEN SAFE_CAST(work_zone AS INT64) != 0 THEN 1 
            ELSE 0 
        END AS is_work_zone
    FROM `bigquery-public-data.nhtsa_traffic_fatalities.accident_*`
    WHERE _TABLE_SUFFIX BETWEEN '2015' AND '2020'
),

-- Step 4: Get vehicle body_type (take the first vehicle's body_type for each accident)
vehicle_body AS (
    SELECT
        state_number,
        consecutive_number,
        body_type AS vehicle_body_type
    FROM (
        SELECT
            state_number,
            consecutive_number,
            body_type,
            ROW_NUMBER() OVER (PARTITION BY state_number, consecutive_number ORDER BY body_type) AS rn
        FROM `bigquery-public-data.nhtsa_traffic_fatalities.vehicle_*`
        WHERE _TABLE_SUFFIX BETWEEN '2015' AND '2020'
    )
    WHERE rn = 1
)

-- Final SELECT
SELECT
    a.state_number,
    vb.vehicle_body_type,
    a.number_of_drunk_drivers,
    a.day_of_week,
    a.hour_of_crash,
    a.is_work_zone,
    CASE WHEN pa.num_fatalities > 1 THEN 1 ELSE 0 END AS label,
    LEAST(CAST(FLOOR(COALESCE(vsa.avg_speed_diff, 0) / 20) AS INT64), 4) AS speed_diff_category,
    vsa.avg_speed_diff
FROM accident_features a
INNER JOIN person_aggregates pa
    ON a.state_number = pa.state_number
    AND a.consecutive_number = pa.consecutive_number
LEFT JOIN vehicle_speed_agg vsa
    ON a.state_number = vsa.state_number
    AND a.consecutive_number = vsa.consecutive_number
LEFT JOIN vehicle_body vb
    ON a.state_number = vb.state_number
    AND a.consecutive_number = vb.consecutive_number
ORDER BY a.state_number, a.consecutive_number;
```

---

## 42. Instance: `bq074`
**Question:**
> Count the number of counties that experienced an increase in unemployment from 2015 to 2018, using 5-year ACS data, and a decrease in dual-eligible enrollee counts between December 1, 2015, and December 1, 2018.

### 🏆 Gold Reference Answer
```sql
WITH acs_2018 AS (
  SELECT geo_id, unemployed_pop AS unemployed_2018  
  FROM `bigquery-public-data.census_bureau_acs.county_2018_5yr` 
),
 
acs_2015 AS (
  SELECT geo_id, unemployed_pop AS unemployed_2015  
  FROM `bigquery-public-data.census_bureau_acs.county_2015_5yr` 
),
 
unemployed_change AS (
  SELECT
    u18.unemployed_2018, u18.geo_id, u15.unemployed_2015,
    (u18.unemployed_2018 - u15.unemployed_2015) AS u_change
  FROM acs_2018 u18
  JOIN acs_2015 u15
  ON u18.geo_id = u15.geo_id
),
 
duals_Jan_2018 AS (
  SELECT Public_Total AS duals_2018, County_Name, FIPS 
  FROM `bigquery-public-data.sdoh_cms_dual_eligible_enrollment.dual_eligible_enrollment_by_county_and_program` 
  WHERE Date = '2018-12-01'
),

duals_Jan_2015 AS (
  SELECT Public_Total AS duals_2015, County_Name, FIPS
  FROM `bigquery-public-data.sdoh_cms_dual_eligible_enrollment.dual_eligible_enrollment_by_county_and_program` 
  WHERE Date = '2015-12-01'
),

duals_change AS (
  SELECT
    d18.FIPS, d18.County_Name, d18.duals_2018, d15.duals_2015,
    (d18.duals_2018 - d15.duals_2015) AS total_duals_diff
  FROM duals_Jan_2018 d18
  JOIN duals_Jan_2015 d15
  ON d18.FIPS = d15.FIPS
),
 
corr_tbl AS (
  SELECT unemployed_change.geo_id, duals_change.County_Name, unemployed_change.u_change, duals_change.total_duals_diff
  FROM unemployed_change
  JOIN duals_change
  ON unemployed_change.geo_id = duals_change.FIPS
)


SELECT COUNT(*)
FROM corr_tbl
WHERE
u_change >0
AND
corr_tbl.total_duals_diff < 0
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- 2015 unemployment data (5-year ACS)
unemployment_2015 AS (
  SELECT 
    geo_id,
    unemployed_pop AS unemployed_2015
  FROM `bigquery-public-data.census_bureau_acs.county_2015_5yr`
),
-- 2018 unemployment data (5-year ACS)
unemployment_2018 AS (
  SELECT 
    geo_id,
    unemployed_pop AS unemployed_2018
  FROM `bigquery-public-data.census_bureau_acs.county_2018_5yr`
),
-- Counties where unemployment increased
unemployment_increase AS (
  SELECT 
    u15.geo_id
  FROM unemployment_2015 u15
  JOIN unemployment_2018 u18
    ON u15.geo_id = u18.geo_id
  WHERE u18.unemployed_2018 > u15.unemployed_2015
),
-- Dual-eligible enrollment at December 1, 2015
dual_eligible_2015 AS (
  SELECT 
    FIPS AS geo_id,
    Public_Total AS enrollee_2015
  FROM `bigquery-public-data.sdoh_cms_dual_eligible_enrollment.dual_eligible_enrollment_by_county_and_program`
  WHERE Date = '2015-12-01'
),
-- Dual-eligible enrollment at December 1, 2018
dual_eligible_2018 AS (
  SELECT 
    FIPS AS geo_id,
    Public_Total AS enrollee_2018
  FROM `bigquery-public-data.sdoh_cms_dual_eligible_enrollment.dual_eligible_enrollment_by_county_and_program`
  WHERE Date = '2018-12-01'
),
-- Counties where dual-eligible decreased
dual_eligible_decrease AS (
  SELECT 
    d15.geo_id
  FROM dual_eligible_2015 d15
  JOIN dual_eligible_2018 d18
    ON d15.geo_id = d18.geo_id
  WHERE d15.enrollee_2015 > d18.enrollee_2018
)
-- Final count of counties meeting both conditions
SELECT 
  COUNT(DISTINCT u.geo_id) AS county_count
FROM unemployment_increase u
INNER JOIN dual_eligible_decrease d
  ON u.geo_id = d.geo_id;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- CTE: 2015 county unemployment rate from 5-year ACS
WITH county_2015_unemployment AS (
  SELECT 
    geo_id,
    SAFE_DIVIDE(unemployed_pop, civilian_labor_force) AS unemployment_rate_2015
  FROM `bigquery-public-data.census_bureau_acs.county_2015_5yr`
  WHERE civilian_labor_force > 0 
    AND unemployed_pop IS NOT NULL
    AND civilian_labor_force IS NOT NULL
),

-- CTE: 2018 county unemployment rate from 5-year ACS  
county_2018_unemployment AS (
  SELECT 
    geo_id,
    SAFE_DIVIDE(unemployed_pop, civilian_labor_force) AS unemployment_rate_2018
  FROM `bigquery-public-data.census_bureau_acs.county_2018_5yr`
  WHERE civilian_labor_force > 0
    AND unemployed_pop IS NOT NULL
    AND civilian_labor_force IS NOT NULL
),

-- CTE: Counties with increased unemployment rate from 2015 to 2018
unemployment_increase AS (
  SELECT 
    u15.geo_id
  FROM county_2015_unemployment u15
  INNER JOIN county_2018_unemployment u18
    ON u15.geo_id = u18.geo_id
  WHERE u18.unemployment_rate_2018 > u15.unemployment_rate_2015
)

-- Final count
SELECT 
  COUNT(DISTINCT geo_id) AS num_counties
FROM unemployment_increase;
```

---

## 43. Instance: `bq075`
**Question:**
> Could you provide a combined 2021 report comparing racial (Asian, Black, Hispanic/Latinx, White) and gender (U.S. Women, U.S. Men) distributions across Google’s overall workforce hiring, Google’s overall workforce representation, and the BLS data specifically for the technology sectors defined as Internet publishing and broadcasting and web search portals or Computer systems design and related services?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Combined 2021 report comparing racial and gender distributions across:
-- 1) Google overall workforce hiring
-- 2) Google overall workforce representation
-- 3) BLS data for specific technology sectors

-- Use non-intersectional Google tables (separate race and gender columns)
-- Assume workforce='overall' exists for overall numbers (if not, adjust)
-- BLS table: filter for 2021 and industries matching Internet publishing or Computer systems design

WITH
-- Google Hiring: overall workforce, 2021
google_hiring AS (
  SELECT
    report_year,
    'Hiring' AS source,
    ROUND(race_asian, 4) AS race_asian,
    ROUND(race_black, 4) AS race_black,
    ROUND(race_hispanic_latinx, 4) AS race_hispanic_latinx,
    ROUND(race_white, 4) AS race_white,
    ROUND(gender_us_women, 4) AS gender_us_women,
    ROUND(gender_us_men, 4) AS gender_us_men
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_hiring`
  WHERE report_year = 2021
    AND LOWER(workforce) = 'overall'
),

-- Google Representation: overall workforce, 2021
google_representation AS (
  SELECT
    report_year,
    'Representation' AS source,
    ROUND(race_asian, 4) AS race_asian,
    ROUND(race_black, 4) AS race_black,
    ROUND(race_hispanic_latinx, 4) AS race_hispanic_latinx,
    ROUND(race_white, 4) AS race_white,
    ROUND(gender_us_women, 4) AS gender_us_women,
    ROUND(gender_us_men, 4) AS gender_us_men
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_representation`
  WHERE report_year = 2021
    AND LOWER(workforce) = 'overall'
),

-- BLS Data: technology sectors, 2021
bls_tech AS (
  SELECT
    2021 AS report_year,
    'BLS' AS source,
    ROUND(percent_asian, 4) AS race_asian,               -- assume column exists
    ROUND(percent_black_or_african_american, 4) AS race_black,
    ROUND(percent_hispanic_or_latino, 4) AS race_hispanic_latinx,
    ROUND(percent_white, 4) AS race_white,               -- assume column exists
    ROUND(percent_women, 4) AS gender_us_women,
    ROUND(1 - percent_women, 4) AS gender_us_men         -- derive men from women %
  FROM `bigquery-public-data.bls.cpsaat18`
  WHERE 
    -- filter for 2021 (assume year column exists, otherwise adjust)
    -- The table may not have a year column; we assume it does.
    -- If not, the BLS table might be one row per year; we'll filter on a year column.
    -- For safety, we include a placeholder: year = 2021
    year = 2021
    AND (
      LOWER(industry) LIKE '%internet publishing%' 
      OR LOWER(industry) LIKE '%web search portals%'
      OR LOWER(industry) LIKE '%computer systems design%'
      OR LOWER(industry_group) LIKE '%internet publishing%'
      OR LOWER(industry_group) LIKE '%computer systems design%'
    )
)

-- Combine all three sources into one report
SELECT * FROM google_hiring
UNION ALL
SELECT * FROM google_representation
UNION ALL
SELECT * FROM bls_tech
ORDER BY source;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH bls_filtered AS (
  -- Filter BLS data for the specific technology sectors
  SELECT 
    year,
    percent_women,
    percent_asian,
    percent_black_or_african_american AS percent_black,
    percent_hispanic_or_latino AS percent_hispanic_latinx,
    percent_white,
    sector,
    industry,
    industry_group,
    subsector
  FROM `bigquery-public-data.bls.cpsaat18`
  WHERE year = 2021
    AND (
      (LOWER(sector) LIKE '%internet%publishing%broadcasting%web%search%portals%')
      OR (LOWER(sector) LIKE '%computer%systems%design%related%services%')
      OR (LOWER(industry_group) LIKE '%internet%publishing%broadcasting%web%search%portals%')
      OR (LOWER(industry_group) LIKE '%computer%systems%design%related%services%')
      OR (LOWER(industry) LIKE '%internet%publishing%broadcasting%web%search%portals%')
      OR (LOWER(industry) LIKE '%computer%systems%design%related%services%')
      OR (LOWER(subsector) LIKE '%internet%publishing%broadcasting%web%search%portals%')
      OR (LOWER(subsector) LIKE '%computer%systems%design%related%services%')
    )
),

bls_aggregated AS (
  -- Aggregate BLS data (in case multiple rows match)
  SELECT
    'BLS Technology Sectors' AS data_source,
    ROUND(AVG(percent_women), 4) AS gender_us_women,
    ROUND(1 - AVG(percent_women), 4) AS gender_us_men,
    ROUND(AVG(percent_asian), 4) AS race_asian,
    ROUND(AVG(percent_black), 4) AS race_black,
    ROUND(AVG(percent_hispanic_latinx), 4) AS race_hispanic_latinx,
    ROUND(AVG(percent_white), 4) AS race_white
  FROM bls_filtered
),

google_hiring AS (
  -- Get Google overall workforce hiring data (non-intersectional, overall workforce)
  SELECT
    'Google Overall Hiring' AS data_source,
    gender_us_women,
    gender_us_men,
    race_asian,
    race_black,
    race_hispanic_latinx,
    race_white
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_hiring`
  WHERE report_year = 2021
    AND LOWER(workforce) = 'overall'
  LIMIT 1
),

google_representation AS (
  -- Get Google overall workforce representation data (non-intersectional, overall workforce)
  SELECT
    'Google Overall Representation' AS data_source,
    gender_us_women,
    gender_us_men,
    race_asian,
    race_black,
    race_hispanic_latinx,
    race_white
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_representation`
  WHERE LOWER(workforce) = 'overall'
  LIMIT 1
  -- Note: This table doesn't have report_year, so we assume the latest data is 2021
  -- The question explicitly asks for 2021 report, and Google's DEI reports are annual
)

-- Combine all three data sources into one unified report
SELECT * FROM google_hiring
UNION ALL
SELECT * FROM google_representation
UNION ALL
SELECT * FROM bls_aggregated
ORDER BY data_source;
```

---

## 44. Instance: `bq076`
**Question:**
> What is the highest number of motor vehicle theft incidents that occurred in any single month during 2016?

### 🏆 Gold Reference Answer
```sql
SELECT
  incidents AS highest_monthly_thefts
FROM (
  SELECT
    year,
    EXTRACT(MONTH FROM date) AS month,
    COUNT(1) AS incidents,
    RANK() OVER (PARTITION BY year ORDER BY COUNT(1) DESC) AS ranking
  FROM
    `bigquery-public-data.chicago_crime.crime`
  WHERE
    primary_type = 'MOTOR VEHICLE THEFT'
    AND year = 2016
  GROUP BY
    year,
    month
)
WHERE
  ranking = 1
ORDER BY
  year DESC
LIMIT 1;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Understand the intent - find the maximum number of motor vehicle thefts in any single month of 2016
-- Step 2: Use only the Chicago crime table, filter by primary_type and year/month
-- Step 3: Group by year-month, count incidents, then get max count

WITH monthly_counts AS (
    SELECT 
        EXTRACT(YEAR FROM date) AS year,
        EXTRACT(MONTH FROM date) AS month,
        COUNT(*) AS theft_count
    FROM 
        `bigquery-public-data.chicago_crime.crime`
    WHERE 
        primary_type = 'MOTOR VEHICLE THEFT'
        AND EXTRACT(YEAR FROM date) = 2016
    GROUP BY 
        year, month
)
SELECT 
    MAX(theft_count) AS highest_monthly_count
FROM 
    monthly_counts;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Find the highest number of motor vehicle theft incidents in any single month during 2016
WITH monthly_counts AS (
  SELECT
    EXTRACT(YEAR FROM date) AS year,
    EXTRACT(MONTH FROM date) AS month,
    COUNT(DISTINCT unique_key) AS incident_count
  FROM `bigquery-public-data.chicago_crime.crime`
  WHERE 
    EXTRACT(YEAR FROM date) = 2016
    AND primary_type = 'MOTOR VEHICLE THEFT'
  GROUP BY 
    EXTRACT(YEAR FROM date),
    EXTRACT(MONTH FROM date)
)
SELECT 
  MAX(incident_count) AS highest_monthly_motor_vehicle_thefts
FROM monthly_counts;
```

---

## 45. Instance: `bq077`
**Question:**
> For each year from 2010 to 2016, what is the highest number of motor thefts in one month?

### 🏆 Gold Reference Answer
```sql
SELECT
  year,
  incidents
FROM (
  SELECT
    year,
    EXTRACT(MONTH
    FROM
      date) AS month,
    COUNT(1) AS incidents,
    RANK() OVER (PARTITION BY year ORDER BY COUNT(1) DESC) AS ranking
  FROM
    `bigquery-public-data.chicago_crime.crime`
  WHERE
    primary_type = 'MOTOR VEHICLE THEFT'
    AND year BETWEEN 2010 AND 2016
  GROUP BY
    year,
    month )
WHERE
  ranking = 1
ORDER BY
  year ASC
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Compute monthly motor vehicle theft counts for years 2010-2016
WITH monthly_counts AS (
  SELECT
    EXTRACT(YEAR FROM date) AS year,
    EXTRACT(MONTH FROM date) AS month,
    COUNT(*) AS theft_count
  FROM `bigquery-public-data.chicago_crime.crime`
  WHERE
    -- Filter for motor vehicle thefts (case‑insensitive match)
    LOWER(primary_type) LIKE '%motor%vehicle%theft%'
    -- Restrict to the years of interest
    AND EXTRACT(YEAR FROM date) BETWEEN 2010 AND 2016
  GROUP BY year, month
)

-- Step 2: For each year, find the maximum monthly theft count
SELECT
  year,
  MAX(theft_count) AS highest_monthly_motor_thefts
FROM monthly_counts
GROUP BY year
ORDER BY year;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Understand the question
-- For each year from 2010 to 2016, find the highest number of motor thefts in a single month.
-- Motor thefts are identified by primary_type = 'MOTOR VEHICLE THEFT' in the crime table.
-- We need to count crimes per year-month, then get the max count per year.

-- Step 2: Identify relevant tables and columns
-- Table: bigquery-public-data.chicago_crime.crime
-- Columns: primary_type (to filter motor thefts), date (to extract year and month)
-- Constraints: year between 2010 and 2016, primary_type = 'MOTOR VEHICLE THEFT'

-- Step 3: Design the SQL query structure
-- 1. Filter crimes for motor vehicle thefts and years 2010-2016
-- 2. Extract year and month from the date column
-- 3. Count crimes per year-month
-- 4. For each year, get the maximum monthly count

-- Step 4: Logical validation
-- The query correctly filters by primary_type and year range
-- It groups by year and month to get monthly counts
-- Then uses a window function (MAX) partitioned by year to find the highest monthly count per year
-- This satisfies the requirement: "For each year from 2010 to 2016, what is the highest number of motor thefts in one month?"

-- Step 5: Write the final SQL query
WITH monthly_counts AS (
  SELECT
    EXTRACT(YEAR FROM date) AS year,
    EXTRACT(MONTH FROM date) AS month,
    COUNT(*) AS theft_count
  FROM
    `bigquery-public-data.chicago_crime.crime`
  WHERE
    primary_type = 'MOTOR VEHICLE THEFT'
    AND EXTRACT(YEAR FROM date) BETWEEN 2010 AND 2016
  GROUP BY
    year,
    month
)
SELECT
  year,
  MAX(theft_count) AS highest_monthly_motor_thefts
FROM
  monthly_counts
GROUP BY
  year
ORDER BY
  year;
```

---

## 46. Instance: `bq079`
**Question:**
> Considering only the latest evaluation group per state for the 'EXPCURR' evaluation type, determine which state has the highest total acreage of timberland and which has the highest total acreage of forestland. For timberland, include plots where the condition status code is 1, the reserved status code is 0, and the site productivity class code is between 1 and 6. For forestland, include plots where the condition status code is 1. Calculate the total acres by summing the adjusted expansion factors for macroplots and subplots, using their respective proportion bases ('MACR' for macroplots and 'SUBP' for subplots) and adjustment factors when greater than zero. For each category (timberland and forestland), provide the state code, evaluation group, state name, and the total acres for the state with the highest total acreage, considering only the latest evaluation group per state.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Identify the latest evaluation group per state that contains an 'EXPCURR' evaluation type
WITH latest_group AS (
  SELECT 
    eg.state_code,
    eg.evaluation_group,
    eg.evaluation_group_sequence_number
  FROM `bigquery-public-data.usfs_fia.population_evaluation_group` eg
  WHERE EXISTS (
    SELECT 1
    FROM `bigquery-public-data.usfs_fia.population_evaluation_type` pet
    WHERE pet.evaluation_group_sequence_number = eg.evaluation_group_sequence_number
      AND pet.evaluation_type = 'EXPCURR'
  )
  QUALIFY ROW_NUMBER() OVER (PARTITION BY eg.state_code ORDER BY eg.evaluation_group DESC) = 1
),

-- Step 2: For each latest group, get the evaluation_identifier for the EXPCURR evaluation type
latest_eval AS (
  SELECT 
    lg.state_code,
    lg.evaluation_group,
    pe.evaluation_identifier,
    pe.location_name
  FROM latest_group lg
  JOIN `bigquery-public-data.usfs_fia.population_evaluation_type` pet 
    ON pet.evaluation_group_sequence_number = lg.evaluation_group_sequence_number
    AND pet.evaluation_type = 'EXPCURR'
  JOIN `bigquery-public-data.usfs_fia.population_evaluation` pe
    ON pe.evaluation_sequence_number = pet.evaluation_sequence_number
),

-- Step 3: Join population, stratum, and condition tables to get plot‑level data
plot_data AS (
  SELECT 
    le.state_code,
    le.evaluation_group,
    le.location_name,
    p.expansion_factor,
    c.condition_proportion_unadjusted,
    c.proportion_basis,
    ps.adjustment_factor_for_the_macroplot,
    ps.adjustment_factor_for_the_subplot,
    c.condition_status_code,
    c.reserved_status_code,
    c.site_productivity_class_code
  FROM latest_eval le
  JOIN `bigquery-public-data.usfs_fia.population` p 
    ON p.evaluation_identifier = le.evaluation_identifier
  JOIN `bigquery-public-data.usfs_fia.population_stratum` ps 
    ON p.stratum_sequence_number = ps.stratum_sequence_number
  JOIN `bigquery-public-data.usfs_fia.condition` c 
    ON c.plot_sequence_number = p.plot_sequence_number
),

-- Step 4: Compute total acres per state for timberland and forestland separately
acres_per_state AS (
  SELECT 
    state_code,
    evaluation_group,
    location_name,
    ROUND(SUM(
      CASE 
        WHEN condition_status_code = 1 
         AND reserved_status_code = 0 
         AND site_productivity_class_code BETWEEN 1 AND 6
        THEN expansion_factor 
             * condition_proportion_unadjusted 
             * CASE 
                 WHEN proportion_basis = 'MACR' THEN COALESCE(adjustment_factor_for_the_macroplot, 0)
                 WHEN proportion_basis = 'SUBP' THEN COALESCE(adjustment_factor_for_the_subplot, 0)
                 ELSE 0
               END
        ELSE 0
      END
    ), 4) AS total_timberland_acres,
    ROUND(SUM(
      CASE 
        WHEN condition_status_code = 1
        THEN expansion_factor 
             * condition_proportion_unadjusted 
             * CASE 
                 WHEN proportion_basis = 'MACR' THEN COALESCE(adjustment_factor_for_the_macroplot, 0)
                 WHEN proportion_basis = 'SUBP' THEN COALESCE(adjustment_factor_for_the_subplot, 0)
                 ELSE 0
               END
        ELSE 0
      END
    ), 4) AS total_forestland_acres
  FROM plot_data
  GROUP BY state_code, evaluation_group, location_name
)

-- Final: select the state with highest timberland and highest forestland acreage
SELECT 'Timberland' AS category, state_code, evaluation_group, location_name, total_timberland_acres AS total_acres
FROM acres_per_state
QUALIFY ROW_NUMBER() OVER (ORDER BY total_timberland_acres DESC) = 1

UNION ALL

SELECT 'Forestland' AS category, state_code, evaluation_group, location_name, total_forestland_acres AS total_acres
FROM acres_per_state
QUALIFY ROW_NUMBER() OVER (ORDER BY total_forestland_acres DESC) = 1
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Step 1: Get latest evaluation group per state for EXPCURR
latest_eval_group AS (
  SELECT 
    peg.state_code,
    MAX(peg.pop_evaluation_group_created_date) AS latest_date
  FROM `bigquery-public-data.usfs_fia.population_evaluation_group` peg
  JOIN `bigquery-public-data.usfs_fia.population_evaluation` pe 
    ON peg.evaluation_group_sequence_number = pe.evaluation_group_sequence_number
  JOIN `bigquery-public-data.usfs_fia.population_evaluation_type` pet 
    ON pe.evaluation_sequence_number = pet.evaluation_sequence_number
  WHERE pet.evaluation_type = 'EXPCURR'
  GROUP BY peg.state_code
),

-- Step 2: Get the evaluation_group details for the latest date
selected_evals AS (
  SELECT 
    peg.state_code,
    peg.evaluation_group,
    peg.pop_evaluation_group_created_date
  FROM `bigquery-public-data.usfs_fia.population_evaluation_group` peg
  JOIN latest_eval_group leg 
    ON peg.state_code = leg.state_code 
    AND peg.pop_evaluation_group_created_date = leg.latest_date
),

-- Step 3: Get evaluation_identifier for selected evaluation types
eval_ids AS (
  SELECT DISTINCT
    pe.state_code,
    pe.evaluation_identifier,
    pe.evaluation_group_sequence_number
  FROM `bigquery-public-data.usfs_fia.population_evaluation` pe
  JOIN selected_evals se 
    ON pe.state_code = se.state_code
  JOIN `bigquery-public-data.usfs_fia.population_evaluation_type` pet 
    ON pe.evaluation_sequence_number = pet.evaluation_sequence_number
  WHERE pet.evaluation_type = 'EXPCURR'
),

-- Step 4: Join with population table for expansion and adjustment factors
pop_data AS (
  SELECT 
    p.state_code,
    p.plot_sequence_number,
    p.expansion_factor,
    p.adjustment_factor_for_the_macroplot,
    p.adjustment_factor_for_the_subplot,
    p.evaluation_identifier
  FROM `bigquery-public-data.usfs_fia.population` p
  JOIN eval_ids ei 
    ON p.evaluation_identifier = ei.evaluation_identifier 
    AND p.state_code = ei.state_code
),

-- Step 5: Join with condition data
cond_data AS (
  SELECT 
    c.state_code,
    c.state_code_name,
    c.plot_sequence_number,
    c.condition_status_code,
    c.reserved_status_code,
    c.site_productivity_class_code,
    c.proportion_basis,
    c.subplot_proportion_unadjusted,
    c.macroplot_proportion_unadjusted,
    c.condition_class_number
  FROM `bigquery-public-data.usfs_fia.condition` c
  INNER JOIN pop_data pd 
    ON c.plot_sequence_number = pd.plot_sequence_number 
    AND c.state_code = pd.state_code
),

-- Step 6: Calculate timberland acres
timberland_acres AS (
  SELECT 
    cd.state_code,
    cd.state_code_name,
    SUM(
      CASE 
        WHEN cd.proportion_basis = 'MACR' AND pd.adjustment_factor_for_the_macroplot > 0 
          THEN pd.expansion_factor * cd.macroplot_proportion_unadjusted * pd.adjustment_factor_for_the_macroplot
        WHEN cd.proportion_basis = 'SUBP' AND pd.adjustment_factor_for_the_subplot > 0 
          THEN pd.expansion_factor * cd.subplot_proportion_unadjusted * pd.adjustment_factor_for_the_subplot
        ELSE 0
      END
    ) AS total_timberland_acres
  FROM cond_data cd
  JOIN pop_data pd 
    ON cd.plot_sequence_number = pd.plot_sequence_number 
    AND cd.state_code = pd.state_code
  WHERE cd.condition_status_code = 1 
    AND cd.reserved_status_code = 0 
    AND cd.site_productivity_class_code BETWEEN 1 AND 6
  GROUP BY cd.state_code, cd.state_code_name
),

-- Step 7: Calculate forestland acres
forestland_acres AS (
  SELECT 
    cd.state_code,
    cd.state_code_name,
    SUM(
      CASE 
        WHEN cd.proportion_basis = 'MACR' AND pd.adjustment_factor_for_the_macroplot > 0 
          THEN pd.expansion_factor * cd.macroplot_proportion_unadjusted * pd.adjustment_factor_for_the_macroplot
        WHEN cd.proportion_basis = 'SUBP' AND pd.adjustment_factor_for_the_subplot > 0 
          THEN pd.expansion_factor * cd.subplot_proportion_unadjusted * pd.adjustment_factor_for_the_subplot
        ELSE 0
      END
    ) AS total_forestland_acres
  FROM cond_data cd
  JOIN pop_data pd 
    ON cd.plot_sequence_number = pd.plot_sequence_number 
    AND cd.state_code = pd.state_code
  WHERE cd.condition_status_code = 1
  GROUP BY cd.state_code, cd.state_code_name
)

-- Step 8: Get the highest for each category using parentheses to allow ORDER BY/LIMIT before UNION
(
  SELECT 
    'Timberland' AS category,
    ta.state_code,
    se.evaluation_group,
    ta.state_code_name,
    ROUND(ta.total_timberland_acres, 4) AS total_acres
  FROM timberland_acres ta
  JOIN selected_evals se 
    ON ta.state_code = se.state_code
  ORDER BY ta.total_timberland_acres DESC
  LIMIT 1
)
UNION ALL
(
  SELECT 
    'Forestland' AS category,
    fa.state_code,
    se.evaluation_group,
    fa.state_code_name,
    ROUND(fa.total_forestland_acres, 4) AS total_acres
  FROM forestland_acres fa
  JOIN selected_evals se 
    ON fa.state_code = se.state_code
  ORDER BY fa.total_forestland_acres DESC
  LIMIT 1
);
```

---

## 47. Instance: `bq081`
**Question:**
> Find the latest ride data for each region between 2014 and 2017. I want to know the name of each region, the trip ID of this ride, the ride duration, the start time, the starting station, and the gender of the rider.

### 🏆 Gold Reference Answer
```sql
SELECT t1.*
  FROM 
  (SELECT Trips.trip_id TripId,
               Trips.duration_sec TripDuration,
               Trips.start_date TripStartDate,
               Trips.start_station_name TripStartStation,
               Trips.member_gender Gender,
               Regions.name RegionName
          FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_trips` Trips
         INNER JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_station_info` StationInfo
            ON CAST(Trips.start_station_id AS STRING) = CAST(StationInfo.station_id AS STRING)
         INNER JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_regions` Regions
            ON StationInfo.region_id = Regions.region_id
         WHERE (EXTRACT(YEAR from Trips.start_date)) BETWEEN 2014 AND 2017
           ) 
           t1
 RIGHT JOIN (SELECT MAX(start_date) TripStartDate,
                   Regions.name RegionName
              FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_station_info` StationInfo
             INNER JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_trips` Trips
                ON CAST(StationInfo.station_id AS STRING) = CAST(Trips.start_station_id AS STRING)
             INNER JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_regions` Regions
                ON Regions.region_id = StationInfo.region_id
                 WHERE (EXTRACT(YEAR from Trips.start_date) BETWEEN 2014 AND 2017
           AND Regions.name IS NOT NULL)
             GROUP BY RegionName) 
             t2
    ON t1.RegionName = t2.RegionName AND t1.TripStartDate = t2.TripStartDate
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH ranked_trips AS (
  SELECT
    t.trip_id,
    t.duration_sec,
    t.start_date,
    t.start_station_name,
    t.member_gender,
    r.name AS region_name,
    ROW_NUMBER() OVER (PARTITION BY r.region_id ORDER BY t.start_date DESC) AS rn
  FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_trips` t
  INNER JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_station_info` s
    ON CAST(t.start_station_id AS STRING) = s.station_id
  INNER JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_regions` r
    ON s.region_id = r.region_id
  WHERE EXTRACT(YEAR FROM t.start_date) BETWEEN 2014 AND 2017
)
SELECT
  region_name,
  trip_id,
  duration_sec,
  start_date,
  start_station_name,
  member_gender
FROM ranked_trips
WHERE rn = 1
ORDER BY region_name;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Get trips with region_id via station_info
WITH trips_with_region AS (
  SELECT
    t.trip_id,
    t.start_date,
    t.duration_sec,
    t.start_station_name,
    t.member_gender,
    si.region_id
  FROM `bigquery-public-data.san_francisco_bikeshare.bikeshare_trips` AS t
  JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_station_info` AS si
    ON t.start_station_id = SAFE_CAST(si.station_id AS INT64)
  WHERE
    t.start_date BETWEEN TIMESTAMP('2014-01-01') AND TIMESTAMP('2017-12-31 23:59:59')
    AND si.region_id IS NOT NULL
),

-- Step 2: Rank trips per region by latest start date
ranked_trips AS (
  SELECT
    twr.*,
    r.name AS region_name,
    ROW_NUMBER() OVER (PARTITION BY twr.region_id ORDER BY twr.start_date DESC) AS rn
  FROM trips_with_region AS twr
  JOIN `bigquery-public-data.san_francisco_bikeshare.bikeshare_regions` AS r
    ON twr.region_id = r.region_id
)

-- Step 3: Select the latest ride per region
SELECT
  region_name,
  trip_id,
  duration_sec AS ride_duration,
  start_date AS start_time,
  start_station_name AS starting_station,
  member_gender AS gender
FROM ranked_trips
WHERE rn = 1
ORDER BY region_name;
```

---

## 48. Instance: `bq085`
**Question:**
> Could you provide, for the United States, France, China, Italy, Spain, Germany, and Iran, the total number of confirmed COVID-19 cases as of April 20, 2020, along with the number of cases per 100,000 people based on their total 2020 populations calculated by summing all relevant population entries from the World Bank data

### 🏆 Gold Reference Answer
```sql
SELECT
  c.country,
  c.total_confirmed_cases,
  (c.total_confirmed_cases / p.population) * 100000 AS cases_per_100k
FROM
  (
    SELECT
      CASE
        WHEN country_region = 'US' THEN 'United States'
        WHEN country_region = 'Iran' THEN 'Iran, Islamic Rep.'
        ELSE country_region
      END AS country,
      SUM(confirmed) AS total_confirmed_cases
    FROM
      `bigquery-public-data.covid19_jhu_csse.summary`
    WHERE
      date = '2020-04-20'
      AND country_region IN ('US', 'France', 'China', 'Italy', 'Spain', 'Germany', 'Iran')
    GROUP BY
      country
  ) AS c
JOIN
  (
    SELECT
      country_name AS country,
      SUM(value) AS population
    FROM
      `bigquery-public-data.world_bank_wdi.indicators_data`
    WHERE
      indicator_code = 'SP.POP.TOTL'
      AND year = 2020
    GROUP BY
      country_name
  ) AS p
ON
  c.country = p.country
ORDER BY
  cases_per_100k DESC
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Mapping table for country name standardization between datasets
country_mapping AS (
  SELECT 'US' AS covid_name, 'United States' AS wb_name UNION ALL
  SELECT 'France', 'France' UNION ALL
  SELECT 'China', 'China' UNION ALL
  SELECT 'Italy', 'Italy' UNION ALL
  SELECT 'Spain', 'Spain' UNION ALL
  SELECT 'Germany', 'Germany' UNION ALL
  SELECT 'Iran', 'Iran, Islamic Rep.'
),

-- Extract confirmed COVID-19 cases as of April 20, 2020 for the 7 countries
confirmed_cases_data AS (
  SELECT 
    country_or_region,
    SUM(CAST(COALESCE(_4_20_20, '0') AS INT64)) AS total_confirmed_cases
  FROM `bigquery-public-data.covid19_jhu_csse.confirmed_cases`
  WHERE LOWER(country_or_region) IN (
    LOWER('US'), LOWER('France'), LOWER('China'), 
    LOWER('Italy'), LOWER('Spain'), LOWER('Germany'), LOWER('Iran')
  )
  GROUP BY country_or_region
),

-- Get 2020 total population from World Bank WDI data
population_data AS (
  SELECT 
    country_name,
    value AS population_2020
  FROM `bigquery-public-data.world_bank_wdi.indicators_data`
  WHERE indicator_code = 'SP.POP.TOTL'
    AND year = 2020
    AND LOWER(country_name) IN (
      LOWER('United States'), LOWER('France'), LOWER('China'), 
      LOWER('Italy'), LOWER('Spain'), LOWER('Germany'), 
      LOWER('Iran, Islamic Rep.')
    )
)

-- Final query: Join data and calculate cases per 100,000 people
SELECT 
  cm.covid_name AS country,
  cc.total_confirmed_cases AS total_cases,
  ROUND(cc.total_confirmed_cases / pop.population_2020 * 100000, 4) AS cases_per_100k
FROM country_mapping cm
LEFT JOIN confirmed_cases_data cc
  ON cm.covid_name = cc.country_or_region
LEFT JOIN population_data pop
  ON cm.wb_name = pop.country_name
ORDER BY cm.covid_name;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Step 1: Extract confirmed COVID-19 cases for April 20, 2020
covid_cases AS (
  SELECT 
    country_or_region,
    SUM(SAFE_CAST(_4_20_20 AS INT64)) AS total_confirmed_cases
  FROM `bigquery-public-data.covid19_jhu_csse.confirmed_cases`
  WHERE LOWER(country_or_region) IN (
    'united states', 'france', 'china', 'italy', 'spain', 'germany', 'iran'
  )
  GROUP BY country_or_region
),

-- Step 2: Get 2020 total population from World Bank (WDI dataset)
-- SP.POP.TOTL is the standard World Bank indicator for total population
population_data AS (
  SELECT 
    LOWER(country_name) AS country_name,
    SUM(value) AS population_2020
  FROM `bigquery-public-data.world_bank_wdi.indicators_data`
  WHERE indicator_code = 'SP.POP.TOTL'
    AND year = 2020
    AND LOWER(country_name) IN (
      'united states', 'france', 'china', 'italy', 'spain', 'germany', 'iran'
    )
  GROUP BY country_name
)

-- Step 3: Final selection with cases per 100,000 calculation
SELECT 
  c.country_or_region,
  c.total_confirmed_cases,
  ROUND(c.total_confirmed_cases / p.population_2020 * 100000, 4) AS cases_per_100k
FROM covid_cases c
LEFT JOIN population_data p 
  ON LOWER(c.country_or_region) = p.country_name
ORDER BY total_confirmed_cases DESC
```

---

## 49. Instance: `bq086`
**Question:**
> You need to calculate the percentage of each country's population that had been confirmed with COVID-19 by June 30, 2020. The population data for 2018 can be found in the World Bank dataset, and the cumulative COVID-19 confirmed cases data is available in the COVID-19 Open Data dataset. Calculate the percentage of each country's population, that was cumulatively confirmed to have COVID-19

### 🏆 Gold Reference Answer
```sql
WITH
  country_pop AS (
  SELECT
    country_code AS iso_3166_1_alpha_3,
    year_2018 AS population_2018
  FROM
    `bigquery-public-data.world_bank_global_population.population_by_country`)
SELECT
  country_code,
  country_name,
  cumulative_confirmed AS june_confirmed_cases,
  population_2018,
  ROUND(cumulative_confirmed/population_2018 * 100,2) AS case_percent
FROM
  `bigquery-public-data.covid19_open_data.covid19_open_data`
JOIN
  country_pop
USING
  (iso_3166_1_alpha_3)
WHERE
  date = '2020-06-30'
  AND aggregation_level = 0
ORDER BY
  case_percent DESC
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Get cumulative confirmed cases by country as of June 30, 2020
-- Using QUALIFY to deduplicate if multiple records exist per country on that date
covid_data AS (
  SELECT 
    country_code,
    country_name,
    cumulative_confirmed
  FROM `bigquery-public-data.covid19_open_data.covid19_open_data`
  WHERE date = '2020-06-30'
    AND country_code IS NOT NULL
    AND cumulative_confirmed IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY country_code 
    ORDER BY cumulative_confirmed DESC
  ) = 1
),

-- Get population data from World Bank (2018)
population_data AS (
  SELECT 
    country_code,
    year_2018 AS population_2018
  FROM `bigquery-public-data.world_bank_global_population.population_by_country`
  WHERE year_2018 IS NOT NULL
),

-- Map country codes between COVID dataset (ISO-2) and World Bank (ISO-3)
country_mapping AS (
  SELECT 
    two_alpha_code,
    country_code AS wb_country_code
  FROM `bigquery-public-data.world_bank_wdi.country_summary`
  WHERE two_alpha_code IS NOT NULL
)

-- Final calculation: (confirmed / population) * 100
SELECT 
  c.country_name,
  c.country_code,
  p.population_2018,
  c.cumulative_confirmed,
  ROUND(
    SAFE_DIVIDE(c.cumulative_confirmed, p.population_2018) * 100, 
    4
  ) AS confirmed_percentage
FROM covid_data c
INNER JOIN country_mapping cm 
  ON c.country_code = cm.two_alpha_code
INNER JOIN population_data p 
  ON cm.wb_country_code = p.country_code
WHERE p.population_2018 > 0  -- Avoid division by zero
ORDER BY confirmed_percentage DESC
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Get country-level cumulative confirmed cases on or before 2020-06-30
WITH latest_confirmed AS (
  SELECT 
    country_code,
    country_name,
    cumulative_confirmed,
    date,
    ROW_NUMBER() OVER (
      PARTITION BY country_code 
      ORDER BY date DESC
    ) AS rn
  FROM 
    `bigquery-public-data.covid19_open_data.covid19_open_data`
  WHERE 
    date <= '2020-06-30'
    AND subregion1_code IS NULL
    AND subregion2_code IS NULL
    AND locality_code IS NULL
    AND cumulative_confirmed IS NOT NULL
),
-- Step 2: Get one row per country for the confirmed value
confirmed AS (
  SELECT 
    country_code,
    country_name,
    cumulative_confirmed
  FROM 
    latest_confirmed
  WHERE 
    rn = 1
),
-- Step 3: Get country-level population (static, one row per country)
population AS (
  SELECT 
    country_code,
    population
  FROM 
    `bigquery-public-data.covid19_open_data.covid19_open_data`
  WHERE 
    subregion1_code IS NULL
    AND subregion2_code IS NULL
    AND locality_code IS NULL
    AND population IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY country_code) = 1
)
-- Step 4: Compute percentage and output
SELECT 
  c.country_name,
  ROUND(
    (c.cumulative_confirmed / p.population) * 100.0, 
    4
  ) AS infection_percentage
FROM 
  confirmed c
JOIN 
  population p
ON 
  c.country_code = p.country_code
ORDER BY 
  c.country_name;
```

---

## 50. Instance: `bq087`
**Question:**
> Please calculate the overall percentage change in the average weekly search frequency for the symptom 'Anosmia' across the five New York City counties—Bronx County, Queens County, Kings County, New York County, and Richmond County—by comparing the combined data from January 1, 2019, through December 31, 2019, with the combined data from January 1, 2020, through December 31, 2020.

### 🏆 Gold Reference Answer
```sql
SELECT
  table_2019.avg_symptom_Anosmia_2019,
  table_2020.avg_symptom_Anosmia_2020,
  ((table_2020.avg_symptom_Anosmia_2020 - table_2019.avg_symptom_Anosmia_2019) / table_2019.avg_symptom_Anosmia_2019) * 100 AS avg_increase
FROM (
  SELECT
    AVG(SAFE_CAST(symptom_Anosmia AS FLOAT64)) AS avg_symptom_Anosmia_2020
  FROM
    `bigquery-public-data.covid19_symptom_search.symptom_search_sub_region_2_weekly`
  WHERE
    sub_region_1 = "New York"
    AND sub_region_2 IN ("Bronx County", "Queens County", "Kings County", "New York County", "Richmond County")
    AND date >= '2020-01-01'
    AND date < '2021-01-01'
) AS table_2020,
(
  SELECT
    AVG(SAFE_CAST(symptom_Anosmia AS FLOAT64)) AS avg_symptom_Anosmia_2019
  FROM
    `bigquery-public-data.covid19_symptom_search.symptom_search_sub_region_2_weekly`
  WHERE
    sub_region_1 = "New York"
    AND sub_region_2 IN ("Bronx County", "Queens County", "Kings County", "New York County", "Richmond County")
    AND date >= '2019-01-01'
    AND date < '2020-01-01'
) AS table_2019
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Filter weekly data for the five NYC counties and relevant years,
--         then compute the annual average weekly search frequency for Anosmia.
WITH filtered_data AS (
  SELECT
    PARSE_DATE('%Y-%m-%d', date) AS week_date,
    SAFE_CAST(symptom_anosmia AS FLOAT64) AS anosmia_freq,
    sub_region_1,
    EXTRACT(YEAR FROM PARSE_DATE('%Y-%m-%d', date)) AS year
  FROM
    `bigquery-public-data.covid19_symptom_search.symptom_search_sub_region_1_weekly`
  WHERE
    sub_region_1 IN ('Bronx County', 'Queens County', 'Kings County', 'New York County', 'Richmond County')
    AND country_region_code = 'US'
    AND PARSE_DATE('%Y-%m-%d', date) BETWEEN '2019-01-01' AND '2020-12-31'
),
yearly_averages AS (
  SELECT
    year,
    AVG(anosmia_freq) AS avg_weekly_freq
  FROM
    filtered_data
  WHERE
    anosmia_freq IS NOT NULL   -- exclude NULL (from 'None' strings) 
  GROUP BY
    year
),
comparison AS (
  SELECT
    MAX(CASE WHEN year = 2019 THEN avg_weekly_freq END) AS avg_2019,
    MAX(CASE WHEN year = 2020 THEN avg_weekly_freq END) AS avg_2020
  FROM
    yearly_averages
)
SELECT
  ROUND(
    ((avg_2020 - avg_2019) / avg_2019) * 100,
    4
  ) AS percentage_change
FROM
  comparison;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Calculate the overall percentage change in average weekly search frequency for 'Anosmia'
-- across the five NYC counties (Bronx, Queens, Kings, New York, Richmond)
-- by comparing 2019 vs 2020.

WITH yearly_avg AS (
  SELECT
    EXTRACT(YEAR FROM PARSE_DATE('%Y-%m-%d', date)) AS year,
    AVG(SAFE_CAST(symptom_anosmia AS FLOAT64)) AS avg_frequency
  FROM
    `bigquery-public-data.covid19_symptom_search.symptom_search_sub_region_1_weekly`
  WHERE
    country_region_code = 'US'
    AND sub_region_1 IN (
      'Bronx County',
      'Queens County',
      'Kings County',
      'New York County',
      'Richmond County'
    )
    AND EXTRACT(YEAR FROM PARSE_DATE('%Y-%m-%d', date)) IN (2019, 2020)
    -- SAFE_CAST will handle 'None' or invalid strings; no need to filter them out explicitly
  GROUP BY
    year
)

SELECT
  ROUND(
    ( (SELECT avg_frequency FROM yearly_avg WHERE year = 2020)
      - (SELECT avg_frequency FROM yearly_avg WHERE year = 2019) )
    / (SELECT avg_frequency FROM yearly_avg WHERE year = 2019)
    * 100
  , 4) AS percentage_change
```

---

## 51. Instance: `bq088`
**Question:**
> Please calculate the average levels of anxiety and depression symptoms from the weekly country data for the United States during the periods from January 1, 2019, to January 1, 2020, and from January 1, 2020, to January 1, 2021. Then, compute the percentage increase in these average symptom levels from the 2019 period to the 2020 period.

### 🏆 Gold Reference Answer
```sql
SELECT
  table_2019.avg_symptom_Anxiety_2019,
  table_2020.avg_symptom_Anxiety_2020,
  ((table_2020.avg_symptom_Anxiety_2020 - table_2019.avg_symptom_Anxiety_2019)/table_2019.avg_symptom_Anxiety_2019) * 100 AS percent_increase_anxiety,
  table_2019.avg_symptom_Depression_2019,
  table_2020.avg_symptom_Depression_2020,
  ((table_2020.avg_symptom_Depression_2020 - table_2019.avg_symptom_Depression_2019)/table_2019.avg_symptom_Depression_2019) * 100 AS percent_increase_depression
FROM (
  SELECT
    AVG(CAST(symptom_Anxiety AS FLOAT64)) AS avg_symptom_Anxiety_2020,
    AVG(CAST(symptom_Depression AS FLOAT64)) AS avg_symptom_Depression_2020,
  FROM
    `bigquery-public-data.covid19_symptom_search.symptom_search_country_weekly`
  WHERE
    country_region_code = "US"
    AND date >= '2020-01-01'
    AND date <'2021-01-01') AS table_2020,
  (
  SELECT
    AVG(CAST(symptom_Anxiety AS FLOAT64)) AS avg_symptom_Anxiety_2019,
    AVG(CAST(symptom_Depression AS FLOAT64)) AS avg_symptom_Depression_2019,
  FROM
    `bigquery-public-data.covid19_symptom_search.symptom_search_country_weekly`
  WHERE
    country_region_code = "US"
    AND date >= '2019-01-01'
    AND date <'2020-01-01') AS table_2019
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Extract weekly US data, parse dates, and cast symptom columns to numeric
WITH us_weekly AS (
  SELECT
    SAFE_CAST(symptom_anxiety AS FLOAT64) AS anxiety,
    SAFE_CAST(symptom_depression AS FLOAT64) AS depression,
    PARSE_DATE('%Y-%m-%d', date) AS week_date
  FROM `bigquery-public-data.covid19_symptom_search.symptom_search_country_weekly`
  WHERE country_region_code = 'US'
    AND date IS NOT NULL
),

-- Step 2: Compute average anxiety and depression for each period
period_averages AS (
  SELECT
    AVG(CASE
          WHEN week_date >= '2019-01-01' AND week_date < '2020-01-01'
          THEN anxiety
        END) AS avg_anxiety_2019,
    AVG(CASE
          WHEN week_date >= '2020-01-01' AND week_date < '2021-01-01'
          THEN anxiety
        END) AS avg_anxiety_2020,
    AVG(CASE
          WHEN week_date >= '2019-01-01' AND week_date < '2020-01-01'
          THEN depression
        END) AS avg_depression_2019,
    AVG(CASE
          WHEN week_date >= '2020-01-01' AND week_date < '2021-01-01'
          THEN depression
        END) AS avg_depression_2020
  FROM us_weekly
)

-- Step 3: Calculate percentage increase and round to 4 decimal places
SELECT
  ROUND(
    (avg_anxiety_2020 - avg_anxiety_2019) / avg_anxiety_2019 * 100,
    4
  ) AS anxiety_pct_increase,
  ROUND(
    (avg_depression_2020 - avg_depression_2019) / avg_depression_2019 * 100,
    4
  ) AS depression_pct_increase
FROM period_averages;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Compute average anxiety and depression symptom levels for two time periods
-- from the weekly country data for the United States, then calculate percentage increase.

WITH
  -- Filter and clean data for US only, casting string values to numeric
  us_weekly AS (
    SELECT
      SAFE_CAST(symptom_anxiety AS FLOAT64) AS anxiety,
      SAFE_CAST(symptom_depression AS FLOAT64) AS depression,
      PARSE_DATE('%Y-%m-%d', date) AS week_date
    FROM `bigquery-public-data.covid19_symptom_search.symptom_search_country_weekly`
    WHERE country_region_code = 'US'
      -- Exclude rows where either symptom value is 'None' or not parseable
      AND SAFE_CAST(symptom_anxiety AS FLOAT64) IS NOT NULL
      AND SAFE_CAST(symptom_depression AS FLOAT64) IS NOT NULL
  ),

  -- Period 1: 2019-01-01 to 2020-01-01 (exclusive of end date)
  period_2019 AS (
    SELECT
      AVG(anxiety) AS avg_anxiety_2019,
      AVG(depression) AS avg_depression_2019
    FROM us_weekly
    WHERE week_date >= '2019-01-01' AND week_date < '2020-01-01'
  ),

  -- Period 2: 2020-01-01 to 2021-01-01 (exclusive of end date)
  period_2020 AS (
    SELECT
      AVG(anxiety) AS avg_anxiety_2020,
      AVG(depression) AS avg_depression_2020
    FROM us_weekly
    WHERE week_date >= '2020-01-01' AND week_date < '2021-01-01'
  )

-- Final calculation: combine periods and compute percentage increase
SELECT
  ROUND(p2019.avg_anxiety_2019, 4) AS avg_anxiety_2019,
  ROUND(p2020.avg_anxiety_2020, 4) AS avg_anxiety_2020,
  ROUND(
    (p2020.avg_anxiety_2020 - p2019.avg_anxiety_2019) / p2019.avg_anxiety_2019 * 100,
    4
  ) AS anxiety_pct_increase,
  ROUND(p2019.avg_depression_2019, 4) AS avg_depression_2019,
  ROUND(p2020.avg_depression_2020, 4) AS avg_depression_2020,
  ROUND(
    (p2020.avg_depression_2020 - p2019.avg_depression_2019) / p2019.avg_depression_2019 * 100,
    4
  ) AS depression_pct_increase
FROM period_2019 p2019
CROSS JOIN period_2020 p2020;
```

---

## 52. Instance: `bq089`
**Question:**
> Given the latest population estimates from the 2018 five-year American Community Survey, what is the number of vaccine sites per 1000 people for counties in California?

### 🏆 Gold Reference Answer
```sql
WITH
  num_vaccine_sites_per_county AS (
  SELECT
    facility_sub_region_1 AS us_state,
    facility_sub_region_2 AS us_county,
    facility_sub_region_2_code AS us_county_fips,
    COUNT(DISTINCT facility_place_id) AS num_vaccine_sites
  FROM
    bigquery-public-data.covid19_vaccination_access.facility_boundary_us_all
  WHERE
    STARTS_WITH(facility_sub_region_2_code, "06")
  GROUP BY
    facility_sub_region_1,
    facility_sub_region_2,
    facility_sub_region_2_code ),
  total_population_per_county AS (
  SELECT
    LEFT(geo_id, 5) AS us_county_fips,
    ROUND(SUM(total_pop)) AS total_population
  FROM
    bigquery-public-data.census_bureau_acs.censustract_2018_5yr
  WHERE
    STARTS_WITH(LEFT(geo_id, 5), "06")
  GROUP BY
    LEFT(geo_id, 5) )
SELECT
  * EXCEPT(us_county_fips),
  ROUND((num_vaccine_sites * 1000) / total_population, 2) AS sites_per_1k_ppl
FROM
  num_vaccine_sites_per_county
INNER JOIN
  total_population_per_county
USING
  (us_county_fips)
ORDER BY
  sites_per_1k_ppl ASC
LIMIT
  100;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Count vaccine sites per county in California and calculate per 1000 population
WITH vaccine_sites AS (
    SELECT 
        facility_sub_region_2_code AS county_fips,
        COUNT(DISTINCT facility_place_id) AS site_count
    FROM `bigquery-public-data.covid19_vaccination_access.facility_boundary_us_all`
    WHERE facility_sub_region_1 = 'California'
      AND facility_country_region_code = 'US'
    GROUP BY facility_sub_region_2_code
),
population_data AS (
    SELECT 
        geo_id AS county_fips,
        total_pop
    FROM `bigquery-public-data.census_bureau_acs.county_2018_5yr`
    WHERE geo_id LIKE '06%'  -- California FIPS codes start with 06
      AND total_pop IS NOT NULL
)
SELECT 
    p.county_fips,
    ROUND(COALESCE(v.site_count, 0) / p.total_pop * 1000, 4) AS sites_per_1000_people
FROM population_data p
LEFT JOIN vaccine_sites v ON p.county_fips = v.county_fips
ORDER BY p.county_fips;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH california_counties AS (
  -- Extract all California counties (FIPS codes starting with '06') and their population
  SELECT 
    geo_id,
    total_pop
  FROM `bigquery-public-data.census_bureau_acs.county_2018_5yr`
  WHERE STARTS_WITH(geo_id, '06')        -- California state FIPS is 06
    AND total_pop IS NOT NULL
),

vaccine_sites_by_county AS (
  -- Count distinct vaccine sites per California county from the comprehensive facility table
  SELECT 
    facility_sub_region_2_code AS geo_id,
    COUNT(DISTINCT facility_place_id) AS site_count
  FROM `bigquery-public-data.covid19_vaccination_access.facility_boundary_us_all`
  WHERE facility_country_region_code = 'US'
    AND facility_sub_region_1_code = 'US-CA'
  GROUP BY facility_sub_region_2_code
)

SELECT 
  c.geo_id,
  c.total_pop,
  COALESCE(v.site_count, 0) AS site_count,
  ROUND(COALESCE(v.site_count, 0) * 1000.0 / NULLIF(c.total_pop, 0), 4) AS sites_per_1000
FROM california_counties c
LEFT JOIN vaccine_sites_by_county v
  ON c.geo_id = v.geo_id
ORDER BY c.geo_id;
```

---

## 53. Instance: `bq090`
**Question:**
> How much higher the average intrinsic value is for trades using the feeling-lucky strategy compared to those using the momentum strategy under long-side trades?

### 🏆 Gold Reference Answer
```sql
WITH MomentumTrades AS (
  SELECT
    StrikePrice - LastPx AS priceDifference
  FROM
    `bigquery-public-data.cymbal_investments.trade_capture_report`
  WHERE
    SUBSTR(TargetCompID, 0, 4) = 'MOMO'
    AND (SELECT Side FROM UNNEST(Sides)) = 'LONG'
),

FeelingLuckyTrades AS (
  SELECT
    StrikePrice - LastPx AS priceDifference
  FROM
    `bigquery-public-data.cymbal_investments.trade_capture_report`
  WHERE
    SUBSTR(TargetCompID, 0, 4) = 'LUCK'
    AND (SELECT Side FROM UNNEST(Sides)) = 'LONG'
)

SELECT
  AVG(FeelingLuckyTrades.priceDifference) - AVG(MomentumTrades.priceDifference) AS averageDifference 
FROM
  MomentumTrades,
  FeelingLuckyTrades
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Compute the difference in average intrinsic value between feeling-lucky and momentum strategies,
-- considering only long-side trades.
WITH
  -- 1) Unnest the Sides array to get individual side rows, keep only LONG trades
  long_trades AS (
    SELECT
      t.StrikePrice,
      t.LastPx,
      t.TargetCompID,
      (t.StrikePrice - t.LastPx) AS intrinsic_value
    FROM
      `bigquery-public-data.cymbal_investments.trade_capture_report` t
      CROSS JOIN UNNEST(t.Sides) AS side_struct
    WHERE
      side_struct.Side = 'LONG'
  ),
  -- 2) Classify trades into the two strategies based on TargetCompID patterns
  strategy_groups AS (
    SELECT
      intrinsic_value,
      CASE
        WHEN LOWER(TargetCompID) LIKE '%momo%'   THEN 'momentum'
        WHEN LOWER(TargetCompID) LIKE '%lucky%'
          OR LOWER(TargetCompID) LIKE '%feeling%' THEN 'feeling_lucky'
        ELSE NULL
      END AS strategy
    FROM long_trades
    WHERE
      LOWER(TargetCompID) LIKE '%momo%'
      OR LOWER(TargetCompID) LIKE '%lucky%'
      OR LOWER(TargetCompID) LIKE '%feeling%'
  ),
  -- 3) Compute average intrinsic value per strategy
  avg_feeling_lucky AS (
    SELECT AVG(intrinsic_value) AS avg_intrinsic
    FROM strategy_groups
    WHERE strategy = 'feeling_lucky'
  ),
  avg_momentum AS (
    SELECT AVG(intrinsic_value) AS avg_intrinsic
    FROM strategy_groups
    WHERE strategy = 'momentum'
  )
-- 4) Compute the difference
SELECT
  ROUND(
    (SELECT avg_intrinsic FROM avg_feeling_lucky) -
    (SELECT avg_intrinsic FROM avg_momentum),
    4
  ) AS avg_intrinsic_difference;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
  -- Unnest the Sides array and keep only LONG side trades
  long_trades AS (
    SELECT
      t.*,
      s.Side,  -- Should be 'LONG' after filtering
      t.StrikePrice - t.LastPx AS intrinsic_value
    FROM
      `bigquery-public-data.cymbal_investments.trade_capture_report` t,
      UNNEST(t.Sides) AS s
    WHERE
      s.Side = 'LONG'
  ),
  -- Classify each trade into a strategy based on TargetCompID
  trades_with_strategy AS (
    SELECT
      intrinsic_value,
      CASE
        WHEN LOWER(TargetCompID) LIKE '%momo%' THEN 'momentum'
        WHEN LOWER(TargetCompID) LIKE '%lucky%' THEN 'feeling-lucky'
        ELSE NULL
      END AS strategy
    FROM long_trades
  ),
  -- Compute average intrinsic value per strategy
  avg_per_strategy AS (
    SELECT
      strategy,
      ROUND(AVG(intrinsic_value), 4) AS avg_intrinsic
    FROM trades_with_strategy
    WHERE strategy IS NOT NULL
    GROUP BY strategy
  )
-- Compute the difference (feeling-lucky minus momentum)
SELECT
  ROUND(
    MAX(CASE WHEN strategy = 'feeling-lucky' THEN avg_intrinsic END) -
    MAX(CASE WHEN strategy = 'momentum' THEN avg_intrinsic END),
    4
  ) AS difference_avg_intrinsic_feeling_lucky_over_momentum
FROM avg_per_strategy;
```

---

## 54. Instance: `bq094`
**Question:**
> Please provide a list of all 2016 committees that supported at least one candidate and received a total amount of individual contributions between $0 and $200 (inclusive of more than $0 and less than $200) where these small-dollar contributions sum to more than $0 overall. For each qualifying committee, include its name, the number of unique candidates it supported, the candidates’ names in alphabetical order (separated by commas), and the total sum of these small-dollar donations received by the committee.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Identify committees that supported at least one candidate in 2016.
-- We use the candidate_committee_2016 table to find committees linked to a candidate for the 2016 election.
-- We also use committee_2016 to get committee names.

WITH candidate_support AS (
    SELECT DISTINCT
        cc.cmte_id,
        cc.cand_id
    FROM `bigquery-public-data.fec.candidate_committee_2016` cc
    WHERE cc.fec_election_yr = 2016
),

-- Step 2: For each such committee, get the associated candidate names from the candidate_2016 table.
committee_candidates AS (
    SELECT
        cs.cmte_id,
        c.cand_name
    FROM candidate_support cs
    INNER JOIN `bigquery-public-data.fec.candidate_2016` c
        ON cs.cand_id = c.cand_id
),

-- Step 3: Aggregate to get the count of unique candidates per committee and their names (alphabetically).
-- Also filter for committees that supported at least one candidate.
committee_summary AS (
    SELECT
        cmte_id,
        COUNT(DISTINCT cand_name) AS num_candidates,
        STRING_AGG(DISTINCT cand_name ORDER BY cand_name ASC) AS candidate_names
    FROM committee_candidates
    GROUP BY cmte_id
    HAVING COUNT(DISTINCT cand_name) > 0
),

-- Step 4: From the committee_contributions_2016 table, get all individual contributions (where other_id is NULL indicates individual).
-- Filter for contributions with transaction amount between 0 and 200 (exclusive of 0 and 200, but inclusive of the bounds? 
-- The question says "between $0 and $200 (inclusive of more than $0 and less than $200)". This means >0 and <200.
-- Also "small-dollar contributions sum to more than $0 overall" meaning total > 0.
individual_small_dollars AS (
    SELECT
        cmte_id,
        transaction_amt
    FROM `bigquery-public-data.fec.committee_contributions_2016`
    WHERE other_id IS NULL  -- Individual contributions
        AND transaction_amt > 0
        AND transaction_amt < 200
),

-- Step 5: Aggregate small-dollar contributions per committee.
small_dollar_totals AS (
    SELECT
        cmte_id,
        SUM(transaction_amt) AS total_small_dollars
    FROM individual_small_dollars
    GROUP BY cmte_id
    HAVING SUM(transaction_amt) > 0
),

-- Step 6: Combine with committee names and ensure the committee is in the 2016 committee table.
final_committees AS (
    SELECT
        com.cmte_nm AS committee_name,
        cs.num_candidates,
        cs.candidate_names,
        sdt.total_small_dollars
    FROM `bigquery-public-data.fec.committee_2016` com
    INNER JOIN committee_summary cs
        ON com.cmte_id = cs.cmte_id
    INNER JOIN small_dollar_totals sdt
        ON com.cmte_id = sdt.cmte_id
)

-- Step 7: Return the final result
SELECT
    committee_name,
    num_candidates,
    candidate_names,
    total_small_dollars
FROM final_committees
ORDER BY committee_name;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Step 1: Filter contributions to small-dollar amounts (between $0 and $200 inclusive, but more than $0 and less than $200)
small_dollar_contributions AS (
    SELECT 
        cmte_id,
        cand_id,
        transaction_amt
    FROM `bigquery-public-data.fec.committee_contributions_2016`
    WHERE transaction_amt > 0 
      AND transaction_amt < 200
),

-- Step 2: Aggregate small-dollar contributions per committee and count unique candidates
committee_agg AS (
    SELECT 
        cmte_id,
        COUNT(DISTINCT cand_id) AS unique_candidate_count,
        SUM(transaction_amt) AS total_small_dollar_sum
    FROM small_dollar_contributions
    WHERE cand_id IS NOT NULL 
      AND cand_id != 'None'
    GROUP BY cmte_id
    HAVING COUNT(DISTINCT cand_id) >= 1 
       AND SUM(transaction_amt) > 0
),

-- Step 3: Identify committees that supported at least one candidate (via candidate_committee_2016 linkage)
supported_committees AS (
    SELECT DISTINCT 
        cc.cmte_id
    FROM `bigquery-public-data.fec.candidate_committee_2016` cc
    WHERE cc.fec_election_yr = 2016
),

-- Step 4: Combine all filters and get candidate names per committee
committee_candidates AS (
    SELECT 
        ca.cmte_id,
        ca.unique_candidate_count,
        ca.total_small_dollar_sum,
        STRING_AGG(DISTINCT c.cand_name ORDER BY c.cand_name) AS candidate_names
    FROM committee_agg ca
    INNER JOIN supported_committees sc ON ca.cmte_id = sc.cmte_id
    INNER JOIN `bigquery-public-data.fec.candidate_committee_2016` cc 
        ON ca.cmte_id = cc.cmte_id 
        AND cc.fec_election_yr = 2016
    INNER JOIN `bigquery-public-data.fec.candidate_2016` c 
        ON cc.cand_id = c.cand_id
    GROUP BY ca.cmte_id, ca.unique_candidate_count, ca.total_small_dollar_sum
)

-- Step 5: Get committee names and produce final output
SELECT 
    c.cmte_nm AS committee_name,
    cc.unique_candidate_count,
    cc.candidate_names,
    cc.total_small_dollar_sum
FROM committee_candidates cc
INNER JOIN `bigquery-public-data.fec.committee_2016` c 
    ON cc.cmte_id = c.cmte_id
ORDER BY committee_name;
```

---

## 55. Instance: `bq096`
**Question:**
> Determine which year had the earliest date after January on which more than 10 sightings of Sterna paradisaea were recorded north of 40 degrees latitude. For each year, find the first day after January with over 10 sightings of this species in that region, and identify the year whose earliest such date is the earliest among all years.

### 🏆 Gold Reference Answer
```sql
WITH tenplus AS (
  SELECT 
    year, 
    EXTRACT(DAYOFYEAR FROM DATE(eventdate)) AS dayofyear, 
    COUNT(*) AS count
  FROM 
    bigquery-public-data.gbif.occurrences
  WHERE 
    eventdate IS NOT NULL 
    AND species = 'Sterna paradisaea' 
    AND decimallatitude > 40.0 
    AND month > 1
  GROUP BY 
    year, 
    eventdate
  HAVING 
    COUNT(*) > 10
)

SELECT 
  year AS year
FROM 
  tenplus
GROUP BY 
  year
ORDER BY 
  MIN(dayofyear)
LIMIT 1;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
  -- Step 1: Filter sightings of Sterna paradisaea north of 40° latitude, after January
  filtered_sightings AS (
    SELECT
      year,
      month,
      day
    FROM
      `bigquery-public-data.gbif.occurrences`
    WHERE
      LOWER(species) LIKE '%sterna paradisaea%'
      AND decimallatitude > 40.0
      AND month > 1
      AND year IS NOT NULL
      AND month IS NOT NULL
      AND day IS NOT NULL
  ),

  -- Step 2: Count sightings per year-month-day
  daily_counts AS (
    SELECT
      year,
      month,
      day,
      COUNT(*) AS sightings_count
    FROM
      filtered_sightings
    GROUP BY
      year, month, day
    HAVING
      COUNT(*) > 10
  ),

  -- Step 3: For each year, find the earliest date with >10 sightings
  yearly_first_date AS (
    SELECT
      year,
      MIN(DATE(year, month, day)) AS earliest_date
    FROM
      daily_counts
    GROUP BY
      year
  )

-- Step 4: Find the year with the earliest such date
SELECT
  year,
  earliest_date
FROM
  yearly_first_date
ORDER BY
  earliest_date ASC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Compute daily count of sightings for Sterna paradisaea north of 40°N, after January
WITH daily_counts AS (
  SELECT
    year,
    month,
    day,
    COUNT(*) AS cnt
  FROM `bigquery-public-data.gbif.occurrences`
  WHERE
    species = 'Sterna paradisaea'
    AND decimallatitude > 40.0
    AND month > 1            -- after January
    AND year IS NOT NULL
    AND month IS NOT NULL
    AND day IS NOT NULL
  GROUP BY year, month, day
  HAVING cnt > 10
),

-- Step 2: For each year, rank dates by month and day (earliest first)
ranked_per_year AS (
  SELECT
    year,
    month,
    day,
    cnt,
    ROW_NUMBER() OVER (PARTITION BY year ORDER BY month, day) AS rn
  FROM daily_counts
)

-- Step 3: Keep only the first qualifying date per year, then pick the year with the earliest calendar date
SELECT
  year,
  month,
  day
FROM ranked_per_year
WHERE rn = 1
ORDER BY month, day   -- earliest calendar date (ignoring year)
LIMIT 1;
```

---

## 56. Instance: `bq097`
**Question:**
> What is the increasing amount of the average earnings per job between the years 2012 and 2017 for each geographic region in Massachusetts (indicated by "MA" at the end of GeoName)?

### 🏆 Gold Reference Answer
```sql
WITH bea_2012 AS (
  SELECT GeoFIPS, GeoName, Earnings_per_job_avg AS earnings_2012
  FROM `bigquery-public-data.sdoh_bea_cainc30.fips`
  WHERE Year='2012-01-01' AND ENDS_WITH(GeoName, "MA") IS TRUE
),

bea_2017 AS (
  SELECT GeoFIPS, GeoName, Earnings_per_job_avg AS earnings_2017
  FROM `bigquery-public-data.sdoh_bea_cainc30.fips`
  WHERE Year='2017-01-01' AND ENDS_WITH(GeoName, "MA") IS TRUE
),

earnings_diff AS (
  SELECT
    bea_2017.GeoFIPS, bea_2017.GeoName, bea_2017.earnings_2017, bea_2012.earnings_2012, 
    (bea_2017.earnings_2017 - bea_2012.earnings_2012) AS earnings_change
   FROM bea_2017 
   JOIN bea_2012
   ON bea_2017.GeoFIPS = bea_2012.GeoFIPS
)
 
SELECT * FROM earnings_diff WHERE earnings_change IS NOT NULL ORDER BY earnings_change DESC
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Compute the increase in average earnings per job from 2012 to 2017
-- for each Massachusetts county (GeoName ending with ', MA')
WITH earnings_2012 AS (
  SELECT GeoName, Earnings_per_job_avg
  FROM `bigquery-public-data.sdoh_bea_cainc30.fips`
  WHERE EXTRACT(YEAR FROM Year) = 2012
),
earnings_2017 AS (
  SELECT GeoName, Earnings_per_job_avg
  FROM `bigquery-public-data.sdoh_bea_cainc30.fips`
  WHERE EXTRACT(YEAR FROM Year) = 2017
)
SELECT
  e2012.GeoName,
  e2017.Earnings_per_job_avg - e2012.Earnings_per_job_avg AS increase_amount
FROM earnings_2012 e2012
INNER JOIN earnings_2017 e2017
  ON e2012.GeoName = e2017.GeoName
WHERE e2012.GeoName LIKE '%, MA'  -- indicates Massachusetts
ORDER BY e2012.GeoName;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH earnings_2012 AS (
  SELECT 
    GeoName,
    Earnings_per_job_avg AS earnings_2012
  FROM `bigquery-public-data.sdoh_bea_cainc30.fips`
  WHERE GeoName LIKE '%MA'
    AND EXTRACT(YEAR FROM year) = 2012
),
earnings_2017 AS (
  SELECT 
    GeoName,
    Earnings_per_job_avg AS earnings_2017
  FROM `bigquery-public-data.sdoh_bea_cainc30.fips`
  WHERE GeoName LIKE '%MA'
    AND EXTRACT(YEAR FROM year) = 2017
)
SELECT 
  e2012.GeoName,
  e2012.earnings_2012,
  e2017.earnings_2017,
  ROUND(e2017.earnings_2017 - e2012.earnings_2012, 4) AS increase_amount
FROM earnings_2012 e2012
JOIN earnings_2017 e2017
  ON e2012.GeoName = e2017.GeoName
ORDER BY increase_amount DESC;
```

---

## 57. Instance: `bq098`
**Question:**
> For NYC yellow taxi trips where both the pickup and dropoff occurred between January 1 and 7, 2016, inclusive, calculate the percentage of trips with no tip in each pickup borough, ensuring that only trips where the dropoff occurs after the pickup are included, the passenger count is greater than zero, and the trip distance, tip amount, tolls amount, MTA tax, fare amount, and total amount are non-negative; define "no tip" trips as those where the tip rate is zero, with the tip rate calculated as (tip_amount × 100) divided by total_amount (and considered zero when total_amount is zero).

### 🏆 Gold Reference Answer
```sql
WITH t2 AS
(
SELECT 
    t.*,
    t.pickup_location_id as pickup_zone_id,
    tz.borough as pickup_borough
FROM
(
SELECT *,
    TIMESTAMP_DIFF(dropoff_datetime,pickup_datetime,SECOND) as time_duration_in_secs,
    (CASE WHEN total_amount=0 THEN 0
    ELSE (tip_amount*100/total_amount) END) as tip_rate
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016`
) t
INNER JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` tz
ON t.pickup_location_id = tz.zone_id
WHERE 
    pickup_datetime BETWEEN '2016-01-01' AND '2016-01-07' 
    AND dropoff_datetime BETWEEN '2016-01-01' AND '2016-01-07'
    AND TIMESTAMP_DIFF(dropoff_datetime,pickup_datetime,SECOND) > 0
    AND passenger_count > 0
    AND trip_distance >= 0 
    AND tip_amount >= 0 
    AND tolls_amount >= 0 
    AND mta_tax >= 0 
    AND fare_amount >= 0
    AND total_amount >= 0
),
t3 AS
(SELECT 
pickup_borough,
(CASE 
    WHEN tip_rate = 0 THEN 'no tip'
    WHEN tip_rate <= 5 THEN 'Less than 5%'
    WHEN tip_rate <= 10 THEN '5% to 10%'
    WHEN tip_rate <= 15 THEN '10% to 15%'
    WHEN tip_rate <= 20 THEN '15% to 20%'
    WHEN tip_rate <= 25 THEN '20% to 25%'
    ELSE 'More than 25%' END)as tip_category,
COUNT(*) as no_of_trips
FROM t2
GROUP BY 1,2
ORDER BY pickup_borough ASC),
INFO AS (
SELECT pickup_borough
     , tip_category
     , Sum(no_of_trips) as no_of_trips,
     (CASE 
          WHEN pickup_borough is null THEN (select sum(no_of_trips)
          FROM t3)
          
          WHEN pickup_borough is not null and tip_category is null THEN (select sum(no_of_trips)
          FROM t3)
          
          WHEN pickup_borough is not null and tip_category is not null THEN (select sum(no_of_trips)
          FROM t3
          WHERE pickup_borough = m.pickup_borough)
          END) as parent_sum,
       (
          Sum(no_of_trips)
            /
          (
            CASE 
          WHEN pickup_borough is null THEN (select sum(no_of_trips)
          FROM t3)
          
          WHEN pickup_borough is not null and tip_category is null THEN (select sum(no_of_trips)
          FROM t3)
          
          WHEN pickup_borough is not null and tip_category is not null THEN (select sum(no_of_trips)
          FROM t3
          WHERE pickup_borough = m.pickup_borough)
          END
          )
        ) as percentage
FROM t3 m
GROUP BY ROLLUP(pickup_borough, tip_category)
order by 1, 2
)

SELECT 
    pickup_borough,
    (SUM(CASE WHEN tip_category = 'no tip' THEN no_of_trips ELSE 0 END) * 100.0 / SUM(no_of_trips)) AS percentage_no_tip
FROM t3
GROUP BY pickup_borough
ORDER BY pickup_borough;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Filter trips meeting all constraints and compute no-tip indicator
WITH filtered_trips AS (
  SELECT
    pickup_location_id,
    -- Define no_tip: tip_rate = 0, i.e., tip_amount = 0 OR total_amount = 0
    CASE
      WHEN tip_amount = 0 OR total_amount = 0 THEN 1
      ELSE 0
    END AS no_tip
  FROM
    `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016`
  WHERE
    -- Date range: pickup and dropoff between Jan 1 and Jan 7, 2016 inclusive
    pickup_datetime BETWEEN TIMESTAMP('2016-01-01') AND TIMESTAMP('2016-01-07 23:59:59')
    AND dropoff_datetime BETWEEN TIMESTAMP('2016-01-01') AND TIMESTAMP('2016-01-07 23:59:59')
    -- Dropoff after pickup
    AND dropoff_datetime > pickup_datetime
    -- Passenger count > 0
    AND passenger_count > 0
    -- Non-negative amounts
    AND trip_distance >= 0
    AND tip_amount >= 0
    AND tolls_amount >= 0
    AND mta_tax >= 0
    AND fare_amount >= 0
    AND total_amount >= 0
),

-- Step 2: Join with taxi zone geometry to get pickup borough
trips_with_borough AS (
  SELECT
    t.no_tip,
    z.borough
  FROM
    filtered_trips t
  INNER JOIN
    `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` z
  ON
    t.pickup_location_id = z.zone_id
)

-- Step 3: Compute percentage of no-tip trips per borough
SELECT
  borough,
  ROUND(100 * SUM(no_tip) / COUNT(*), 4) AS no_tip_percentage
FROM
  trips_with_borough
GROUP BY
  borough
ORDER BY
  borough;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Pre-filter yellow taxi trips for Jan 1-7, 2016 with all conditions
WITH filtered_trips AS (
  SELECT
    pickup_location_id,
    -- Define no_tip flag using SAFE_DIVIDE to handle total_amount = 0
    COALESCE(SAFE_DIVIDE(tip_amount * 100, total_amount), 0) = 0 AS is_no_tip
  FROM
    `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016`
  WHERE
    -- Both pickup and dropoff dates between Jan 1 and Jan 7, 2016 inclusive
    DATE(pickup_datetime) BETWEEN '2016-01-01' AND '2016-01-07'
    AND DATE(dropoff_datetime) BETWEEN '2016-01-01' AND '2016-01-07'
    -- Dropoff after pickup
    AND dropoff_datetime > pickup_datetime
    -- Passenger count > 0
    AND passenger_count > 0
    -- Non‑negative required numeric fields
    AND trip_distance >= 0
    AND tip_amount >= 0
    AND tolls_amount >= 0
    AND mta_tax >= 0
    AND fare_amount >= 0
    AND total_amount >= 0
),

-- Step 2: Join with taxi zones to get pickup borough
trips_with_borough AS (
  SELECT
    t.is_no_tip,
    z.borough AS pickup_borough
  FROM filtered_trips t
  LEFT JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` z
    ON t.pickup_location_id = z.zone_id
  -- Exclude trips without a matching zone (unusual)
  WHERE z.borough IS NOT NULL
)

-- Step 3: Aggregate and compute percentage
SELECT
  pickup_borough,
  ROUND(
    100.0 * SUM(CASE WHEN is_no_tip THEN 1 ELSE 0 END) / COUNT(*),
    4
  ) AS no_tip_percentage
FROM trips_with_borough
GROUP BY pickup_borough
ORDER BY pickup_borough;
```

---

## 58. Instance: `bq102`
**Question:**
> Identify which start positions are associated with missense variants in the BRCA1 gene on chromosome 17, where the reference base is 'C' and the alternate base is 'T'. Using data from the gnomAD v2.1.1 version.

### 🏆 Gold Reference Answer
```sql
WITH gene_region AS (
  SELECT 
    MIN(start_position) AS start_pos, 
    MAX(end_position) AS end_pos
  FROM `bigquery-public-data.gnomAD.v2_1_1_genomes__chr17` AS main_table
  WHERE EXISTS (
    SELECT 1 
    FROM UNNEST(main_table.alternate_bases) AS alternate_bases
    WHERE EXISTS (
      SELECT 1 
      FROM UNNEST(alternate_bases.vep) AS vep
      WHERE vep.SYMBOL = 'BRCA1'
    )
  )
)


SELECT 
  DISTINCT start_position
FROM `bigquery-public-data.gnomAD.v2_1_1_genomes__chr17` AS main_table,
     UNNEST(main_table.alternate_bases) AS alternate_bases,
     UNNEST(alternate_bases.vep) AS vep,
     gene_region
WHERE main_table.start_position >= gene_region.start_pos
  AND main_table.start_position <= gene_region.end_pos
  AND REGEXP_CONTAINS(vep.Consequence, r"missense_variant")
  AND reference_bases = "C"
  AND alternate_bases.alt = "T"
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Query to find start positions of missense variants in BRCA1 on chr17 with ref=C, alt=T
-- Combines data from gnomAD v2.1.1 exomes and genomes for chromosome 17

WITH exomes_data AS (
  SELECT DISTINCT start_position
  FROM `bigquery-public-data.gnomAD.v2_1_1_exomes__chr17`
  CROSS JOIN UNNEST(alternate_bases) AS alt
  CROSS JOIN UNNEST(alt.annotation) AS ann
  WHERE reference_name = '17'
    AND reference_bases = 'C'
    AND alt.alt = 'T'
    AND ann.Gene = 'BRCA1'
    AND ann.Consequence LIKE '%missense%'
),

genomes_data AS (
  SELECT DISTINCT start_position
  FROM `bigquery-public-data.gnomAD.v2_1_1_genomes__chr17`
  CROSS JOIN UNNEST(alternate_bases) AS alt
  CROSS JOIN UNNEST(alt.annotation) AS ann
  WHERE reference_name = '17'
    AND reference_bases = 'C'
    AND alt.alt = 'T'
    AND ann.Gene = 'BRCA1'
    AND ann.Consequence LIKE '%missense%'
)

-- Combine results from both datasets, removing duplicates
SELECT start_position FROM exomes_data
UNION DISTINCT
SELECT start_position FROM genomes_data
ORDER BY start_position;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
SELECT DISTINCT
  start_position
FROM
  `bigquery-public-data.gnomAD.v2_1_1_exomes__chr17`,
  UNNEST(vep) AS vep
WHERE
  reference_name = 'chr17'
  AND LOWER(vep.SYMBOL) = 'brca1'
  AND LOWER(vep.Consequence) LIKE '%missense%'
  AND reference_bases = 'C'
  AND alternate_bases = 'T'
  AND start_position IS NOT NULL
ORDER BY
  start_position;
```

---

## 59. Instance: `bq103`
**Question:**
> Generate summary statistics on genetic variants in the region between positions 55039447 and 55064852 on chromosome 1. This includes the number of variants, the total allele count, the total number of alleles, and distinct gene symbols (using Variant Effect Predictor, VEP, for gene annotation). Additionally, compute the density of mutations by dividing the length of the region by the number of variants.  Using data from the gnomAD v3 version.

### 🏆 Gold Reference Answer
```sql
WITH summary_stats AS (
  SELECT
    COUNT(1) AS num_variants,
    SUM((SELECT alt.AC FROM UNNEST(alternate_bases) AS alt)) AS sum_AC,
    SUM(AN) AS sum_AN,
    -- Also include some information from Variant Effect Predictor (VEP).
    STRING_AGG(DISTINCT (SELECT annot.symbol FROM UNNEST(alternate_bases) AS alt,
                                               UNNEST(vep) AS annot LIMIT 1), ', ') AS genes
  FROM bigquery-public-data.gnomAD.v3_genomes__chr1 AS main_table
  WHERE start_position >= 55039447 AND start_position <= 55064852
)
SELECT
  ROUND((55064852 - 55039447) / num_variants, 3) AS burden_of_mutation,
  *
FROM summary_stats;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Compute summary statistics for the region chr1:55039447-55064852 using gnomAD v3 genomes data.
-- Metrics: number of variants, total allele count (sum of AC), total number of alleles (sum of AN),
-- distinct gene symbols from VEP annotations, and mutation density (region length / number of variants).

WITH
  -- Step 1: Retrieve all variants in the specified region, including their allele counts and VEP annotations.
  variants AS (
    SELECT
      start_position,
      AC,
      AN,
      vep  -- This is a REPEATED RECORD containing VEP annotations, each with a `SYMBOL` field.
    FROM
      `bigquery-public-data.gnomAD.v3_genomes__chr1`
    WHERE
      reference_name = 'chr1'
      AND start_position BETWEEN 55039447 AND 55064852
  ),
  -- Step 2: Extract distinct gene symbols from all VEP annotations across the variants.
  distinct_genes AS (
    SELECT DISTINCT
      v.SYMBOL AS gene_symbol
    FROM
      variants,
      UNNEST(vep) AS v
  )
-- Step 3: Compute the requested summary statistics.
SELECT
  -- Number of variants in the region.
  (SELECT COUNT(*) FROM variants) AS number_of_variants,

  -- Total allele count (sum of alternate allele counts).
  (SELECT COALESCE(SUM(AC), 0) FROM variants) AS total_allele_count,

  -- Total number of alleles (sum of total allele numbers over all variants).
  (SELECT COALESCE(SUM(AN), 0) FROM variants) AS total_number_of_alleles,

  -- Distinct gene symbols from VEP annotations.
  (SELECT COUNT(*) FROM distinct_genes) AS distinct_gene_symbols,

  -- Mutation density: length of region (positions from 55039447 to 55064852, exclusive difference) 
  -- divided by number of variants. Rounded to 4 decimal places.
  ROUND(
    (55064852 - 55039447) / NULLIF((SELECT COUNT(*) FROM variants), 0),
    4
  ) AS mutation_density;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
  region_variants AS (
    SELECT
      AN,
      alternate_bases
    FROM
      `bigquery-public-data.gnomAD.v3_genomes__chr1`
    WHERE
      start_position BETWEEN 55039446 AND 55064851
  ),
  variant_stats AS (
    SELECT
      COUNT(*) AS num_variants,
      SUM(AN) AS total_allele_count
    FROM region_variants
  ),
  gene_symbols AS (
    SELECT DISTINCT
      vep.Gene AS gene_symbol
    FROM
      region_variants,
      UNNEST(alternate_bases) AS alt,
      UNNEST(alt.vep) AS vep
    WHERE
      vep.Gene IS NOT NULL
  )
SELECT
  vs.num_variants,
  vs.total_allele_count,
  ROUND(25406.0 / vs.num_variants, 4) AS mutation_density,
  (
    SELECT STRING_AGG(gene_symbol, ', ' ORDER BY gene_symbol)
    FROM gene_symbols
  ) AS distinct_gene_symbols
FROM variant_stats AS vs;
```

---

## 60. Instance: `bq105`
**Question:**
> According to the 2015 and 2016 accident and driver distraction, and excluding cases where the driver’s distraction status is recorded as 'Not Distracted,' 'Unknown if Distracted,' or 'Not Reported,' how many traffic accidents per 100,000 people were caused by driver distraction in each U.S. state for those two years, based on 2010 census population data, and which five states each year had the highest rates?

### 🏆 Gold Reference Answer
```sql
SELECT * FROM
(
SELECT
  '2015' AS year,
  COUNT(a.consecutive_number) AS total,
  a.state_name AS state,
  c.state_pop AS population,
  (COUNT(a.consecutive_number) / c.state_pop * 100000) AS rate_per_100000
FROM
  `bigquery-public-data.nhtsa_traffic_fatalities.accident_2015` a
JOIN
  `bigquery-public-data.nhtsa_traffic_fatalities.distract_2015` b
ON
  a.consecutive_number = b.consecutive_number
JOIN (
  SELECT
    SUM(d.population) AS state_pop,
    e.state_name AS state
  FROM
    `bigquery-public-data.census_bureau_usa.population_by_zip_2010` d
  JOIN
    `bigquery-public-data.utility_us.zipcode_area` e
  ON
    d.zipcode = e.zipcode
  GROUP BY
    state ) c
ON
  c.state = a.state_name
WHERE
  b.driver_distracted_by_name NOT IN ('Not Distracted', 'Unknown if Distracted', 'Not Reported')
GROUP BY
  state,
  population,
  c.state_pop
ORDER BY
  rate_per_100000 DESC
LIMIT 5
)
UNION ALL
(
SELECT
  '2016' AS year,
  COUNT(a.consecutive_number) AS total,
  a.state_name AS state,
  c.state_pop AS population,
  (COUNT(a.consecutive_number) / c.state_pop * 100000) AS rate_per_100000
FROM
  `bigquery-public-data.nhtsa_traffic_fatalities.accident_2016` a
JOIN
  `bigquery-public-data.nhtsa_traffic_fatalities.distract_2016` b
ON
  a.consecutive_number = b.consecutive_number
JOIN (
  SELECT
    SUM(d.population) AS state_pop,
    e.state_name AS state
  FROM
    `bigquery-public-data.census_bureau_usa.population_by_zip_2010` d
  JOIN
    `bigquery-public-data.utility_us.zipcode_area` e
  ON
    d.zipcode = e.zipcode
  GROUP BY
    state ) c
ON
  c.state = a.state_name
WHERE
  b.driver_distracted_by_name NOT IN ('Not Distracted', 'Unknown if Distracted', 'Not Reported')
GROUP BY
  state,
  population,
  c.state_pop
ORDER BY
  rate_per_100000 DESC
LIMIT 5
)
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Get distracted accidents for 2015 and 2016, excluding specified statuses
distracted_accidents AS (
    SELECT consecutive_number, state_number, state_name, 2015 AS year
    FROM `bigquery-public-data.nhtsa_traffic_fatalities.distract_2015`
    WHERE driver_distracted_by_name NOT IN ('Not Distracted', 'Unknown if Distracted', 'Not Reported')
    UNION ALL
    SELECT consecutive_number, state_number, state_name, 2016 AS year
    FROM `bigquery-public-data.nhtsa_traffic_fatalities.distract_2016`
    WHERE driver_distracted_by_name NOT IN ('Not Distracted', 'Unknown if Distracted', 'Not Reported')
),

-- Count distinct accidents per state per year
accident_counts AS (
    SELECT 
        state_name,
        year,
        COUNT(DISTINCT consecutive_number) AS distracted_accidents
    FROM distracted_accidents
    GROUP BY state_name, year
),

-- Get state-level population from 2010 census
state_population AS (
    SELECT 
        z.state_name,
        SUM(p.population) AS population
    FROM `bigquery-public-data.census_bureau_usa.population_by_zip_2010` p
    JOIN `bigquery-public-data.utility_us.zipcode_area` z
        ON p.zipcode = z.zipcode
    WHERE z.state_name IS NOT NULL AND z.state_name != ''
    GROUP BY z.state_name
),

-- Calculate rates per 100,000 people
rates AS (
    SELECT 
        a.state_name,
        a.year,
        a.distracted_accidents,
        s.population,
        ROUND((a.distracted_accidents * 100000.0) / s.population, 4) AS rate_per_100k
    FROM accident_counts a
    JOIN state_population s
        ON a.state_name = s.state_name
),

-- Rank states by rate within each year
ranked AS (
    SELECT 
        state_name,
        year,
        distracted_accidents,
        population,
        rate_per_100k,
        DENSE_RANK() OVER (PARTITION BY year ORDER BY rate_per_100k DESC) AS rank
    FROM rates
)

-- Select top 5 states for each year
SELECT 
    state_name,
    year,
    distracted_accidents,
    population,
    rate_per_100k,
    rank
FROM ranked
WHERE rank <= 5
ORDER BY year, rank;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
  -- Step 1: Create a mapping of state FIPS codes to state names
  state_codes AS (
    SELECT 1 AS state_number, 'Alabama' AS state_name UNION ALL
    SELECT 2, 'Alaska' UNION ALL
    SELECT 4, 'Arizona' UNION ALL
    SELECT 5, 'Arkansas' UNION ALL
    SELECT 6, 'California' UNION ALL
    SELECT 8, 'Colorado' UNION ALL
    SELECT 9, 'Connecticut' UNION ALL
    SELECT 10, 'Delaware' UNION ALL
    SELECT 11, 'District of Columbia' UNION ALL
    SELECT 12, 'Florida' UNION ALL
    SELECT 13, 'Georgia' UNION ALL
    SELECT 15, 'Hawaii' UNION ALL
    SELECT 16, 'Idaho' UNION ALL
    SELECT 17, 'Illinois' UNION ALL
    SELECT 18, 'Indiana' UNION ALL
    SELECT 19, 'Iowa' UNION ALL
    SELECT 20, 'Kansas' UNION ALL
    SELECT 21, 'Kentucky' UNION ALL
    SELECT 22, 'Louisiana' UNION ALL
    SELECT 23, 'Maine' UNION ALL
    SELECT 24, 'Maryland' UNION ALL
    SELECT 25, 'Massachusetts' UNION ALL
    SELECT 26, 'Michigan' UNION ALL
    SELECT 27, 'Minnesota' UNION ALL
    SELECT 28, 'Mississippi' UNION ALL
    SELECT 29, 'Missouri' UNION ALL
    SELECT 30, 'Montana' UNION ALL
    SELECT 31, 'Nebraska' UNION ALL
    SELECT 32, 'Nevada' UNION ALL
    SELECT 33, 'New Hampshire' UNION ALL
    SELECT 34, 'New Jersey' UNION ALL
    SELECT 35, 'New Mexico' UNION ALL
    SELECT 36, 'New York' UNION ALL
    SELECT 37, 'North Carolina' UNION ALL
    SELECT 38, 'North Dakota' UNION ALL
    SELECT 39, 'Ohio' UNION ALL
    SELECT 40, 'Oklahoma' UNION ALL
    SELECT 41, 'Oregon' UNION ALL
    SELECT 42, 'Pennsylvania' UNION ALL
    SELECT 44, 'Rhode Island' UNION ALL
    SELECT 45, 'South Carolina' UNION ALL
    SELECT 46, 'South Dakota' UNION ALL
    SELECT 47, 'Tennessee' UNION ALL
    SELECT 48, 'Texas' UNION ALL
    SELECT 49, 'Utah' UNION ALL
    SELECT 50, 'Vermont' UNION ALL
    SELECT 51, 'Virginia' UNION ALL
    SELECT 53, 'Washington' UNION ALL
    SELECT 54, 'West Virginia' UNION ALL
    SELECT 55, 'Wisconsin' UNION ALL
    SELECT 56, 'Wyoming'
  ),
  -- Step 2: 2010 census population per state (from original query)
  state_populations AS (
    SELECT 'Alabama' AS state_name, 4779736 AS population UNION ALL
    SELECT 'Alaska', 710231 UNION ALL
    SELECT 'Arizona', 6392017 UNION ALL
    SELECT 'Arkansas', 2915918 UNION ALL
    SELECT 'California', 37253956 UNION ALL
    SELECT 'Colorado', 5029196 UNION ALL
    SELECT 'Connecticut', 3574097 UNION ALL
    SELECT 'Delaware', 897934 UNION ALL
    SELECT 'District of Columbia', 601723 UNION ALL
    SELECT 'Florida', 18801310 UNION ALL
    SELECT 'Georgia', 9687653 UNION ALL
    SELECT 'Hawaii', 1360301 UNION ALL
    SELECT 'Idaho', 1567582 UNION ALL
    SELECT 'Illinois', 12830632 UNION ALL
    SELECT 'Indiana', 6483802 UNION ALL
    SELECT 'Iowa', 3046355 UNION ALL
    SELECT 'Kansas', 2853118 UNION ALL
    SELECT 'Kentucky', 4339367 UNION ALL
    SELECT 'Louisiana', 4533372 UNION ALL
    SELECT 'Maine', 1328361 UNION ALL
    SELECT 'Maryland', 5773552 UNION ALL
    SELECT 'Massachusetts', 6547629 UNION ALL
    SELECT 'Michigan', 9883640 UNION ALL
    SELECT 'Minnesota', 5303925 UNION ALL
    SELECT 'Mississippi', 2967297 UNION ALL
    SELECT 'Missouri', 5988927 UNION ALL
    SELECT 'Montana', 989415 UNION ALL
    SELECT 'Nebraska', 1826341 UNION ALL
    SELECT 'Nevada', 2700551 UNION ALL
    SELECT 'New Hampshire', 1316470 UNION ALL
    SELECT 'New Jersey', 8791894 UNION ALL
    SELECT 'New Mexico', 2059179 UNION ALL
    SELECT 'New York', 19378102 UNION ALL
    SELECT 'North Carolina', 9535483 UNION ALL
    SELECT 'North Dakota', 672591 UNION ALL
    SELECT 'Ohio', 11536504 UNION ALL
    SELECT 'Oklahoma', 3751351 UNION ALL
    SELECT 'Oregon', 3831074 UNION ALL
    SELECT 'Pennsylvania', 12702379 UNION ALL
    SELECT 'Rhode Island', 1052567 UNION ALL
    SELECT 'South Carolina', 4625364 UNION ALL
    SELECT 'South Dakota', 814180 UNION ALL
    SELECT 'Tennessee', 6346105 UNION ALL
    SELECT 'Texas', 25145561 UNION ALL
    SELECT 'Utah', 2763885 UNION ALL
    SELECT 'Vermont', 625741 UNION ALL
    SELECT 'Virginia', 8001024 UNION ALL
    SELECT 'Washington', 6724540 UNION ALL
    SELECT 'West Virginia', 1852994 UNION ALL
    SELECT 'Wisconsin', 5686986 UNION ALL
    SELECT 'Wyoming', 563626
  ),
  -- Step 3: Combine distraction records for 2015 and 2016, excluding non-distracted
  distracted_events AS (
    SELECT state_number, consecutive_number, 2015 AS year
    FROM `bigquery-public-data.nhtsa_traffic_fatalities.distract_2015`
    WHERE driver_distracted_by_name NOT IN ('Not Distracted', 'Unknown if Distracted', 'Not Reported')
    UNION ALL
    SELECT state_number, consecutive_number, 2016 AS year
    FROM `bigquery-public-data.nhtsa_traffic_fatalities.distract_2016`
    WHERE driver_distracted_by_name NOT IN ('Not Distracted', 'Unknown if Distracted', 'Not Reported')
  ),
  -- Step 4: Count distinct distracted accidents per state per year
  distracted_counts AS (
    SELECT state_number, year, COUNT(DISTINCT consecutive_number) AS distracted_accidents
    FROM distracted_events
    GROUP BY state_number, year
  ),
  -- Step 5: Compute rate per 100,000 people for each state and year
  rates AS (
    SELECT
      c.state_number,
      sc.state_name,
      c.year,
      ROUND((c.distracted_accidents * 100000.0) / p.population, 4) AS rate_per_100k
    FROM distracted_counts c
    INNER JOIN state_codes sc ON c.state_number = sc.state_number
    INNER JOIN state_populations p ON sc.state_name = p.state_name
  ),
  -- Step 6: Rank states within each year by descending rate
  ranked AS (
    SELECT
      state_name,
      year,
      rate_per_100k,
      ROW_NUMBER() OVER (PARTITION BY year ORDER BY rate_per_100k DESC) AS rank
    FROM rates
  )
-- Final: select top 5 states per year
SELECT
  year,
  state_name,
  rate_per_100k,
  rank
FROM ranked
WHERE rank <= 5
ORDER BY year, rank;
```

---

## 61. Instance: `bq108`
**Question:**
> Within the 2015 dataset for accidents that occurred from January through August and involved more than one distinct person, what percentage of these accidents had more than one individual with a severe injury (injury severity = 4)

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH person_stats AS (
  -- Step 1: Filter accidents from January to August (months 1-8) and aggregate per accident
  SELECT
    st_case,
    COUNT(*) AS total_persons,
    COUNTIF(injury_severity = 4) AS severe_count
  FROM `bigquery-public-data.nhtsa_traffic_fatalities.person_2015`
  WHERE month_of_crash BETWEEN 1 AND 8   -- January through August
  GROUP BY st_case
  HAVING total_persons > 1               -- more than one distinct person
)
-- Step 2: Compute percentage of accidents with more than one severe injury
SELECT
  ROUND(
    COUNTIF(severe_count > 1) * 100.0 / COUNT(*),
    4
  ) AS percentage_accidents_with_multiple_severe_injuries
FROM person_stats;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Identify accidents in Jan-Aug 2015 with more than one person
-- Step 2: Count severe injuries (injury_severity = 4) per accident
-- Step 3: Among those, find accidents with more than one severe injury
-- Step 4: Calculate percentage

WITH accidents_with_multiple_persons AS (
  SELECT 
    consecutive_number,
    COUNT(DISTINCT person_number) AS total_persons,
    COUNTIF(injury_severity = 4) AS severe_count
  FROM `bigquery-public-data.nhtsa_traffic_fatalities.person_2015`
  WHERE month_of_crash BETWEEN 1 AND 8  -- January through August
  GROUP BY consecutive_number
  HAVING total_persons > 1  -- more than one distinct person
),
accidents_with_multiple_severe AS (
  SELECT 
    consecutive_number
  FROM accidents_with_multiple_persons
  WHERE severe_count > 1  -- more than one individual with severe injury
)
SELECT 
  ROUND(
    (SELECT COUNT(*) FROM accidents_with_multiple_severe) * 100.0 / 
    (SELECT COUNT(*) FROM accidents_with_multiple_persons),
    4
  ) AS percentage
```

---

## 62. Instance: `bq109`
**Question:**
> Find the average, variance, max-min difference, and the QTL source(right study) of the maximum log2(h4/h3) for data where right gene id is "ENSG00000169174", h4 > 0.8, h3 < 0.02, reported trait includes "lesterol levels", right biological feature is "IPSC", and the variant is '1_55029009_C_T'.

### 🏆 Gold Reference Answer
```sql
WITH coloc_stats AS (
  SELECT
    coloc.coloc_log2_h4_h3,
    coloc.right_study AS qtl_source
  FROM
    `open-targets-genetics.genetics.variant_disease_coloc` AS coloc
  JOIN
    `open-targets-genetics.genetics.studies` AS studies
  ON
    coloc.left_study = studies.study_id
  WHERE
    coloc.right_gene_id = "ENSG00000169174"
    AND coloc.coloc_h4 > 0.8
    AND coloc.coloc_h3 < 0.02
    AND studies.trait_reported LIKE "%lesterol levels%"
    AND coloc.right_bio_feature = 'IPSC'
    AND CONCAT(coloc.left_chrom, '_', coloc.left_pos, '_', coloc.left_ref, '_', coloc.left_alt) = '1_55029009_C_T'
),
max_value AS (
  SELECT
    MAX(coloc_log2_h4_h3) AS max_log2_h4_h3
  FROM
    coloc_stats
)

SELECT
  AVG(coloc_log2_h4_h3) AS average,
  VAR_SAMP(coloc_log2_h4_h3) AS variance,
  MAX(coloc_log2_h4_h3) - MIN(coloc_log2_h4_h3) AS max_min_difference,
  (SELECT qtl_source FROM coloc_stats WHERE coloc_log2_h4_h3 = (SELECT max_log2_h4_h3 FROM max_value)) AS qtl_source_of_max
FROM
  coloc_stats;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Define filtered data with all necessary joins and conditions
WITH
filtered_data AS (
  SELECT
    vdc.coloc_log2_h4_h3,
    vdc.right_study
  FROM
    `open-targets-genetics.genetics.variant_disease_coloc` AS vdc
  INNER JOIN
    `open-targets-genetics.genetics.studies` AS s
    ON vdc.left_study = s.study_id
  WHERE
    vdc.right_gene_id = 'ENSG00000169174'
    AND vdc.coloc_h4 > 0.8
    AND vdc.coloc_h3 < 0.02
    AND LOWER(s.trait_reported) LIKE '%lesterol%'
    AND vdc.right_bio_feature = 'IPSC'
    AND vdc.left_chrom = '1'
    AND vdc.left_pos = 55029009
    AND vdc.left_ref = 'C'
    AND vdc.left_alt = 'T'
),

-- Step 2: Compute aggregate statistics (average, variance, max-min difference)
aggregates AS (
  SELECT
    AVG(coloc_log2_h4_h3) AS avg_log2,
    -- Use sample variance; if only one row, returns NULL
    VAR_SAMP(coloc_log2_h4_h3) AS var_log2,
    MAX(coloc_log2_h4_h3) - MIN(coloc_log2_h4_h3) AS range_log2
  FROM filtered_data
),

-- Step 3: Identify the row with the maximum log2(h4/h3)
max_row AS (
  SELECT
    coloc_log2_h4_h3,
    right_study
  FROM filtered_data
  ORDER BY coloc_log2_h4_h3 DESC
  LIMIT 1
)

-- Step 4: Combine results into a single output row
SELECT
  (SELECT avg_log2 FROM aggregates) AS average,
  (SELECT var_log2 FROM aggregates) AS variance,
  (SELECT range_log2 FROM aggregates) AS max_min_difference,
  (SELECT right_study FROM max_row) AS qtl_source_right_study;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH filtered_data AS (
  SELECT
    LOG(2, vdc.coloc_h4 / vdc.coloc_h3) AS coloc_log2_h4_h3,
    vdc.right_study
  FROM `open-targets-genetics.genetics.variant_disease_coloc` vdc
  WHERE
    vdc.coloc_h4 > 0.8
    AND vdc.coloc_h3 < 0.02
    AND vdc.left_chrom = '1'
    AND vdc.left_pos = 55029009
    AND vdc.left_ref = 'C'
    AND vdc.left_alt = 'T'
    AND vdc.right_bio_feature = 'IPSC'
    AND LOWER(vdc.right_phenotype) LIKE '%lesterol%'
)
SELECT
  ROUND(AVG(coloc_log2_h4_h3), 4) AS average_log2_h4_h3,
  ROUND(VAR_POP(coloc_log2_h4_h3), 4) AS variance_log2_h4_h3,
  ROUND(MAX(coloc_log2_h4_h3) - MIN(coloc_log2_h4_h3), 4) AS max_min_diff,
  (
    SELECT right_study
    FROM filtered_data
    ORDER BY coloc_log2_h4_h3 DESC
    LIMIT 1
  ) AS qtl_source
FROM filtered_data;
```

---

## 63. Instance: `bq110`
**Question:**
> What is the change in the number of homeless veterans between 2012 and 2018 for each CoC region in New York that has data available in both years?

### 🏆 Gold Reference Answer
```sql
WITH homeless_2012 AS (
  SELECT Homeless_Veterans AS Vet12, CoC_Name  
  FROM `bigquery-public-data.sdoh_hud_pit_homelessness.hud_pit_by_coc` 
  WHERE SUBSTR(CoC_Number,0,2) = "NY" AND Count_Year = 2012
),
 
homeless_2018 AS (
  SELECT Homeless_Veterans AS Vet18, CoC_Name  
  FROM `bigquery-public-data.sdoh_hud_pit_homelessness.hud_pit_by_coc` 
  WHERE SUBSTR(CoC_Number,0,2) = "NY" AND Count_Year = 2018
),
 
veterans_change AS (
  SELECT homeless_2012.COC_Name, Vet12, Vet18, Vet18 - Vet12 AS VetChange
  FROM homeless_2018
  JOIN homeless_2012
  ON homeless_2018.CoC_Name = homeless_2012.CoC_Name
)

SELECT COC_Name, VetChange FROM veterans_change
ORDER BY CoC_Name;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Filter for New York CoC regions (CoC_Number starts with 'NY-') and years 2012 and 2018
-- Step 2: Use conditional aggregation to get homeless veteran counts for both years per CoC
-- Step 3: Keep only CoCs that have non-null values in both years
-- Step 4: Compute the change (2018 - 2012)
WITH coc_data AS (
  SELECT 
    CoC_Number,
    CoC_Name,
    MAX(CASE WHEN Count_Year = 2012 THEN Homeless_Veterans END) AS veterans_2012,
    MAX(CASE WHEN Count_Year = 2018 THEN Homeless_Veterans END) AS veterans_2018
  FROM `bigquery-public-data.sdoh_hud_pit_homelessness.hud_pit_by_coc`
  WHERE Count_Year IN (2012, 2018)
    AND CoC_Number LIKE 'NY-%'   -- New York state CoC numbers
  GROUP BY CoC_Number, CoC_Name
  HAVING veterans_2012 IS NOT NULL 
     AND veterans_2018 IS NOT NULL
)
SELECT 
  CoC_Number,
  CoC_Name,
  veterans_2012,
  veterans_2018,
  (veterans_2018 - veterans_2012) AS change_in_homeless_veterans
FROM coc_data
ORDER BY CoC_Number;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Compute the change in homeless veterans between 2012 and 2018 for each CoC region in New York that has data in both years.
-- We use self-join on CoC_Number after filtering for New York (prefix 'NY-') and the two years.
WITH 
  data_2012 AS (
    SELECT 
      CoC_Number,
      CoC_Name,
      Homeless_Veterans AS v2012
    FROM `bigquery-public-data.sdoh_hud_pit_homelessness.hud_pit_by_coc`
    WHERE Count_Year = 2012
      AND CoC_Number LIKE 'NY-%'  -- New York CoC regions
  ),
  data_2018 AS (
    SELECT 
      CoC_Number,
      CoC_Name,
      Homeless_Veterans AS v2018
    FROM `bigquery-public-data.sdoh_hud_pit_homelessness.hud_pit_by_coc`
    WHERE Count_Year = 2018
      AND CoC_Number LIKE 'NY-%'
  )
SELECT 
  d2012.CoC_Number,
  d2012.CoC_Name,
  d2012.v2012 AS homeless_veterans_2012,
  d2018.v2018 AS homeless_veterans_2018,
  (d2018.v2018 - d2012.v2012) AS change
FROM data_2012 d2012
INNER JOIN data_2018 d2018
  ON d2012.CoC_Number = d2018.CoC_Number
WHERE d2012.v2012 IS NOT NULL 
  AND d2018.v2018 IS NOT NULL
ORDER BY CoC_Number;
```

---

## 64. Instance: `bq111`
**Question:**
> Could you compute, by chromosome, the Pearson correlation between the frequency of copy number aberrations (including amplifications, gains, losses, and deletions) from the Mitelman database for cases with morph = 3111 and topo = 0401, and those computed from TCGA data, returning correlation coefficients and corresponding p-values for each aberration type, ensuring only results with at least five matching records are shown.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
  -- Step 1: Get Mitelman cases with morph=3111 and topo=0401
  mitelman_cases AS (
    SELECT DISTINCT c.RefNo, c.CaseNo, c.CaseOrder
    FROM `mitelman-db.prod.Cytogen` c
    WHERE c.Morph = '3111' AND c.Topo = '0401'
  ),

  -- Step 2: Get the CNV data for Mitelman cases (from CytoConverted)
  -- Note: We need to map cases to their CNVs. The CytoConverted table links via RefNo and CaseNo
  mitelman_cnv AS (
    SELECT 
      cc.Chr AS chromosome,
      -- Simplify to just chromosome (remove 'chr' prefix)
      CAST(REPLACE(cc.Chr, 'chr', '') AS STRING) AS chr_number,
      cc.Type AS aberration_type,
      COUNT(*) AS aberration_count
    FROM `mitelman-db.prod.CytoConverted` cc
    INNER JOIN mitelman_cases mc 
      ON cc.RefNo = mc.RefNo AND cc.CaseNo = mc.CaseNo
    WHERE cc.Type IN ('Amplification', 'Gain', 'Loss', 'Deletion')
    GROUP BY chromosome, aberration_type
  ),

  -- Step 3: Count total Mitelman cases for frequency calculation
  mitelman_total_cases AS (
    SELECT COUNT(DISTINCT CONCAT(RefNo, CaseNo)) AS total_cases
    FROM mitelman_cases
  ),

  -- Step 4: Compute Mitelman frequency per chromosome and aberration type
  mitelman_freq AS (
    SELECT 
      mc.chr_number,
      mc.aberration_type,
      -- Ensure at least 5 records per group
      COUNT(*) AS num_records,
      SAFE_DIVIDE(SUM(mc.aberration_count), mtc.total_cases) AS frequency
    FROM mitelman_cnv mc
    CROSS JOIN mitelman_total_cases mtc
    GROUP BY mc.chr_number, mc.aberration_type
    HAVING COUNT(*) >= 5
  ),

  -- Step 5: Get TCGA data for breast cancer (BRCA) with similar CNV categories
  -- We need to map TCGA segments to cytobands for frequency calculation
  tcga_segments AS (
    SELECT 
      chromosome,
      cytoband_name,
      hg38_start,
      hg38_stop,
      -- Classify segments: Amplifications (>2 copies), Gains (1-2 extra), Losses (1-2 lost), Deletions (0 copies)
      CASE 
        WHEN seg_mean > 0.9 THEN 'Amplification'      -- Rough threshold for amplification
        WHEN seg_mean > 0.2 AND seg_mean <= 0.9 THEN 'Gain'
        WHEN seg_mean < -0.2 AND seg_mean >= -0.9 THEN 'Loss'
        WHEN seg_mean < -0.9 THEN 'Deletion'
        ELSE 'Normal'
      END AS aberration_type,
      COUNT(*) AS segment_count
    FROM `isb-cgc.Genome.wgs_segments` -- TCGA segment table
    WHERE project = 'BRCA'
    GROUP BY chromosome, cytoband_name, hg38_start, hg38_stop, aberration_type
  ),

  -- Step 6: Compute TCGA frequency per chromosome and aberration type
  tcga_freq AS (
    SELECT 
      -- Get chromosome number (strip 'chr')
      CAST(REPLACE(chromosome, 'chr', '') AS STRING) AS chr_number,
      aberration_type,
      -- Normalize by total segments per chromosome
      COUNT(*) AS segment_count,
      ROUND(SUM(segment_count) * 100.0 / SUM(SUM(segment_count)) OVER (PARTITION BY chromosome), 4) AS frequency_pct
    FROM tcga_segments
    GROUP BY chromosome, aberration_type
    HAVING COUNT(*) >= 5
  ),

  -- Step 7: Join Mitelman and TCGA frequencies per chromosome and aberration type
  combined_data AS (
    SELECT 
      mf.chr_number,
      mf.aberration_type,
      mf.frequency AS mf_freq,
      tf.frequency_pct AS tcga_freq,
      -- Use both datasets' record counts for correlation
      mf.num_records AS mitelman_n,
      tf.segment_count AS tcga_n
    FROM mitelman_freq mf
    INNER JOIN tcga_freq tf
      ON mf.chr_number = tf.chr_number 
      AND mf.aberration_type = tf.aberration_type
  ),

  -- Step 8: Compute Pearson correlation and p-value using BigQuery functions
  correlations AS (
    SELECT 
      cd.chr_number,
      cd.aberration_type,
      -- Pearson correlation
      CORR(cd.mf_freq, cd.tcga_freq) AS correlation_coefficient,
      -- P-value from correlation
      `isb-cgc-bq.functions.corr_pvalue_current`(
        cd.mf_freq, 
        cd.tcga_freq, 
        cd.mitelman_n + cd.tcga_n
      ) AS p_value
    FROM combined_data cd
    GROUP BY cd.chr_number, cd.aberration_type
  )

-- Final output: only results with at least 5 matching records and non-null correlation
SELECT 
  chr_number,
  aberration_type,
  ROUND(correlation_coefficient, 4) AS pearson_r,
  ROUND(p_value, 6) AS p_value
FROM correlations
WHERE 
  correlation_coefficient IS NOT NULL
  AND mitelman_n >= 5  -- Already enforced via HAVING
  AND tcga_n >= 5      -- Already enforced via HAVING
ORDER BY chr_number, aberration_type;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql

```

---

## 65. Instance: `bq112`
**Question:**
> Between 1998 and 2017, for Allegheny County in the Pittsburgh area, did the average annual wages for all industries keep pace with the inflation of all consumer items, and what were the respective percentage growth rates (to two decimal places) for wages and the CPI over that period?

### 🏆 Gold Reference Answer
```sql
WITH geo AS (
  SELECT DISTINCT geo_id
  FROM `bigquery-public-data.geo_us_boundaries.counties`
  WHERE county_name = "Allegheny" 
),
avg_wage_1998 AS(
  SELECT
    ROUND(AVG(avg_wkly_wage_10_total_all_industries) * 52, 2) AS wages_1998
  FROM
    `bigquery-public-data.bls_qcew.1998*`
  WHERE
    geoid = (SELECT geo_id FROM geo) --Selecting Allgeheny County
),
    
avg_wage_2017 AS (
  SELECT
    ROUND(AVG(avg_wkly_wage_10_total_all_industries) * 52, 2) AS wages_2017
  FROM
    `bigquery-public-data.bls_qcew.2017*`
  WHERE
    geoid = (SELECT geo_id FROM geo) --Selecting Allgeheny County
),

avg_cpi_1998 AS (
  SELECT
    AVG(value) AS cpi_1998
  FROM
    `bigquery-public-data.bls.cpi_u` c
  WHERE
    year = 1998
    AND item_code in (
      SELECT DISTINCT item_code FROM `bigquery-public-data.bls.cpi_u` WHERE LOWER(item_name) = "all items"
    )
    AND area_code = (
      SELECT DISTINCT area_code FROM `bigquery-public-data.bls.cpi_u` WHERE area_name LIKE '%Pittsburgh%'
    )
), 
-- A104 is the code for Pittsburgh, PA
-- SA0 is the code for all items
    
avg_cpi_2017 AS(
  SELECT
    AVG(value) AS cpi_2017
  FROM
    `bigquery-public-data.bls.cpi_u` c
  WHERE
    year = 2017
    AND item_code in (
      SELECT DISTINCT item_code FROM `bigquery-public-data.bls.cpi_u` WHERE LOWER(item_name) = "all items"
    )
    AND area_code = (
      SELECT DISTINCT area_code FROM `bigquery-public-data.bls.cpi_u` WHERE area_name LIKE '%Pittsburgh%'
    )
)
-- A104 is the code for Pittsburgh, PA
-- SA0 is the code for all items

SELECT
  ROUND((wages_2017 - wages_1998) / wages_1998 * 100, 2) AS wages_percent_change,
  ROUND((cpi_2017 - cpi_1998) / cpi_1998 * 100, 2) AS cpi_percent_change
FROM
  avg_wage_2017,
  avg_wage_1998,
  avg_cpi_2017,
  avg_cpi_1998
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Final optimized query
WITH wage_data AS (
  -- Use wildcard union for all QCEW quarterly tables
  SELECT 
    EXTRACT(YEAR FROM DATE(
      CASE 
        WHEN _TABLE_SUFFIX LIKE '%_q1' THEN CONCAT(SUBSTR(_TABLE_SUFFIX, 1, 4), '-01-01')
        WHEN _TABLE_SUFFIX LIKE '%_q2' THEN CONCAT(SUBSTR(_TABLE_SUFFIX, 1, 4), '-04-01')
        WHEN _TABLE_SUFFIX LIKE '%_q3' THEN CONCAT(SUBSTR(_TABLE_SUFFIX, 1, 4), '-07-01')
        WHEN _TABLE_SUFFIX LIKE '%_q4' THEN CONCAT(SUBSTR(_TABLE_SUFFIX, 1, 4), '-10-01')
      END
    )) AS year,
    avg_wkly_wage_10_total_all_industries AS weekly_wage
  FROM `bigquery-public-data.bls_qcew.*`
  WHERE _TABLE_SUFFIX BETWEEN '1998_q1' AND '2017_q4'
    AND area_fips = '42003'
    AND avg_wkly_wage_10_total_all_industries IS NOT NULL
    AND avg_wkly_wage_10_total_all_industries > 0
),
annual_wages AS (
  SELECT 
    year,
    ROUND(AVG(weekly_wage) * 52, 2) AS annual_wage
  FROM wage_data
  GROUP BY year
),
cpi_data AS (
  SELECT 
    year,
    AVG(value) AS avg_cpi
  FROM `bigquery-public-data.bls.cpi_u`
  WHERE area_code = '0' 
    AND item_code = 'SA0' 
    AND year BETWEEN 1998 AND 2017
    AND value IS NOT NULL
  GROUP BY year
)
SELECT 
  ROUND(((w2017.annual_wage - w1998.annual_wage) / w1998.annual_wage) * 100, 2) AS avg_annual_wage_growth_rate_pct,
  ROUND(((c2017.avg_cpi - c1998.avg_cpi) / c1998.avg_cpi) * 100, 2) AS cpi_growth_rate_pct,
  CASE 
    WHEN ((w2017.annual_wage - w1998.annual_wage) / w1998.annual_wage) >= ((c2017.avg_cpi - c1998.avg_cpi) / c1998.avg_cpi) 
    THEN 'Yes, wages kept pace with inflation'
    ELSE 'No, wages did not keep pace with inflation'
  END AS wages_kept_pace_with_inflation
FROM annual_wages w1998
CROSS JOIN annual_wages w2017
CROSS JOIN cpi_data c1998
CROSS JOIN cpi_data c2017
WHERE w1998.year = 1998 
  AND w2017.year = 2017 
  AND c1998.year = 1998 
  AND c2017.year = 2017;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Compute average annual weekly wage for Allegheny County (all industries)
wage_quarterly AS (
  SELECT
    CAST(SUBSTR(_TABLE_SUFFIX, 1, 4) AS INT64) AS year,
    avg_wkly_wage_10_total_all_industries AS weekly_wage
  FROM `bigquery-public-data.bls_qcew.*`
  WHERE _TABLE_SUFFIX BETWEEN '1998_q1' AND '2017_q4'
    AND area_fips = '42003'               -- Allegheny County, PA
    AND avg_wkly_wage_10_total_all_industries IS NOT NULL
),
annual_wage AS (
  SELECT
    year,
    AVG(weekly_wage) AS avg_weekly_wage
  FROM wage_quarterly
  GROUP BY year
),

-- Compute annual average CPI-U (All items, U.S. city average, seasonally adjusted)
cpi_monthly AS (
  SELECT
    year,
    value
  FROM `bigquery-public-data.bls.cpi_u`
  WHERE series_id = 'CUSR0000SA0'        -- U.S. city average, All items, seasonally adjusted
    AND year IN (1998, 2017)
    AND period LIKE 'M%'                 -- monthly values
    AND value IS NOT NULL
),
annual_cpi AS (
  SELECT
    year,
    AVG(value) AS avg_cpi
  FROM cpi_monthly
  GROUP BY year
),

-- Extract scalar values for start (1998) and end (2017)
wage_1998 AS (
  SELECT avg_weekly_wage AS wage_1998
  FROM annual_wage
  WHERE year = 1998
),
wage_2017 AS (
  SELECT avg_weekly_wage AS wage_2017
  FROM annual_wage
  WHERE year = 2017
),
cpi_1998 AS (
  SELECT avg_cpi AS cpi_1998
  FROM annual_cpi
  WHERE year = 1998
),
cpi_2017 AS (
  SELECT avg_cpi AS cpi_2017
  FROM annual_cpi
  WHERE year = 2017
)

-- Final calculation: growth rates and comparison
SELECT
  ROUND(((wage_2017.wage_2017 - wage_1998.wage_1998) / wage_1998.wage_1998) * 100, 2) AS wage_growth_rate_pct,
  ROUND(((cpi_2017.cpi_2017 - cpi_1998.cpi_1998) / cpi_1998.cpi_1998) * 100, 2) AS cpi_growth_rate_pct,
  CASE
    WHEN ((wage_2017.wage_2017 - wage_1998.wage_1998) / wage_1998.wage_1998) >= ((cpi_2017.cpi_2017 - cpi_1998.cpi_1998) / cpi_1998.cpi_1998)
    THEN 'Yes, wages kept pace with inflation'
    ELSE 'No, wages did not keep pace'
  END AS kept_pace_with_inflation
FROM wage_1998, wage_2017, cpi_1998, cpi_2017;
```

---

## 66. Instance: `bq113`
**Question:**
> Which county in Utah experienced the greatest percentage increase in construction employment from 2000 to 2018, calculated by averaging the employment levels during the third month of each quarter in those years? What is the corresponding percentage increase?

### 🏆 Gold Reference Answer
```sql
WITH utah_code AS (
  SELECT DISTINCT geo_id
  FROM bigquery-public-data.geo_us_boundaries.states
  WHERE state_name = 'Utah'
),
e2000 as(
  SELECT
    AVG(month3_emplvl_23_construction) AS construction_employees_2000,
    geoid
  FROM
    `bigquery-public-data.bls_qcew.2000_*`
  WHERE
    geoid LIKE CONCAT((SELECT geo_id FROM utah_code), '%')
  GROUP BY
    geoid),

e2018 AS (
  SELECT
    AVG(month3_emplvl_23_construction) AS construction_employees_2018,
    geoid,
  FROM
    `bigquery-public-data.bls_qcew.2018_*` e2018
  WHERE
    geoid LIKE CONCAT((SELECT geo_id FROM utah_code), '%')
  GROUP BY
    geoid)

SELECT
  c.county_name AS county,
  (construction_employees_2018 - construction_employees_2000) / construction_employees_2000 * 100 AS increase_rate
FROM
  e2000
JOIN
  e2018 USING (geoid)
JOIN 
  `bigquery-public-data.geo_us_boundaries.counties` c ON c.geo_id = e2018.geoid
WHERE
  c.state_fips_code = (SELECT geo_id FROM utah_code)
ORDER BY
  increase_rate desc
LIMIT 1
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Step 1: Get all quarterly construction employment data for 2000 and 2018
quarterly_data AS (
  SELECT 
    area_fips,
    -- Extract year from table suffix: '2000_q1' → 2000
    CAST(REGEXP_EXTRACT(_TABLE_SUFFIX, r'^(\d{4})') AS INT64) AS year,
    month3_emplvl_23_construction AS construction_employment
  FROM `bigquery-public-data.bls_qcew.*`
  WHERE _TABLE_SUFFIX IN ('2000_q1', '2000_q2', '2000_q3', '2000_q4',
                           '2018_q1', '2018_q2', '2018_q3', '2018_q4')
    AND month3_emplvl_23_construction IS NOT NULL
),

-- Step 2: Average by county and year (4 quarters per year)
avg_by_year AS (
  SELECT 
    area_fips,
    year,
    AVG(construction_employment) AS avg_employment
  FROM quarterly_data
  GROUP BY area_fips, year
),

-- Step 3: Pivot averages for 2000 and 2018 side by side
pivot_data AS (
  SELECT 
    a2000.area_fips,
    a2000.avg_employment AS avg_2000,
    a2018.avg_employment AS avg_2018
  FROM avg_by_year a2000
  JOIN avg_by_year a2018
    ON a2000.area_fips = a2018.area_fips
   AND a2000.year = 2000
   AND a2018.year = 2018
),

-- Step 4: Calculate percentage increase
pct_increase AS (
  SELECT 
    area_fips,
    avg_2000,
    avg_2018,
    ROUND((avg_2018 - avg_2000) / avg_2000 * 100, 4) AS pct_increase
  FROM pivot_data
  WHERE avg_2000 > 0  -- avoid division by zero
),

-- Step 5: Join with county names and filter for Utah
county_info AS (
  SELECT 
    p.area_fips,
    c.county_name,
    p.avg_2000,
    p.avg_2018,
    p.pct_increase
  FROM pct_increase p
  JOIN `bigquery-public-data.geo_us_boundaries.counties` c
    ON p.area_fips = c.geo_id
  WHERE c.state_fips_code = '49'  -- Utah's FIPS code
)

-- Step 6: Get the county with the greatest percentage increase
SELECT 
  county_name,
  pct_increase AS percentage_increase
FROM county_info
ORDER BY pct_increase DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- This query finds the Utah county with the greatest percentage increase in construction employment
-- from 2000 to 2018, using the average of the third-month employment levels of each quarter.
-- It joins quarterly BLS QCEW data with the counties lookup table, filtering for Utah.

WITH quarter_data AS (
  -- Extract construction employment for all relevant quarters of 2000 and 2018.
  SELECT
    area_fips,
    CAST(SUBSTR(_TABLE_SUFFIX, 1, 4) AS INT64) AS year,
    month3_emplvl_23_construction AS construction_empl
  FROM
    `bigquery-public-data.bls_qcew.*`
  WHERE
    _TABLE_SUFFIX IN ('2000_q1','2000_q2','2000_q3','2000_q4',
                      '2018_q1','2018_q2','2018_q3','2018_q4')
    AND month3_emplvl_23_construction IS NOT NULL  -- ignore missing values
),
yearly_avg AS (
  -- Compute average construction employment per county per year, requiring all 4 quarters.
  SELECT
    area_fips,
    year,
    AVG(construction_empl) AS avg_empl,
    COUNT(construction_empl) AS cnt_quarters
  FROM quarter_data
  GROUP BY area_fips, year
  HAVING cnt_quarters = 4
),
both_years AS (
  -- Join the 2000 and 2018 averages for each county, excluding counties with zero 2000 employment.
  SELECT
    y2000.area_fips,
    y2000.avg_empl AS avg_2000,
    y2018.avg_empl AS avg_2018
  FROM yearly_avg y2000
  INNER JOIN yearly_avg y2018
    ON y2000.area_fips = y2018.area_fips
   AND y2000.year = 2000
   AND y2018.year = 2018
  WHERE y2000.avg_empl > 0  -- avoid division by zero
),
pct_change AS (
  -- Calculate percentage increase from 2000 to 2018.
  SELECT
    area_fips,
    ROUND((avg_2018 - avg_2000) / avg_2000 * 100, 4) AS pct_increase
  FROM both_years
)
-- Join with counties table to get county name and filter for Utah (state_fips_code = '49')
SELECT
  c.county_name,
  p.pct_increase
FROM pct_change p
JOIN `bigquery-public-data.geo_us_boundaries.counties` c
  ON p.area_fips = c.county_fips_code
WHERE c.state_fips_code = '49'
ORDER BY p.pct_increase DESC
LIMIT 1
```

---

## 67. Instance: `bq114`
**Question:**
> Which three cities have the largest difference between their 1990 EPA PM2.5 measurements (using units_of_measure = 'Micrograms/cubic meter (LC)' and parameter_name = 'Acceptable PM2.5 AQI & Speciation Mass') and their 2020 OpenAQ PM2.5 measurements (where pollutant = 'pm25' based on the year extracted from the timestamp), with both datasets matched by latitude and longitude rounded to two decimals, and the difference ordered from greatest to least?

### 🏆 Gold Reference Answer
```sql
SELECT
  aq.city,
  epa.arithmetic_mean,
  aq.value,
  aq.timestamp,
  (epa.arithmetic_mean - aq.value)
FROM
  `bigquery-public-data.openaq.global_air_quality` AS aq
JOIN
  `bigquery-public-data.epa_historical_air_quality.air_quality_annual_summary` AS epa
ON
  ROUND(aq.latitude, 2) = ROUND(epa.latitude, 2)
  AND ROUND(aq.longitude, 2) = ROUND(epa.longitude, 2)
WHERE
  epa.units_of_measure = "Micrograms/cubic meter (LC)"
  AND epa.parameter_name = "Acceptable PM2.5 AQI & Speciation Mass"
  AND epa.year = 1990
  AND aq.pollutant = "pm25"
  AND EXTRACT(YEAR FROM aq.timestamp) = 2020
ORDER BY
  (epa.arithmetic_mean - aq.value) DESC
LIMIT 3
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Compute average 1990 EPA PM2.5 per location (rounded lat/lon)
WITH epa_1990 AS (
  SELECT
    ROUND(latitude, 2) AS lat,
    ROUND(longitude, 2) AS lon,
    AVG(arithmetic_mean) AS epa_avg,
    ANY_VALUE(city_name) AS city_name
  FROM `bigquery-public-data.epa_historical_air_quality.pm25_nonfrm_daily_summary`
  WHERE
    EXTRACT(YEAR FROM date_local) = 1990
    AND parameter_name = 'Acceptable PM2.5 AQI & Speciation Mass'
    AND units_of_measure = 'Micrograms/cubic meter (LC)'
  GROUP BY lat, lon
),

-- Step 2: Compute average 2020 OpenAQ PM2.5 per location (rounded lat/lon)
openaq_2020 AS (
  SELECT
    ROUND(latitude, 2) AS lat,
    ROUND(longitude, 2) AS lon,
    AVG(value) AS openaq_avg
  FROM `bigquery-public-data.openaq.global_air_quality`
  WHERE
    pollutant = 'pm25'
    AND EXTRACT(YEAR FROM timestamp) = 2020
    AND country = 'US'   -- EPA data is US-only; restrict to US to avoid foreign matches
  GROUP BY lat, lon
)

-- Step 3: Join on rounded coordinates, compute absolute difference, and get top 3 cities
SELECT
  e.city_name AS city,
  ABS(e.epa_avg - o.openaq_avg) AS difference
FROM epa_1990 e
INNER JOIN openaq_2020 o
  ON e.lat = o.lat AND e.lon = o.lon
WHERE e.epa_avg IS NOT NULL AND o.openaq_avg IS NOT NULL
ORDER BY difference DESC
LIMIT 3;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- The provided database schema does not contain the necessary columns
-- to answer this question accurately:
-- 
-- 1. EPA PM2.5 tables (pm25_nonfrm_daily_summary, pm25_frm_daily_summary, etc.)
--    do NOT have: sample_measurement, city_name, latitude, longitude,
--    parameter_name, or units_of_measure columns
-- 
-- 2. OpenAQ global_air_quality table does NOT have:
--    parameter, value, or city columns in the provided schema
-- 
-- A correct query cannot be constructed with the given schema.
-- Please provide the full table schemas or additional tables
-- that contain the required columns.
SELECT 'Insufficient schema to answer query' AS error_message;
```

---

## 68. Instance: `bq115`
**Question:**
> Which country has the highest percentage of population under the age of 25 in 2017?

### 🏆 Gold Reference Answer
```sql
SELECT
country_name
FROM
(SELECT
  age.country_name,
  SUM(age.population) AS under_25,
  pop.midyear_population AS total,
  ROUND((SUM(age.population) / pop.midyear_population) * 100,2) AS pct_under_25
FROM (
  SELECT
    country_name,
    population,
    country_code
  FROM
    `bigquery-public-data.census_bureau_international.midyear_population_agespecific`
  WHERE
    year =2017
    AND age < 25) age
INNER JOIN (
  SELECT
    midyear_population,
    country_code
  FROM
    `bigquery-public-data.census_bureau_international.midyear_population`
  WHERE
    year = 2017) pop
ON
  age.country_code = pop.country_code
GROUP BY
  1,
  3
ORDER BY
  4 DESC
)
LIMIT
1
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Calculate total and under-25 population per country in 2017
WITH population_stats AS (
  SELECT
    country_name,
    -- Sum of all ages 0-24 (both sexes)
    SUM(population_age_0 + population_age_1 + population_age_2 + population_age_3 + population_age_4 +
        population_age_5 + population_age_6 + population_age_7 + population_age_8 + population_age_9 +
        population_age_10 + population_age_11 + population_age_12 + population_age_13 + population_age_14 +
        population_age_15 + population_age_16 + population_age_17 + population_age_18 + population_age_19 +
        population_age_20 + population_age_21 + population_age_22 + population_age_23 + population_age_24) AS under_25_pop,
    -- Sum of all ages 0-100 (both sexes)
    SUM(population_age_0 + population_age_1 + population_age_2 + population_age_3 + population_age_4 +
        population_age_5 + population_age_6 + population_age_7 + population_age_8 + population_age_9 +
        population_age_10 + population_age_11 + population_age_12 + population_age_13 + population_age_14 +
        population_age_15 + population_age_16 + population_age_17 + population_age_18 + population_age_19 +
        population_age_20 + population_age_21 + population_age_22 + population_age_23 + population_age_24 +
        population_age_25 + population_age_26 + population_age_27 + population_age_28 + population_age_29 +
        population_age_30 + population_age_31 + population_age_32 + population_age_33 + population_age_34 +
        population_age_35 + population_age_36 + population_age_37 + population_age_38 + population_age_39 +
        population_age_40 + population_age_41 + population_age_42 + population_age_43 + population_age_44 +
        population_age_45 + population_age_46 + population_age_47 + population_age_48 + population_age_49 +
        population_age_50 + population_age_51 + population_age_52 + population_age_53 + population_age_54 +
        population_age_55 + population_age_56 + population_age_57 + population_age_58 + population_age_59 +
        population_age_60 + population_age_61 + population_age_62 + population_age_63 + population_age_64 +
        population_age_65 + population_age_66 + population_age_67 + population_age_68 + population_age_69 +
        population_age_70 + population_age_71 + population_age_72 + population_age_73 + population_age_74 +
        population_age_75 + population_age_76 + population_age_77 + population_age_78 + population_age_79 +
        population_age_80 + population_age_81 + population_age_82 + population_age_83 + population_age_84 +
        population_age_85 + population_age_86 + population_age_87 + population_age_88 + population_age_89 +
        population_age_90 + population_age_91 + population_age_92 + population_age_93 + population_age_94 +
        population_age_95 + population_age_96 + population_age_97 + population_age_98 + population_age_99 +
        population_age_100) AS total_pop
  FROM
    `bigquery-public-data.census_bureau_international.midyear_population_age_sex`
  WHERE
    year = 2017
  GROUP BY
    country_name
)
SELECT
  country_name,
  ROUND((under_25_pop / total_pop) * 100, 4) AS percentage_under_25
FROM
  population_stats
ORDER BY
  percentage_under_25 DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Use the midyear_population_agespecific table which stores population per age, sex, and year.
-- Step 2: Filter for year = 2017.
-- Step 3: For each country, compute total population under age 25 (age < 25) and total population (all ages).
-- Step 4: Calculate percentage = (under_25 / total) * 100, round to 4 decimal places.
-- Step 5: Order descending and take the top country.

SELECT
  country_name,
  ROUND(100.0 * SUM(CASE WHEN age < 25 THEN population ELSE 0 END) / SUM(population), 4) AS pct_under_25
FROM
  `bigquery-public-data.census_bureau_international.midyear_population_agespecific`
WHERE
  year = 2017
GROUP BY
  country_name
ORDER BY
  pct_under_25 DESC
LIMIT 1;
```

---

## 69. Instance: `bq116`
**Question:**
> Which U.S. state reported the highest total annual revenue in billions of dollars during fiscal year 2016, considering companies that provided four quarters of data and reported measure tags in ('Revenues','SalesRevenueNet','SalesRevenueGoodsNet'), excluding any entries where the state field (stprba) is null or empty?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Identify U.S. state with highest total annual revenue in billions for fiscal year 2016
-- from companies that reported exactly four quarters of data (i.e., annual figures)
-- for revenue-related measure tags, excluding null/empty state fields.

WITH revenue_data AS (
  SELECT
    s.stprba AS state_code,
    qs.value AS revenue_value
  FROM
    `bigquery-public-data.sec_quarterly_financials.quick_summary` AS qs
  INNER JOIN
    `bigquery-public-data.sec_quarterly_financials.submission` AS s
    ON qs.submission_number = s.submission_number
  WHERE
    qs.fiscal_year = 2016
    AND qs.number_of_quarters = 4
    AND qs.measure_tag IN ('Revenues', 'SalesRevenueNet', 'SalesRevenueGoodsNet')
    AND qs.units = 'USD'
    -- Exclude invalid state values (NULL, empty string, literal 'None')
    AND s.stprba IS NOT NULL
    AND s.stprba != 'None'
    AND TRIM(s.stprba) != ''
)

SELECT
  state_code,
  ROUND(SUM(revenue_value) / 1000000000.0, 2) AS total_revenue_billions
FROM
  revenue_data
GROUP BY
  state_code
ORDER BY
  total_revenue_billions DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Identify companies that filed all four quarters (Q1, Q2, Q3, FY) for fiscal year 2016
WITH four_quarter_companies AS (
  SELECT ein
  FROM `bigquery-public-data.sec_quarterly_financials.submission`
  WHERE fiscal_year = 2016
    AND fiscal_period_focus IN ('Q1', 'Q2', 'Q3', 'FY')
  GROUP BY ein
  HAVING COUNT(DISTINCT fiscal_period_focus) = 4
),

-- Step 2: Get annual revenue (FY) for those companies using the specified measure tags,
-- taking the maximum value per company to avoid duplicates
revenue_values AS (
  SELECT q.ein,
         MAX(q.value) AS revenue
  FROM `bigquery-public-data.sec_quarterly_financials.quick_summary` q
  INNER JOIN four_quarter_companies f
    ON q.ein = f.ein
  WHERE q.fiscal_year = 2016
    AND q.fiscal_period_focus = 'FY'
    AND q.measure_tag IN ('Revenues', 'SalesRevenueNet', 'SalesRevenueGoodsNet')
    AND q.value IS NOT NULL
  GROUP BY q.ein
),

-- Step 3: Join to submission to get the state (stprba) for each company,
-- excluding null or empty states
state_revenue AS (
  SELECT DISTINCT s.stprba,
         r.revenue
  FROM revenue_values r
  INNER JOIN `bigquery-public-data.sec_quarterly_financials.submission` s
    ON r.ein = s.ein
    AND s.fiscal_year = 2016
  WHERE s.stprba IS NOT NULL
    AND s.stprba != ''
)

-- Step 4: Aggregate revenue by state, convert to billions, and pick the highest
SELECT stprba AS state,
       ROUND(SUM(revenue) / 1e9, 2) AS total_revenue_billions
FROM state_revenue
GROUP BY stprba
ORDER BY total_revenue_billions DESC
LIMIT 1;
```

---

## 70. Instance: `bq119`
**Question:**
> Please show information about the hurricane with the third longest total travel distance in the North Atlantic during 2020, including its travel coordinates, the cumulative travel distance (in kilometers) at each point, and the maximum sustained wind speed at those times.

### 🏆 Gold Reference Answer
```sql
WITH hurricane_geometry AS (
  SELECT
    * EXCEPT (longitude, latitude),
    ST_GEOGPOINT(longitude, latitude) AS geom,
  FROM
    `bigquery-public-data.noaa_hurricanes.hurricanes`
  WHERE
    season = '2020'
    AND basin = 'NA'
    AND name != 'NOT NAMED'
),
dist_between_points AS (
  SELECT
    sid,
    name,
    season,
    iso_time,
    usa_wind,
    geom,
    ST_DISTANCE(geom, LAG(geom, 1) OVER (PARTITION BY sid ORDER BY iso_time ASC)) / 1000 AS dist
  FROM
    hurricane_geometry
),
total_distances AS (
  SELECT
    sid,
    name,
    season,
    iso_time,
    usa_wind,
    geom,
    SUM(dist) OVER (PARTITION BY sid ORDER BY iso_time ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_distance,
    SUM(dist) OVER (PARTITION BY sid) AS total_dist
  FROM
    dist_between_points
),
ranked_hurricanes AS (
  SELECT
    *,
    DENSE_RANK() OVER (ORDER BY total_dist DESC) AS dense_rank
  FROM
    total_distances
)

SELECT
  geom,cumulative_distance,usa_wind
FROM
  ranked_hurricanes
WHERE
  dense_rank = 3
ORDER BY
cumulative_distance;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Filter North Atlantic hurricanes in 2020 with main tracks
hurricane_points AS (
    SELECT sid, name, iso_time, latitude, longitude, usa_wind
    FROM `bigquery-public-data.noaa_hurricanes.hurricanes`
    WHERE basin = 'NA' 
      AND season = '2020'
      AND track_type = 'main'
      AND latitude IS NOT NULL 
      AND longitude IS NOT NULL
      AND name != 'NOT_NAMED'
),

-- For each hurricane, get previous point coordinates using LAG
points_with_distance AS (
    SELECT 
        sid,
        name,
        iso_time,
        latitude,
        longitude,
        usa_wind,
        LAG(latitude) OVER (PARTITION BY sid ORDER BY iso_time) AS prev_lat,
        LAG(longitude) OVER (PARTITION BY sid ORDER BY iso_time) AS prev_lon
    FROM hurricane_points
),

-- Calculate segment distance in kilometers between consecutive points
distances AS (
    SELECT 
        sid,
        name,
        iso_time,
        latitude,
        longitude,
        usa_wind,
        CASE 
            WHEN prev_lat IS NOT NULL AND prev_lon IS NOT NULL 
            THEN ST_DISTANCE(
                ST_GEOGPOINT(longitude, latitude),
                ST_GEOGPOINT(prev_lon, prev_lat)
            ) / 1000.0
            ELSE 0 
        END AS segment_distance_km
    FROM points_with_distance
),

-- Calculate total distance per hurricane
storm_totals AS (
    SELECT 
        sid,
        name,
        ROUND(SUM(segment_distance_km), 2) AS total_distance_km
    FROM distances
    GROUP BY sid, name
),

-- Rank hurricanes by total distance descending
ranked_storms AS (
    SELECT 
        sid,
        name,
        total_distance_km,
        ROW_NUMBER() OVER (ORDER BY total_distance_km DESC) AS rank
    FROM storm_totals
),

-- Select the 3rd longest hurricane
third_longest AS (
    SELECT sid, name
    FROM ranked_storms
    WHERE rank = 3
)

-- Final output: all track points with cumulative distance and wind speed
SELECT 
    d.sid AS storm_id,
    d.name AS storm_name,
    d.iso_time,
    d.latitude,
    d.longitude,
    ROUND(SUM(d.segment_distance_km) OVER (
        PARTITION BY d.sid 
        ORDER BY d.iso_time 
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ), 2) AS cumulative_distance_km,
    d.usa_wind AS max_sustained_wind_knots
FROM distances d
INNER JOIN third_longest t ON d.sid = t.sid
ORDER BY d.iso_time;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Step 1: Filter North Atlantic hurricanes in 2020
atlantic_2020 AS (
  SELECT 
    sid,
    name,
    iso_time,
    latitude,
    longitude,
    usa_wind,
    -- Create geography points for distance calculations
    ST_GEOGPOINT(longitude, latitude) AS point
  FROM `bigquery-public-data.noaa_hurricanes.hurricanes`
  WHERE basin = 'NA'  -- North Atlantic
    AND season = '2020'
    -- Ensure we have valid coordinates
    AND latitude IS NOT NULL 
    AND longitude IS NOT NULL
),

-- Step 2: Calculate distance between consecutive points for each hurricane
distance_between_points AS (
  SELECT 
    sid,
    name,
    iso_time,
    latitude,
    longitude,
    usa_wind,
    point,
    -- Calculate distance to previous point using LAG
    ST_DISTANCE(
      point, 
      LAG(point) OVER (PARTITION BY sid ORDER BY iso_time)
    ) AS distance_to_prev_meters
  FROM atlantic_2020
),

-- Step 3: Calculate cumulative distance per hurricane
cumulative_distance AS (
  SELECT 
    sid,
    name,
    iso_time,
    latitude,
    longitude,
    usa_wind,
    -- Cumulative sum of distances (convert meters to kilometers)
    ROUND(
      SUM(COALESCE(distance_to_prev_meters, 0)) OVER (
        PARTITION BY sid 
        ORDER BY iso_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      ) / 1000, 
      4
    ) AS cumulative_distance_km
  FROM distance_between_points
),

-- Step 4: Find the storm with the 3rd longest total distance
total_distance_per_storm AS (
  SELECT 
    sid,
    name,
    MAX(cumulative_distance_km) AS total_distance_km
  FROM cumulative_distance
  GROUP BY sid, name
),

ranked_storms AS (
  SELECT 
    sid,
    name,
    total_distance_km,
    ROW_NUMBER() OVER (ORDER BY total_distance_km DESC) AS distance_rank
  FROM total_distance_per_storm
),

third_longest AS (
  SELECT sid, name
  FROM ranked_storms
  WHERE distance_rank = 3
)

-- Step 5: Return full details for the 3rd longest storm
SELECT 
  cd.sid,
  cd.name,
  cd.iso_time,
  cd.latitude,
  cd.longitude,
  cd.cumulative_distance_km,
  cd.usa_wind AS max_sustained_wind_knots
FROM cumulative_distance cd
INNER JOIN third_longest tl
  ON cd.sid = tl.sid AND cd.name = tl.name
ORDER BY cd.iso_time;
```

---

## 71. Instance: `bq120`
**Question:**
> Identify the top 10 regions (counties) with the highest total number of SNAP-participating households, using the 2017 5-year ACS county-level data and SNAP enrollment data from January 1, 2017, excluding regions where the total SNAP participation is zero. For each of these regions, calculate the ratio of households earning under $20,000 to the total number of SNAP-participating households.

### 🏆 Gold Reference Answer
```sql
WITH acs_2017 AS (
  SELECT geo_id, income_less_10000 AS i10, income_10000_14999 AS i15, income_15000_19999 AS i20
  FROM `bigquery-public-data.census_bureau_acs.county_2017_5yr`
 ),

snap_2017_Jan AS (
  SELECT FIPS, SNAP_All_Participation_Households AS snap_total
  FROM `bigquery-public-data.sdoh_snap_enrollment.snap_enrollment`
  WHERE Date = '2017-01-01'
)

SELECT acs_2017.geo_id, snap_2017_Jan.snap_total,
(acs_2017.i10 + acs_2017.i15 + acs_2017.i20) As households_under_20,
(acs_2017.i10 + acs_2017.i15 + acs_2017.i20)/snap_2017_Jan.snap_total As under_20_snap_ratio 
FROM acs_2017
JOIN snap_2017_Jan
ON  acs_2017.geo_id = snap_2017_Jan.FIPS
WHERE snap_2017_Jan.snap_total > 0
ORDER BY snap_2017_Jan.snap_total DESC
LIMIT 10
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Get top 10 counties by SNAP participation and compute income ratio
WITH 
-- Step 1: Get SNAP enrollment data for 2017-01-01
snap_2017 AS (
  SELECT 
    FIPS AS county_fips,
    SNAP_All_Participation_Households AS total_snap_households
  FROM `bigquery-public-data.sdoh_snap_enrollment.snap_enrollment`
  WHERE Date = '2017-01-01'
    AND SNAP_All_Participation_Households > 0
),

-- Step 2: Get ACS county income data for 2017 5-year
acs_income AS (
  SELECT 
    geo_id,
    -- Households earning under $20,000 (sum of three income bins)
    COALESCE(income_less_10000, 0) + COALESCE(income_10000_14999, 0) + COALESCE(income_15000_19999, 0) AS households_under_20k
  FROM `bigquery-public-data.census_bureau_acs.county_2017_5yr`
)

-- Step 3: Join, calculate ratio, and get top 10
SELECT 
  snap.county_fips AS county_fips,
  snap.total_snap_households,
  acs.households_under_20k,
  ROUND(acs.households_under_20k / NULLIF(snap.total_snap_households, 0), 4) AS ratio_under_20k_to_snap
FROM snap_2017 snap
JOIN acs_income acs
  ON snap.county_fips = acs.geo_id
ORDER BY snap.total_snap_households DESC
LIMIT 10
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Compute low income households (under $20k) per county from 2017 5-year ACS
WITH county_income AS (
  SELECT
    geo_id,
    -- SNAP-participating households (total)
    households_public_asst_or_food_stamps AS total_snap_hh,
    -- Sum households with income under $20,000 (less than $10k, $10-14,999, $15-19,999)
    COALESCE(income_less_10000, 0) + COALESCE(income_10000_14999, 0) + COALESCE(income_15000_19999, 0) AS low_income_hh
  FROM
    `bigquery-public-data.census_bureau_acs.county_2017_5yr`
  WHERE
    households_public_asst_or_food_stamps > 0  -- exclude zero SNAP participation
)

-- Step 2: Select top 10 counties by total SNAP households, compute ratio
SELECT
  geo_id,
  total_snap_hh,
  ROUND(SAFE_DIVIDE(low_income_hh, total_snap_hh), 4) AS ratio_low_income_to_snap
FROM
  county_income
ORDER BY
  total_snap_hh DESC
LIMIT 10;
```

---

## 72. Instance: `bq123`
**Question:**
> You need to determine which day of the week has the third highest percentage of questions on Stack Overflow that receive an answer within an hour. To do this, use the question creation date from the posts_questions table and the earliest answer creation date from the posts_answers table. Once you’ve calculated the percentage of questions that get answered within an hour for each day, identify the day with the third highest percentage and report that percentage.

### 🏆 Gold Reference Answer
```sql
WITH first_answers AS (
  SELECT
    parent_id AS question_id,
    MIN(creation_date) AS first_answer_date
  FROM
    `bigquery-public-data.stackoverflow.posts_answers`
  GROUP BY
    parent_id
)

SELECT
  FORMAT_DATE('%A', DATE(q.creation_date)) AS question_day,
  SUM(CASE WHEN f.first_answer_date IS NOT NULL AND TIMESTAMP_DIFF(f.first_answer_date, q.creation_date, MINUTE) <= 60 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS percent_questions
FROM
  `bigquery-public-data.stackoverflow.posts_questions` q
LEFT JOIN
  first_answers f
ON
  q.id = f.question_id
GROUP BY
  question_day
ORDER BY
  percent_questions DESC
LIMIT 1 OFFSET 2
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Get earliest answer time for each question
questions_with_earliest_answer AS (
  SELECT 
    q.id AS question_id,
    q.creation_date AS question_creation,
    MIN(a.creation_date) AS earliest_answer_creation
  FROM `bigquery-public-data.stackoverflow.posts_questions` q
  LEFT JOIN `bigquery-public-data.stackoverflow.posts_answers` a
    ON q.id = a.parent_id
  GROUP BY q.id, q.creation_date
),

-- Determine which questions got answered within 1 hour
answer_time_analysis AS (
  SELECT 
    question_id,
    question_creation,
    earliest_answer_creation,
    EXTRACT(DAYOFWEEK FROM question_creation) AS day_of_week_num,
    FORMAT_TIMESTAMP('%A', question_creation) AS day_of_week_name,
    CASE 
      WHEN earliest_answer_creation IS NOT NULL 
           AND TIMESTAMP_DIFF(earliest_answer_creation, question_creation, SECOND) <= 3600 
      THEN 1 
      ELSE 0 
    END AS answered_within_hour
  FROM questions_with_earliest_answer
),

-- Calculate percentage per day of week
daily_percentages AS (
  SELECT 
    day_of_week_num,
    day_of_week_name,
    COUNT(*) AS total_questions,
    SUM(answered_within_hour) AS answered_within_hour_count,
    ROUND(SUM(answered_within_hour) * 100.0 / COUNT(*), 4) AS percentage
  FROM answer_time_analysis
  GROUP BY day_of_week_num, day_of_week_name
),

-- Rank days by percentage descending
ranked_days AS (
  SELECT 
    day_of_week_num,
    day_of_week_name,
    percentage,
    DENSE_RANK() OVER (ORDER BY percentage DESC) AS rank
  FROM daily_percentages
)

-- Select the day with third highest percentage
SELECT 
  day_of_week_name AS day_of_week,
  percentage
FROM ranked_days
WHERE rank = 3;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Get the earliest answer creation date for each question
WITH earliest_answers AS (
  SELECT
    parent_id AS question_id,
    MIN(creation_date) AS first_answer_date
  FROM `bigquery-public-data.stackoverflow.posts_answers`
  GROUP BY parent_id
),

-- Step 2: Combine with questions, compute time difference, flag answered within 1 hour
question_answer_gap AS (
  SELECT
    q.id AS question_id,
    q.creation_date AS question_date,
    ea.first_answer_date,
    -- Time difference in seconds
    TIMESTAMP_DIFF(ea.first_answer_date, q.creation_date, SECOND) AS diff_seconds,
    -- Flag: answered within 1 hour (3600 seconds)
    CASE
      WHEN TIMESTAMP_DIFF(ea.first_answer_date, q.creation_date, SECOND) <= 3600 THEN 1
      ELSE 0
    END AS answered_within_hour
  FROM `bigquery-public-data.stackoverflow.posts_questions` q
  LEFT JOIN earliest_answers ea
    ON q.id = ea.question_id
),

-- Step 3: Aggregate by day of the week
daily_stats AS (
  SELECT
    FORMAT_TIMESTAMP('%A', question_date) AS day_of_week,
    COUNT(*) AS total_questions,
    SUM(answered_within_hour) AS answered_questions,
    -- Percentage, rounded to 4 decimal places
    ROUND(100.0 * SUM(answered_within_hour) / COUNT(*), 4) AS percentage
  FROM question_answer_gap
  GROUP BY day_of_week
),

-- Step 4: Rank days by percentage descending
ranked_days AS (
  SELECT
    day_of_week,
    percentage,
    DENSE_RANK() OVER (ORDER BY percentage DESC) AS rank
  FROM daily_stats
)

-- Step 5: Select the day with third highest percentage
SELECT
  day_of_week,
  percentage
FROM ranked_days
WHERE rank = 3;
```

---

## 73. Instance: `bq124`
**Question:**
> Among all patients, how many individuals remain alive (i.e., with no recorded deceased.dateTime), have a diagnosis of either Diabetes or Hypertension, and are prescribed at least seven distinct active medications?

### 🏆 Gold Reference Answer
```sql
With INFO AS (
SELECT 
  MR.patientId, 
  P.last_name,
  ARRAY_TO_STRING(P.first_name, " ") AS First_name,
  Condition.Codes, 
  Condition.Conditions,
  MR.med_count AS COUNT_NUMBER
FROM
  (SELECT 
    id, 
    name[safe_offset(0)].family as last_name, 
    name[safe_offset(0)].given as first_name, 
    TIMESTAMP(deceased.dateTime) AS deceased_datetime 
  FROM `bigquery-public-data.fhir_synthea.patient`) AS P
JOIN
  (SELECT  subject.patientId as patientId, 
           COUNT(DISTINCT medication.codeableConcept.coding[safe_offset(0)].code) AS med_count
   FROM    `bigquery-public-data.fhir_synthea.medication_request`
   WHERE   status = 'active'
   GROUP BY 1
   ) AS MR
ON MR.patientId = P.id 
JOIN
  (SELECT 
  PatientId, 
  STRING_AGG(DISTINCT condition_desc, ", ") AS Conditions, 
  STRING_AGG(DISTINCT condition_code, ", ") AS Codes
  FROM(
    SELECT 
      subject.patientId as PatientId, 
              code.coding[safe_offset(0)].code condition_code,
              code.coding[safe_offset(0)].display condition_desc
       FROM `bigquery-public-data.fhir_synthea.condition`
       wHERE 
         code.coding[safe_offset(0)].display = 'Diabetes'
         OR 
         code.coding[safe_offset(0)].display = 'Hypertension' 
    )
  GROUP BY PatientId
  ) AS Condition
ON MR.patientId = Condition.PatientId
WHERE med_count >= 7 
AND P.deceased_datetime is NULL /*only alive patients*/
GROUP BY patientId, last_name, first_name, Condition.Codes, Condition.Conditions, MR.med_count
ORDER BY last_name
)

SELECT COUNT(*) FROM INFO
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Get alive patients (no recorded deceased.dateTime)
alive_patients AS (
    SELECT id
    FROM `bigquery-public-data.fhir_synthea.patient`
    WHERE deceased.dateTime IS NULL
),

-- Get patients diagnosed with Diabetes or Hypertension
diagnosis_patients AS (
    SELECT DISTINCT subject.patientId AS patient_id
    FROM `bigquery-public-data.fhir_synthea.condition`
    WHERE EXISTS (
        SELECT 1 
        FROM UNNEST(code.coding) AS c
        WHERE c.code IN ('44054006', '38341003')  -- 44054006 = Diabetes, 38341003 = Hypertension
    )
),

-- Get patients with at least 7 distinct active medications
medication_count AS (
    SELECT 
        subject.patientId AS patient_id,
        COUNT(DISTINCT medication.codeableConcept.coding[SAFE_OFFSET(0)].code) AS distinct_med_count
    FROM `bigquery-public-data.fhir_synthea.medication_request`
    WHERE status = 'active'
    GROUP BY subject.patientId
    HAVING COUNT(DISTINCT medication.codeableConcept.coding[SAFE_OFFSET(0)].code) >= 7
)

-- Final count of patients meeting all criteria
SELECT COUNT(*) AS patient_count
FROM alive_patients a
INNER JOIN diagnosis_patients d ON a.id = d.patient_id
INNER JOIN medication_count m ON a.id = m.patient_id;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
-- CTE 1: Identify alive patients (no recorded death)
alive_patients AS (
    SELECT id
    FROM `bigquery-public-data.fhir_synthea.patient`
    WHERE deceased.dateTime IS NULL
),

-- CTE 2: Identify patients with Diabetes or Hypertension diagnosis
diabetes_hypertension_patients AS (
    SELECT DISTINCT subject.patientId AS patient_id
    FROM `bigquery-public-data.fhir_synthea.condition`
    WHERE EXISTS (
        SELECT 1
        FROM UNNEST(code.coding) AS coding
        WHERE LOWER(coding.display) LIKE '%diabetes%'
           OR LOWER(coding.display) LIKE '%hypertension%'
    )
),

-- CTE 3: Count distinct active medications per patient
medication_count AS (
    SELECT 
        subject.patientId AS patient_id,
        COUNT(DISTINCT medication.codeableConcept.coding[SAFE_OFFSET(0)].display) AS distinct_meds
    FROM `bigquery-public-data.fhir_synthea.medication_request`
    WHERE status = 'active'
    GROUP BY subject.patientId
    HAVING COUNT(DISTINCT medication.codeableConcept.coding[SAFE_OFFSET(0)].display) >= 7
)

-- Final count of patients meeting all criteria
SELECT COUNT(*) AS patient_count
FROM alive_patients a
INNER JOIN diabetes_hypertension_patients d ON a.id = d.patient_id
INNER JOIN medication_count m ON a.id = m.patient_id;
```

---

## 74. Instance: `bq126`
**Question:**
> What are the titles, artist names, mediums, and original image URLs of objects with 'Photograph' in their names from the 'Photographs' department, created not by an unknown artist, with an object end date of 1839 or earlier?

### 🏆 Gold Reference Answer
```sql
SELECT
  o.artist_display_name,
  o.title,
  o.object_end_date,
  o.medium,
  i.original_image_url
FROM (
  SELECT
    object_id,
    title,
    artist_display_name,
    object_end_date,
    medium
  FROM
    `bigquery-public-data.the_met.objects`
  WHERE
    department = "Photographs"
    AND object_name LIKE "%Photograph%"
    AND artist_display_name != "Unknown"
    AND object_end_date <= 1839
) o
INNER JOIN (
  SELECT
    original_image_url,
    object_id
  FROM
    `bigquery-public-data.the_met.images`
) i
ON
  o.object_id = i.object_id
ORDER BY
  o.object_end_date
;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Filter objects in 'Photographs' department with 'Photograph' in name,
--         end date <= 1839, and artist not unknown.
-- Step 2: Join with images to get original image URLs.
SELECT
    o.title,
    o.artist_display_name AS artist_name,
    o.medium,
    i.original_image_url
FROM `bigquery-public-data.the_met.objects` AS o
INNER JOIN `bigquery-public-data.the_met.images` AS i
    ON o.object_id = i.object_id
WHERE
    o.department = 'Photographs'
    AND LOWER(o.object_name) LIKE '%photograph%'
    AND o.object_end_date <= 1839
    AND o.artist_display_name IS NOT NULL
    AND LOWER(o.artist_display_name) NOT LIKE '%unknown%'
    AND TRIM(o.artist_display_name) != ''
ORDER BY
    o.object_end_date,
    o.object_id;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH matching_objects AS (
  SELECT
    o.object_id,
    o.title,
    o.artist_display_name,
    o.medium,
    o.object_end_date
  FROM
    `bigquery-public-data.the_met.objects` AS o
  WHERE
    LOWER(o.object_name) LIKE '%photograph%'
    AND LOWER(o.department) = 'photographs'
    AND LOWER(o.artist_display_name) NOT LIKE '%unknown%'
    AND o.artist_display_name IS NOT NULL
    AND TRIM(o.artist_display_name) != ''
    AND o.object_end_date <= 1839
    AND o.object_end_date IS NOT NULL
)
SELECT
  mo.title,
  mo.artist_display_name AS artist_name,
  mo.medium,
  img.original_image_url
FROM
  matching_objects AS mo
  INNER JOIN `bigquery-public-data.the_met.images` AS img
    ON mo.object_id = img.object_id
WHERE
  img.original_image_url IS NOT NULL
  AND LENGTH(TRIM(img.original_image_url)) > 0
ORDER BY
  mo.object_end_date DESC,
  mo.title ASC;
```

---

## 75. Instance: `bq130`
**Question:**
> Analyze daily new COVID-19 case counts from March to May 2020, identifying the top five states by daily increases. Please compile a ranking based on how often each state appears in these daily top fives. Then, examine the state that ranks fourth overall and identify its top five counties based on their frequency of appearing in the daily top five new case counts.

### 🏆 Gold Reference Answer
```sql
WITH StateCases AS (
    SELECT
        b.state_name,
        b.date,
        b.confirmed_cases - a.confirmed_cases AS daily_new_cases
    FROM 
        (SELECT
            state_name,
            state_fips_code,
            confirmed_cases,
            DATE_ADD(date, INTERVAL 1 DAY) AS date_shift
        FROM
            `bigquery-public-data.covid19_nyt.us_states`
        WHERE
            date >= '2020-02-29' AND date <= '2020-05-30'
        ) a
    JOIN
        `bigquery-public-data.covid19_nyt.us_states` b 
        ON a.state_fips_code = b.state_fips_code AND a.date_shift = b.date
    WHERE
        b.date >= '2020-03-01' AND b.date <= '2020-05-31'
),
RankedStatesPerDay AS (
    SELECT
        state_name,
        date,
        daily_new_cases,
        RANK() OVER (PARTITION BY date ORDER BY daily_new_cases DESC) as rank
    FROM
        StateCases
),
TopStates AS (
    SELECT
        state_name,
        COUNT(*) AS appearance_count
    FROM
        RankedStatesPerDay
    WHERE
        rank <= 5
    GROUP BY
        state_name
    ORDER BY
        appearance_count DESC
),
FourthState AS (
    SELECT
        state_name
    FROM
        TopStates
    LIMIT 1
    OFFSET 3
),
CountyCases AS (
    SELECT
        b.county,
        b.date,
        b.confirmed_cases - a.confirmed_cases AS daily_new_cases
    FROM 
        (SELECT
            county,
            county_fips_code,
            confirmed_cases,
            DATE_ADD(date, INTERVAL 1 DAY) AS date_shift
        FROM
            `bigquery-public-data.covid19_nyt.us_counties`
        WHERE
            date >= '2020-02-29' AND date <= '2020-05-30'
        ) a
    JOIN
        `bigquery-public-data.covid19_nyt.us_counties` b 
        ON a.county_fips_code = b.county_fips_code AND a.date_shift = b.date
    WHERE
        b.date >= '2020-03-01' AND b.date <= '2020-05-31'
        AND b.state_name = (SELECT state_name FROM FourthState)
),
RankedCountiesPerDay AS (
    SELECT
        county,
        date,
        daily_new_cases,
        RANK() OVER (PARTITION BY date ORDER BY daily_new_cases DESC) as rank
    FROM
        CountyCases
),
TopCounties AS (
    SELECT
        county,
        COUNT(*) AS appearance_count
    FROM
        RankedCountiesPerDay
    WHERE
        rank <= 5
    GROUP BY
        county
    ORDER BY
        appearance_count DESC
    LIMIT 5
)
SELECT
    county
FROM
    TopCounties;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Compute daily new cases per state from March to May 2020
WITH state_daily_new AS (
  SELECT
    state_name,
    date,
    confirmed_cases - LAG(confirmed_cases) OVER (
      PARTITION BY state_name ORDER BY date
    ) AS new_cases
  FROM `bigquery-public-data.covid19_nyt.us_states`
  WHERE date BETWEEN '2020-03-01' AND '2020-05-31'
),
-- Step 2: Rank states per day by new cases, keep top 5 each day
state_daily_top5 AS (
  SELECT
    state_name,
    date,
    ROW_NUMBER() OVER (
      PARTITION BY date 
      ORDER BY new_cases DESC, state_name
    ) AS rank_in_day
  FROM state_daily_new
  WHERE new_cases IS NOT NULL  -- exclude first day per state where no prior day
)
-- Step 3: Count days each state appears in daily top 5 and rank states by frequency
, state_frequency AS (
  SELECT
    state_name,
    COUNT(*) AS days_in_top5,
    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, state_name) AS overall_rank
  FROM state_daily_top5
  WHERE rank_in_day <= 5
  GROUP BY state_name
)
-- Identify the state with overall rank 4
, target_state AS (
  SELECT state_name
  FROM state_frequency
  WHERE overall_rank = 4
)
-- Step 4: For the target state, compute daily new cases per county (same date range)
, county_daily_new AS (
  SELECT
    state_name,
    county,
    date,
    confirmed_cases - LAG(confirmed_cases) OVER (
      PARTITION BY county, state_name ORDER BY date
    ) AS new_cases
  FROM `bigquery-public-data.covid19_nyt.us_counties`
  WHERE state_name = (SELECT state_name FROM target_state)
    AND date BETWEEN '2020-03-01' AND '2020-05-31'
),
-- Rank counties each day, keep top 5
county_daily_top5 AS (
  SELECT
    county,
    ROW_NUMBER() OVER (
      PARTITION BY date 
      ORDER BY new_cases DESC, county
    ) AS rank_in_day
  FROM county_daily_new
  WHERE new_cases IS NOT NULL
)
-- Count and get top 5 counties by frequency
, county_frequency AS (
  SELECT
    county,
    COUNT(*) AS days_in_top5,
    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, county) AS county_rank
  FROM county_daily_top5
  WHERE rank_in_day <= 5
  GROUP BY county
)
-- Final output: target state and its top 5 counties
SELECT
  'Target state' AS label,
  (SELECT state_name FROM target_state) AS state_name
UNION ALL
SELECT
  'Top 5 counties',
  county
FROM county_frequency
WHERE county_rank <= 5
ORDER BY label;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
  -- Step 1: Calculate daily new cases per state
  daily_new_cases_by_state AS (
    SELECT
      state_name,
      date,
      confirmed_cases - LAG(confirmed_cases, 1) OVER (
        PARTITION BY state_name 
        ORDER BY date
      ) AS daily_new_cases
    FROM
      `bigquery-public-data.covid19_nyt.us_states`
    WHERE
      date BETWEEN '2020-03-01' AND '2020-05-31'
      AND state_name IS NOT NULL
  ),

  -- Step 2: For each day, get top 5 states by new cases
  daily_top5_states AS (
    SELECT
      state_name,
      date,
      daily_new_cases,
      DENSE_RANK() OVER (
        PARTITION BY date 
        ORDER BY daily_new_cases DESC
      ) AS daily_rank
    FROM
      daily_new_cases_by_state
    WHERE
      daily_new_cases >= 0  -- Filter out negative values (data corrections)
  ),

  -- Step 3: Count how many times each state appears in daily top 5
  state_appearance_count AS (
    SELECT
      state_name,
      COUNT(*) AS appearance_count
    FROM
      daily_top5_states
    WHERE
      daily_rank <= 5
    GROUP BY
      state_name
  ),

  -- Step 4: Rank states by appearance count and find 4th place
  state_ranking AS (
    SELECT
      state_name,
      appearance_count,
      DENSE_RANK() OVER (
        ORDER BY appearance_count DESC
      ) AS state_rank
    FROM
      state_appearance_count
  ),

  -- Step 5: Identify the 4th ranked state
  target_state AS (
    SELECT
      state_name
    FROM
      state_ranking
    WHERE
      state_rank = 4
    LIMIT 1
  ),

  -- Step 6: Calculate daily new cases per county for the target state
  daily_new_cases_by_county AS (
    SELECT
      c.state_name,
      c.county,
      c.date,
      c.confirmed_cases - LAG(c.confirmed_cases, 1) OVER (
        PARTITION BY c.state_name, c.county 
        ORDER BY c.date
      ) AS daily_new_cases
    FROM
      `bigquery-public-data.covid19_nyt.us_counties` c
    INNER JOIN
      target_state t
    ON
      c.state_name = t.state_name
    WHERE
      c.date BETWEEN '2020-03-01' AND '2020-05-31'
      AND c.county IS NOT NULL
  ),

  -- Step 7: For each day, get top 5 counties within the target state
  daily_top5_counties AS (
    SELECT
      state_name,
      county,
      date,
      daily_new_cases,
      DENSE_RANK() OVER (
        PARTITION BY date 
        ORDER BY daily_new_cases DESC
      ) AS daily_rank
    FROM
      daily_new_cases_by_county
    WHERE
      daily_new_cases >= 0  -- Filter out negative values
  ),

  -- Step 8: Count appearances per county in daily top 5 lists
  county_appearance_count AS (
    SELECT
      state_name,
      county,
      COUNT(*) AS appearance_count
    FROM
      daily_top5_counties
    WHERE
      daily_rank <= 5
    GROUP BY
      state_name,
      county
  )

-- Final: Get top 5 counties by appearance count for the target state
SELECT
  state_name,
  county,
  appearance_count
FROM
  county_appearance_count
ORDER BY
  appearance_count DESC,
  county
LIMIT 5;
```

---

## 76. Instance: `bq137`
**Question:**
> Please find all zip code areas located within 10 kilometers of the coordinates (-122.3321, 47.6062) by joining the 2010 census population data (summing only male and female populations with no age constraints) and the zip code area information, and return each area’s polygon, land and water area in meters, latitude and longitude, state code, state name, city, county, and total population.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Compute total male+female population per zipcode from 2010 census
-- We filter for rows where gender is explicitly 'male' or 'female' and both age fields are NULL (total for that gender)
WITH population_2010 AS (
  SELECT
    zipcode,
    SUM(population) AS total_population
  FROM
    `bigquery-public-data.census_bureau_usa.population_by_zip_2010`
  WHERE
    gender IN ('male', 'female')
    AND minimum_age IS NULL
    AND maximum_age IS NULL
  GROUP BY
    zipcode
)

-- Step 2: Join zipcode_area with population data and geospatial filter
SELECT
  z.zipcode_geom,                -- Polygon representation of the zip code area
  z.area_land_meters,            -- Land area in square meters
  z.area_water_meters,           -- Water area in square meters
  z.latitude,                    -- Latitude of the zip code area
  z.longitude,                   -- Longitude of the zip code area
  z.state_code,                  -- Two-letter state abbreviation
  z.state_name,                  -- Full state name
  z.city,                        -- City name(s)
  z.county,                      -- County name(s)
  COALESCE(p.total_population, 0) AS total_population  -- Use 0 if no census data found
FROM
  `bigquery-public-data.utility_us.zipcode_area` AS z
LEFT JOIN
  population_2010 AS p
  ON z.zipcode = p.zipcode
WHERE
  -- Use ST_DWITHIN to find zipcodes whose polygon is within 10,000 meters (10 km) of the given point
  ST_DWITHIN(
    ST_GEOGPOINT(-122.3321, 47.6062),    -- Reference point (longitude, latitude)
    ST_GEOGFROMTEXT(z.zipcode_geom),      -- Convert polygon string to GEOGRAPHY
    10000                                 -- Distance in meters
  )
-- Optionally order results
ORDER BY
  z.zipcode;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH zip_population AS (
    SELECT
        zipcode,
        SUM(population) AS total_population
    FROM `bigquery-public-data.census_bureau_usa.population_by_zip_2010`
    WHERE gender IN ('male', 'female')
      AND minimum_age IS NULL
    GROUP BY zipcode
),
zip_areas AS (
    SELECT
        zipcode,
        ST_GEOGFROMTEXT(zipcode_geom) AS polygon_geom,
        area_land_meters,
        area_water_meters,
        latitude,
        longitude,
        state_code,
        state_name,
        city,
        county
    FROM `bigquery-public-data.utility_us.zipcode_area`
    WHERE zipcode_geom IS NOT NULL
)
SELECT
    za.polygon_geom AS polygon,
    za.area_land_meters,
    za.area_water_meters,
    za.latitude,
    za.longitude,
    za.state_code,
    za.state_name,
    za.city,
    za.county,
    zp.total_population
FROM zip_areas za
INNER JOIN zip_population zp
    ON za.zipcode = zp.zipcode
WHERE ST_DWITHIN(
    za.polygon_geom,
    ST_GEOGPOINT(-122.3321, 47.6062),
    10000
);
```

---

## 77. Instance: `bq143`
**Question:**
> Use CPTAC proteomics and RNAseq data for Clear Cell Renal Cell Carcinoma to select 'Primary Tumor' and 'Solid Tissue Normal' samples. Join the datasets on sample submitter IDs and gene symbols. Calculate the correlation between protein abundance (log2 ratio) and gene expression levels (log-transformed+1 FPKM) for each gene and sample type. Filter out correlations with an absolute value greater than 0.5, and compute the average correlation for each sample type.

### 🏆 Gold Reference Answer
```sql
WITH 
quant AS (
    SELECT 
        meta.sample_submitter_id, 
        meta.sample_type, 
        quant.case_id, 
        quant.aliquot_id, 
        quant.gene_symbol, 
        CAST(quant.protein_abundance_log2ratio AS FLOAT64) AS protein_abundance_log2ratio 
    FROM 
        `isb-cgc-bq.CPTAC.quant_proteome_CPTAC_CCRCC_discovery_study_pdc_current` AS quant
    JOIN 
        `isb-cgc-bq.PDC_metadata.aliquot_to_case_mapping_current` AS meta
        ON quant.case_id = meta.case_id
        AND quant.aliquot_id = meta.aliquot_id
        AND meta.sample_type IN ('Primary Tumor', 'Solid Tissue Normal')
),
gexp AS (
    SELECT DISTINCT 
        meta.sample_submitter_id, 
        meta.sample_type, 
        rnaseq.gene_name, 
        LOG(rnaseq.fpkm_unstranded + 1) AS HTSeq__FPKM   -- Confirm the correct column name here
    FROM 
        `isb-cgc-bq.CPTAC.RNAseq_hg38_gdc_current` AS rnaseq
    JOIN 
        `isb-cgc-bq.PDC_metadata.aliquot_to_case_mapping_current` AS meta
        ON meta.sample_submitter_id = rnaseq.sample_barcode
),
correlation AS (
    SELECT 
        quant.gene_symbol, 
        gexp.sample_type, 
        COUNT(*) AS n, 
        CORR(protein_abundance_log2ratio, HTSeq__FPKM) AS corr  -- Confirm the correct column name here
    FROM 
        quant 
    JOIN 
        gexp 
        ON quant.sample_submitter_id = gexp.sample_submitter_id
        AND gexp.gene_name = quant.gene_symbol
        AND gexp.sample_type = quant.sample_type
    GROUP BY 
        quant.gene_symbol, gexp.sample_type
),
pval AS (
    SELECT  
        gene_symbol, 
        sample_type, 
        n, 
        corr
    FROM 
        correlation
    WHERE 
        ABS(corr) <= 0.5
)
SELECT sample_type, AVG(corr)
FROM pval
GROUP BY sample_type;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Get proteomics data with gene symbols and sample metadata
WITH proteomics_with_gene AS (
  SELECT
    p.protein_abundance_log2ratio,
    p.sample_id,
    g.gene_symbol,
    m.case_submitter_id,
    m.sample_type
  FROM `isb-cgc-bq.CPTAC.quant_proteome_CPTAC_CCRCC_discovery_study_pdc_current` AS p
  LEFT JOIN `isb-cgc-bq.PDC_metadata.gene_info_current` AS g
    ON p.NCBI_gene_id = g.NCBI_gene_id
  LEFT JOIN `isb-cgc-bq.CPTAC.per_sample_file_metadata_CPTAC3_discovery_and_confirmatory_pdc_current` AS m
    ON p.sample_id = m.sample_id
  WHERE m.sample_type IN ('Primary Tumor', 'Solid Tissue Normal')
),

-- Step 2: Get RNAseq data with sample barcodes and case barcodes
rna_with_sample AS (
  SELECT
    r.fpkm_unstranded,
    r.gene_name,
    r.sample_gdc_id,
    m.case_barcode,
    m.sample_barcode
  FROM `isb-cgc-bq.CPTAC.RNAseq_hg38_gdc_current` AS r
  LEFT JOIN `isb-cgc-bq.CPTAC.per_sample_file_metadata_hg38_gdc_current` AS m
    ON r.sample_gdc_id = m.sample_gdc_id
  WHERE r.sample_type_name IN ('Primary Tumor', 'Solid Tissue Normal')
),

-- Step 3: Join proteomics and RNAseq on case submitter/barcode and gene symbol
paired_data AS (
  SELECT
    p.protein_abundance_log2ratio,
    LOG(r.fpkm_unstranded + 1) AS log_fpkm,  -- log-transformed (natural log, can also be log2)
    p.gene_symbol,
    p.sample_type
  FROM proteomics_with_gene AS p
  INNER JOIN rna_with_sample AS r
    ON p.case_submitter_id = r.case_barcode
    AND p.gene_symbol = r.gene_name
  WHERE r.fpkm_unstranded IS NOT NULL
    AND p.protein_abundance_log2ratio IS NOT NULL
),

-- Step 4: Compute correlation per gene per sample type
correlations AS (
  SELECT
    gene_symbol,
    sample_type,
    CORR(protein_abundance_log2ratio, log_fpkm) AS corr
  FROM paired_data
  GROUP BY gene_symbol, sample_type
  HAVING ABS(corr) > 0.5
)

-- Step 5: Average correlation per sample type
SELECT
  sample_type,
  ROUND(AVG(corr), 4) AS avg_correlation
FROM correlations
GROUP BY sample_type
ORDER BY sample_type;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
-- Get all unique gene symbols from CCRCC proteomics
ccrcc_genes AS (
  SELECT DISTINCT
    gene_symbol
  FROM `isb-cgc-bq.CPTAC.quant_proteome_CPTAC_CCRCC_discovery_study_pdc_current`
  WHERE gene_symbol IS NOT NULL
),

-- Get RNAseq data for Kidney, filtering for required sample types
rnaseq AS (
  SELECT
    gene_name,
    fpkm_unstranded,
    sample_type_name,
    sample_barcode
  FROM `isb-cgc-bq.CPTAC.RNAseq_hg38_gdc_current`
  WHERE primary_site = 'Kidney'
    AND sample_type_name IN ('Primary Tumor', 'Solid Tissue Normal')
    AND fpkm_unstranded IS NOT NULL
    AND fpkm_unstranded >= 0
),

-- Join genes with RNAseq data
joined AS (
  SELECT
    c.gene_symbol,
    LOG(1 + r.fpkm_unstranded) AS log_gene_expression,
    r.sample_type_name,
    r.sample_barcode
  FROM ccrcc_genes c
  INNER JOIN rnaseq r
    ON LOWER(c.gene_symbol) = LOWER(r.gene_name)
),

-- Compute per-gene, per-sample-type statistics (since no protein abundance, use gene expression as proxy)
per_gene AS (
  SELECT
    gene_symbol,
    sample_type_name,
    AVG(log_gene_expression) AS avg_log_expression,
    STDDEV(log_gene_expression) AS std_log_expression,
    COUNT(*) AS sample_count
  FROM joined
  GROUP BY gene_symbol, sample_type_name
  HAVING COUNT(*) >= 3
)

SELECT
  sample_type_name,
  ROUND(AVG(avg_log_expression), 4) AS avg_gene_expression,
  COUNT(gene_symbol) AS number_of_genes
FROM per_gene
GROUP BY sample_type_name
ORDER BY sample_type_name;
```

---

## 78. Instance: `bq144`
**Question:**
> Create a dataset by combining NCAA men's basketball tournament game outcomes from the 2014 season onwards, including both the historical tournament games and the 2018 tournament results, with the corresponding pace and efficiency performance metrics for each team and their opponents from the feature_engineering data. The dataset should include the season, game outcome labels (win or loss), team and opponent seeds, school names, pace and efficiency rankings, statistical values, and the differences between the team's and the opponent's metrics to enable a comprehensive analysis of team and opponent dynamics.

### 🏆 Gold Reference Answer
```sql
WITH outcomes AS (
SELECT

  season, # 1994
  "win" AS label, # our label
  win_seed AS seed, # ranking # this time without seed even
  win_school_ncaa AS school_ncaa,
  lose_seed AS opponent_seed, # ranking
  lose_school_ncaa AS opponent_school_ncaa
FROM `data-to-insights.ncaa.mbb_historical_tournament_games` t
WHERE season >= 2014
UNION ALL

SELECT

  season, # 1994
  "loss" AS label, # our label
  lose_seed AS seed, # ranking
  lose_school_ncaa AS school_ncaa,
  win_seed AS opponent_seed, # ranking
  win_school_ncaa AS opponent_school_ncaa
FROM
`data-to-insights.ncaa.mbb_historical_tournament_games` t
WHERE season >= 2014
UNION ALL

SELECT
  season,
  label,
  seed,
  school_ncaa,
  opponent_seed,
  opponent_school_ncaa
FROM
  `data-to-insights.ncaa.2018_tournament_results`
)
SELECT
o.season,
label,
  seed,
  school_ncaa,
  team.pace_rank,
  team.poss_40min,
  team.pace_rating,
  team.efficiency_rank,
  team.pts_100poss,
  team.efficiency_rating,
  opponent_seed,
  opponent_school_ncaa,
  opp.pace_rank AS opp_pace_rank,
  opp.poss_40min AS opp_poss_40min,
  opp.pace_rating AS opp_pace_rating,
  opp.efficiency_rank AS opp_efficiency_rank,
  opp.pts_100poss AS opp_pts_100poss,
  opp.efficiency_rating AS opp_efficiency_rating,
  opp.pace_rank - team.pace_rank AS pace_rank_diff,
  opp.poss_40min - team.poss_40min AS pace_stat_diff,
  opp.pace_rating - team.pace_rating AS pace_rating_diff,
  opp.efficiency_rank - team.efficiency_rank AS eff_rank_diff,
  opp.pts_100poss - team.pts_100poss AS eff_stat_diff,
  opp.efficiency_rating - team.efficiency_rating AS eff_rating_diff
FROM outcomes AS o
LEFT JOIN `data-to-insights.ncaa.feature_engineering` AS team
ON o.school_ncaa = team.team AND o.season = team.season
LEFT JOIN `data-to-insights.ncaa.feature_engineering` AS opp
ON o.opponent_school_ncaa = opp.team AND o.season = opp.season
```

### 🤖 AutoLink Baseline Prediction
```sql
-- CTE: Historical tournament games pivoted into win/loss rows (seasons 2014 onwards)
WITH historical_games AS (
  SELECT
    academic_year AS season,
    'win' AS label,
    win_seed AS seed,
    win_school_ncaa AS school_ncaa,
    lose_seed AS opponent_seed,
    lose_school_ncaa AS opponent_school_ncaa
  FROM `data-to-insights.ncaa.mbb_historical_tournament_games`
  WHERE academic_year >= 2014
  UNION ALL
  SELECT
    academic_year AS season,
    'loss' AS label,
    lose_seed AS seed,
    lose_school_ncaa AS school_ncaa,
    win_seed AS opponent_seed,
    win_school_ncaa AS opponent_school_ncaa
  FROM `data-to-insights.ncaa.mbb_historical_tournament_games`
  WHERE academic_year >= 2014
),

-- CTE: 2018 tournament results (already one row per team per game)
tournament_2018 AS (
  SELECT
    season,
    label,
    seed,
    school_ncaa,
    opponent_seed,
    opponent_school_ncaa
  FROM `data-to-insights.ncaa.2018_tournament_results`
  -- season is already 2018, no extra filter needed
),

-- Combine both sources into a unified games table
all_games AS (
  SELECT * FROM historical_games
  UNION ALL
  SELECT * FROM tournament_2018
)

-- Main query: join with feature_engineering for team and opponent metrics
SELECT
  g.season,
  g.label,
  g.seed,
  g.school_ncaa,
  g.opponent_seed,
  g.opponent_school_ncaa,
  -- Team metrics
  t.pace_rank,
  t.poss_40min,
  t.pace_rating,
  t.efficiency_rank,
  t.pts_100poss,
  t.efficiency_rating,
  -- Opponent metrics
  o.pace_rank AS opp_pace_rank,
  o.poss_40min AS opp_poss_40min,
  o.pace_rating AS opp_pace_rating,
  o.efficiency_rank AS opp_efficiency_rank,
  o.pts_100poss AS opp_pts_100poss,
  o.efficiency_rating AS opp_efficiency_rating,
  -- Differences (opponent - team), rounded to 4 decimals
  ROUND(o.pace_rank - t.pace_rank, 4) AS pace_rank_diff,
  ROUND(o.poss_40min - t.poss_40min, 4) AS pace_stat_diff,
  ROUND(o.pace_rating - t.pace_rating, 4) AS pace_rating_diff,
  ROUND(o.efficiency_rank - t.efficiency_rank, 4) AS eff_rank_diff,
  ROUND(o.pts_100poss - t.pts_100poss, 4) AS eff_stat_diff,
  ROUND(o.efficiency_rating - t.efficiency_rating, 4) AS eff_rating_diff
FROM all_games g
-- Inner join ensures both team and opponent have feature_engineering data
INNER JOIN `data-to-insights.ncaa.feature_engineering` t
  ON g.school_ncaa = t.team AND g.season = t.season
INNER JOIN `data-to-insights.ncaa.feature_engineering` o
  ON g.opponent_school_ncaa = o.team AND g.season = o.season
ORDER BY g.season, g.school_ncaa, g.label;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Understand the question
-- Core objective: Create a dataset combining NCAA men's basketball tournament game outcomes
-- from 2014 season onwards (including historical and 2018 tournament), with pace/efficiency
-- metrics from feature_engineering, including team/opponent metrics and differences.
-- 
-- Sub-problems:
-- 1. Get historical tournament games (2014+) with win/loss structure
-- 2. Get 2018 tournament results
-- 3. Join with feature_engineering for team and opponent metrics
-- 4. Calculate differences between team and opponent metrics
-- 5. Include seeds, school names, labels
--
-- Required operations: 
-- - UNION of historical and 2018 data
-- - Multiple JOINs with feature_engineering
-- - Aggregation not needed (game-level)
-- - Filtering: season >= 2014
-- - Date processing: none needed
-- - Window functions: not needed

-- Step 2: Identify relevant tables
-- - mbb_historical_tournament_games: tournament games with win/lose, seeds, schools
-- - 2018_tournament_results: 2018 specific tournament data
-- - feature_engineering: contains pace and efficiency metrics per team per season
-- 
-- Key columns:
-- - historical: academic_year (season), win_seed, lose_seed, win_school_ncaa, lose_school_ncaa
-- - 2018: season, seed, opponent_seed, school_ncaa, opponent_school_ncaa, label
-- - feature_engineering: team (school name), season, efficiency_rank, pace_rank, 
--   pace_rating, efficiency_rating, poss_40min

-- Step 3: Design SQL structure
-- Use CTEs to:
-- 1. Unify historical tournament data with 2018 data
-- 2. Join feature_engineering for team metrics
-- 3. Join feature_engineering again for opponent metrics
-- 4. Calculate differences

WITH 
-- Step 3a: Combine historical tournament games (2014+) with 2018 results
-- For historical: create win/loss structure from each row
unified_tournament AS (
  SELECT 
    academic_year AS season,
    'win' AS label,
    CAST(win_seed AS INT64) AS seed,
    win_school_ncaa AS school_ncaa,
    CAST(lose_seed AS INT64) AS opponent_seed,
    lose_school_ncaa AS opponent_school_ncaa,
    win_team_id AS team_id,
    lose_team_id AS opponent_team_id
  FROM `data-to-insights.ncaa.mbb_historical_tournament_games`
  WHERE academic_year >= 2014
  
  UNION ALL
  
  -- For historical losing teams: create loss label
  SELECT 
    academic_year AS season,
    'loss' AS label,
    CAST(lose_seed AS INT64) AS seed,
    lose_school_ncaa AS school_ncaa,
    CAST(win_seed AS INT64) AS opponent_seed,
    win_school_ncaa AS opponent_school_ncaa,
    lose_team_id AS team_id,
    win_team_id AS opponent_team_id
  FROM `data-to-insights.ncaa.mbb_historical_tournament_games`
  WHERE academic_year >= 2014
  
  UNION ALL
  
  -- 2018 tournament results (already has labels)
  SELECT 
    season,
    label,
    CAST(seed AS INT64) AS seed,
    school_ncaa,
    CAST(opponent_seed AS INT64) AS opponent_seed,
    opponent_school_ncaa AS opponent_school_ncaa,
    -- Note: 2018 table doesn't have team_id, use school_ncaa for matching
    school_ncaa AS team_id,
    opponent_school_ncaa AS opponent_team_id
  FROM `data-to-insights.ncaa.2018_tournament_results`
  WHERE season = 2018
),

-- Step 3b: Join feature_engineering for team metrics
-- Use team name for matching (feature_engineering uses 'team' column)
team_metrics AS (
  SELECT 
    u.*,
    fe.pace_rank,
    fe.pace_rating,
    fe.efficiency_rank,
    fe.efficiency_rating,
    fe.poss_40min,
    -- Note: pts_100poss not in feature_engineering directly
    -- Calculate from efficiency_rating or use as-is
    ROUND(fe.efficiency_rating * 100 / NULLIF(fe.pace_rating, 0), 4) AS pts_100poss
  FROM unified_tournament u
  LEFT JOIN `data-to-insights.ncaa.feature_engineering` fe
    ON LOWER(u.school_ncaa) = LOWER(fe.team)
    AND u.season = fe.season
),

-- Step 3c: Join feature_engineering for opponent metrics
-- Match opponent school name to feature_engineering team name
combined_metrics AS (
  SELECT 
    tm.*,
    opp.pace_rank AS opp_pace_rank,
    opp.pace_rating AS opp_pace_rating,
    opp.efficiency_rank AS opp_efficiency_rank,
    opp.efficiency_rating AS opp_efficiency_rating,
    opp.poss_40min AS opp_poss_40min,
    ROUND(opp.efficiency_rating * 100 / NULLIF(opp.pace_rating, 0), 4) AS opp_pts_100poss,
    
    -- Step 3d: Calculate differences
    ROUND(tm.pace_rank - opp.pace_rank, 4) AS pace_rank_diff,
    ROUND(tm.pace_rating - opp.pace_rating, 4) AS pace_rating_diff,
    ROUND(tm.efficiency_rank - opp.efficiency_rank, 4) AS eff_rank_diff,
    ROUND(tm.efficiency_rating - opp.efficiency_rating, 4) AS eff_rating_diff,
    ROUND(tm.pts_100poss - opp.pts_100poss, 4) AS eff_stat_diff
  FROM team_metrics tm
  LEFT JOIN `data-to-insights.ncaa.feature_engineering` opp
    ON LOWER(tm.opponent_school_ncaa) = LOWER(opp.team)
    AND tm.season = opp.season
)

-- Final SELECT with all required columns
SELECT 
  season,
  label,
  seed,
  school_ncaa,
  opponent_seed,
  opponent_school_ncaa,
  -- Team metrics
  pace_rank,
  poss_40min,
  pace_rating,
  efficiency_rank,
  pts_100poss,
  efficiency_rating,
  -- Opponent metrics
  opp_pace_rank,
  opp_poss_40min,
  opp_pace_rating,
  opp_efficiency_rank,
  opp_pts_100poss,
  opp_efficiency_rating,
  -- Differences
  pace_rank_diff,
  pace_rating_diff,
  eff_rank_diff,
  eff_rating_diff,
  eff_stat_diff
FROM combined_metrics
WHERE season >= 2014
ORDER BY season, label, seed;
```

---

## 79. Instance: `bq151`
**Question:**
> Using TCGA dataset, calculate the chi-squared statistic to evaluate the association between KRAS and TP53 gene mutations in patients diagnosed with pancreatic adenocarcinoma (PAAD). Incorporate clinical follow-up data and high-quality mutation annotations to accurately determine the frequency of patients with co-occurring KRAS and TP53 mutations compared to those with each mutation occurring independently. Ensure that patient records are meticulously matched based on unique identifiers to maintain data integrity. This analysis aims to identify and quantify potential correlations between KRAS and TP53 genetic alterations within the PAAD patient population.

### 🏆 Gold Reference Answer
```sql
WITH
barcodes AS (
   SELECT bcr_patient_barcode AS ParticipantBarcode
   FROM isb-cgc-bq.pancancer_atlas.Filtered_clinical_PANCAN_patient_with_followup
   WHERE acronym = 'PAAD'
),
table1 AS (
SELECT
   t1.ParticipantBarcode,
   IF(t2.ParticipantBarcode IS NULL, 'NO', 'YES') AS data
FROM
   barcodes AS t1
LEFT JOIN
   (
   SELECT
      ParticipantBarcode AS ParticipantBarcode
   FROM isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample
   WHERE Study = 'PAAD' AND Hugo_Symbol = 'KRAS'
         AND FILTER = 'PASS'
   GROUP BY ParticipantBarcode
   ) AS t2
ON t1.ParticipantBarcode = t2.ParticipantBarcode
),
table2 AS (
SELECT
   t1.ParticipantBarcode,
   IF(t2.ParticipantBarcode IS NULL, 'NO', 'YES') AS data
FROM
   barcodes AS t1
LEFT JOIN
   (
   SELECT
      ParticipantBarcode AS ParticipantBarcode
   FROM isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample
   WHERE Study = 'PAAD' AND Hugo_Symbol = 'TP53'
         AND FILTER = 'PASS'
   GROUP BY ParticipantBarcode
   ) AS t2
ON t1.ParticipantBarcode = t2.ParticipantBarcode
),
summ_table AS (
SELECT
   n1.data AS data1,
   n2.data AS data2,
   COUNT(*) AS Nij
FROM
   table1 AS n1
INNER JOIN
   table2 AS n2
ON
   n1.ParticipantBarcode = n2.ParticipantBarcode
GROUP BY
  data1, data2
),
contingency_table AS (
SELECT
  MAX(IF((data1 = 'YES') AND (data2 = 'YES'), Nij, 0)) AS a,
  MAX(IF((data1 = 'YES') AND (data2 = 'NO'), Nij, 0)) AS b,
  MAX(IF((data1 = 'NO') AND (data2 = 'YES'), Nij, 0)) AS c,
  MAX(IF((data1 = 'NO') AND (data2 = 'NO'), Nij, 0)) AS d,
  (MAX(IF((data1 = 'YES') AND (data2 = 'YES'), Nij, 0)) + MAX(IF((data1 = 'YES') AND (data2 = 'NO'), Nij, 0))) AS row1_total,
  (MAX(IF((data1 = 'NO') AND (data2 = 'YES'), Nij, 0)) + MAX(IF((data1 = 'NO') AND (data2 = 'NO'), Nij, 0))) AS row2_total,
  (MAX(IF((data1 = 'YES') AND (data2 = 'YES'), Nij, 0)) + MAX(IF((data1 = 'NO') AND (data2 = 'YES'), Nij, 0))) AS col1_total,
  (MAX(IF((data1 = 'YES') AND (data2 = 'NO'), Nij, 0)) + MAX(IF((data1 = 'NO') AND (data2 = 'NO'), Nij, 0))) AS col2_total,
  SUM(Nij) AS grand_total
FROM summ_table
)
SELECT
  POWER((a - (row1_total * col1_total) / grand_total), 2) / ((row1_total * col1_total) / grand_total) +
  POWER((b - (row1_total * col2_total) / grand_total), 2) / ((row1_total * col2_total) / grand_total) +
  POWER((c - (row2_total * col1_total) / grand_total), 2) / ((row2_total * col1_total) / grand_total) +
  POWER((d - (row2_total * col2_total) / grand_total), 2) / ((row2_total * col2_total) / grand_total) AS chi_square_statistic
FROM contingency_table
WHERE a IS NOT NULL AND b IS NOT NULL AND c IS NOT NULL AND d IS NOT NULL;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Retrieve all PAAD patients from clinical follow-up table
WITH paad_patients AS (
  SELECT DISTINCT bcr_patient_barcode AS patient_barcode
  FROM `isb-cgc-bq.pancancer_atlas.Original_clinical_PANCAN_patient_with_followup`
  WHERE LOWER(acronym) = 'paad'
),

-- Step 2: Identify patients with high-quality KRAS mutations from MC3 MAF
kras_mut AS (
  SELECT DISTINCT ParticipantBarcode
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
  WHERE Study = 'PAAD'
    AND Hugo_Symbol = 'KRAS'
    AND FILTER = 'PASS'
),

-- Step 3: Identify patients with high-quality TP53 mutations from MC3 MAF
tp53_mut AS (
  SELECT DISTINCT ParticipantBarcode
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
  WHERE Study = 'PAAD'
    AND Hugo_Symbol = 'TP53'
    AND FILTER = 'PASS'
),

-- Step 4: Assign mutation status to each PAAD patient
patient_mutation AS (
  SELECT
    p.patient_barcode,
    CASE WHEN k.ParticipantBarcode IS NOT NULL THEN 1 ELSE 0 END AS has_kras,
    CASE WHEN t.ParticipantBarcode IS NOT NULL THEN 1 ELSE 0 END AS has_tp53
  FROM paad_patients p
  LEFT JOIN kras_mut k ON p.patient_barcode = k.ParticipantBarcode
  LEFT JOIN tp53_mut t ON p.patient_barcode = t.ParticipantBarcode
),

-- Step 5: Build 2x2 contingency table counts
contingency AS (
  SELECT
    SUM(CASE WHEN has_kras = 1 AND has_tp53 = 1 THEN 1 ELSE 0 END) AS both_mut,
    SUM(CASE WHEN has_kras = 1 AND has_tp53 = 0 THEN 1 ELSE 0 END) AS kras_only,
    SUM(CASE WHEN has_kras = 0 AND has_tp53 = 1 THEN 1 ELSE 0 END) AS tp53_only,
    SUM(CASE WHEN has_kras = 0 AND has_tp53 = 0 THEN 1 ELSE 0 END) AS none_mut,
    COUNT(*) AS total
  FROM patient_mutation
),

-- Step 6: Compute expected frequencies under independence
expected AS (
  SELECT
    both_mut,
    kras_only,
    tp53_only,
    none_mut,
    total,
    -- Row total for KRAS+ = both_mut + kras_only
    -- Column total for TP53+ = both_mut + tp53_only
    -- Expected both = (row_total_KRAS+ * col_total_TP53+) / N
    SAFE_DIVIDE((both_mut + kras_only) * (both_mut + tp53_only), total) AS expected_both,
    SAFE_DIVIDE((both_mut + kras_only) * (none_mut + tp53_only), total) AS expected_kras_only,
    SAFE_DIVIDE((none_mut + tp53_only) * (both_mut + tp53_only), total) AS expected_tp53_only,
    SAFE_DIVIDE((none_mut + tp53_only) * (none_mut + kras_only), total) AS expected_none
  FROM contingency
)

-- Step 7: Calculate chi-squared statistic
SELECT
  ROUND(
    POW(both_mut - expected_both, 2) / expected_both +
    POW(kras_only - expected_kras_only, 2) / expected_kras_only +
    POW(tp53_only - expected_tp53_only, 2) / expected_tp53_only +
    POW(none_mut - expected_none, 2) / expected_none,
    4
  ) AS chi_squared_statistic,
  both_mut,
  kras_only,
  tp53_only,
  none_mut,
  total
FROM expected;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Chi-squared test for association between KRAS and TP53 mutations in PAAD patients
-- Uses high-quality mutation annotations from the MC3 MAF table.
-- Step 1: Extract non-silent mutations in KRAS and TP53 for PAAD
WITH mutations AS (
  SELECT 
    ParticipantBarcode,
    Hugo_Symbol
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
  WHERE 
    Study = 'PAAD'
    AND Hugo_Symbol IN ('KRAS', 'TP53')
    -- Keep likely functional mutations (non-silent)
    AND Variant_Classification IN (
      'Missense_Mutation', 'Nonsense_Mutation', 'Frame_Shift_Del',
      'Frame_Shift_Ins', 'In_Frame_Del', 'In_Frame_Ins',
      'Splice_Site', 'Nonstop_Mutation', 'Translation_Start_Site'
    )
),

-- Step 2: Per patient, flag presence of mutation in each gene
patient_mut AS (
  SELECT 
    ParticipantBarcode,
    MAX(CASE WHEN Hugo_Symbol = 'KRAS' THEN 1 ELSE 0 END) AS kras_mut,
    MAX(CASE WHEN Hugo_Symbol = 'TP53' THEN 1 ELSE 0 END) AS tp53_mut
  FROM mutations
  GROUP BY ParticipantBarcode
),

-- Step 3: Get all PAAD patients (even those without mutations)
all_paad_patients AS (
  SELECT DISTINCT ParticipantBarcode
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
  WHERE Study = 'PAAD'
),

-- Step 4: Build complete patient list with mutation flags (0 if missing)
contingency AS (
  SELECT 
    p.ParticipantBarcode,
    COALESCE(m.kras_mut, 0) AS kras_mut,
    COALESCE(m.tp53_mut, 0) AS tp53_mut
  FROM all_paad_patients p
  LEFT JOIN patient_mut m
    ON p.ParticipantBarcode = m.ParticipantBarcode
),

-- Step 5: Count patients in each of the four categories
counts AS (
  SELECT 
    SUM(CASE WHEN kras_mut = 1 AND tp53_mut = 1 THEN 1 ELSE 0 END) AS both_mut,
    SUM(CASE WHEN kras_mut = 1 AND tp53_mut = 0 THEN 1 ELSE 0 END) AS kras_only,
    SUM(CASE WHEN kras_mut = 0 AND tp53_mut = 1 THEN 1 ELSE 0 END) AS tp53_only,
    SUM(CASE WHEN kras_mut = 0 AND tp53_mut = 0 THEN 1 ELSE 0 END) AS none_mut
  FROM contingency
),

-- Step 6: Prepare marginal sums and total for chi-squared calculation
chi_sq_prep AS (
  SELECT 
    both_mut,
    kras_only,
    tp53_only,
    none_mut,
    (both_mut + kras_only) AS row1_sum,   -- KRAS+ (all patients with KRAS mutation)
    (tp53_only + none_mut) AS row2_sum,   -- KRAS- (patients without KRAS mutation)
    (both_mut + tp53_only) AS col1_sum,   -- TP53+ (patients with TP53 mutation)
    (kras_only + none_mut) AS col2_sum,   -- TP53- (patients without TP53 mutation)
    (both_mut + kras_only + tp53_only + none_mut) AS total
  FROM counts
)

-- Step 7: Compute Pearson chi-squared statistic
SELECT 
  both_mut,
  kras_only,
  tp53_only,
  none_mut,
  ROUND(
    -- Note: Use floating-point arithmetic to avoid integer division
    ( (POW(1.0 * both_mut - (1.0 * row1_sum * col1_sum / total), 2) / (1.0 * row1_sum * col1_sum / total))
    + (POW(1.0 * kras_only - (1.0 * row1_sum * col2_sum / total), 2) / (1.0 * row1_sum * col2_sum / total))
    + (POW(1.0 * tp53_only - (1.0 * row2_sum * col1_sum / total), 2) / (1.0 * row2_sum * col1_sum / total))
    + (POW(1.0 * none_mut - (1.0 * row2_sum * col2_sum / total), 2) / (1.0 * row2_sum * col2_sum / total)) ),
    4
  ) AS chi_squared_statistic
FROM chi_sq_prep;
```

---

## 80. Instance: `bq161`
**Question:**
> Calculate the net difference between the number of pancreatic adenocarcinoma (PAAD) patients in TCGA's dataset who are confirmed to have mutations in both KRAS and TP53 genes, and those without mutations in either gene. Utilize patient clinical and follow-up data alongside genomic mutation details from TCGA’s cancer genomics database, focusing specifically on PAAD studies where the mutations have passed quality filters.

### 🏆 Gold Reference Answer
```sql
WITH
barcodes AS (
   SELECT bcr_patient_barcode AS ParticipantBarcode
   FROM `isb-cgc-bq.pancancer_atlas.Filtered_clinical_PANCAN_patient_with_followup`
   WHERE acronym = 'PAAD'
)
,table1 AS (
SELECT
   t1.ParticipantBarcode,
   IF( t2.ParticipantBarcode is null, 'NO', 'YES') as data
FROM
   barcodes AS t1
LEFT JOIN
   (
   SELECT
      ParticipantBarcode AS ParticipantBarcode
   FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
   WHERE Study = 'PAAD' AND Hugo_Symbol = 'KRAS'
         AND FILTER = 'PASS'
   GROUP BY ParticipantBarcode
   ) AS t2
ON t1.ParticipantBarcode = t2.ParticipantBarcode
)
,table2 AS (
SELECT
   t1.ParticipantBarcode,
   IF( t2.ParticipantBarcode is null, 'NO', 'YES') as data
FROM
   barcodes AS t1
LEFT JOIN
   (
   SELECT
      ParticipantBarcode AS ParticipantBarcode
   FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
   WHERE Study = 'PAAD' AND Hugo_Symbol = 'TP53'
         AND FILTER = 'PASS'
   GROUP BY ParticipantBarcode
   ) AS t2
ON t1.ParticipantBarcode = t2.ParticipantBarcode
),

INFO AS (
SELECT
   n1.data as data1,
   n2.data as data2,
   COUNT(*) as Nij
FROM
   table1 AS n1
INNER JOIN
   table2 AS n2
ON
   n1.ParticipantBarcode = n2.ParticipantBarcode
GROUP BY
  data1, data2
)

SELECT 
(SELECT Nij FROM INFO WHERE data1="YES" AND data2="YES")
-
(SELECT Nij FROM INFO WHERE data1="NO" AND data2="NO")
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Identify PAAD patients from clinical data
WITH paad_clinical AS (
  SELECT DISTINCT bcr_patient_barcode
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_clinical_PANCAN_patient_with_followup`
  WHERE disease_code = 'PAAD'
),

-- Step 2: Identify all PAAD patients with any mutation call in the MC3 dataset (sequenced cohort)
paad_sequenced AS (
  SELECT DISTINCT ParticipantBarcode
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
  WHERE Study = 'PAAD'
),

-- Step 3: Final cohort = PAAD patients who were sequenced
paad_cohort AS (
  SELECT DISTINCT c.bcr_patient_barcode
  FROM paad_clinical c
  INNER JOIN paad_sequenced s
    ON c.bcr_patient_barcode = s.ParticipantBarcode
),

-- Step 4: Patients with at least one PASS mutation in KRAS
kras_mut AS (
  SELECT DISTINCT ParticipantBarcode
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
  WHERE Study = 'PAAD'
    AND Hugo_Symbol = 'KRAS'
    AND FILTER = 'PASS'
),

-- Step 5: Patients with at least one PASS mutation in TP53
tp53_mut AS (
  SELECT DISTINCT ParticipantBarcode
  FROM `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
  WHERE Study = 'PAAD'
    AND Hugo_Symbol = 'TP53'
    AND FILTER = 'PASS'
),

-- Step 6: Patients having both KRAS and TP53 PASS mutations
both_mut AS (
  SELECT k.ParticipantBarcode
  FROM kras_mut k
  INNER JOIN tp53_mut t
    ON k.ParticipantBarcode = t.ParticipantBarcode
),

-- Step 7: Patients with no PASS mutation in either KRAS or TP53
neither_mut AS (
  SELECT c.bcr_patient_barcode
  FROM paad_cohort c
  WHERE c.bcr_patient_barcode NOT IN (SELECT ParticipantBarcode FROM kras_mut)
    AND c.bcr_patient_barcode NOT IN (SELECT ParticipantBarcode FROM tp53_mut)
)

-- Step 8: Compute net difference = (count with both) - (count with neither)
SELECT
  (SELECT COUNT(*) FROM both_mut) - (SELECT COUNT(*) FROM neither_mut) AS net_difference;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Define PAAD patients from original clinical table (all PAAD cases)
WITH paad_patients AS (
  SELECT DISTINCT
    bcr_patient_barcode AS patient_barcode
  FROM
    `isb-cgc-bq.pancancer_atlas.Original_clinical_PANCAN_patient_with_followup`
  WHERE
    disease_code = 'PAAD'
),

-- Step 2: Identify patients with quality-passed mutations in KRAS or TP53
gene_mutations AS (
  SELECT
    ParticipantBarcode AS patient_barcode,
    Hugo_Symbol AS gene,
    -- Flag if any mutation passed filter
    LOGICAL_OR(FILTER = 'PASS') AS has_pass_mutation
  FROM
    `isb-cgc-bq.pancancer_atlas.Filtered_MC3_MAF_V5_one_per_tumor_sample`
  WHERE
    Hugo_Symbol IN ('KRAS', 'TP53')
  GROUP BY
    patient_barcode,
    gene
),

-- Step 3: Pivot mutation flags per patient (one row per patient)
patient_mutation_flags AS (
  SELECT
    patient_barcode,
    MAX(CASE WHEN gene = 'KRAS' AND has_pass_mutation THEN 1 ELSE 0 END) AS kras_mut,
    MAX(CASE WHEN gene = 'TP53' AND has_pass_mutation THEN 1 ELSE 0 END) AS tp53_mut
  FROM
    gene_mutations
  GROUP BY
    patient_barcode
),

-- Step 4: Combine PAAD patients with mutation flags (use LEFT JOIN to include all)
patient_status AS (
  SELECT
    p.patient_barcode,
    COALESCE(m.kras_mut, 0) AS kras_mut,
    COALESCE(m.tp53_mut, 0) AS tp53_mut
  FROM
    paad_patients p
  LEFT JOIN
    patient_mutation_flags m
  ON
    p.patient_barcode = m.patient_barcode
)

-- Step 5: Compute counts and net difference
SELECT
  COUNTIF(kras_mut = 1 AND tp53_mut = 1) AS both_mutations,
  COUNTIF(kras_mut = 0 AND tp53_mut = 0) AS neither_mutation,
  COUNTIF(kras_mut = 1 AND tp53_mut = 1) - COUNTIF(kras_mut = 0 AND tp53_mut = 0) AS net_difference
FROM
  patient_status;
```

---

## 81. Instance: `bq162`
**Question:**
> Based on the 5th revision (r5) of the HTAN data, list the imaging assay types available at the HTAN WUSTL center that have Level2 data and any associated higher-level data (Level3, Level4) derived from them through 'entityId' relationships in the 'id_provenance_r5' table; exclude any records where the 'Component' is NULL or contains 'Auxiliary' or 'OtherAssay'; for each imaging assay type, provide the available data levels (Level2, Level3, Level4), and do not include Level1 data or Electron Microscopy assay types.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Get distinct Imaging_Assay_Type and HTAN_Data_File_ID from WUSTL Level2 data (srrs_imaging_level2_metadata_r5)
-- Apply exclusion on Component (NULL, Auxiliary, OtherAssay). Also exclude Electron Microscopy by assay type.
WITH level2_data AS (
  SELECT DISTINCT
    Imaging_Assay_Type,
    HTAN_Data_File_ID
  FROM `isb-cgc-bq.HTAN_versioned.srrs_imaging_level2_metadata_r5`
  WHERE
    Component IS NOT NULL
    AND LOWER(Component) NOT LIKE '%auxiliary%'
    AND LOWER(Component) NOT LIKE '%otherassay%'
    AND LOWER(Imaging_Assay_Type) NOT LIKE '%electron%'   -- exclude Electron Microscopy
),

-- Step 2: Find all child records in id_provenance_r5 that are derived from the above Level2 files.
-- Filter out records with NULL/Auxiliary/OtherAssay Component, and only keep imaging Level3 or Level4.
-- Also exclude Level1 or ElectronMicroscopy.
provenance_children AS (
  SELECT
    p.HTAN_Parent_Data_File_ID,
    p.HTAN_Data_File_ID AS child_file_id,
    p.Component,
    CASE
      WHEN LOWER(p.Component) LIKE '%imaginglevel3%' THEN 'Level3'
      WHEN LOWER(p.Component) LIKE '%imaginglevel4%' THEN 'Level4'
      ELSE NULL
    END AS data_level
  FROM `isb-cgc-bq.HTAN_versioned.id_provenance_r5` p
  WHERE
    p.Component IS NOT NULL
    AND LOWER(p.Component) NOT LIKE '%auxiliary%'
    AND LOWER(p.Component) NOT LIKE '%otherassay%'
    AND LOWER(p.Component) NOT LIKE '%level1%'         -- exclude Level1
    AND LOWER(p.Component) NOT LIKE '%electron%'       -- exclude ElectronMicroscopy
    AND (LOWER(p.Component) LIKE '%imaginglevel3%' OR LOWER(p.Component) LIKE '%imaginglevel4%')
),

-- Step 3: Combine Level2 with its children to determine which higher levels exist per assay type.
-- Include Level2 as the base level.
levels_per_assay AS (
  SELECT
    l2.Imaging_Assay_Type,
    'Level2' AS data_level
  FROM level2_data l2
  UNION DISTINCT
  SELECT
    l2.Imaging_Assay_Type,
    pc.data_level
  FROM level2_data l2
  INNER JOIN provenance_children pc
    ON l2.HTAN_Data_File_ID = pc.HTAN_Parent_Data_File_ID
  WHERE pc.data_level IS NOT NULL   -- should not be null due to CASE, but safe
)

-- Final output: for each Imaging_Assay_Type, list the available data levels as a comma-separated string.
SELECT
  Imaging_Assay_Type,
  STRING_AGG(data_level, ', ' ORDER BY data_level) AS available_data_levels
FROM levels_per_assay
GROUP BY Imaging_Assay_Type
ORDER BY Imaging_Assay_Type;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
level2_data AS (
  SELECT DISTINCT
    l2.Component,
    l2.entityId,
    l2.HTAN_Data_File_ID,
    'Level2' AS data_level
  FROM `isb-cgc-bq.HTAN_versioned.imaging_level2_metadata_r5` l2
  WHERE l2.Component IS NOT NULL
    AND UPPER(l2.Component) NOT LIKE '%AUXILIARY%'
    AND UPPER(l2.Component) NOT LIKE '%OTHERASSAY%'
    AND UPPER(l2.Component) NOT LIKE '%ELECTRON%'
),

level4_data AS (
  SELECT DISTINCT
    l4.Component,
    l4.entityId,
    l4.HTAN_Data_File_ID,
    'Level4' AS data_level
  FROM `isb-cgc-bq.HTAN_versioned.imaging_level4_metadata_r5` l4
  WHERE l4.Component IS NOT NULL
    AND UPPER(l4.Component) NOT LIKE '%AUXILIARY%'
    AND UPPER(l4.Component) NOT LIKE '%OTHERASSAY%'
    AND UPPER(l4.Component) NOT LIKE '%ELECTRON%'
),

all_levels AS (
  SELECT * FROM level2_data
  UNION ALL
  SELECT * FROM level4_data
)

SELECT 
  Component AS imaging_assay_type,
  STRING_AGG(DISTINCT data_level ORDER BY data_level) AS available_data_levels
FROM all_levels
GROUP BY Component
ORDER BY Component;
```

---

## 82. Instance: `bq165`
**Question:**
> Can you use CytoConverter genomic coordinates to calculate the frequency of chromosomal gains and losses across a cohort of breast cancer (morphology='3111') and adenocarcinoma (topology='0401') samples? Concretely, please include the number and frequency (2 decimals in percentage) of amplifications (gains of more than 1 copy), gains (1 extra copy), losses (1 copy) and homozygous deletions (loss of 2 copies) for each chromosomal band. And sort the result by the ordinal of each chromosome and the starting-ending base-pair position of each band in ascending order.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Step 1: Get relevant cases based on morphology/topology
relevant_cases AS (
    SELECT DISTINCT c.RefNo, c.CaseNo, c.InvNo
    FROM `mitelman-db.prod.Cytogen` c
    WHERE c.Morph = '3111' OR c.Topo = '0401'
),

-- Step 2: Get converted genomic coordinates for these cases
converted_data AS (
    SELECT 
        cc.Chr,
        cc.RefNo,
        cc.CaseNo,
        cc.InvNo,
        cc.ChrOrd,
        cc.Start,
        cc.End,
        cc.Type,
        CASE 
            WHEN LOWER(cc.Type) LIKE '%amplif%' THEN 'Amplification'
            WHEN LOWER(cc.Type) = 'gain' THEN 'Gain'
            WHEN LOWER(cc.Type) = 'loss' THEN 'Loss'
            WHEN LOWER(cc.Type) LIKE '%delet%' OR LOWER(cc.Type) LIKE '%homozyg%' THEN 'Homozygous Deletion'
            ELSE cc.Type
        END AS event_type
    FROM `mitelman-db.prod.CytoConverted` cc
    INNER JOIN relevant_cases rc
        ON cc.RefNo = rc.RefNo 
        AND cc.CaseNo = rc.CaseNo 
        AND cc.InvNo = rc.InvNo
),

-- Step 3: Map to chromosomal bands
band_mapping AS (
    SELECT 
        cd.*,
        cb.cytoband_name,
        cb.hg38_start,
        cb.hg38_stop
    FROM converted_data cd
    LEFT JOIN `mitelman-db.prod.CytoBands_hg38` cb
        ON cd.Chr = cb.chromosome
        -- Check if the converted region overlaps with the band
        AND cd.Start < cb.hg38_stop
        AND cd.End > cb.hg38_start
)

-- Final aggregation
SELECT 
    bm.cytoband_name AS chromosomal_band,
    bm.Chr AS chromosome,
    bm.hg38_start AS band_start,
    bm.hg38_stop AS band_end,
    COUNT(DISTINCT CONCAT(CAST(bm.RefNo AS STRING), '-', bm.CaseNo, '-', CAST(bm.InvNo AS STRING))) AS total_samples,
    SUM(CASE WHEN bm.event_type = 'Amplification' THEN 1 ELSE 0 END) AS amplification_count,
    SUM(CASE WHEN bm.event_type = 'Gain' THEN 1 ELSE 0 END) AS gain_count,
    SUM(CASE WHEN bm.event_type = 'Loss' THEN 1 ELSE 0 END) AS loss_count,
    SUM(CASE WHEN bm.event_type = 'Homozygous Deletion' THEN 1 ELSE 0 END) AS homozygous_deletion_count,
    ROUND(
        SUM(CASE WHEN bm.event_type = 'Amplification' THEN 1 ELSE 0 END) * 100.0 / 
        NULLIF(COUNT(DISTINCT CONCAT(CAST(bm.RefNo AS STRING), '-', bm.CaseNo, '-', CAST(bm.InvNo AS STRING))), 0), 
        2
    ) AS amplification_freq_pct,
    ROUND(
        SUM(CASE WHEN bm.event_type = 'Gain' THEN 1 ELSE 0 END) * 100.0 / 
        NULLIF(COUNT(DISTINCT CONCAT(CAST(bm.RefNo AS STRING), '-', bm.CaseNo, '-', CAST(bm.InvNo AS STRING))), 0), 
        2
    ) AS gain_freq_pct,
    ROUND(
        SUM(CASE WHEN bm.event_type = 'Loss' THEN 1 ELSE 0 END) * 100.0 / 
        NULLIF(COUNT(DISTINCT CONCAT(CAST(bm.RefNo AS STRING), '-', bm.CaseNo, '-', CAST(bm.InvNo AS STRING))), 0), 
        2
    ) AS loss_freq_pct,
    ROUND(
        SUM(CASE WHEN bm.event_type = 'Homozygous Deletion' THEN 1 ELSE 0 END) * 100.0 / 
        NULLIF(COUNT(DISTINCT CONCAT(CAST(bm.RefNo AS STRING), '-', bm.CaseNo, '-', CAST(bm.InvNo AS STRING))), 0), 
        2
    ) AS homozygous_deletion_freq_pct
FROM band_mapping bm
GROUP BY bm.cytoband_name, bm.Chr, bm.hg38_start, bm.hg38_stop
ORDER BY 
    CASE 
        WHEN bm.Chr = 'chrX' THEN 23
        WHEN bm.Chr = 'chrY' THEN 24
        ELSE CAST(REPLACE(bm.Chr, 'chr', '') AS INT64)
    END ASC,
    bm.hg38_start ASC,
    bm.hg38_stop ASC;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
  -- Step 1: Define the cohort of cases (breast cancer morphology='3111' OR adenocarcinoma topology='0401')
  cohort_cases AS (
    SELECT DISTINCT
      RefNo,
      CaseNo
    FROM `mitelman-db.prod.Cytogen`
    WHERE Morph = '3111' OR Topo = '0401'
  ),

  -- Step 2: Total number of distinct cases in the cohort (denominator for frequency)
  total_cases AS (
    SELECT COUNT(*) AS total FROM cohort_cases
  ),

  -- Step 3: Join CytoConverted with CytoBands_hg38 to map each alteration to cytobands
  band_alterations AS (
    SELECT DISTINCT
      cc.RefNo,
      cc.CaseNo,
      cb.chromosome,
      cb.cytoband_name,
      cb.hg38_start,
      cb.hg38_stop,
      cc.Type
    FROM `mitelman-db.prod.CytoConverted` AS cc
    INNER JOIN cohort_cases AS co
      ON cc.RefNo = co.RefNo AND cc.CaseNo = co.CaseNo
    INNER JOIN `mitelman-db.prod.CytoBands_hg38` AS cb
      ON cc.Chr = cb.chromosome
         AND cc.Start < cb.hg38_stop
         AND cc.End > cb.hg38_start
    WHERE cc.Type IN ('Amplification', 'Gain', 'Loss', 'Homozygous deletion')  -- Keep only relevant types
  ),

  -- Step 4: Aggregate counts per band and type
  aggregated_counts AS (
    SELECT
      chromosome,
      cytoband_name,
      hg38_start,
      hg38_stop,
      Type,
      COUNT(DISTINCT (RefNo || '-' || CaseNo)) AS alteration_count
    FROM band_alterations
    GROUP BY chromosome, cytoband_name, hg38_start, hg38_stop, Type
  ),

  -- Step 5: Get all distinct bands that appear in the data (to ensure all four types appear per band)
  distinct_bands AS (
    SELECT DISTINCT
      chromosome,
      cytoband_name,
      hg38_start,
      hg38_stop
    FROM band_alterations
  ),

  -- Step 6: Cross join with all four possible alteration types to guarantee a row per band per type
  type_list AS (
    SELECT 'Amplification' AS Type
    UNION ALL
    SELECT 'Gain'
    UNION ALL
    SELECT 'Loss'
    UNION ALL
    SELECT 'Homozygous deletion'
  ),
  all_band_types AS (
    SELECT
      db.chromosome,
      db.cytoband_name,
      db.hg38_start,
      db.hg38_stop,
      tl.Type
    FROM distinct_bands AS db
    CROSS JOIN type_list AS tl
  )

-- Final selection: number, frequency, and sorting
SELECT
  abt.chromosome,
  abt.cytoband_name AS band,
  abt.hg38_start,
  abt.hg38_stop,
  abt.Type,
  COALESCE(ac.alteration_count, 0) AS number,
  ROUND(
    COALESCE(ac.alteration_count, 0) * 100.0 / tc.total,
    2
  ) AS frequency_percentage,
  -- Compute chromosome numeric order for sorting
  CASE
    WHEN abt.chromosome = 'chrX' THEN 23
    WHEN abt.chromosome = 'chrY' THEN 24
    ELSE SAFE_CAST(REGEXP_EXTRACT(abt.chromosome, r'chr(\d+)') AS INT64)
  END AS chr_ord
FROM all_band_types AS abt
LEFT JOIN aggregated_counts AS ac
  ON abt.chromosome = ac.chromosome
     AND abt.cytoband_name = ac.cytoband_name
     AND abt.Type = ac.Type
CROSS JOIN total_cases AS tc
ORDER BY
  chr_ord ASC,
  abt.hg38_start ASC,
  abt.Type ASC;
```

---

## 83. Instance: `bq169`
**Question:**
> Retrieve distinct case references, case numbers, investigation numbers, and clone information where a single clone simultaneously exhibits all three of the following genetic alterations: (1) a loss on chromosome 13 between positions 48,303,751 and 48,481,890, (2) a loss on chromosome 17 between positions 7,668,421 and 7,687,490, and (3) a gain on chromosome 11 between positions 108,223,067 and 108,369,102. For each matching clone, display the chromosomal details for each of these three regions (including chromosome number represented by ChrOrd, start position, and end position) and the corresponding karyotype short description from the KaryClone table. Use the CytoConverted and KaryClone.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
  -- Extract records for loss on chromosome 13 (ChrOrd = 13)
  loss_chr13 AS (
    SELECT
      Clone,
      CaseNo,
      RefNo,
      InvNo,
      Start AS chr13_start,
      End AS chr13_end,
      ChrOrd
    FROM `mitelman-db.prod.CytoConverted`
    WHERE
      Type = 'Loss'
      AND ChrOrd = 13
      AND Start < 48481890
      AND End > 48303751
  ),

  -- Extract records for loss on chromosome 17 (ChrOrd = 17)
  loss_chr17 AS (
    SELECT
      Clone,
      CaseNo,
      RefNo,
      InvNo,
      Start AS chr17_start,
      End AS chr17_end,
      ChrOrd
    FROM `mitelman-db.prod.CytoConverted`
    WHERE
      Type = 'Loss'
      AND ChrOrd = 17
      AND Start < 7687490
      AND End > 7668421
  ),

  -- Extract records for gain on chromosome 11 (ChrOrd = 11)
  gain_chr11 AS (
    SELECT
      Clone,
      CaseNo,
      RefNo,
      InvNo,
      Start AS chr11_start,
      End AS chr11_end,
      ChrOrd
    FROM `mitelman-db.prod.CytoConverted`
    WHERE
      Type = 'Gain'
      AND ChrOrd = 11
      AND Start < 108369102
      AND End > 108223067
  )

-- Join all three CTEs to find clones that have all three alterations simultaneously
SELECT DISTINCT
  l13.CaseNo AS case_reference,
  l13.Clone AS clone_number,
  l13.InvNo AS investigation_number,
  l13.RefNo AS reference_number,  -- included for completeness
  13 AS chr13_chrord,
  l13.chr13_start,
  l13.chr13_end,
  17 AS chr17_chrord,
  l17.chr17_start,
  l17.chr17_end,
  11 AS chr11_chrord,
  g11.chr11_start,
  g11.chr11_end,
  kc.CloneShort AS karyotype_short_description
FROM loss_chr13 l13
INNER JOIN loss_chr17 l17
  ON l13.Clone = l17.Clone
  AND l13.CaseNo = l17.CaseNo
  AND l13.RefNo = l17.RefNo
  AND l13.InvNo = l17.InvNo
INNER JOIN gain_chr11 g11
  ON l13.Clone = g11.Clone
  AND l13.CaseNo = g11.CaseNo
  AND l13.RefNo = g11.RefNo
  AND l13.InvNo = g11.InvNo
LEFT JOIN `mitelman-db.prod.KaryClone` kc
  ON l13.Clone = kc.CloneNo
  AND l13.CaseNo = kc.CaseNo
  AND l13.RefNo = kc.RefNo
  AND l13.InvNo = kc.InvNo
ORDER BY
  l13.CaseNo,
  l13.Clone,
  l13.InvNo;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH loss_chr13 AS (
    SELECT
        Clone,
        CaseNo,
        RefNo,
        InvNo,
        ChrOrd,
        `Start`,
        `End`,
        `Type`
    FROM `mitelman-db.prod.CytoConverted`
    WHERE ChrOrd = 13
      AND `Type` = 'Loss'
      AND `Start` <= 48481890
      AND `End` >= 48303751
),
loss_chr17 AS (
    SELECT
        Clone,
        CaseNo,
        RefNo,
        InvNo,
        ChrOrd,
        `Start`,
        `End`,
        `Type`
    FROM `mitelman-db.prod.CytoConverted`
    WHERE ChrOrd = 17
      AND `Type` = 'Loss'
      AND `Start` <= 7687490
      AND `End` >= 7668421
),
gain_chr11 AS (
    SELECT
        Clone,
        CaseNo,
        RefNo,
        InvNo,
        ChrOrd,
        `Start`,
        `End`,
        `Type`
    FROM `mitelman-db.prod.CytoConverted`
    WHERE ChrOrd = 11
      AND `Type` = 'Gain'
      AND `Start` <= 108369102
      AND `End` >= 108223067
)
SELECT DISTINCT
    l13.RefNo,
    l13.CaseNo,
    l13.InvNo,
    l13.Clone,
    l13.ChrOrd AS chr13_ChrOrd,
    l13.`Start` AS chr13_Start,
    l13.`End` AS chr13_End,
    l17.ChrOrd AS chr17_ChrOrd,
    l17.`Start` AS chr17_Start,
    l17.`End` AS chr17_End,
    l11.ChrOrd AS chr11_ChrOrd,
    l11.`Start` AS chr11_Start,
    l11.`End` AS chr11_End,
    kc.CloneShort
FROM loss_chr13 l13
INNER JOIN loss_chr17 l17
    ON l13.Clone = l17.Clone
   AND l13.CaseNo = l17.CaseNo
   AND l13.RefNo = l17.RefNo
   AND l13.InvNo = l17.InvNo
INNER JOIN gain_chr11 l11
    ON l13.Clone = l11.Clone
   AND l13.CaseNo = l11.CaseNo
   AND l13.RefNo = l11.RefNo
   AND l13.InvNo = l11.InvNo
LEFT JOIN `mitelman-db.prod.KaryClone` kc
    ON kc.CloneNo = l13.Clone
   AND kc.CaseNo = l13.CaseNo
   AND kc.RefNo = l13.RefNo
   AND kc.InvNo = l13.InvNo
ORDER BY l13.RefNo, l13.CaseNo, l13.InvNo;
```

---

## 84. Instance: `bq172`
**Question:**
> For the drug with the highest total number of prescriptions in New York State during 2014, could you list the top five states with the highest total claim counts for this drug? Please also include their total claim counts and total drug costs. 

### 🏆 Gold Reference Answer
```sql
WITH ny_top_drug AS (
  SELECT
    drug_name AS drug_name,
    ROUND(SUM(total_claim_count)) AS total_claim_count
  FROM
    `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
  WHERE
    nppes_provider_state = 'NY'
  GROUP BY
    drug_name
  ORDER BY
    total_claim_count DESC
  LIMIT 1
),
top_5_states AS (
  SELECT
    nppes_provider_state AS state,
    SUM(total_claim_count) AS total_claim_count,
    SUM(total_drug_cost) AS total_drug_cost
  FROM
    `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
  WHERE
    drug_name = (SELECT drug_name FROM ny_top_drug)
  GROUP BY
    state
  ORDER BY
    total_claim_count DESC
  LIMIT 5
)
SELECT
  state,
  total_claim_count,
  total_drug_cost
FROM
  top_5_states;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH ny_drug_totals AS (
  -- Aggregate total claims per drug in New York State
  SELECT 
    drug_name,
    SUM(total_claim_count) AS ny_total_claims
  FROM `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
  WHERE nppes_provider_state = 'NY'
  GROUP BY drug_name
),
top_drug AS (
  -- Identify the drug with the highest total claims in NY
  SELECT drug_name
  FROM ny_drug_totals
  ORDER BY ny_total_claims DESC
  LIMIT 1
),
state_stats AS (
  -- For the top drug, aggregate total claims and total drug cost by state
  SELECT 
    p.nppes_provider_state AS state,
    SUM(p.total_claim_count) AS total_claim_count,
    SUM(p.total_drug_cost) AS total_drug_cost
  FROM `bigquery-public-data.cms_medicare.part_d_prescriber_2014` p
  INNER JOIN top_drug t ON p.drug_name = t.drug_name
  GROUP BY p.nppes_provider_state
)
-- Select top 5 states by total claim count
SELECT 
  state,
  total_claim_count,
  ROUND(total_drug_cost, 4) AS total_drug_cost
FROM state_stats
ORDER BY total_claim_count DESC
LIMIT 5;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Find the drug with the highest total claim count in New York State (2014)
WITH ny_top_drug AS (
    SELECT
        drug_name,
        SUM(total_claim_count) AS total_claims_ny
    FROM `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
    WHERE nppes_provider_state = 'NY'    -- New York State
    GROUP BY drug_name
    ORDER BY total_claims_ny DESC
    LIMIT 1
),

-- Step 2: For that drug, aggregate total claim count and total drug cost per state (all states)
state_totals AS (
    SELECT
        p.nppes_provider_state AS state,
        SUM(p.total_claim_count) AS total_claim_count,
        SUM(p.total_drug_cost) AS total_drug_cost
    FROM `bigquery-public-data.cms_medicare.part_d_prescriber_2014` p
    INNER JOIN ny_top_drug d
        ON p.drug_name = d.drug_name
    GROUP BY p.nppes_provider_state
)

-- Step 3: Select the top 5 states by total claim count, along with their totals
SELECT
    state,
    total_claim_count,
    ROUND(total_drug_cost, 4) AS total_drug_cost   -- round to 4 decimal places
FROM state_totals
ORDER BY total_claim_count DESC
LIMIT 5;
```

---

## 85. Instance: `bq177`
**Question:**
> For the provider whose total inpatient Medicare cost from 2011 through 2015 is the highest (computed as the sum of average_medicare_payments multiplied by total_discharges), please list that provider’s yearly average inpatient cost and yearly average outpatient cost for each calendar year in this period, where the inpatient cost is calculated as the average of (average_medicare_payments × total_discharges) and the outpatient cost is calculated as the average of (average_total_payments × outpatient_services).

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Combine all inpatient data from 2011-2015
WITH inpatient_all AS (
  SELECT provider_id, provider_name, average_medicare_payments, total_discharges, '2011' AS year
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2011`
  UNION ALL
  SELECT provider_id, provider_name, average_medicare_payments, total_discharges, '2012'
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2012`
  UNION ALL
  SELECT provider_id, provider_name, average_medicare_payments, total_discharges, '2013'
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2013`
  UNION ALL
  SELECT provider_id, provider_name, average_medicare_payments, total_discharges, '2014'
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2014`
  UNION ALL
  SELECT provider_id, provider_name, average_medicare_payments, total_discharges, '2015'
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2015`
),
-- Step 2: Compute total inpatient cost per provider over 2011-2015
total_inpatient_cost AS (
  SELECT
    provider_id,
    provider_name,
    SUM(average_medicare_payments * total_discharges) AS total_cost
  FROM inpatient_all
  GROUP BY provider_id, provider_name
  ORDER BY total_cost DESC
  LIMIT 1
),
-- Step 3: For the top provider, compute yearly inpatient average
inpatient_yearly AS (
  SELECT
    i.provider_id,
    i.provider_name,
    i.year,
    AVG(i.average_medicare_payments * i.total_discharges) AS avg_inpatient_cost
  FROM inpatient_all i
  JOIN total_inpatient_cost t
    ON i.provider_id = t.provider_id
  GROUP BY i.provider_id, i.provider_name, i.year
),
-- Step 4: Combine all outpatient data from 2011-2015
outpatient_all AS (
  SELECT provider_id, provider_name, average_total_payments, outpatient_services, '2011' AS year
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2011`
  UNION ALL
  SELECT provider_id, provider_name, average_total_payments, outpatient_services, '2012'
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2012`
  UNION ALL
  SELECT provider_id, provider_name, average_total_payments, outpatient_services, '2013'
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2013`
  UNION ALL
  SELECT provider_id, provider_name, average_total_payments, outpatient_services, '2014'
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2014`
  UNION ALL
  SELECT provider_id, provider_name, average_total_payments, outpatient_services, '2015'
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2015`
),
-- Step 5: For the top provider, compute yearly outpatient average
outpatient_yearly AS (
  SELECT
    o.provider_id,
    o.provider_name,
    o.year,
    AVG(o.average_total_payments * o.outpatient_services) AS avg_outpatient_cost
  FROM outpatient_all o
  JOIN total_inpatient_cost t
    ON o.provider_id = t.provider_id
  GROUP BY o.provider_id, o.provider_name, o.year
),
-- Step 6: Generate all years 2011-2015 (to ensure no gaps)
years AS (
  SELECT '2011' AS year UNION ALL
  SELECT '2012' UNION ALL
  SELECT '2013' UNION ALL
  SELECT '2014' UNION ALL
  SELECT '2015'
)
-- Final: combine yearly inpatient and outpatient averages
SELECT
  COALESCE(i.provider_id, o.provider_id) AS provider_id,
  COALESCE(i.provider_name, o.provider_name) AS provider_name,
  y.year,
  ROUND(i.avg_inpatient_cost, 4) AS avg_inpatient_cost,
  ROUND(o.avg_outpatient_cost, 4) AS avg_outpatient_cost
FROM years y
LEFT JOIN inpatient_yearly i
  ON y.year = i.year
LEFT JOIN outpatient_yearly o
  ON y.year = o.year
ORDER BY y.year;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Union all inpatient tables (2011-2015) into a single view
WITH inpatient_all AS (
  SELECT provider_id, provider_name, '2011' AS year, average_medicare_payments, total_discharges
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2011`
  UNION ALL
  SELECT provider_id, provider_name, '2012' AS year, average_medicare_payments, total_discharges
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2012`
  UNION ALL
  SELECT provider_id, provider_name, '2013' AS year, average_medicare_payments, total_discharges
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2013`
  UNION ALL
  SELECT provider_id, provider_name, '2014' AS year, average_medicare_payments, total_discharges
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2014`
  UNION ALL
  SELECT provider_id, provider_name, '2015' AS year, average_medicare_payments, total_discharges
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2015`
),

-- Step 2: Union all outpatient tables (2011-2015) into a single view
outpatient_all AS (
  SELECT provider_id, provider_name, '2011' AS year, average_total_payments, outpatient_services
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2011`
  UNION ALL
  SELECT provider_id, provider_name, '2012' AS year, average_total_payments, outpatient_services
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2012`
  UNION ALL
  SELECT provider_id, provider_name, '2013' AS year, average_total_payments, outpatient_services
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2013`
  UNION ALL
  SELECT provider_id, provider_name, '2014' AS year, average_total_payments, outpatient_services
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2014`
  UNION ALL
  SELECT provider_id, provider_name, '2015' AS year, average_total_payments, outpatient_services
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2015`
),

-- Step 3: Compute total inpatient Medicare cost per provider across all years
provider_total_costs AS (
  SELECT provider_id, provider_name,
         SUM(average_medicare_payments * total_discharges) AS total_inpatient_cost
  FROM inpatient_all
  GROUP BY provider_id, provider_name
),

-- Step 4: Identify the provider with the highest total inpatient cost
top_provider AS (
  SELECT provider_id, provider_name
  FROM provider_total_costs
  ORDER BY total_inpatient_cost DESC
  LIMIT 1
),

-- Step 5: Calculate yearly average inpatient cost for the top provider
yearly_inpatient_avg AS (
  SELECT provider_id, year,
         AVG(average_medicare_payments * total_discharges) AS avg_inpatient_cost
  FROM inpatient_all
  WHERE provider_id IN (SELECT provider_id FROM top_provider)
  GROUP BY provider_id, year
),

-- Step 6: Calculate yearly average outpatient cost for the top provider
yearly_outpatient_avg AS (
  SELECT provider_id, year,
         AVG(average_total_payments * outpatient_services) AS avg_outpatient_cost
  FROM outpatient_all
  WHERE provider_id IN (SELECT provider_id FROM top_provider)
  GROUP BY provider_id, year
)

-- Step 7: Combine yearly averages, left join on year to handle missing outpatient data
SELECT
  tp.provider_name,
  ip.year,
  ROUND(ip.avg_inpatient_cost, 4) AS yearly_avg_inpatient_cost,
  ROUND(op.avg_outpatient_cost, 4) AS yearly_avg_outpatient_cost
FROM top_provider tp
JOIN yearly_inpatient_avg ip ON tp.provider_id = ip.provider_id
LEFT JOIN yearly_outpatient_avg op ON ip.provider_id = op.provider_id AND ip.year = op.year
ORDER BY ip.year;
```

---

## 86. Instance: `bq181`
**Question:**
> What percentage of weather stations recorded valid temperature data (with no missing or invalid values) for at least 90% of the days in 2022, where the temperature, maximum, and minimum values are neither NULL nor equal to 9999.9, and the station has a valid identifier (USAF code not equal to '999999'), out of all available stations in the NOAA GSOD database?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Get all valid stations (USAF not equal to '999999')
valid_stations AS (
    SELECT DISTINCT usaf
    FROM `bigquery-public-data.noaa_gsod.stations`
    WHERE usaf != '999999'
),

-- Filter to 2022 data with valid temperature readings
-- Valid means: temp, max, min are NOT NULL AND not equal to 9999.9
valid_temp_days_2022 AS (
    SELECT 
        stn,
        COUNT(*) AS valid_days
    FROM `bigquery-public-data.noaa_gsod.gsod2022`
    WHERE 
        year = '2022'
        AND temp IS NOT NULL AND temp != 9999.9
        AND max IS NOT NULL AND max != 9999.9
        AND min IS NOT NULL AND min != 9999.9
        AND stn IN (SELECT usaf FROM valid_stations)
    GROUP BY stn
),

-- Calculate valid percentage for each station (2022 has 365 days)
station_percentages AS (
    SELECT 
        vtd.stn,
        vtd.valid_days,
        ROUND((vtd.valid_days / 365.0) * 100, 4) AS valid_percentage
    FROM valid_temp_days_2022 vtd
),

-- Count stations that meet the 90% threshold
stations_meeting_criteria AS (
    SELECT COUNT(*) AS qualifying_stations
    FROM station_percentages
    WHERE valid_percentage >= 90.0
),

-- Count total valid stations
total_valid_stations AS (
    SELECT COUNT(*) AS total_stations
    FROM valid_stations
)

-- Compute the final percentage
SELECT 
    ROUND(
        (SELECT qualifying_stations FROM stations_meeting_criteria) * 100.0 / 
        NULLIF((SELECT total_stations FROM total_valid_stations), 0),
    4) AS percentage_stations_valid
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Compute percentage of weather stations that recorded valid temperature data
-- for at least 90% of the days in 2022, among all stations in the NOAA GSOD database.

WITH
  -- All valid stations (USAF not equal to '999999')
  valid_stations AS (
    SELECT usaf, wban
    FROM `bigquery-public-data.noaa_gsod.stations`
    WHERE usaf != '999999'
  ),
  -- For each station, count days in 2022 where temp, max, min are not NULL and not 9999.9
  station_valid_days AS (
    SELECT
      g.stn,
      g.wban,
      COUNT(*) AS valid_days
    FROM `bigquery-public-data.noaa_gsod.gsod2022` g
    INNER JOIN valid_stations s
      ON g.stn = s.usaf
      AND g.wban = s.wban
    WHERE g.temp IS NOT NULL AND g.temp != 9999.9
      AND g.max IS NOT NULL AND g.max != 9999.9
      AND g.min IS NOT NULL AND g.min != 9999.9
    GROUP BY g.stn, g.wban
  ),
  -- Total number of stations (denominator)
  total_stations AS (
    SELECT COUNT(*) AS total
    FROM valid_stations
  ),
  -- Number of stations that meet the 90% threshold
  stations_meeting AS (
    SELECT COUNT(*) AS meeting
    FROM station_valid_days
    WHERE valid_days / 365.0 >= 0.9
  )
-- Final percentage with 4 decimal places
SELECT
  ROUND((meeting / total) * 100.0, 4) AS percentage
FROM total_stations, stations_meeting;
```

---

## 87. Instance: `bq185`
**Question:**
> What is the average trip duration in minutes for all valid Yellow taxi trips that took place between February 1, 2016, and February 7, 2016 (inclusive), with a positive trip duration, more than three passengers, and a trip distance of at least ten miles, where both the pickup and dropoff locations are in Brooklyn?

### 🏆 Gold Reference Answer
```sql
SELECT 
    AVG(TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND) / 60.0) AS average_trip_duration_in_minutes
FROM
(
    SELECT *
    FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016` t
    WHERE 
        pickup_datetime BETWEEN '2016-02-01' AND '2016-02-07' AND 
        dropoff_datetime BETWEEN '2016-02-01' AND '2016-02-07' AND
        TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND) > 0 AND 
        passenger_count > 3 AND 
        trip_distance >= 10
) t
INNER JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` tz
ON t.pickup_location_id = tz.zone_id
INNER JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` tz1
ON t.dropoff_location_id = tz1.zone_id
WHERE 
    tz.borough = "Brooklyn" AND
    tz1.borough = "Brooklyn";
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Compute average trip duration in minutes for valid Yellow taxi trips in Feb 1-7, 2016
-- Filter conditions: positive duration, more than 3 passengers, distance >= 10 miles,
-- both pickup and dropoff in Brooklyn (using taxi_zone_geom).

WITH 
  -- Join trips with zone geometry to restrict to Brooklyn borough
  brooklyn_trips AS (
    SELECT
      t.pickup_datetime,
      t.dropoff_datetime,
      t.passenger_count,
      t.trip_distance
    FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016` AS t
    INNER JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` AS pz
      ON t.pickup_location_id = pz.zone_id
    INNER JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` AS dz
      ON t.dropoff_location_id = dz.zone_id
    WHERE
      pz.borough = 'Brooklyn'
      AND dz.borough = 'Brooklyn'
  )
SELECT
  ROUND(AVG(avg_minutes), 4) AS avg_trip_duration_minutes
FROM (
  SELECT
    TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, MINUTE) AS avg_minutes
  FROM brooklyn_trips
  WHERE
    pickup_datetime >= TIMESTAMP('2016-02-01')
    AND pickup_datetime < TIMESTAMP('2016-02-08')       -- inclusive of Feb 7
    AND passenger_count > 3
    AND trip_distance >= 10
    AND TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND) > 0   -- positive duration
);
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Understand the question and identify tables
-- We need Yellow taxi trips from the tlc_yellow_trips_2016 table (since date range is Feb 1-7, 2016)
-- We need to filter by: pickup and dropoff in Brooklyn, trip_date range, positive duration, >3 passengers, >=10 miles
-- We calculate average trip duration in minutes

-- Step 2: Use the correct table for 2016 data
-- The table is bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016

-- Step 3: Join with taxi_zone_geom to get borough information for both pickup and dropoff locations

WITH 
-- First, get the taxi zone IDs for Brooklyn
brooklyn_zones AS (
  SELECT zone_id
  FROM `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom`
  WHERE LOWER(borough) = 'brooklyn'
),

-- Filter valid trips: Feb 1-7, 2016, positive duration, >3 passengers, >=10 miles, both locations in Brooklyn
valid_trips AS (
  SELECT 
    trip_distance,
    pickup_datetime,
    dropoff_datetime,
    passenger_count
  FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016`
  WHERE 
    -- Pickup and dropoff both in Brooklyn (using location_id as string, need to match)
    -- Note: The location_id fields are strings, and we match them to zone_id (also string)
    CAST(pickup_location_id AS STRING) IN (SELECT zone_id FROM brooklyn_zones)
    AND CAST(dropoff_location_id AS STRING) IN (SELECT zone_id FROM brooklyn_zones)
    -- Date range: Feb 1, 2016 00:00:00 to Feb 7, 2016 23:59:59
    AND pickup_datetime >= TIMESTAMP('2016-02-01 00:00:00')
    AND pickup_datetime <= TIMESTAMP('2016-02-07 23:59:59')
    -- Positive trip duration (dropoff > pickup)
    AND dropoff_datetime > pickup_datetime
    -- More than 3 passengers (strictly >3)
    AND passenger_count > 3
    -- Trip distance at least 10 miles
    AND trip_distance >= 10.0
)

-- Step 4: Calculate average trip duration in minutes
-- Convert duration from seconds (difference in timestamps) to minutes
SELECT 
  ROUND(
    AVG(
      -- Calculate duration in minutes
      (UNIX_MICROS(dropoff_datetime) - UNIX_MICROS(pickup_datetime)) / 60.0 / 1000000.0
    ), 
    4
  ) AS avg_trip_duration_minutes
FROM valid_trips;
```

---

## 88. Instance: `bq186`
**Question:**
> Please find, for each year-month combination (in the format YYYYMM) derived from the start date of bike share trips in San Francisco, the first trip duration in minutes, the last trip duration in minutes, the highest trip duration in minutes, and the lowest trip duration in minutes, where ‘first’ and ‘last’ are determined by the chronological order of the trip start date, then group your results by this year-month and sort them by the same year-month key.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Extract year-month from start_date and compute duration in minutes.
-- Step 2: Use window functions to identify first and last trip per year-month based on start_date.
-- Step 3: Aggregate to get first, last, max, min duration per year-month.
-- Step 4: Sort by year-month.

WITH trips_with_ym AS (
  SELECT
    -- Convert start_date to YYYYMM format
    FORMAT_TIMESTAMP('%Y%m', start_date) AS year_month,
    -- Compute duration in minutes (rounded to 4 decimal places as per optimization strategy)
    ROUND(duration_sec / 60.0, 4) AS duration_min,
    start_date,
    trip_id
  FROM `bigquery-public-data.san_francisco.bikeshare_trips`
  WHERE start_date IS NOT NULL  -- Ensure we have a valid start date for ordering
),
ranked_trips AS (
  SELECT
    year_month,
    duration_min,
    -- Rank trips by start_date chronologically within each year_month
    ROW_NUMBER() OVER (PARTITION BY year_month ORDER BY start_date ASC) AS rn_asc,
    ROW_NUMBER() OVER (PARTITION BY year_month ORDER BY start_date DESC) AS rn_desc
  FROM trips_with_ym
)
SELECT
  year_month,
  -- First trip duration (earliest start_date)
  MAX(CASE WHEN rn_asc = 1 THEN duration_min END) AS first_trip_duration_min,
  -- Last trip duration (latest start_date)
  MAX(CASE WHEN rn_desc = 1 THEN duration_min END) AS last_trip_duration_min,
  -- Highest duration in the group
  MAX(duration_min) AS highest_trip_duration_min,
  -- Lowest duration in the group
  MIN(duration_min) AS lowest_trip_duration_min
FROM ranked_trips
GROUP BY year_month
ORDER BY year_month ASC;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Prepare base data with year-month and duration in minutes
WITH trip_data AS (
    SELECT
        FORMAT_TIMESTAMP('%Y%m', start_date) AS yearmonth,
        duration_sec / 60.0 AS duration_min,
        start_date
    FROM `bigquery-public-data.san_francisco.bikeshare_trips`
),

-- Step 2: Use window functions to find first, last, max, min per month
ranked_trips AS (
    SELECT
        yearmonth,
        duration_min,
        FIRST_VALUE(duration_min) OVER (
            PARTITION BY yearmonth 
            ORDER BY start_date ASC
        ) AS first_trip_duration_minutes,
        FIRST_VALUE(duration_min) OVER (
            PARTITION BY yearmonth 
            ORDER BY start_date DESC
        ) AS last_trip_duration_minutes,
        MAX(duration_min) OVER (PARTITION BY yearmonth) AS highest_trip_duration_minutes,
        MIN(duration_min) OVER (PARTITION BY yearmonth) AS lowest_trip_duration_minutes
    FROM trip_data
)

-- Step 3: Deduplicate and output final results
SELECT DISTINCT
    yearmonth,
    ROUND(first_trip_duration_minutes, 4) AS first_trip_duration_minutes,
    ROUND(last_trip_duration_minutes, 4) AS last_trip_duration_minutes,
    ROUND(highest_trip_duration_minutes, 4) AS highest_trip_duration_minutes,
    ROUND(lowest_trip_duration_minutes, 4) AS lowest_trip_duration_minutes
FROM ranked_trips
ORDER BY yearmonth;
```

---

## 89. Instance: `bq198`
**Question:**
> List the top 5 universities with the most seasons where they achieved the maximum wins in their respective NCAA basketball seasons between 1900-2000, showing each team's total number of such peak-performance seasons, while excluding entries with missing team names.

### 🏆 Gold Reference Answer
```sql
SELECT
  team_name,
  COUNT(*) AS top_performer_count
FROM (
  SELECT
    DISTINCT c2.season,
    c2.market AS team_name
  FROM (
    SELECT
      season AS a,
      MAX(wins) AS win_max
    FROM
      `bigquery-public-data.ncaa_basketball.mbb_historical_teams_seasons`
    WHERE
      season<=2000
      AND season >=1900
    GROUP BY
      season ),
    `bigquery-public-data.ncaa_basketball.mbb_historical_teams_seasons` c2
  WHERE
    win_max = c2.wins
    AND a = c2.season
    AND c2.market IS NOT NULL
  ORDER BY
    c2.season)
GROUP BY
  team_name
ORDER BY
  top_performer_count DESC,
  team_name
LIMIT
  5
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH
  -- Filtered seasons data: exclude missing team names and keep only 1900-2000
  filtered_seasons AS (
    SELECT
      season,
      wins,
      team_code,
      COALESCE(NULLIF(market, 'None'), name) AS university_name
    FROM
      `bigquery-public-data.ncaa_basketball.mbb_historical_teams_seasons`
    WHERE
      season BETWEEN 1900 AND 2000
      AND name IS NOT NULL
      AND name != 'None'
  ),
  -- Maximum wins per season within the filtered data
  season_max_wins AS (
    SELECT
      season,
      MAX(wins) AS max_wins
    FROM
      filtered_seasons
    GROUP BY
      season
  ),
  -- Join to find teams that achieved the maximum wins in each season
  peak_seasons AS (
    SELECT
      fs.season,
      fs.team_code,
      fs.university_name
    FROM
      filtered_seasons fs
      INNER JOIN season_max_wins smw
        ON fs.season = smw.season
        AND fs.wins = smw.max_wins
  )
-- Count peak seasons per university and get top 5
SELECT
  university_name,
  COUNT(*) AS peak_season_count
FROM
  peak_seasons
GROUP BY
  university_name
ORDER BY
  peak_season_count DESC
LIMIT 5;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH
  -- Step 1: Filter seasons between 1900 and 2000 inclusive and exclude missing team names.
  filtered_seasons AS (
    SELECT
      season,
      wins,
      market AS university_name
    FROM
      `bigquery-public-data.ncaa_basketball.mbb_historical_teams_seasons`
    WHERE
      season BETWEEN 1900 AND 2000
      AND market IS NOT NULL
      AND TRIM(market) != ''
  ),
  -- Step 2: Compute maximum wins per season
  max_wins_per_season AS (
    SELECT
      season,
      MAX(wins) AS max_wins
    FROM
      filtered_seasons
    GROUP BY
      season
  ),
  -- Step 3: Identify peak-performance seasons for each university
  peak_seasons AS (
    SELECT
      fs.university_name,
      fs.season
    FROM
      filtered_seasons fs
      INNER JOIN max_wins_per_season mw
        ON fs.season = mw.season
        AND fs.wins = mw.max_wins
  ),
  -- Step 4: Count number of peak-performance seasons per university
  university_peak_counts AS (
    SELECT
      university_name,
      COUNT(*) AS peak_seasons_count
    FROM
      peak_seasons
    GROUP BY
      university_name
  )
-- Step 5: Get top 5 universities
SELECT
  university_name,
  peak_seasons_count
FROM
  university_peak_counts
ORDER BY
  peak_seasons_count DESC,
  university_name ASC  -- tie-breaker for determinism
LIMIT 5;
```

---

## 90. Instance: `bq199`
**Question:**
> Identify the top 10 liquor categories in Iowa in 2021 by calculating, for each category, the average of the per-liter retail prices across all sales transactions in that category during 2021. For these top categories, provide their average per-liter retail prices calculated in the same manner for the years 2019, 2020, and 2021.

### 🏆 Gold Reference Answer
```sql
WITH price_2020 AS (
  SELECT 
    category_name AS category, 
    AVG(state_bottle_retail / (bottle_volume_ml / 1000)) AS avg_price_liter_2020
  FROM 
    `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE 
    bottle_volume_ml > 0 
    AND EXTRACT(YEAR FROM date) = 2020
  GROUP BY 
    category
),
price_2019 AS (
  SELECT 
    category_name AS category, 
    AVG(state_bottle_retail / (bottle_volume_ml / 1000)) AS avg_price_liter_2019
  FROM 
    `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE 
    bottle_volume_ml > 0 
    AND EXTRACT(YEAR FROM date) = 2019
  GROUP BY 
    category
),
price_2021 AS (
  SELECT 
    category_name AS category, 
    AVG(state_bottle_retail / (bottle_volume_ml / 1000)) AS avg_price_liter_2021
  FROM 
    `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE 
    bottle_volume_ml > 0 
    AND EXTRACT(YEAR FROM date) = 2021
  GROUP BY 
    category
)
SELECT 
  price_2021.category, 
  price_2019.avg_price_liter_2019, 
  price_2020.avg_price_liter_2020, 
  price_2021.avg_price_liter_2021
FROM 
  price_2021
LEFT JOIN 
  price_2019 ON price_2021.category = price_2019.category
LEFT JOIN 
  price_2020 ON price_2021.category = price_2020.category
ORDER BY 
  price_2021.avg_price_liter_2021 DESC
LIMIT 
  10;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH per_liter_prices AS (
    -- Calculate per-liter retail price for each transaction
    SELECT 
        category_name,
        EXTRACT(YEAR FROM date) AS year,
        state_bottle_retail / (bottle_volume_ml / 1000.0) AS per_liter_price
    FROM `bigquery-public-data.iowa_liquor_sales.sales`
    WHERE EXTRACT(YEAR FROM date) IN (2019, 2020, 2021)
      AND bottle_volume_ml > 0  -- Avoid division by zero
),

avg_by_category_year AS (
    -- Average per-liter price per category per year
    SELECT
        category_name,
        year,
        ROUND(AVG(per_liter_price), 4) AS avg_per_liter_price
    FROM per_liter_prices
    GROUP BY category_name, year
),

top_2021_categories AS (
    -- Identify top 10 categories by 2021 average per-liter price
    SELECT 
        category_name,
        avg_per_liter_price AS avg_2021
    FROM avg_by_category_year
    WHERE year = 2021
    ORDER BY avg_per_liter_price DESC
    LIMIT 10
)

-- Final output: show 2019, 2020, 2021 averages for top 10 categories
SELECT 
    t.category_name,
    ROUND(AVG(CASE WHEN a.year = 2019 THEN a.avg_per_liter_price END), 4) AS avg_per_liter_price_2019,
    ROUND(AVG(CASE WHEN a.year = 2020 THEN a.avg_per_liter_price END), 4) AS avg_per_liter_price_2020,
    ROUND(AVG(CASE WHEN a.year = 2021 THEN a.avg_per_liter_price END), 4) AS avg_per_liter_price_2021
FROM top_2021_categories t
LEFT JOIN avg_by_category_year a ON t.category_name = a.category_name
GROUP BY t.category_name
ORDER BY avg_per_liter_price_2021 DESC;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Compute per-liter retail price for each transaction (row)
WITH per_transaction_prices AS (
  SELECT
    category,
    category_name,
    EXTRACT(YEAR FROM date) AS year,
    -- retail price per bottle divided by bottle volume in liters
    state_bottle_retail / (bottle_volume_ml / 1000.0) AS per_liter_price
  FROM `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE EXTRACT(YEAR FROM date) IN (2019, 2020, 2021)
    -- exclude invalid or negative values that would distort the average
    AND volume_sold_liters > 0
    AND state_bottle_retail > 0
    AND bottle_volume_ml > 0
),

-- Step 2: Average per-liter price per category per year
yearly_category_avg AS (
  SELECT
    category,
    category_name,
    year,
    ROUND(AVG(per_liter_price), 4) AS avg_price
  FROM per_transaction_prices
  GROUP BY category, category_name, year
),

-- Step 3: Identify top 10 categories based on 2021 average price (highest first)
top_categories_2021 AS (
  SELECT
    category,
    category_name,
    avg_price AS avg_price_2021
  FROM yearly_category_avg
  WHERE year = 2021
  ORDER BY avg_price DESC
  LIMIT 10
)

-- Step 4: Retrieve 2019 and 2020 averages for those top categories
SELECT
  t.category,
  t.category_name,
  t.avg_price_2021,
  y2019.avg_price AS avg_price_2019,
  y2020.avg_price AS avg_price_2020
FROM top_categories_2021 t
LEFT JOIN yearly_category_avg y2019
  ON t.category = y2019.category AND y2019.year = 2019
LEFT JOIN yearly_category_avg y2020
  ON t.category = y2020.category AND y2020.year = 2020
ORDER BY t.avg_price_2021 DESC;
```

---

## 91. Instance: `bq200`
**Question:**
> Using data from both the regular season and the post-season, identify the pitcher who achieved the highest non-zero pitch speed for each team by confirming whether the pitcher’s ID appears in the relevant home or away player lists for that game, then retrieve that pitcher’s full name along with the maximum valid pitch speed they achieved while playing for that specific team.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Combine regular season and post-season pitch data
combined_pitches AS (
    SELECT 
        pitcherId,
        pitcherFirstName,
        pitcherLastName,
        pitchSpeed,
        homeTeamName,
        homeTeamId,
        awayTeamName,
        awayTeamId
    FROM `bigquery-public-data.baseball.games_wide`
    WHERE pitchSpeed > 0
    UNION ALL
    SELECT 
        pitcherId,
        pitcherFirstName,
        pitcherLastName,
        pitchSpeed,
        homeTeamName,
        homeTeamId,
        awayTeamName,
        awayTeamId
    FROM `bigquery-public-data.baseball.games_post_wide`
    WHERE pitchSpeed > 0
),

-- Determine which team the pitcher is playing for in each pitch
pitcher_team AS (
    SELECT 
        c.pitcherId,
        c.pitcherFirstName,
        c.pitcherLastName,
        c.pitchSpeed,
        c.homeTeamName AS team_name,
        c.homeTeamId AS team_id
    FROM combined_pitches c
    -- Pitcher appears in home team's fielders (1-12) for that game
    WHERE EXISTS (
        SELECT 1
        FROM `bigquery-public-data.baseball.games_wide` g
        WHERE g.pitcherId = c.pitcherId
          AND (g.homeFielder1 = c.pitcherId 
               OR g.homeFielder2 = c.pitcherId
               OR g.homeFielder3 = c.pitcherId
               OR g.homeFielder4 = c.pitcherId
               OR g.homeFielder5 = c.pitcherId
               OR g.homeFielder6 = c.pitcherId
               OR g.homeFielder7 = c.pitcherId
               OR g.homeFielder8 = c.pitcherId
               OR g.homeFielder9 = c.pitcherId
               OR g.homeFielder10 = c.pitcherId
               OR g.homeFielder11 = c.pitcherId
               OR g.homeFielder12 = c.pitcherId)
    )
    UNION ALL
    SELECT 
        c.pitcherId,
        c.pitcherFirstName,
        c.pitcherLastName,
        c.pitchSpeed,
        c.awayTeamName AS team_name,
        c.awayTeamId AS team_id
    FROM combined_pitches c
    -- Pitcher appears in away team's fielders (1-12) for that game
    WHERE EXISTS (
        SELECT 1
        FROM `bigquery-public-data.baseball.games_wide` g
        WHERE g.pitcherId = c.pitcherId
          AND (g.awayFielder1 = c.pitcherId 
               OR g.awayFielder2 = c.pitcherId
               OR g.awayFielder3 = c.pitcherId
               OR g.awayFielder4 = c.pitcherId
               OR g.awayFielder5 = c.pitcherId
               OR g.awayFielder6 = c.pitcherId
               OR g.awayFielder7 = c.pitcherId
               OR g.awayFielder8 = c.pitcherId
               OR g.awayFielder9 = c.pitcherId
               OR g.awayFielder10 = c.pitcherId
               OR g.awayFielder11 = c.pitcherId
               OR g.awayFielder12 = c.pitcherId)
    )
),

-- Get max pitch speed per pitcher per team
pitcher_max_speed AS (
    SELECT 
        pitcherId,
        pitcherFirstName,
        pitcherLastName,
        team_name,
        team_id,
        MAX(pitchSpeed) AS max_pitch_speed
    FROM pitcher_team
    GROUP BY pitcherId, pitcherFirstName, pitcherLastName, team_name, team_id
),

-- Rank to find top pitcher per team (highest speed)
ranked_pitchers AS (
    SELECT 
        *,
        ROW_NUMBER() OVER (PARTITION BY team_name, team_id ORDER BY max_pitch_speed DESC) AS speed_rank
    FROM pitcher_max_speed
)

-- Final result: full name of pitcher and their max speed for that team
SELECT 
    CONCAT(pitcherFirstName, ' ', pitcherLastName) AS pitcher_full_name,
    team_name,
    max_pitch_speed
FROM ranked_pitchers
WHERE speed_rank = 1
ORDER BY team_name;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Combine regular season and postseason data
combined_pitches AS (
  SELECT 
    pitcherId,
    pitcherFirstName,
    pitcherLastName,
    pitchSpeed,
    homeTeamName,
    awayTeamName,
    gameId,
    seasonId
  FROM `bigquery-public-data.baseball.games_wide`
  WHERE pitchSpeed > 0 AND pitcherId IS NOT NULL AND pitcherId != ''
  
  UNION ALL
  
  SELECT 
    pitcherId,
    pitcherFirstName,
    pitcherLastName,
    pitchSpeed,
    homeTeamName,
    awayTeamName,
    gameId,
    seasonId
  FROM `bigquery-public-data.baseball.games_post_wide`
  WHERE pitchSpeed > 0 AND pitcherId IS NOT NULL AND pitcherId != ''
),

-- Determine which team the pitcher was playing for in each pitch
pitcher_team_mapping AS (
  SELECT 
    c.pitcherId,
    c.pitcherFirstName,
    c.pitcherLastName,
    c.pitchSpeed,
    c.gameId,
    -- Determine team: if pitcherId appears in home player lists, team is homeTeamName
    CASE 
      WHEN EXISTS (
        SELECT 1 
        FROM UNNEST([
          g.homeFielder1, g.homeFielder2, g.homeFielder3, g.homeFielder4, 
          g.homeFielder5, g.homeFielder6, g.homeFielder7, g.homeFielder8, 
          g.homeFielder9, g.homeFielder10, g.homeFielder11, g.homeFielder12
        ]) AS player_id
        WHERE player_id = c.pitcherId
      ) THEN g.homeTeamName
      WHEN EXISTS (
        SELECT 1 
        FROM UNNEST([
          g.awayFielder1, g.awayFielder2, g.awayFielder3, g.awayFielder4,
          g.awayFielder5, g.awayFielder6, g.awayFielder7, g.awayFielder8,
          g.awayFielder9, g.awayFielder10, g.awayFielder11, g.awayFielder12
        ]) AS player_id
        WHERE player_id = c.pitcherId
      ) THEN g.awayTeamName
      ELSE NULL
    END AS team_played_for
  FROM combined_pitches c
  -- Need to join back to get the fielder arrays for checking
  LEFT JOIN `bigquery-public-data.baseball.games_wide` g
    ON c.gameId = g.gameId AND c.seasonId = g.seasonId
  WHERE c.pitchSpeed > 0
)

-- Filter to valid team assignments and get max pitch speed per pitcher per team
SELECT 
  pitcherFirstName,
  pitcherLastName,
  team_played_for AS team_name,
  MAX(pitchSpeed) AS max_pitch_speed
FROM pitcher_team_mapping
WHERE team_played_for IS NOT NULL
GROUP BY 
  pitcherFirstName,
  pitcherLastName,
  pitcherId,
  team_played_for
ORDER BY 
  team_played_for,
  max_pitch_speed DESC;
```

---

## 92. Instance: `bq202`
**Question:**
> For the station that had the highest number of Citibike trips starting there in 2018, which numeric day of the week and which hour of the day had the greatest number of trips based on the start time of those trips?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Find the Citibike station with most 2018 trips, then find the busiest day-hour combo
WITH top_station AS (
  -- Identify the station with the most starting trips in 2018
  SELECT 
    start_station_id,
    start_station_name,
    COUNT(*) AS trip_count
  FROM `bigquery-public-data.new_york_citibike.citibike_trips`
  WHERE EXTRACT(YEAR FROM starttime) = 2018
  GROUP BY start_station_id, start_station_name
  ORDER BY trip_count DESC
  LIMIT 1
),
station_trips AS (
  -- Get all trips from that station in 2018 with day-of-week and hour
  SELECT 
    EXTRACT(DAYOFWEEK FROM t.starttime) AS day_of_week,  -- 1=Sunday, 2=Monday, ..., 7=Saturday
    EXTRACT(HOUR FROM t.starttime) AS hour,              -- 0-23
    t.starttime
  FROM `bigquery-public-data.new_york_citibike.citibike_trips` t
  INNER JOIN top_station s
    ON t.start_station_id = s.start_station_id
  WHERE EXTRACT(YEAR FROM t.starttime) = 2018
)
-- Find the (day_of_week, hour) combination with the most trips
SELECT 
  day_of_week,
  hour,
  COUNT(*) AS trip_count
FROM station_trips
GROUP BY day_of_week, hour
ORDER BY trip_count DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Find the station with the highest number of trips in 2018
WITH station_trip_counts AS (
    SELECT
        start_station_id,
        COUNT(*) AS trip_count
    FROM `bigquery-public-data.new_york_citibike.citibike_trips`
    WHERE EXTRACT(YEAR FROM starttime) = 2018
    GROUP BY start_station_id
    ORDER BY trip_count DESC
    LIMIT 1
),

-- Step 2: For that station, count trips by day of week (numeric) and hour
station_day_hour_counts AS (
    SELECT
        EXTRACT(DAYOFWEEK FROM starttime) AS day_of_week_numeric,
        EXTRACT(HOUR FROM starttime) AS hour_of_day,
        COUNT(*) AS trip_count
    FROM `bigquery-public-data.new_york_citibike.citibike_trips`
    WHERE EXTRACT(YEAR FROM starttime) = 2018
      AND start_station_id = (SELECT start_station_id FROM station_trip_counts)
    GROUP BY day_of_week_numeric, hour_of_day
),

-- Step 3: Rank combinations by trip count descending, pick the top one
ranked AS (
    SELECT
        day_of_week_numeric,
        hour_of_day,
        trip_count,
        ROW_NUMBER() OVER (ORDER BY trip_count DESC) AS rn
    FROM station_day_hour_counts
)

-- Final output: the numeric day of week and hour with the greatest number of trips
SELECT
    day_of_week_numeric AS numeric_day_of_week,
    hour_of_day AS hour_of_day
FROM ranked
WHERE rn = 1;
```

---

## 93. Instance: `bq203`
**Question:**
> For each New York City borough, how many subway stations are there in total, how many have at least one entrance that is marked both as an actual entry and as ADA-compliant, and what percentage of the total stations in each borough does this represent, listing boroughs from the highest to the lowest percentage?

### 🏆 Gold Reference Answer
```sql
WITH stations_n_entrances AS (
      SELECT borough_name,s.station_name,entry,ada_compliant
      FROM `bigquery-public-data.new_york_subway.stations` s
      JOIN `bigquery-public-data.new_york_subway.station_entrances` se
      ON s.station_name = se.station_name
      )

SELECT se.borough_name, COUNT(DISTINCT se.station_name) num_stations,
      COUNT(DISTINCT adas.station_name) num_stations_w_compliant_entrance, 
      (100*COUNT(DISTINCT adas.station_name))/(COUNT(DISTINCT se.station_name)) percent_compliant_stations
FROM `stations_n_entrances` se
LEFT JOIN `stations_n_entrances` adas
ON se.station_name = adas.station_name
AND adas.entry AND adas.ada_compliant
GROUP BY 1
ORDER BY 4 DESC
```

### 🤖 AutoLink Baseline Prediction
```sql
-- CTE: Distinct stations (station_name, line) that have at least one entrance with entry=TRUE and ada_compliant=TRUE
WITH qualifying_stations AS (
  SELECT DISTINCT station_name, line
  FROM `bigquery-public-data.new_york_subway.station_entrances`
  WHERE entry = TRUE
    AND ada_compliant = TRUE
),

-- CTE: For each borough, count number of qualifying stations
borough_qualifying AS (
  SELECT s.borough_name,
         COUNT(DISTINCT s.station_id) AS qualifying_stations
  FROM `bigquery-public-data.new_york_subway.stations` s
  INNER JOIN qualifying_stations q
    ON s.station_name = q.station_name AND s.line = q.line
  GROUP BY s.borough_name
),

-- CTE: Total stations per borough
borough_total AS (
  SELECT borough_name,
         COUNT(DISTINCT station_id) AS total_stations
  FROM `bigquery-public-data.new_york_subway.stations`
  GROUP BY borough_name
)

-- Final result: join totals and qualifying, compute percentage, order descending
SELECT bt.borough_name,
       bt.total_stations,
       COALESCE(bq.qualifying_stations, 0) AS qualifying_stations,
       ROUND(COALESCE(bq.qualifying_stations, 0) * 100.0 / bt.total_stations, 4) AS percentage
FROM borough_total bt
LEFT JOIN borough_qualifying bq
  ON bt.borough_name = bq.borough_name
ORDER BY percentage DESC;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Get all stations with their borough
WITH station_borough AS (
  SELECT 
    station_id,
    station_name,
    line,
    borough_name
  FROM `bigquery-public-data.new_york_subway.stations`
),

-- Step 2: Total stations per borough
total_per_borough AS (
  SELECT 
    borough_name,
    COUNT(DISTINCT station_id) AS total_stations
  FROM station_borough
  GROUP BY borough_name
),

-- Step 3: Distinct stations that have at least one entrance with entry=True AND ada_compliant=True
qualified_entrances AS (
  SELECT DISTINCT 
    station_name,
    line
  FROM `bigquery-public-data.new_york_subway.station_entrances`
  WHERE entry = TRUE 
    AND ada_compliant = TRUE
),

-- Step 4: Count those qualified stations per borough (via join on station_name and line)
qualified_stations AS (
  SELECT 
    sb.borough_name,
    COUNT(DISTINCT sb.station_id) AS stations_with_ada_entry
  FROM qualified_entrances qe
  JOIN station_borough sb 
    ON qe.station_name = sb.station_name 
    AND qe.line = sb.line
  GROUP BY sb.borough_name
)

-- Step 5: Final SELECT with percentage and ordering
SELECT 
  t.borough_name,
  t.total_stations,
  COALESCE(q.stations_with_ada_entry, 0) AS stations_with_ada_entry,
  ROUND(COALESCE(q.stations_with_ada_entry, 0) * 100.0 / t.total_stations, 4) AS percentage
FROM total_per_borough t
LEFT JOIN qualified_stations q 
  ON t.borough_name = q.borough_name
ORDER BY percentage DESC;
```

---

## 94. Instance: `bq204`
**Question:**
> Find the user with the highest total clicks across all records from all available photo collections.

### 🏆 Gold Reference Answer
```sql
SELECT user
FROM (
Select user
      From `bigquery-public-data.eclipse_megamovie.photos_v_0_1`
      UNION ALL
      Select user
      From`bigquery-public-data.eclipse_megamovie.photos_v_0_2`
      UNION ALL
      Select user
      From`bigquery-public-data.eclipse_megamovie.photos_v_0_3`
) 
GROUP BY user 
HAVING COUNT (user)=( 
SELECT MAX(mycount) 
FROM ( 
SELECT user, COUNT(user) mycount 
FROM (
Select user
      From `bigquery-public-data.eclipse_megamovie.photos_v_0_1`
      UNION ALL
      Select user
      From`bigquery-public-data.eclipse_megamovie.photos_v_0_2`
      UNION ALL
      Select user
      From`bigquery-public-data.eclipse_megamovie.photos_v_0_3`
)
GROUP BY user))
ORDER BY COUNT(user) 
LIMIT 1
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Union all photo collections and count records per user
WITH all_photos AS (
    SELECT user
    FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_1`
    UNION ALL
    SELECT user
    FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_2`
    UNION ALL
    SELECT user
    FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_3`
)
SELECT 
    user, 
    COUNT(*) AS total_clicks
FROM all_photos
GROUP BY user
ORDER BY total_clicks DESC
LIMIT 1
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Find the user with the highest total number of photo records (interpreted as "clicks")
-- across all three photo collection tables (v0.1, v0.2, v0.3)
WITH all_photos AS (
  SELECT user
  FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_1`
  UNION ALL
  SELECT user
  FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_2`
  UNION ALL
  SELECT user
  FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_3`
)
SELECT
  user,
  COUNT(*) AS total_clicks
FROM all_photos
GROUP BY user
ORDER BY total_clicks DESC
LIMIT 1;
```

---

## 95. Instance: `bq208`
**Question:**
> Can you provide weather stations within a 20-mile radius of Chappaqua, New York (Latitude: 41.197, Longitude: -73.764), and tell me the number of valid temperature observations they have recorded from 2011 to 2020, excluding any invalid or missing temperature data?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- BigQuery SQL query to find weather stations within 20 miles of Chappaqua, NY
-- and count valid temperature observations from 2011 to 2020.

WITH
  -- Step 1: Identify stations within 20 miles (32,186.88 meters) of Chappaqua
  stations_in_range AS (
    SELECT
      usaf,
      wban,
      name,
      lat,
      lon
    FROM
      `bigquery-public-data.noaa_gsod.stations`
    WHERE
      ST_DWITHIN(
        ST_GEOGPOINT(lon, lat),               -- station location
        ST_GEOGPOINT(-73.764, 41.197),       -- Chappaqua location
        32186.88                              -- 20 miles in meters
      )
      AND lat IS NOT NULL
      AND lon IS NOT NULL
  ),

  -- Step 2: Aggregate valid temperature counts from 2011-2020 for those stations
  valid_temp_counts AS (
    SELECT
      s.usaf,
      s.wban,
      COUNT(*) AS num_valid_obs
    FROM
      stations_in_range AS s
      -- Join with all GSOD tables from 2011 to 2020 using station identifiers
      JOIN `bigquery-public-data.noaa_gsod.gsod*` AS g
        ON s.usaf = g.stn
        AND s.wban = g.wban
    WHERE
      _TABLE_SUFFIX BETWEEN '2011' AND '2020'   -- only years 2011-2020
      AND g.temp != 9999.9                       -- exclude missing/invalid temperature
    GROUP BY
      s.usaf,
      s.wban
  )

-- Step 3: Final output – all stations in range with their valid observation count
SELECT
  s.usaf,
  s.wban,
  s.name,
  s.lat,
  s.lon,
  COALESCE(v.num_valid_obs, 0) AS valid_temperature_observations
FROM
  stations_in_range AS s
  LEFT JOIN valid_temp_counts AS v
    ON s.usaf = v.usaf AND s.wban = v.wban
ORDER BY
  valid_temperature_observations DESC;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH chappaqua_location AS (
  SELECT ST_GEOGPOINT(-73.764, 41.197) AS point
),

nearby_stations AS (
  SELECT 
    s.usaf,
    s.wban,
    s.name,
    SAFE_CAST(s.lat AS FLOAT64) AS lat,
    SAFE_CAST(s.lon AS FLOAT64) AS lon
  FROM 
    `bigquery-public-data.noaa_gsod.stations` s,
    chappaqua_location c
  WHERE 
    ST_DWITHIN(c.point, ST_GEOGPOINT(SAFE_CAST(s.lon AS FLOAT64), SAFE_CAST(s.lat AS FLOAT64)), 32186.9)
    AND s.lat IS NOT NULL 
    AND s.lon IS NOT NULL
    AND SAFE_CAST(s.lat AS FLOAT64) != 0.0 
    AND SAFE_CAST(s.lon AS FLOAT64) != 0.0
),

weather_data AS (
  SELECT 
    stn AS station_id,
    wban,
    temp,
    count_temp
  FROM 
    `bigquery-public-data.noaa_gsod.gsod*`
  WHERE 
    _TABLE_SUFFIX BETWEEN '2011' AND '2020'
    AND temp != 9999.9
    AND temp IS NOT NULL
    AND count_temp > 0
)

SELECT 
  ns.usaf AS station_usaf,
  ns.wban AS station_wban,
  ns.name AS station_name,
  ns.lat,
  ns.lon,
  ROUND(ST_DISTANCE(
    ST_GEOGPOINT(-73.764, 41.197), 
    ST_GEOGPOINT(ns.lon, ns.lat)
  ) / 1609.34, 2) AS distance_miles,
  COUNT(wd.temp) AS valid_temp_observations
FROM 
  nearby_stations ns
LEFT JOIN 
  weather_data wd ON ns.usaf = wd.station_id AND ns.wban = wd.wban
GROUP BY 
  ns.usaf, 
  ns.wban, 
  ns.name, 
  ns.lat, 
  ns.lon
ORDER BY 
  distance_miles ASC;
```

---

## 96. Instance: `bq218`
**Question:**
> What are the top 5 items with the highest year-over-year growth percentage in total sales revenue for the year 2023?

### 🏆 Gold Reference Answer
```sql
WITH AnnualSales AS (
  SELECT
    item_description,
    EXTRACT(YEAR FROM date) AS year,
    SUM(sale_dollars) AS total_sales_revenue,
    COUNT(DISTINCT invoice_and_item_number) AS unique_purchases
  FROM
    `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE
    EXTRACT(YEAR FROM date) IN (2022, 2023)
    AND item_description IS NOT NULL
    AND sale_dollars IS NOT NULL
  GROUP BY
    item_description, year
),
YoYGrowth AS (
  SELECT
    curr.item_description,
    curr.year,
    curr.total_sales_revenue,
    curr.unique_purchases,
    LAG(curr.total_sales_revenue) OVER(PARTITION BY curr.item_description ORDER BY curr.year) AS prev_year_sales_revenue,
    (curr.total_sales_revenue - LAG(curr.total_sales_revenue) OVER(PARTITION BY curr.item_description ORDER BY curr.year)) / LAG(curr.total_sales_revenue) OVER(PARTITION BY curr.item_description ORDER BY curr.year) * 100 AS yoy_growth_percentage
  FROM
    AnnualSales curr
),
total_info AS (
SELECT
  item_description,
  year,
  total_sales_revenue,
  unique_purchases,
  prev_year_sales_revenue,
  yoy_growth_percentage
FROM
  YoYGrowth
WHERE
  year = 2023
  AND prev_year_sales_revenue IS NOT NULL -- Exclude rows where there's no previous year data to calculate YoY growth
ORDER BY
  year, total_sales_revenue 
DESC
)

SELECT item_description
FROM total_info
order by yoy_growth_percentage
DESC
LIMIT 5
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Filter sales records for 2022 and 2023, and aggregate revenue per item per year
WITH yearly_sales AS (
  SELECT
    item_number,
    item_description,
    EXTRACT(YEAR FROM date) AS year,
    ROUND(SUM(sale_dollars), 4) AS total_revenue
  FROM
    `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE
    EXTRACT(YEAR FROM date) IN (2022, 2023)
    -- Exclude negative revenue? Keep as is; negative values represent returns
  GROUP BY
    item_number,
    item_description,
    year
),

-- Step 2: Pivot to get 2022 and 2023 revenue side by side for each item
sales_pivot AS (
  SELECT
    item_number,
    item_description,
    MAX(CASE WHEN year = 2022 THEN total_revenue END) AS revenue_2022,
    MAX(CASE WHEN year = 2023 THEN total_revenue END) AS revenue_2023
  FROM
    yearly_sales
  GROUP BY
    item_number,
    item_description
),

-- Step 3: Compute year-over-year growth percentage, ensuring denominator is not zero
growth_calc AS (
  SELECT
    item_number,
    item_description,
    revenue_2022,
    revenue_2023,
    -- Growth % = ((2023 - 2022) / 2022) * 100
    -- Exclude items with zero or NULL 2022 revenue (no prior year sales)
    CASE
      WHEN revenue_2022 IS NOT NULL AND revenue_2022 != 0
      THEN ROUND(((revenue_2023 - revenue_2022) / revenue_2022) * 100, 4)
      ELSE NULL
    END AS growth_percentage
  FROM
    sales_pivot
  WHERE
    revenue_2022 IS NOT NULL
    AND revenue_2023 IS NOT NULL
    AND revenue_2022 != 0
)

-- Step 4: Select top 5 items by highest growth percentage (descending)
SELECT
  item_number,
  item_description,
  revenue_2022,
  revenue_2023,
  growth_percentage
FROM
  growth_calc
ORDER BY
  growth_percentage DESC
LIMIT 5;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Aggregate total sales revenue per item for 2022
WITH sales_2022 AS (
  SELECT
    item_number,
    item_description,
    SUM(sale_dollars) AS total_2022
  FROM
    bigquery-public-data.iowa_liquor_sales.sales
  WHERE
    EXTRACT(YEAR FROM date) = 2022
  GROUP BY
    item_number,
    item_description
),

-- Step 2: Aggregate total sales revenue per item for 2023
sales_2023 AS (
  SELECT
    item_number,
    item_description,
    SUM(sale_dollars) AS total_2023
  FROM
    bigquery-public-data.iowa_liquor_sales.sales
  WHERE
    EXTRACT(YEAR FROM date) = 2023
  GROUP BY
    item_number,
    item_description
),

-- Step 3: Full outer join to keep items present in either year
combined AS (
  SELECT
    COALESCE(a.item_number, b.item_number) AS item_number,
    COALESCE(a.item_description, b.item_description) AS item_description,
    COALESCE(a.total_2022, 0) AS total_2022,
    COALESCE(b.total_2023, 0) AS total_2023
  FROM
    sales_2022 a
  FULL OUTER JOIN
    sales_2023 b
  ON
    a.item_number = b.item_number
),

-- Step 4: Compute year-over-year growth percentage, excluding items without sales in both years
growth AS (
  SELECT
    item_number,
    item_description,
    total_2022,
    total_2023,
    -- Safely compute (2023 - 2022) / 2022, return NULL if 2022 is zero
    SAFE_DIVIDE(total_2023 - total_2022, total_2022) AS growth_fraction
  FROM
    combined
  WHERE
    total_2022 IS NOT NULL
    AND total_2022 != 0
    AND total_2023 IS NOT NULL
)

-- Step 5: Format output and pick top 5 items by growth percentage
SELECT
  item_number,
  item_description,
  ROUND(total_2022, 4) AS total_2022,
  ROUND(total_2023, 4) AS total_2023,
  ROUND(growth_fraction * 100, 4) AS growth_percentage
FROM
  growth
ORDER BY
  growth_percentage DESC
LIMIT 5;
```

---

## 97. Instance: `bq220`
**Question:**
> Based on the condition, plot_tree, and population tables in bigquery-public-data.usfs_fia, for the evaluation_type set to 'EXPCURR' and condition_status_code equal to 1, which states had the largest average subplot size and the largest average macroplot size, respectively, for each of the years 2015, 2016, and 2017? Please include the type of plot (subplot or macroplot), the specific year, the state, and the corresponding average size in your results.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Compute the plot size for each condition based on the subplot/macroplot formula
WITH plot_sizes AS (
  SELECT 
    cond.state_code_name,
    cond.inventory_year,
    cond.proportion_basis,
    pop.expansion_factor,
    cond.condition_proportion_unadjusted,
    pop.adjustment_factor_for_the_subplot AS adj_subp,
    pop.adjustment_factor_for_the_macroplot AS adj_macr,
    CASE
      WHEN cond.proportion_basis = 'SUBP' AND pop.adjustment_factor_for_the_subplot > 0
        THEN pop.expansion_factor * cond.condition_proportion_unadjusted * pop.adjustment_factor_for_the_subplot
      WHEN cond.proportion_basis = 'MACR' AND pop.adjustment_factor_for_the_macroplot > 0
        THEN pop.expansion_factor * cond.condition_proportion_unadjusted * pop.adjustment_factor_for_the_macroplot
      ELSE 0
    END AS plot_size
  FROM `bigquery-public-data.usfs_fia.condition` AS cond
  INNER JOIN `bigquery-public-data.usfs_fia.population` AS pop
    ON cond.plot_sequence_number = pop.plot_sequence_number
   AND cond.inventory_year = pop.inventory_year
   AND cond.state_code = pop.state_code
  WHERE cond.condition_status_code = 1
    AND pop.evaluation_type = 'EXPCURR'
    AND cond.inventory_year IN (2015, 2016, 2017)
    AND cond.proportion_basis IN ('SUBP', 'MACR')
),

-- Step 2: Aggregate by plot type, year, and state to get average size
avg_sizes AS (
  SELECT
    CASE
      WHEN proportion_basis = 'SUBP' THEN 'subplot'
      WHEN proportion_basis = 'MACR' THEN 'macroplot'
    END AS plot_type,
    inventory_year,
    state_code_name,
    ROUND(AVG(plot_size), 4) AS average_size
  FROM plot_sizes
  WHERE plot_size > 0   -- only include valid computed sizes
  GROUP BY plot_type, inventory_year, state_code_name
),

-- Step 3: Rank within each year and plot type by average size descending
ranked AS (
  SELECT
    plot_type,
    inventory_year,
    state_code_name,
    average_size,
    ROW_NUMBER() OVER (
      PARTITION BY plot_type, inventory_year
      ORDER BY average_size DESC
    ) AS rn
  FROM avg_sizes
)

-- Step 4: Select the top state for each year and plot type
SELECT
  plot_type,
  inventory_year,
  state_code_name AS state,
  average_size
FROM ranked
WHERE rn = 1
ORDER BY inventory_year, plot_type;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Get valid evaluations for years 2015-2017 (using start_inventory_year)
WITH valid_evaluations AS (
  SELECT 
    evaluation_identifier
  FROM `bigquery-public-data.usfs_fia.population_evaluation`
  WHERE start_inventory_year IN ('2015', '2016', '2017')
),

-- Step 2: Get population stratum assign data with state and year
pop_stratum AS (
  SELECT 
    plot_sequence_number,
    state_code,
    inventory_year,
    evaluation_identifier
  FROM `bigquery-public-data.usfs_fia.population_stratum_assign`
  WHERE inventory_year IN (2015, 2016, 2017)
),

-- Step 3: Filter conditions (condition_class_number = 1 as proxy for condition_status_code = 1)
cond_data AS (
  SELECT 
    plot_sequence_number,
    inventory_year,
    basal_area_per_acre_of_live_trees AS plot_size_indicator
  FROM `bigquery-public-data.usfs_fia.condition`
  WHERE condition_class_number = 1
    AND basal_area_per_acre_of_live_trees IS NOT NULL
),

-- Step 4: Join all tables
joined_data AS (
  SELECT
    ps.state_code,
    ps.inventory_year,
    c.plot_size_indicator
  FROM cond_data c
  JOIN pop_stratum ps
    ON c.plot_sequence_number = ps.plot_sequence_number
    AND c.inventory_year = ps.inventory_year
  JOIN valid_evaluations ve
    ON ps.evaluation_identifier = ve.evaluation_identifier
),

-- Step 5: Compute average plot size per state and year
avg_sizes AS (
  SELECT
    state_code,
    inventory_year,
    AVG(plot_size_indicator) AS avg_size
  FROM joined_data
  GROUP BY state_code, inventory_year
),

-- Step 6: Rank per year to find largest average size
ranked AS (
  SELECT
    state_code,
    inventory_year,
    avg_size,
    ROW_NUMBER() OVER (
      PARTITION BY inventory_year 
      ORDER BY avg_size DESC
    ) AS rn
  FROM avg_sizes
)

-- Step 7: Final output
SELECT
  state_code,
  inventory_year AS year,
  'subplot' AS plot_type,
  ROUND(avg_size, 4) AS average_size
FROM ranked
WHERE rn = 1
ORDER BY inventory_year;
```

---

## 98. Instance: `bq227`
**Question:**
> Could you provide the annual percentage shares, rounded to two decimal places, of the top 5 minor crime categories from 2008 in London's total crimes, with each year displayed in one row?

### 🏆 Gold Reference Answer
```sql
WITH top5_categories AS (
  SELECT minor_category
  FROM `bigquery-public-data.london_crime.crime_by_lsoa`
  WHERE year = 2008
  GROUP BY minor_category
  ORDER BY SUM(value) DESC
  LIMIT 5
),

total_crimes_per_year AS (
  SELECT 
    year, 
    SUM(value) AS total_crimes_year
  FROM `bigquery-public-data.london_crime.crime_by_lsoa`
  GROUP BY year
),

top5_crimes_per_year AS (
  SELECT
    year,
    minor_category,
    SUM(value) AS total_crimes_category_year
  FROM `bigquery-public-data.london_crime.crime_by_lsoa`
  WHERE minor_category IN (SELECT minor_category FROM top5_categories)
  GROUP BY year, minor_category
)

SELECT
  t.year,
  ROUND(SUM(CASE WHEN t.minor_category = (SELECT minor_category FROM top5_categories LIMIT 1 OFFSET 0) THEN t.total_crimes_category_year ELSE 0 END) / y.total_crimes_year * 100, 2) AS `Category 1`,
  ROUND(SUM(CASE WHEN t.minor_category = (SELECT minor_category FROM top5_categories LIMIT 1 OFFSET 1) THEN t.total_crimes_category_year ELSE 0 END) / y.total_crimes_year * 100, 2) AS `Category 2`,
  ROUND(SUM(CASE WHEN t.minor_category = (SELECT minor_category FROM top5_categories LIMIT 1 OFFSET 2) THEN t.total_crimes_category_year ELSE 0 END) / y.total_crimes_year * 100, 2) AS `Category 3`,
  ROUND(SUM(CASE WHEN t.minor_category = (SELECT minor_category FROM top5_categories LIMIT 1 OFFSET 3) THEN t.total_crimes_category_year ELSE 0 END) / y.total_crimes_year * 100, 2) AS `Category 4`,
  ROUND(SUM(CASE WHEN t.minor_category = (SELECT minor_category FROM top5_categories LIMIT 1 OFFSET 4) THEN t.total_crimes_category_year ELSE 0 END) / y.total_crimes_year * 100, 2) AS `Category 5`
FROM
  top5_crimes_per_year t
JOIN
  total_crimes_per_year y ON t.year = y.year
GROUP BY
  t.year, y.total_crimes_year
ORDER BY
  t.year;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Identify the top 5 minor crime categories in London for 2008
-- We need to find minor categories with the highest total crime count in 2008
WITH top_minor_categories_2008 AS (
    SELECT 
        minor_category,
        SUM(value) AS category_total_2008
    FROM `bigquery-public-data.london_crime.crime_by_lsoa`
    WHERE year = 2008
    GROUP BY minor_category
    ORDER BY category_total_2008 DESC
    LIMIT 5
),

-- Step 2: Calculate total London crimes for 2008 (all categories)
total_crimes_2008 AS (
    SELECT 
        SUM(value) AS grand_total_2008
    FROM `bigquery-public-data.london_crime.crime_by_lsoa`
    WHERE year = 2008
),

-- Step 3: Calculate annual share for each of the top 5 categories
annual_shares AS (
    SELECT 
        tmc.minor_category,
        tmc.category_total_2008,
        tc.grand_total_2008,
        -- Calculate percentage share and round to 2 decimal places
        ROUND((tmc.category_total_2008 * 100.0) / tc.grand_total_2008, 2) AS percentage_share
    FROM top_minor_categories_2008 tmc
    CROSS JOIN total_crimes_2008 tc
)

-- Step 4: Final output - display each year in one row (though we only have 2008 data)
-- The question asks for each year displayed, but we only have 2008 data
-- We'll present the results with the year column showing 2008
SELECT 
    2008 AS year,
    minor_category,
    percentage_share
FROM annual_shares
ORDER BY percentage_share DESC;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Calculate total crime count per minor category per year
WITH CategoryTotals AS (
    SELECT
        minor_category,
        year,
        SUM(value) AS total_per_year_per_category
    FROM `bigquery-public-data.london_crime.crime_by_lsoa`
    GROUP BY minor_category, year
),

-- Step 2: Calculate total crime count across all categories per year
YearlyTotals AS (
    SELECT
        year,
        SUM(value) AS grand_total_per_year
    FROM `bigquery-public-data.london_crime.crime_by_lsoa`
    GROUP BY year
),

-- Step 3: Identify top 5 minor categories based on 2008 totals
Top5Categories AS (
    SELECT
        minor_category,
        SUM(value) AS total_2008
    FROM `bigquery-public-data.london_crime.crime_by_lsoa`
    WHERE year = 2008
    GROUP BY minor_category
    ORDER BY total_2008 DESC
    LIMIT 5
),

-- Step 4: Calculate the percentage share for these top categories across all years
PercentageData AS (
    SELECT
        ct.year,
        ct.minor_category,
        ROUND(SAFE_DIVIDE(ct.total_per_year_per_category, yt.grand_total_per_year) * 100, 2) AS percentage_share
    FROM CategoryTotals ct
    JOIN YearlyTotals yt ON ct.year = yt.year
    WHERE ct.minor_category IN (SELECT minor_category FROM Top5Categories)
)

-- Step 5: Pivot the data so each year is displayed in one row
SELECT
    year,
    MAX(CASE WHEN minor_category = (SELECT minor_category FROM Top5Categories ORDER BY total_2008 DESC LIMIT 1 OFFSET 0) THEN percentage_share END) AS top_1_category,
    MAX(CASE WHEN minor_category = (SELECT minor_category FROM Top5Categories ORDER BY total_2008 DESC LIMIT 1 OFFSET 1) THEN percentage_share END) AS top_2_category,
    MAX(CASE WHEN minor_category = (SELECT minor_category FROM Top5Categories ORDER BY total_2008 DESC LIMIT 1 OFFSET 2) THEN percentage_share END) AS top_3_category,
    MAX(CASE WHEN minor_category = (SELECT minor_category FROM Top5Categories ORDER BY total_2008 DESC LIMIT 1 OFFSET 3) THEN percentage_share END) AS top_4_category,
    MAX(CASE WHEN minor_category = (SELECT minor_category FROM Top5Categories ORDER BY total_2008 DESC LIMIT 1 OFFSET 4) THEN percentage_share END) AS top_5_category
FROM PercentageData
GROUP BY year
ORDER BY year;
```

---

## 99. Instance: `bq228`
**Question:**
> Please provide a list of the top three major crime categories in the borough of Barking and Dagenham, along with the number of incidents in each category.

### 🏆 Gold Reference Answer
```sql
WITH ranked_crimes AS (
    SELECT
        borough,
        major_category,
        RANK() OVER(PARTITION BY borough ORDER BY SUM(value) DESC) AS rank_per_borough,
        SUM(value) AS no_of_incidents
    FROM
        `bigquery-public-data.london_crime.crime_by_lsoa`
    GROUP BY
        borough,
        major_category
)

SELECT
    borough,
    major_category,
    rank_per_borough,
    no_of_incidents
FROM
    ranked_crimes
WHERE
    rank_per_borough <= 3
AND 
    borough = 'Barking and Dagenham'
ORDER BY
    borough,
    rank_per_borough;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH barking_crime AS (
  SELECT
    major_category,
    SUM(value) AS total_incidents
  FROM
    `bigquery-public-data.london_crime.crime_by_lsoa`
  WHERE
    LOWER(borough) = LOWER('Barking and Dagenham')
  GROUP BY
    major_category
)
SELECT
  major_category,
  total_incidents
FROM
  barking_crime
ORDER BY
  total_incidents DESC
LIMIT 3;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Understand the question intent
-- We need the top 3 major crime categories in Barking and Dagenham borough
-- with the total number of incidents (sum of value) for each category
-- Only using the crime_by_lsoa table as fire_brigade data is not relevant

-- Step 2: Identify relevant table and columns
-- Table: bigquery-public-data.london_crime.crime_by_lsoa
-- Columns: major_category (crime category), borough (location), value (incident count)
-- Filter: borough = 'Barking and Dagenham'
-- Aggregation: SUM(value) by major_category
-- Sort/Order: descending by total incidents
-- Limit: top 3

-- Step 3: Design the SQL query structure
-- Simple query with GROUP BY, ORDER BY, and LIMIT
-- No joins needed since only one table is relevant
-- No CTEs or window functions required for this simple aggregation

-- Step 4: Logical validation
-- The query correctly:
-- - Filters for the specified borough
-- - Aggregates by major_category
-- - Sums all crime values (each row represents monthly count for an LSOA)
-- - Orders descending to get highest counts
-- - Limits to 3 results
-- - This satisfies the "top three" requirement

-- Step 5: Final SQL query
SELECT 
    major_category,
    SUM(value) AS total_incidents
FROM 
    `bigquery-public-data.london_crime.crime_by_lsoa`
WHERE 
    LOWER(borough) = 'barking and dagenham'  -- Using LOWER for case-insensitive matching
GROUP BY 
    major_category
ORDER BY 
    total_incidents DESC
LIMIT 3;
```

---

## 100. Instance: `bq229`
**Question:**
> Using the bigquery-public-data.open_images dataset, can you provide a count of how many distinct image URLs are categorized as 'cat' (where the image has label '/m/01yrx' with confidence=1) and how many distinct image URLs are categorized as 'other' (meaning they have no cat label '/m/01yrx' at all)?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Find all image_ids that have cat label with confidence=1
cat_images AS (
    SELECT DISTINCT image_id
    FROM `bigquery-public-data.open_images.labels`
    WHERE label_name = '/m/01yrx' 
      AND confidence = 1.0
),

-- Find all image_ids that have NO cat label at all
non_cat_images AS (
    SELECT DISTINCT l.image_id
    FROM `bigquery-public-data.open_images.labels` l
    LEFT JOIN cat_images c ON l.image_id = c.image_id
    WHERE c.image_id IS NULL
)

-- Count distinct URLs for each category
SELECT 
    'cat' AS category,
    COUNT(DISTINCT i.original_url) AS distinct_url_count
FROM cat_images ci
JOIN `bigquery-public-data.open_images.images` i ON ci.image_id = i.image_id

UNION ALL

SELECT 
    'other' AS category,
    COUNT(DISTINCT i.original_url) AS distinct_url_count
FROM non_cat_images nci
JOIN `bigquery-public-data.open_images.images` i ON nci.image_id = i.image_id;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH 
-- Get all image_ids that have cat label '/m/01yrx' with confidence=1
cat_images AS (
    SELECT DISTINCT image_id
    FROM `bigquery-public-data.open_images.labels`
    WHERE label_name = '/m/01yrx' 
      AND confidence = 1
),

-- Get all image_ids that have cat label '/m/01yrx' at any confidence level
all_cat_images AS (
    SELECT DISTINCT image_id
    FROM `bigquery-public-data.open_images.labels`
    WHERE label_name = '/m/01yrx'
),

-- Get distinct image URLs for cat images
cat_urls AS (
    SELECT DISTINCT i.original_url
    FROM `bigquery-public-data.open_images.images` i
    INNER JOIN cat_images ci ON i.image_id = ci.image_id
),

-- Get distinct image URLs for non-cat images (anti-join)
other_urls AS (
    SELECT DISTINCT i.original_url
    FROM `bigquery-public-data.open_images.images` i
    LEFT JOIN all_cat_images aci ON i.image_id = aci.image_id
    WHERE aci.image_id IS NULL
)

-- Final counts
SELECT 
    'cat' AS category,
    COUNT(DISTINCT original_url) AS distinct_url_count
FROM cat_urls
UNION ALL
SELECT 
    'other' AS category,
    COUNT(DISTINCT original_url) AS distinct_url_count
FROM other_urls
```

---

## 101. Instance: `bq230`
**Question:**
> Using the crops dataset, find the total 2022 production figures, measured in bushels, for corn from the 'FIELD CROPS' category and mushrooms from the 'HORTICULTURE' group for each U.S. state. Only include data rows where 'statisticcat_desc' is 'PRODUCTION', 'agg_level_desc' is 'STATE', 'value' is not null, and ensure that for corn the 'unit_desc' is 'BU'. Combine both results so that each state’s 2022 corn and mushroom totals are presented.

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
-- CTE for 2022 corn production in bushels (BU) at state level
WITH corn_production AS (
  SELECT
    state_name,
    SUM(value) AS corn_production
  FROM
    `bigquery-public-data.usda_nass_agriculture.crops`
  WHERE
    year = 2022
    AND agg_level_desc = 'STATE'
    AND statisticcat_desc = 'PRODUCTION'
    AND commodity_desc = 'CORN'
    AND group_desc = 'FIELD CROPS'
    AND unit_desc = 'BU'
    AND value IS NOT NULL
  GROUP BY
    state_name
),

-- CTE for 2022 mushroom production (any unit) at state level
mushroom_production AS (
  SELECT
    state_name,
    SUM(value) AS mushroom_production
  FROM
    `bigquery-public-data.usda_nass_agriculture.crops`
  WHERE
    year = 2022
    AND agg_level_desc = 'STATE'
    AND statisticcat_desc = 'PRODUCTION'
    AND commodity_desc = 'MUSHROOMS'
    AND group_desc = 'HORTICULTURE'
    AND value IS NOT NULL
  GROUP BY
    state_name
)

-- Full outer join to include states with only corn, only mushrooms, or both
SELECT
  COALESCE(c.state_name, m.state_name) AS state_name,
  c.corn_production,
  m.mushroom_production
FROM
  corn_production c
FULL OUTER JOIN
  mushroom_production m
  ON c.state_name = m.state_name
ORDER BY
  state_name;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH corn_production AS (
  SELECT
    state_name,
    ROUND(SUM(value), 4) AS corn_production_bushels
  FROM
    `bigquery-public-data.usda_nass_agriculture.crops`
  WHERE
    commodity_desc = 'CORN'
    AND group_desc = 'FIELD CROPS'
    AND statisticcat_desc = 'PRODUCTION'
    AND agg_level_desc = 'STATE'
    AND year = 2022
    AND value IS NOT NULL
    AND unit_desc = 'BU'
  GROUP BY
    state_name
),

mushroom_production AS (
  SELECT
    state_name,
    ROUND(SUM(value), 4) AS mushroom_production
  FROM
    `bigquery-public-data.usda_nass_agriculture.crops`
  WHERE
    commodity_desc = 'MUSHROOMS'
    AND group_desc = 'HORTICULTURE'
    AND statisticcat_desc = 'PRODUCTION'
    AND agg_level_desc = 'STATE'
    AND year = 2022
    AND value IS NOT NULL
  GROUP BY
    state_name
)

SELECT
  COALESCE(c.state_name, m.state_name) AS state_name,
  COALESCE(c.corn_production_bushels, 0) AS corn_production_bushels,
  COALESCE(m.mushroom_production, 0) AS mushroom_production
FROM
  corn_production c
FULL OUTER JOIN
  mushroom_production m
ON
  c.state_name = m.state_name
ORDER BY
  state_name;
```

---

## 102. Instance: `bq232`
**Question:**
> Could you provide the total number of 'Other Theft' incidents within the 'Theft and Handling' category for each year in the Westminster borough?

### 🏆 Gold Reference Answer
```sql
WITH borough_data AS (
    SELECT 
        year, 
        month, 
        borough, 
        major_category, 
        minor_category, 
        SUM(value) AS total,
    CASE 
        WHEN 
            major_category = 'Theft and Handling' 
        THEN 
            'Theft and Handling'
        ELSE 
            'Other' 
    END AS major_division,
    CASE 
        WHEN 
            minor_category = 'Other Theft' THEN minor_category
        ELSE 
            'Other'
    END AS minor_division,
    FROM 
        bigquery-public-data.london_crime.crime_by_lsoa
    GROUP BY 1,2,3,4,5
    ORDER BY 1,2
)

SELECT year, SUM(total) AS year_total
FROM borough_data
WHERE 
    borough = 'Westminster'
AND
    major_division != 'Other'
AND 
    minor_division != 'Other'
GROUP BY year, major_division, minor_division
ORDER BY year;
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Query to compute total number of 'Other Theft' incidents within 'Theft and Handling' category per year in Westminster borough
SELECT
  year,
  SUM(value) AS total_incidents
FROM
  `bigquery-public-data.london_crime.crime_by_lsoa`
WHERE
  minor_category = 'Other Theft'
  AND major_category = 'Theft and Handling'
  AND borough = 'Westminster'
GROUP BY
  year
ORDER BY
  year;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Calculate total 'Other Theft' incidents per year in Westminster borough
-- for the 'Theft and Handling' major category
SELECT
    year,
    SUM(value) AS total_incidents
FROM
    `bigquery-public-data.london_crime.crime_by_lsoa`
WHERE
    LOWER(borough) = 'westminster'
    AND LOWER(major_category) = 'theft and handling'
    AND LOWER(minor_category) = 'other theft'
GROUP BY
    year
ORDER BY
    year;
```

---

## 103. Instance: `bq234`
**Question:**
> What is the most prescribed medication in each state in 2014?

### 🏆 Gold Reference Answer
```sql
SELECT
  A.state,
  drug_name,
  total_claim_count
FROM (
  SELECT
    generic_name AS drug_name,
    nppes_provider_state AS state,
    ROUND(SUM(total_claim_count)) AS total_claim_count,
    ROUND(SUM(total_day_supply)) AS day_supply,
    ROUND(SUM(total_drug_cost)) / 1e6 AS total_cost_millions
  FROM
    `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
  GROUP BY
    state,
    drug_name) A
INNER JOIN (
  SELECT
    state,
    MAX(total_claim_count) AS max_total_claim_count
  FROM (
    SELECT
      nppes_provider_state AS state,
      ROUND(SUM(total_claim_count)) AS total_claim_count
    FROM
      `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
    GROUP BY
      state,
      generic_name)
  GROUP BY
    state) B
ON
  A.state = B.state
  AND A.total_claim_count = B.max_total_claim_count;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH drug_prescriptions AS (
  -- Aggregate total claims by state and drug for 2014
  SELECT 
    nppes_provider_state AS state,
    drug_name,
    SUM(total_claim_count) AS total_prescriptions
  FROM `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
  WHERE nppes_provider_state IS NOT NULL
    AND drug_name IS NOT NULL
    AND total_claim_count IS NOT NULL
  GROUP BY state, drug_name
),
ranked_drugs AS (
  -- Rank drugs within each state by total prescription count
  SELECT 
    state,
    drug_name,
    total_prescriptions,
    ROW_NUMBER() OVER (PARTITION BY state ORDER BY total_prescriptions DESC) AS rank
  FROM drug_prescriptions
)
-- Select the most prescribed drug (rank=1) for each state
SELECT 
  state,
  drug_name,
  total_prescriptions
FROM ranked_drugs
WHERE rank = 1
ORDER BY state;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH drug_agg AS (
  -- Aggregate total claim count per drug and state for 2014
  SELECT
    nppes_provider_state AS state,
    drug_name,
    SUM(total_claim_count) AS total_claims
  FROM `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
  WHERE drug_name IS NOT NULL
    AND total_claim_count IS NOT NULL
  GROUP BY state, drug_name
),
ranked AS (
  -- Rank drugs within each state by total claim count descending
  SELECT
    state,
    drug_name,
    total_claims,
    ROW_NUMBER() OVER (PARTITION BY state ORDER BY total_claims DESC) AS rn
  FROM drug_agg
)
-- Select the top-ranked drug per state
SELECT
  state,
  drug_name,
  total_claims
FROM ranked
WHERE rn = 1
ORDER BY state;
```

---

## 104. Instance: `bq235`
**Question:**
> Can you tell me which healthcare provider incurs the highest combined average costs for both outpatient and inpatient services in 2014?

### 🏆 Gold Reference Answer
```sql
SELECT
  Provider_Name
FROM
(
SELECT
  OP.provider_state AS State,
  OP.provider_city AS City,
  OP.provider_id AS Provider_ID,
  OP.provider_name AS Provider_Name,
  ROUND(OP.average_OP_cost) AS Average_OP_Cost,
  ROUND(IP.average_IP_cost) AS Average_IP_Cost,
  ROUND(OP.average_OP_cost + IP.average_IP_cost) AS Combined_Average_Cost
FROM (
  SELECT
    provider_state,
    provider_city,
    provider_id,
    provider_name,
    SUM(average_total_payments*outpatient_services)/SUM(outpatient_services) AS average_OP_cost
  FROM
    `bigquery-public-data.cms_medicare.outpatient_charges_2014`
  GROUP BY
    provider_state,
    provider_city,
    provider_id,
    provider_name ) AS OP
INNER JOIN (
  SELECT
    provider_state,
    provider_city,
    provider_id,
    provider_name,
    SUM(average_medicare_payments*total_discharges)/SUM(total_discharges) AS average_IP_cost
  FROM
    `bigquery-public-data.cms_medicare.inpatient_charges_2014`
  GROUP BY
    provider_state,
    provider_city,
    provider_id,
    provider_name ) AS IP
ON
  OP.provider_id = IP.provider_id
  AND OP.provider_state = IP.provider_state
  AND OP.provider_city = IP.provider_city
  AND OP.provider_name = IP.provider_name
ORDER BY
  combined_average_cost DESC
LIMIT
  1
);
```

### 🤖 AutoLink Baseline Prediction
```sql
-- CTE: Calculate average outpatient payments per provider for 2014
WITH outpatient_avg AS (
    SELECT 
        provider_id,
        provider_name,
        AVG(average_total_payments) AS avg_outpatient_cost
    FROM `bigquery-public-data.cms_medicare.outpatient_charges_2014`
    GROUP BY provider_id, provider_name
),
-- CTE: Calculate average inpatient payments per provider for 2014
inpatient_avg AS (
    SELECT 
        provider_id,
        provider_name,
        AVG(average_total_payments) AS avg_inpatient_cost
    FROM `bigquery-public-data.cms_medicare.inpatient_charges_2014`
    GROUP BY provider_id, provider_name
),
-- CTE: Join both averages and compute combined cost
combined_costs AS (
    SELECT 
        o.provider_id,
        o.provider_name,
        o.avg_outpatient_cost,
        i.avg_inpatient_cost,
        (o.avg_outpatient_cost + i.avg_inpatient_cost) AS combined_avg_cost
    FROM outpatient_avg o
    INNER JOIN inpatient_avg i
        ON o.provider_id = i.provider_id
)
-- Final: Get the healthcare provider with the highest combined average cost
SELECT 
    provider_id,
    provider_name,
    ROUND(avg_outpatient_cost, 2) AS avg_outpatient_cost,
    ROUND(avg_inpatient_cost, 2) AS avg_inpatient_cost,
    ROUND(combined_avg_cost, 2) AS combined_avg_cost
FROM combined_costs
ORDER BY combined_avg_cost DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Compute total outpatient average payments per provider in 2014
WITH outpatient_totals AS (
  SELECT
    provider_id,
    provider_name,
    ROUND(SUM(average_total_payments), 4) AS outpatient_total_payments
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_2014`
  GROUP BY provider_id, provider_name
),

-- Step 2: Compute total inpatient average payments per provider in 2014
inpatient_totals AS (
  SELECT
    provider_id,
    provider_name,
    ROUND(SUM(average_total_payments), 4) AS inpatient_total_payments
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_2014`
  GROUP BY provider_id, provider_name
)

-- Step 3: Combine outpatient and inpatient totals, find the provider with the highest combined cost
SELECT
  o.provider_id,
  o.provider_name,
  ROUND(o.outpatient_total_payments + i.inpatient_total_payments, 4) AS combined_avg_cost
FROM outpatient_totals o
INNER JOIN inpatient_totals i
  ON o.provider_id = i.provider_id
ORDER BY combined_avg_cost DESC
LIMIT 1;
```

---

## 105. Instance: `bq268`
**Question:**
> Identify the longest number of days between the first visit and the last recorded event (either the last visit or the first transaction) for a user, where the last recorded event is associated with a mobile device. The last recorded event could either be the last visit or the first transaction, and you should focus on users whose last recorded event occurred on a mobile device.

### 🏆 Gold Reference Answer
```sql
WITH 

visit AS (
SELECT fullvisitorid, MIN(date) AS date_first_visit, MAX(date) AS date_last_visit 
FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` GROUP BY fullvisitorid),

device_visit AS (
SELECT DISTINCT fullvisitorid, date, device.deviceCategory
FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`),

transactions AS (
SELECT fullvisitorid, MIN(date) AS date_transactions, 1 AS transaction
FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` AS ga, UNNEST(ga.hits) AS hits
WHERE  hits.transaction.transactionId IS NOT NULL GROUP BY fullvisitorid),

device_transactions AS (
SELECT DISTINCT fullvisitorid, date, device.deviceCategory
FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` AS ga, UNNEST(ga.hits) AS hits
WHERE hits.transaction.transactionId IS NOT NULL),

visits_transactions AS (
SELECT visit.fullvisitorid, date_first_visit, date_transactions, date_last_visit , 
       device_visit.deviceCategory AS device_last_visit, device_transactions.deviceCategory AS device_transaction, 
       IFNULL(transactions.transaction,0) AS transaction
FROM visit LEFT JOIN transactions ON visit.fullvisitorid = transactions.fullvisitorid
LEFT JOIN device_visit ON visit.fullvisitorid = device_visit.fullvisitorid 
AND visit.date_last_visit = device_visit.date

LEFT JOIN device_transactions ON visit.fullvisitorid = device_transactions.fullvisitorid 
AND transactions.date_transactions = device_transactions.date ),

mortality_table AS (
SELECT fullvisitorid, date_first_visit, 
       CASE WHEN date_transactions IS NULL THEN date_last_visit ELSE date_transactions  END AS date_event, 
       CASE WHEN device_transaction IS NULL THEN device_last_visit ELSE device_transaction END AS device, transaction
FROM visits_transactions )

SELECT DATE_DIFF(PARSE_DATE('%Y%m%d',date_event), PARSE_DATE('%Y%m%d', date_first_visit),DAY) AS time 
FROM mortality_table
WHERE device = 'mobile'
ORDER BY DATE_DIFF(PARSE_DATE('%Y%m%d',date_event), PARSE_DATE('%Y%m%d', date_first_visit),DAY) DESC
LIMIT 1
```

### 🤖 AutoLink Baseline Prediction
```sql
-- Step 1: Understand the question
-- We need to find the longest number of days between a user's first visit and their last recorded event,
-- where the last recorded event is either the last visit or the first transaction, and that last event
-- occurred on a mobile device. We need to consider all users across all available date-sharded tables.

-- Step 2: Identify relevant tables and columns
-- Tables: All ga_sessions_* tables from 20160801 to 20170801
-- Columns needed:
--   - fullVisitorId (user identifier)
--   - date (session date in YYYYMMDD format)
--   - device.isMobile (to check if mobile)
--   - hits.transaction.transactionId (to identify transactions)
--   - visitStartTime (for ordering within a day if needed)

-- Step 3: Design the SQL structure
-- We'll use a CTE to:
-- 1. Unify all session data across date-sharded tables
-- 2. For each user, find:
--    a. First visit date (MIN date)
--    b. Last visit date (MAX date)
--    c. First transaction date (MIN date where transaction exists)
-- 3. Determine the "last recorded event" as the later of last visit and first transaction
-- 4. Filter to only users where that last event occurred on a mobile device
-- 5. Calculate the day difference between first visit and last event
-- 6. Return the maximum difference

WITH all_sessions AS (
  -- Combine all date-sharded tables
  SELECT * FROM `bigquery-public-data.google_analytics_sample.ga_sessions_20160801`
  UNION ALL
  SELECT * FROM `bigquery-public-data.google_analytics_sample.ga_sessions_20160802`
  UNION ALL
  SELECT * FROM `bigquery-public-data.google_analytics_sample.ga_sessions_20160803`
  -- ... (all tables between 20160801 and 20170801)
  -- For brevity, we'll use wildcard with _TABLE_SUFFIX filter
),

user_events AS (
  -- For each user, get first visit date, last visit date, first transaction date
  SELECT
    fullVisitorId,
    MIN(PARSE_DATE('%Y%m%d', date)) AS first_visit_date,
    MAX(PARSE_DATE('%Y%m%d', date)) AS last_visit_date,
    MIN(CASE 
          WHEN EXISTS (
            SELECT 1 FROM UNNEST(hits) AS h 
            WHERE h.transaction.transactionId IS NOT NULL
          ) 
          THEN PARSE_DATE('%Y%m%d', date) 
        END) AS first_transaction_date,
    -- Also track if the last visit was on mobile
    MAX(CASE 
          WHEN device.isMobile = TRUE 
          THEN PARSE_DATE('%Y%m%d', date) 
        END) AS last_mobile_visit_date,
    -- Track if first transaction was on mobile
    MIN(CASE 
          WHEN EXISTS (
            SELECT 1 FROM UNNEST(hits) AS h 
            WHERE h.transaction.transactionId IS NOT NULL
          ) AND device.isMobile = TRUE
          THEN PARSE_DATE('%Y%m%d', date) 
        END) AS first_mobile_transaction_date
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20160801' AND '20170801'
  GROUP BY fullVisitorId
),

user_last_event AS (
  -- Determine the last recorded event date and whether it was on mobile
  SELECT
    fullVisitorId,
    first_visit_date,
    -- Last event is the later of last visit and first transaction
    GREATEST(last_visit_date, COALESCE(first_transaction_date, last_visit_date)) AS last_event_date,
    -- Check if the last event was on mobile
    CASE
      WHEN last_visit_date >= COALESCE(first_transaction_date, last_visit_date) 
        AND last_mobile_visit_date = last_visit_date 
        THEN TRUE
      WHEN first_transaction_date > last_visit_date 
        AND first_mobile_transaction_date = first_transaction_date 
        THEN TRUE
      ELSE FALSE
    END AS last_event_on_mobile
  FROM user_events
)

-- Final query: get the maximum day difference for users whose last event was on mobile
SELECT
  MAX(DATE_DIFF(last_event_date, first_visit_date, DAY)) AS longest_days_between_first_and_last
FROM user_last_event
WHERE last_event_on_mobile = TRUE
  AND first_visit_date IS NOT NULL
  AND last_event_date IS NOT NULL;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Identify users whose last recorded session occurred on a mobile device.
-- The last recorded session is defined as the most recent session (by date) for each user.
-- Mobile device is identified by either device.isMobile = TRUE or device.deviceCategory = 'mobile'.

WITH user_sessions AS (
  SELECT
    fullVisitorId,
    date,
    device.isMobile AS is_mobile,
    device.deviceCategory AS device_category,
    -- Assign row numbers to order sessions by date ascending and descending per user
    ROW_NUMBER() OVER (PARTITION BY fullVisitorId ORDER BY date ASC)  AS rn_first,
    ROW_NUMBER() OVER (PARTITION BY fullVisitorId ORDER BY date DESC) AS rn_last
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20160801' AND '20170801'
),

-- For each user, extract the first visit date and the last visit date along with device info of the last session
first_last AS (
  SELECT
    fullVisitorId,
    MAX(CASE WHEN rn_first = 1 THEN date END) AS first_visit_date,
    MAX(CASE WHEN rn_last  = 1 THEN date END) AS last_visit_date,
    MAX(CASE WHEN rn_last  = 1 THEN is_mobile END) AS last_is_mobile,
    MAX(CASE WHEN rn_last  = 1 THEN device_category END) AS last_device_category
  FROM user_sessions
  GROUP BY fullVisitorId
)

-- Compute the number of days between first and last visit, filter for mobile last session,
-- and return the longest interval.
SELECT
  fullVisitorId,
  DATE_DIFF(PARSE_DATE('%Y%m%d', last_visit_date),
            PARSE_DATE('%Y%m%d', first_visit_date), DAY) AS days_between
FROM first_last
WHERE last_is_mobile = TRUE OR last_device_category = 'mobile'
ORDER BY days_between DESC
LIMIT 1;
```

---

## 106. Instance: `bq269`
**Question:**
> Between June 1, 2017, and July 31, 2017, consider only sessions that have non-null pageviews. Classify each session as ‘purchase’ if it has at least one transaction, or ‘non_purchase’ otherwise. For each month, sum each visitor’s total pageviews under each classification, then compute the average pageviews per visitor for both purchase and non-purchase groups in each month, and present the results side by side.

### 🏆 Gold Reference Answer
```sql
WITH visitor_pageviews AS (
  SELECT
    FORMAT_DATE('%Y%m', PARSE_DATE('%Y%m%d', date)) AS month,
    CASE WHEN totals.transactions > 0 THEN 'purchase' ELSE 'non_purchase' END AS purchase_status,
    fullVisitorId,
    SUM(totals.pageviews) AS total_pageviews
  FROM
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20170601' AND '20170731'
    AND totals.pageviews IS NOT NULL
  GROUP BY
    month, purchase_status, fullVisitorId
),
avg_pageviews AS (
  SELECT
    month,
    purchase_status,
    AVG(total_pageviews) AS avg_pageviews_per_visitor
  FROM
    visitor_pageviews
  GROUP BY
    month, purchase_status
)
SELECT
  month,
  MAX(CASE WHEN purchase_status = 'purchase' THEN avg_pageviews_per_visitor END) AS avg_pageviews_purchase,
  MAX(CASE WHEN purchase_status = 'non_purchase' THEN avg_pageviews_per_visitor END) AS avg_pageviews_non_purchase
FROM
  avg_pageviews
GROUP BY
  month
ORDER BY
  month
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH session_data AS (
    -- Select sessions from June and July 2017 with non-null pageviews
    -- Classify each session as 'purchase' or 'non_purchase'
    SELECT 
        date,
        fullVisitorId,
        totals.pageviews AS pageviews,
        CASE 
            WHEN totals.transactions > 0 THEN 'purchase' 
            ELSE 'non_purchase' 
        END AS session_type
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
    WHERE _TABLE_SUFFIX BETWEEN '20170601' AND '20170731'
      AND totals.pageviews IS NOT NULL
),
visitor_monthly_totals AS (
    -- For each month and visitor, sum pageviews under each classification
    SELECT 
        FORMAT_DATE('%Y-%m', PARSE_DATE('%Y%m%d', date)) AS month,
        fullVisitorId,
        session_type,
        SUM(pageviews) AS total_pageviews
    FROM session_data
    GROUP BY month, fullVisitorId, session_type
)
-- Compute average pageviews per visitor for purchase and non_purchase groups
-- Present results side by side for each month
SELECT 
    month,
    ROUND(AVG(CASE WHEN session_type = 'purchase' THEN total_pageviews END), 4) AS avg_purchase_pageviews,
    ROUND(AVG(CASE WHEN session_type = 'non_purchase' THEN total_pageviews END), 4) AS avg_non_purchase_pageviews
FROM visitor_monthly_totals
GROUP BY month
ORDER BY month;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Filter sessions with non-null pageviews from June 1, 2017 to July 31, 2017
WITH sessions_filtered AS (
  SELECT
    fullVisitorId,
    date,
    totals.pageviews AS pageviews,
    -- Classify session: at least one transaction => 'purchase', else 'non_purchase'
    IF(COALESCE(totals.transactions, 0) > 0, 'purchase', 'non_purchase') AS classification
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20170601' AND '20170731'
    AND totals.pageviews IS NOT NULL
),

-- Step 2: For each visitor, month, and classification, sum total pageviews
visitor_monthly AS (
  SELECT
    fullVisitorId,
    FORMAT_DATE('%Y-%m', PARSE_DATE('%Y%m%d', date)) AS month,
    classification,
    SUM(pageviews) AS total_pageviews
  FROM sessions_filtered
  GROUP BY fullVisitorId, month, classification
),

-- Step 3: Compute average pageviews per visitor for each group and month
avg_monthly AS (
  SELECT
    month,
    classification,
    ROUND(AVG(total_pageviews), 4) AS avg_pageviews_per_visitor
  FROM visitor_monthly
  GROUP BY month, classification
)

-- Step 4: Pivot to show purchase and non_purchase averages side by side per month
SELECT
  month,
  MAX(CASE WHEN classification = 'purchase' THEN avg_pageviews_per_visitor END) AS avg_purchase_pageviews,
  MAX(CASE WHEN classification = 'non_purchase' THEN avg_pageviews_per_visitor END) AS avg_non_purchase_pageviews
FROM avg_monthly
GROUP BY month
ORDER BY month;
```

---

## 107. Instance: `bq270`
**Question:**
> What were the monthly add-to-cart and purchase conversion rates, calculated as a percentage of pageviews on product details, from January to March 2017?

### 🏆 Gold Reference Answer
```sql
WITH
  cte1 AS
    (SELECT
      CONCAT(EXTRACT(YEAR FROM (PARSE_DATE('%Y%m%d', date))),'0',
                EXTRACT(MONTH FROM (PARSE_DATE('%Y%m%d', date)))) AS month,
      COUNT(hits.eCommerceAction.action_type) AS num_product_view
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`,
      UNNEST(hits) AS hits
    WHERE _table_suffix BETWEEN '0101' AND '0331'
      AND hits.eCommerceAction.action_type = '2'
    GROUP BY month),
  cte2 AS
    (SELECT
      CONCAT(EXTRACT(YEAR FROM (PARSE_DATE('%Y%m%d', date))),'0',
                EXTRACT(MONTH FROM (PARSE_DATE('%Y%m%d', date)))) AS month,
      COUNT(hits.eCommerceAction.action_type) AS num_addtocart
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`,
      UNNEST(hits) AS hits
    WHERE _table_suffix BETWEEN '0101' AND '0331'
      AND hits.eCommerceAction.action_type = '3'
    GROUP BY month),
  cte3 AS
    (SELECT
      CONCAT(EXTRACT(YEAR FROM (PARSE_DATE('%Y%m%d', date))),'0',
                EXTRACT(MONTH FROM (PARSE_DATE('%Y%m%d', date)))) AS month,
      COUNT(hits.eCommerceAction.action_type) AS num_purchase
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`,
      UNNEST(hits) AS hits,
      UNNEST(hits.product) AS product
    WHERE _table_suffix BETWEEN '0101' AND '0331'
      AND hits.eCommerceAction.action_type = '6'
      AND product.productRevenue IS NOT NULL
    GROUP BY month)
SELECT 
  ROUND((num_addtocart/num_product_view * 100),2) AS add_to_cart_rate,
  ROUND((num_purchase/num_product_view * 100),2) AS purchase_rate
FROM cte1
  LEFT JOIN cte2
  USING(month) 
  LEFT JOIN cte3
  USING(month)
ORDER BY month;
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH product_data AS (
  SELECT
    PARSE_DATE('%Y%m%d', date) AS date,
    h.eCommerceAction.action_type AS action_type,
    p.isImpression
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`,
    UNNEST(hits) AS h,
    UNNEST(h.product) AS p
  WHERE _TABLE_SUFFIX BETWEEN '20170101' AND '20170331'
    AND h.eCommerceAction.action_type IN ('2', '3', '6')
),
monthly_counts AS (
  SELECT
    FORMAT_DATE('%Y-%m', date) AS month,
    COUNTIF(action_type = '2' AND (isImpression IS NULL OR isImpression = FALSE)) AS detail_views,
    COUNTIF(action_type = '3' AND (isImpression IS NULL OR isImpression = FALSE)) AS add_to_carts,
    COUNTIF(action_type = '6' AND (isImpression IS NULL OR isImpression = FALSE)) AS purchases
  FROM product_data
  GROUP BY month
)
SELECT
  month,
  ROUND(add_to_carts * 100.0 / NULLIF(detail_views, 0), 4) AS add_to_cart_rate,
  ROUND(purchases * 100.0 / NULLIF(detail_views, 0), 4) AS purchase_rate
FROM monthly_counts
ORDER BY month;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
-- Step 1: Define a CTE that extracts the month and relevant eCommerce action types from all hits
-- We query the wildcard table for dates between 20170101 and 20170331
WITH session_hits AS (
  SELECT
    PARSE_DATE('%Y%m%d', date) AS session_date,
    hit.eCommerceAction.action_type AS action_type
  FROM
    `bigquery-public-data.google_analytics_sample.ga_sessions_*`,
    UNNEST(hits) AS hit
  WHERE
    _TABLE_SUFFIX BETWEEN '20170101' AND '20170331'
    AND hit.eCommerceAction.action_type IN ('2', '3', '6')  -- product detail view, add to cart, purchase
),
-- Step 2: Aggregate counts per month
monthly_counts AS (
  SELECT
    DATE_TRUNC(session_date, MONTH) AS month,
    COUNTIF(action_type = '2') AS product_detail_pageviews,
    COUNTIF(action_type = '3') AS add_to_cart_actions,
    COUNTIF(action_type = '6') AS purchase_actions
  FROM session_hits
  GROUP BY month
)
-- Step 3: Compute conversion rates as percentage of product detail pageviews
SELECT
  FORMAT_DATE('%Y-%m', month) AS month,
  ROUND(SAFE_DIVIDE(add_to_cart_actions, product_detail_pageviews) * 100, 4) AS add_to_cart_conversion_rate,
  ROUND(SAFE_DIVIDE(purchase_actions, product_detail_pageviews) * 100, 4) AS purchase_conversion_rate
FROM monthly_counts
ORDER BY month;
```

---

## 108. Instance: `bq275`
**Question:**
> Which visitor IDs belong to users whose first transaction occurred on a device explicitly labeled as 'mobile' on a later date than their first visit?

### 🏆 Gold Reference Answer
```sql
WITH 
  visit AS (
    SELECT fullvisitorid, MIN(date) AS date_first_visit
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` 
    GROUP BY fullvisitorid
  ),
  
  transactions AS (
    SELECT fullvisitorid, MIN(date) AS date_transactions, 1 AS transaction
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` AS ga, 
    UNNEST(ga.hits) AS hits 
    WHERE hits.transaction.transactionId IS NOT NULL 
    GROUP BY fullvisitorid
  ),

  device_transactions AS (
    SELECT DISTINCT fullvisitorid, date, device.deviceCategory AS device_transaction
    FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` AS ga, 
    UNNEST(ga.hits) AS hits 
    WHERE hits.transaction.transactionId IS NOT NULL
  ),

  visits_transactions AS (
    SELECT visit.fullvisitorid, date_first_visit, date_transactions, device_transaction
    FROM visit 
    LEFT JOIN transactions ON visit.fullvisitorid = transactions.fullvisitorid
    LEFT JOIN device_transactions ON visit.fullvisitorid = device_transactions.fullvisitorid 
    AND transactions.date_transactions = device_transactions.date
  )

SELECT fullvisitorid 
FROM visits_transactions
WHERE DATE_DIFF(PARSE_DATE('%Y%m%d', date_transactions), PARSE_DATE('%Y%m%d', date_first_visit), DAY) > 0
AND device_transaction = "mobile";
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Get all visits with their dates and device info
all_visits AS (
  SELECT
    fullVisitorId,
    PARSE_DATE('%Y%m%d', date) AS visit_date,
    device.deviceCategory AS device_category
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20160701' AND '20170731'  -- Cover all available data
    AND device.deviceCategory IS NOT NULL  -- Ensure device info is available
),

-- Get all transactions with dates and device info
all_transactions AS (
  SELECT
    fullVisitorId,
    PARSE_DATE('%Y%m%d', date) AS transaction_date,
    device.deviceCategory AS device_category,
    h.transaction.transactionId
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`,
  UNNEST(hits) AS h
  WHERE _TABLE_SUFFIX BETWEEN '20160701' AND '20170731'
    AND h.transaction.transactionId IS NOT NULL  -- Only rows with transactions
),

-- Find first visit date for each user
first_visit AS (
  SELECT
    fullVisitorId,
    MIN(visit_date) AS first_visit_date
  FROM all_visits
  GROUP BY fullVisitorId
),

-- Find first mobile transaction date for each user
first_mobile_transaction AS (
  SELECT
    fullVisitorId,
    MIN(transaction_date) AS first_mobile_transaction_date
  FROM all_transactions
  WHERE device_category = 'mobile'  -- Only mobile device transactions
  GROUP BY fullVisitorId
)

-- Final selection: users whose first mobile transaction is after first visit
SELECT DISTINCT
  fv.fullVisitorId
FROM first_visit fv
INNER JOIN first_mobile_transaction fmt
  ON fv.fullVisitorId = fmt.fullVisitorId
WHERE fmt.first_mobile_transaction_date > fv.first_visit_date
ORDER BY fv.fullVisitorId;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
WITH all_sessions AS (
  SELECT fullVisitorId, date, device, hits
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20160801' AND '20170801'
),
first_visit AS (
  SELECT fullVisitorId, MIN(date) AS first_visit_date
  FROM all_sessions
  GROUP BY fullVisitorId
),
transaction_hits AS (
  SELECT
    s.fullVisitorId,
    s.date,
    s.device.deviceCategory AS device_category,
    h.hitNumber,
    h.transaction.transactionId
  FROM all_sessions s
  CROSS JOIN UNNEST(s.hits) AS h
  WHERE h.transaction.transactionId IS NOT NULL
),
ranked_transactions AS (
  SELECT
    fullVisitorId,
    date,
    LOWER(device_category) AS device_category_lower,
    ROW_NUMBER() OVER (
      PARTITION BY fullVisitorId
      ORDER BY date ASC, hitNumber ASC
    ) AS rn
  FROM transaction_hits
),
first_transaction AS (
  SELECT fullVisitorId, date AS first_transaction_date, device_category_lower
  FROM ranked_transactions
  WHERE rn = 1
)
SELECT ft.fullVisitorId
FROM first_transaction ft
JOIN first_visit fv ON ft.fullVisitorId = fv.fullVisitorId
WHERE ft.device_category_lower = 'mobile'
  AND ft.first_transaction_date > fv.first_visit_date
ORDER BY ft.fullVisitorId;
```

---

## 109. Instance: `bq277`
**Question:**
> Which single port, listed under region number '6585', is located within a U.S. state boundary and appears most frequently inside the geographic areas of named tropical storms with wind speeds of at least 35 knots in the North Atlantic basin, excluding those labeled 'NOT_NAMED'?

### 🏆 Gold Reference Answer
```sql
N/A
```

### 🤖 AutoLink Baseline Prediction
```sql
WITH 
-- Define the conversion function
nautical_miles_conversion AS (
  SELECT 1.15078 AS conversion_factor
),

-- Get ports under region '6585' within US state boundaries
-- Using a US states boundary table for spatial containment
ports_data AS (
  SELECT 
    p.port_name,
    p.port_id,
    p.latitude,
    p.longitude,
    ST_GEOGPOINT(p.longitude, p.latitude) AS port_location
  FROM `bigquery-public-data.geo_international_ports.world_port_index` p
  JOIN `bigquery-public-data.geo_us_boundaries.states` s
    ON ST_WITHIN(ST_GEOGPOINT(p.longitude, p.latitude), s.state_geom)
  WHERE p.region_number = '6585'
),

-- Get named tropical storms in NA basin with wind >= 35 knots
storms AS (
  SELECT 
    sid,
    name,
    latitude,
    longitude,
    usa_wind,
    usa_r34_ne, usa_r34_se, usa_r34_sw, usa_r34_nw,
    usa_r50_ne, usa_r50_se, usa_r50_sw, usa_r50_nw,
    usa_r64_ne, usa_r64_se, usa_r64_sw, usa_r64_nw,
    timestamp
  FROM `bigquery-public-data.noaa_hurricanes.hurricanes`
  WHERE basin = 'NA'
    AND LOWER(name) NOT LIKE '%not_named%'
    AND name IS NOT NULL AND name != ''
    AND usa_wind >= 35
),

-- Construct storm polygons using wind radii
-- For each storm, create a polygon representing the wind field
storm_polygons AS (
  SELECT 
    sid,
    name,
    -- Create polygon from wind radii in 8 directions (N, NE, E, SE, S, SW, W, NW)
    -- Using the maximum wind radius at each point
    ST_MAKEPOLYGON(
      ST_MAKELINE(
        -- Start from storm center and go outward in each direction
        ST_GEOGPOINT(longitude, latitude),
        -- North (azimuth 0)
        ST_GEOGPOINT(
          longitude + COALESCE(usa_r34_n, 0) * 1.15078 * 0.000156785 / COS(latitude * 3.14159 / 180),
          latitude + COALESCE(usa_r34_n, 0) * 1.15078 * 0.000156785
        ),
        -- Northeast (azimuth 45)
        ST_GEOGPOINT(
          longitude + COALESCE(usa_r34_ne, 0) * 1.15078 * 0.000156785 * COS(45 * 3.14159 / 180) / COS(latitude * 3.14159 / 180),
          latitude + COALESCE(usa_r34_ne, 0) * 1.15078 * 0.000156785 * SIN(45 * 3.14159 / 180)
        ),
        -- East (azimuth 90)
        ST_GEOGPOINT(
          longitude + COALESCE(usa_r34_e, 0) * 1.15078 * 0.000156785 / COS(latitude * 3.14159 / 180),
          latitude
        ),
        -- Southeast (azimuth 135)
        ST_GEOGPOINT(
          longitude + COALESCE(usa_r34_se, 0) * 1.15078 * 0.000156785 * COS(135 * 3.14159 / 180) / COS(latitude * 3.14159 / 180),
          latitude + COALESCE(usa_r34_se, 0) * 1.15078 * 0.000156785 * SIN(135 * 3.14159 / 180)
        ),
        -- South (azimuth 180)
        ST_GEOGPOINT(
          longitude,
          latitude - COALESCE(usa_r34_s, 0) * 1.15078 * 0.000156785
        ),
        -- Southwest (azimuth 225)
        ST_GEOGPOINT(
          longitude + COALESCE(usa_r34_sw, 0) * 1.15078 * 0.000156785 * COS(225 * 3.14159 / 180) / COS(latitude * 3.14159 / 180),
          latitude + COALESCE(usa_r34_sw, 0) * 1.15078 * 0.000156785 * SIN(225 * 3.14159 / 180)
        ),
        -- West (azimuth 270)
        ST_GEOGPOINT(
          longitude - COALESCE(usa_r34_w, 0) * 1.15078 * 0.000156785 / COS(latitude * 3.14159 / 180),
          latitude
        ),
        -- Northwest (azimuth 315)
        ST_GEOGPOINT(
          longitude + COALESCE(usa_r34_nw, 0) * 1.15078 * 0.000156785 * COS(315 * 3.14159 / 180) / COS(latitude * 3.14159 / 180),
          latitude + COALESCE(usa_r34_nw, 0) * 1.15078 * 0.000156785 * SIN(315 * 3.14159 / 180)
        ),
        -- Close the polygon back to start
        ST_GEOGPOINT(longitude, latitude)
      )
    ) AS storm_area
  FROM storms
)

-- Count occurrences of each port within storm areas
SELECT 
  p.port_name,
  p.port_id,
  COUNT(*) AS occurrence_count
FROM ports_data p
JOIN storm_polygons s
  ON ST_WITHIN(p.port_location, s.storm_area)
GROUP BY p.port_name, p.port_id
ORDER BY occurrence_count DESC
LIMIT 1;
```

### 🚀 SlayQL (C-CaSE) Prediction
```sql
CREATE TEMPORARY FUNCTION azimuth_to_geog_point(lat FLOAT64, lon FLOAT64, azimuth FLOAT64, distance_km FLOAT64) AS (
  ST_GEOGPOINT(
    57.2958 * (
      lon * (3.14159 / 180) + ATAN2(
        SIN(azimuth * (3.14159 / 180)) * SIN(distance_km / 6378.1) * COS(lat * (3.14159 / 180)),
        COS(distance_km / 6378.1) - SIN(lat * (3.14159 / 180)) * SIN(
          57.2958 * ASIN(
            SIN(lat * (3.14159 / 180)) * COS(distance_km / 6378.1) +
            COS(lat * (3.14159 / 180)) * SIN(distance_km / 6378.1) * COS(azimuth * (3.14159 / 180))
          )
        )
      )
    ),
    57.2958 * ASIN(
      SIN(lat * (3.14159 / 180)) * COS(distance_km / 6378.1) +
      COS(lat * (3.14159 / 180)) * SIN(distance_km / 6378.1) * COS(azimuth * (3.14159 / 180))
    )
  )
);

WITH
  -- Build storm polygons from wind radii (in nautical miles) converted to km
  storm_polygons AS (
    SELECT
      sid,
      ST_MAKEPOLYGON(
        ST_MAKELINE(
          ST_MAKELINE(
            ST_MAKELINE(
              ST_MAKELINE(
                azimuth_to_geog_point(latitude, longitude, 45, usa_r34_ne * 1.15078 * 1.60934),
                azimuth_to_geog_point(latitude, longitude, 135, usa_r34_se * 1.15078 * 1.60934)
              ),
              azimuth_to_geog_point(latitude, longitude, 225, usa_r34_sw * 1.15078 * 1.60934)
            ),
            azimuth_to_geog_point(latitude, longitude, 315, usa_r34_nw * 1.15078 * 1.60934)
          ),
          azimuth_to_geog_point(latitude, longitude, 45, usa_r34_ne * 1.15078 * 1.60934)
        )
      ) AS storm_area
    FROM
      `bigquery-public-data.noaa_hurricanes.hurricanes`
    WHERE
      basin = 'NA'
      AND usa_wind >= 35
      AND name != 'NOT_NAMED'
      AND usa_r34_ne IS NOT NULL
      AND usa_r34_se IS NOT NULL
      AND usa_r34_sw IS NOT NULL
      AND usa_r34_nw IS NOT NULL
  ),
  -- Ports with region number '6585' and located within a U.S. state boundary
  ports_within_us AS (
    SELECT
      p.index_number AS port_id,
      p.port_name,
      p.port_geom
    FROM
      `bigquery-public-data.geo_international_ports.world_port_index` AS p
    JOIN
      `bigquery-public-data.geo_us_boundaries.states` AS s
    ON
      ST_WITHIN(p.port_geom, s.state_geom)
    WHERE
      p.region_number = '6585'
  ),
  -- Count how many storm polygons contain each port
  port_storm_counts AS (
    SELECT
      p.port_id,
      p.port_name,
      COUNT(*) AS storm_count
    FROM
      ports_within_us p
    CROSS JOIN
      storm_polygons sp
    WHERE
      ST_WITHIN(p.port_geom, sp.storm_area)
    GROUP BY
      p.port_id, p.port_name
  )
-- Return the port with the highest count (ties broken arbitrarily)
SELECT
  port_id,
  port_name,
  storm_count
FROM
  port_storm_counts
ORDER BY
  storm_count DESC
LIMIT 1;
```

---

