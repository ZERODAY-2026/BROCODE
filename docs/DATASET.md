# DataMind — Dataset Specification & Attribution

## Dataset Name: Global World Indicators (2018–2022)

### 1. Origin & Attribution
- **Primary Sources**:
  - World Bank Open Data ([data.worldbank.org](https://data.worldbank.org))
  - Our World in Data ([ourworldindata.org](https://ourworldindata.org))
- **Attribution**: Based on open data published by the World Bank and Our World in Data contributors.
- **Licence**: Creative Commons Attribution 4.0 International ([CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)). Free to share, adapt, and use for commercial and non-commercial purposes with appropriate attribution.

---

## 2. Table Schema: `WORLD_INDICATORS`

| Column Name | Data Type | Nullable | Description | Example Value |
|---|---|---|---|---|
| `COUNTRY` | `VARCHAR(100)` | No | Country standard English name | `'United States'` |
| `COUNTRY_CODE` | `VARCHAR(3)` | No | ISO 3166-1 alpha-3 code | `'USA'` |
| `CONTINENT` | `VARCHAR(50)` | No | Continental region | `'North America'` |
| `YEAR` | `INT` | No | Calendar observation year (2018–2022) | `2022` |
| `GDP_USD` | `NUMBER(18, 2)` | Yes | Gross Domestic Product in current US Dollars | `25462700000000.00` |
| `POPULATION` | `NUMBER(14, 0)` | Yes | Total resident population | `333287557` |
| `LIFE_EXPECTANCY` | `NUMBER(5, 2)` | Yes | Life expectancy at birth in years | `77.43` |
| `CO2_EMISSIONS_PER_CAPITA` | `NUMBER(6, 2)` | Yes | Annual metric tons of CO2 per capita | `14.44` |
| `INTERNET_USERS_PCT` | `NUMBER(5, 2)` | Yes | Percentage of population using internet | `92.20` |

---

## 3. Setup and Loading

### Automated Loading via Python
If `.env` is configured with Snowflake credentials:
```bash
python scripts/load_sample_data.py
```

### Direct Snowflake Worksheet Setup
Open Snowflake Snowsight, open a new SQL Worksheet, and paste the contents of:
`scripts/setup_dataset.sql`

---

## 4. Benchmark Analytical Queries

### Query 1: Top GDP in Latest Available Year
```sql
SELECT COUNTRY, GDP_USD, YEAR
FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS
WHERE YEAR = 2022
ORDER BY GDP_USD DESC
LIMIT 5;
```

### Query 2: Continental Life Expectancy
```sql
SELECT CONTINENT, ROUND(AVG(LIFE_EXPECTANCY), 2) AS AVG_LIFE_EXPECTANCY
FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS
WHERE YEAR = 2022
GROUP BY CONTINENT
ORDER BY AVG_LIFE_EXPECTANCY DESC;
```

### Query 3: Population Trajectory Over Time
```sql
SELECT YEAR, POPULATION
FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS
WHERE COUNTRY = 'India' AND YEAR BETWEEN 2018 AND 2022
ORDER BY YEAR ASC;
```
