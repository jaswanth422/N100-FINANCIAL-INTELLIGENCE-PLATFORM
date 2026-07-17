-- 1. Company count
SELECT COUNT(*) AS company_count FROM companies;

-- 2. Companies by broad sector
SELECT broad_sector, COUNT(*) AS companies
FROM sectors GROUP BY broad_sector ORDER BY companies DESC;

-- 3. Latest market capitalisation leaders
SELECT c.company_name, m.year, m.market_cap_crore
FROM market_cap m JOIN companies c ON c.id = m.company_id
WHERE m.year = (SELECT MAX(m2.year) FROM market_cap m2 WHERE m2.company_id = m.company_id)
ORDER BY m.market_cap_crore DESC LIMIT 10;

-- 4. Five-year average return on equity
SELECT c.company_name, ROUND(AVG(r.return_on_equity_pct), 2) AS avg_roe
FROM financial_ratios r JOIN companies c ON c.id = r.company_id
GROUP BY r.company_id ORDER BY avg_roe DESC LIMIT 10;

-- 5. Annual-report coverage
SELECT year, COUNT(*) AS reports FROM documents GROUP BY year ORDER BY year DESC;

-- 6. Revenue trend for one example company
SELECT year, sales, operating_profit, net_profit
FROM financial_statements
WHERE company_id = 'RELIANCE' AND statement_type = 'profit_and_loss'
ORDER BY year;

-- 7. Latest close price for every company
SELECT p.company_id, p.date, p.close_price
FROM stock_prices p
WHERE p.date = (SELECT MAX(p2.date) FROM stock_prices p2 WHERE p2.company_id = p.company_id)
ORDER BY p.company_id;

-- 8. Companies with fewer than five annual P&L observations
SELECT c.id, c.company_name, COUNT(f.year) AS years_available
FROM companies c
LEFT JOIN financial_statements f
  ON f.company_id = c.id AND f.statement_type = 'profit_and_loss' AND f.year IS NOT NULL
GROUP BY c.id HAVING COUNT(f.year) < 5 ORDER BY years_available, c.id;

-- 9. Balance-sheet reconciliation exceptions
SELECT company_id, year, total_assets, total_liabilities,
       ABS(total_assets - total_liabilities) AS difference
FROM financial_statements
WHERE statement_type = 'balance_sheet'
  AND ABS(total_assets - total_liabilities) > MAX(1, ABS(total_assets) * 0.01)
ORDER BY difference DESC;

-- 10. Foreign-key integrity check (expected: no rows)
PRAGMA foreign_key_check;

