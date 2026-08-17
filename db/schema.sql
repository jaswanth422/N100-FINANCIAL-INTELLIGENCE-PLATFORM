PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    company_logo TEXT,
    company_name TEXT NOT NULL,
    chart_link TEXT,
    about_company TEXT,
    website TEXT,
    nse_profile TEXT,
    bse_profile TEXT,
    face_value REAL,
    book_value REAL,
    roce_percentage REAL,
    roe_percentage REAL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    year INTEGER,
    annual_report TEXT
);

CREATE TABLE IF NOT EXISTS analysis (
    id INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    compounded_sales_growth TEXT,
    compounded_profit_growth TEXT,
    stock_price_cagr TEXT,
    roe TEXT
);

CREATE TABLE IF NOT EXISTS pros_and_cons (
    id INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    pros TEXT,
    cons TEXT
);

CREATE TABLE IF NOT EXISTS financial_statements (
    statement_type TEXT NOT NULL,
    id INTEGER NOT NULL,
    company_id TEXT NOT NULL REFERENCES companies(id),
    year INTEGER,
    sales REAL,
    expenses REAL,
    operating_profit REAL,
    opm_percentage REAL,
    other_income REAL,
    interest REAL,
    depreciation REAL,
    profit_before_tax REAL,
    tax_percentage REAL,
    net_profit REAL,
    eps REAL,
    dividend_payout REAL,
    equity_capital REAL,
    reserves REAL,
    borrowings REAL,
    other_liabilities REAL,
    total_liabilities REAL,
    fixed_assets REAL,
    cwip REAL,
    investments REAL,
    other_asset REAL,
    total_assets REAL,
    operating_activity REAL,
    investing_activity REAL,
    financing_activity REAL,
    net_cash_flow REAL,
    PRIMARY KEY (statement_type, id)
);

CREATE TABLE IF NOT EXISTS financial_ratios (
    id INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    year INTEGER,
    net_profit_margin_pct REAL,
    operating_profit_margin_pct REAL,
    return_on_equity_pct REAL,
    return_on_capital_employed_pct REAL,
    return_on_assets_pct REAL,
    debt_to_equity REAL,
    high_leverage_flag INTEGER NOT NULL DEFAULT 0 CHECK (high_leverage_flag IN (0, 1)),
    interest_coverage REAL,
    icr_label TEXT,
    icr_warning_flag INTEGER NOT NULL DEFAULT 0 CHECK (icr_warning_flag IN (0, 1)),
    net_debt REAL,
    asset_turnover REAL,
    revenue_cagr_3yr REAL,
    revenue_cagr_3yr_flag TEXT,
    revenue_cagr_5yr REAL,
    revenue_cagr_5yr_flag TEXT,
    revenue_cagr_10yr REAL,
    revenue_cagr_10yr_flag TEXT,
    pat_cagr_3yr REAL,
    pat_cagr_3yr_flag TEXT,
    pat_cagr_5yr REAL,
    pat_cagr_5yr_flag TEXT,
    pat_cagr_10yr REAL,
    pat_cagr_10yr_flag TEXT,
    eps_cagr_3yr REAL,
    eps_cagr_3yr_flag TEXT,
    eps_cagr_5yr REAL,
    eps_cagr_5yr_flag TEXT,
    eps_cagr_10yr REAL,
    eps_cagr_10yr_flag TEXT,
    free_cash_flow_cr REAL,
    fcf_cagr_5yr REAL,
    fcf_cagr_5yr_flag TEXT,
    cfo_quality_score REAL,
    cfo_quality_label TEXT,
    capex_cr REAL,
    capex_intensity_pct REAL,
    capex_intensity_label TEXT,
    fcf_conversion_rate_pct REAL,
    capital_allocation_pattern TEXT,
    earnings_per_share REAL,
    book_value_per_share REAL,
    dividend_payout_ratio_pct REAL,
    total_debt_cr REAL,
    cash_from_operations_cr REAL,
    composite_quality_score REAL,
    composite_score_coverage_pct REAL
);

CREATE TABLE IF NOT EXISTS stock_prices (
    id INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    date TEXT NOT NULL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    close_price REAL,
    volume INTEGER,
    adjusted_close REAL
);

CREATE TABLE IF NOT EXISTS market_cap (
    id INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    year INTEGER,
    market_cap_crore REAL,
    enterprise_value_crore REAL,
    pe_ratio REAL,
    pb_ratio REAL,
    ev_ebitda REAL,
    dividend_yield_pct REAL
);

CREATE TABLE IF NOT EXISTS sectors (
    id INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL UNIQUE REFERENCES companies(id),
    broad_sector TEXT,
    sub_sector TEXT,
    index_weight_pct REAL,
    market_cap_category TEXT
);

CREATE TABLE IF NOT EXISTS peer_groups (
    id INTEGER PRIMARY KEY,
    peer_group_name TEXT NOT NULL,
    company_id TEXT NOT NULL REFERENCES companies(id),
    is_benchmark INTEGER NOT NULL DEFAULT 0 CHECK (is_benchmark IN (0, 1))
);

CREATE TABLE IF NOT EXISTS peer_percentiles (
    company_id TEXT NOT NULL REFERENCES companies(id),
    peer_group_name TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    percentile_rank REAL,
    year INTEGER NOT NULL,
    PRIMARY KEY (company_id, peer_group_name, metric, year)
);

CREATE INDEX IF NOT EXISTS idx_documents_company_year ON documents(company_id, year);
CREATE INDEX IF NOT EXISTS idx_statements_company_year ON financial_statements(company_id, year);
CREATE INDEX IF NOT EXISTS idx_ratios_company_year ON financial_ratios(company_id, year);
CREATE INDEX IF NOT EXISTS idx_prices_company_date ON stock_prices(company_id, date);
CREATE INDEX IF NOT EXISTS idx_market_cap_company_year ON market_cap(company_id, year);
CREATE INDEX IF NOT EXISTS idx_peer_percentiles_company_year
    ON peer_percentiles(company_id, year);
