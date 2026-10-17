BEGIN TRANSACTION;
CREATE TABLE capital_structure_observations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	observation_date VARCHAR(20) NOT NULL, 
	total_shares DOUBLE, 
	tradable_shares DOUBLE, 
	restricted_shares DOUBLE, 
	a_shares DOUBLE, 
	b_shares DOUBLE, 
	h_shares DOUBLE, 
	treasury_shares DOUBLE, 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	source VARCHAR(100) NOT NULL, 
	raw_text TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_capital_structure_identity UNIQUE (company_id, observation_date, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE companies (
	id INTEGER NOT NULL, 
	security_code VARCHAR(12) NOT NULL, 
	exchange VARCHAR(8) NOT NULL, 
	board VARCHAR(40), 
	legal_name_cn VARCHAR(300), 
	short_name_cn VARCHAR(100), 
	legal_name_en VARCHAR(300), 
	status VARCHAR(50), 
	listing_date VARCHAR(20), 
	org_id VARCHAR(100), 
	source_last_seen VARCHAR(100), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_company_security_exchange UNIQUE (security_code, exchange)
);
INSERT INTO "companies" VALUES(1,'600519','SSE',NULL,'贵州茅台酒股份有限公司','贵州茅台',NULL,NULL,NULL,NULL,NULL,'2025-01-01 00:00:00','2025-01-01 00:00:00');
CREATE TABLE disclosures (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	announcement_id VARCHAR(100) NOT NULL, 
	announcement_date VARCHAR(20), 
	title_cn VARCHAR(1000), 
	announcement_type_cn VARCHAR(200), 
	kind VARCHAR(100), 
	sec_code VARCHAR(20), 
	sec_name VARCHAR(100), 
	adjunct_url VARCHAR(2000), 
	document_url VARCHAR(2000), 
	local_path VARCHAR(2000), 
	content_type VARCHAR(200), 
	file_size INTEGER, 
	sha256 VARCHAR(64), 
	source VARCHAR(100), 
	retrieved_at DATETIME NOT NULL, 
	raw_json TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_disclosure_company_announcement UNIQUE (company_id, announcement_id), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE financial_facts (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	reporting_period VARCHAR(20), 
	period_type VARCHAR(30), 
	statement_type VARCHAR(50), 
	metric VARCHAR(150) NOT NULL, 
	metric_cn VARCHAR(300), 
	value DOUBLE, 
	raw_value VARCHAR(500), 
	unit VARCHAR(50), 
	currency VARCHAR(10), 
	consolidation_scope VARCHAR(50), 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	source_xbrl_tag VARCHAR(500), 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50) NOT NULL, 
	retrieved_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_financial_fact_identity UNIQUE (company_id, disclosure_id, reporting_period, period_type, metric, consolidation_scope, extraction_method), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE market_bars (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	trade_date VARCHAR(20) NOT NULL, 
	open DOUBLE, 
	high DOUBLE, 
	low DOUBLE, 
	close DOUBLE, 
	prev_close DOUBLE, 
	volume DOUBLE, 
	amount DOUBLE, 
	pct_change DOUBLE, 
	change DOUBLE, 
	turnover_rate DOUBLE, 
	adjustment VARCHAR(20) NOT NULL, 
	status VARCHAR(50), 
	source VARCHAR(100) NOT NULL, 
	raw_json TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_market_bar_identity UNIQUE (company_id, trade_date, adjustment, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE market_snapshots (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	trade_date VARCHAR(20) NOT NULL, 
	close DOUBLE, 
	market_cap DOUBLE, 
	float_market_cap DOUBLE, 
	shares_outstanding DOUBLE, 
	float_shares DOUBLE, 
	pe DOUBLE, 
	pb DOUBLE, 
	source VARCHAR(100) NOT NULL, 
	raw_json TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_market_snapshot_identity UNIQUE (company_id, trade_date, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE ownership_observations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	observation_date VARCHAR(20) NOT NULL, 
	shareholder_name VARCHAR(500), 
	shareholder_type VARCHAR(100), 
	relationship VARCHAR(200), 
	shares DOUBLE, 
	ownership_pct DOUBLE, 
	tradable_shares DOUBLE, 
	pledged_shares DOUBLE, 
	restricted_shares DOUBLE, 
	change_shares DOUBLE, 
	change_pct DOUBLE, 
	is_controlling_shareholder BOOLEAN, 
	is_actual_controller BOOLEAN, 
	rank INTEGER, 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	source VARCHAR(100) NOT NULL, 
	raw_text TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ownership_observation_identity UNIQUE (company_id, observation_date, shareholder_name, source, rank), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE raw_records (
	id INTEGER NOT NULL, 
	source_id INTEGER NOT NULL, 
	company_id INTEGER, 
	retrieved_at DATETIME NOT NULL, 
	url VARCHAR(2000), 
	content_type VARCHAR(100), 
	sha256 VARCHAR(64), 
	payload_path VARCHAR(1000), 
	metadata_json TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(source_id) REFERENCES sources (id), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE securities (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	security_code VARCHAR(12) NOT NULL, 
	security_type VARCHAR(50) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_security_company_code UNIQUE (company_id, security_code), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE sources (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	base_url VARCHAR(1000), 
	access_type VARCHAR(50) NOT NULL, 
	notes TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE INDEX ix_companies_exchange ON companies (exchange);
CREATE INDEX ix_companies_status ON companies (status);
CREATE INDEX ix_companies_board ON companies (board);
CREATE INDEX ix_companies_org_id ON companies (org_id);
CREATE INDEX ix_companies_security_code ON companies (security_code);
CREATE INDEX ix_company_name_cn ON companies (legal_name_cn);
CREATE INDEX ix_securities_security_code ON securities (security_code);
CREATE INDEX ix_securities_company_id ON securities (company_id);
CREATE INDEX ix_disclosures_company_id ON disclosures (company_id);
CREATE INDEX ix_disclosures_announcement_date ON disclosures (announcement_date);
CREATE INDEX ix_disclosures_kind ON disclosures (kind);
CREATE INDEX ix_disclosures_sec_code ON disclosures (sec_code);
CREATE INDEX ix_disclosures_announcement_id ON disclosures (announcement_id);
CREATE INDEX ix_disclosures_sha256 ON disclosures (sha256);
CREATE INDEX ix_disclosure_company_date ON disclosures (company_id, announcement_date);
CREATE INDEX ix_market_bars_trade_date ON market_bars (trade_date);
CREATE INDEX ix_market_bar_company_date ON market_bars (company_id, trade_date);
CREATE INDEX ix_market_bars_adjustment ON market_bars (adjustment);
CREATE INDEX ix_market_bars_source ON market_bars (source);
CREATE INDEX ix_market_bars_company_id ON market_bars (company_id);
CREATE INDEX ix_market_snapshots_source ON market_snapshots (source);
CREATE INDEX ix_market_snapshots_trade_date ON market_snapshots (trade_date);
CREATE INDEX ix_market_snapshots_company_id ON market_snapshots (company_id);
CREATE INDEX ix_raw_records_company_id ON raw_records (company_id);
CREATE INDEX ix_raw_records_source_id ON raw_records (source_id);
CREATE INDEX ix_raw_records_sha256 ON raw_records (sha256);
CREATE INDEX ix_financial_facts_statement_type ON financial_facts (statement_type);
CREATE INDEX ix_financial_fact_company_metric_period ON financial_facts (company_id, metric, reporting_period);
CREATE INDEX ix_financial_facts_company_id ON financial_facts (company_id);
CREATE INDEX ix_financial_facts_reporting_period ON financial_facts (reporting_period);
CREATE INDEX ix_financial_facts_metric ON financial_facts (metric);
CREATE INDEX ix_financial_facts_disclosure_id ON financial_facts (disclosure_id);
CREATE INDEX ix_financial_facts_period_type ON financial_facts (period_type);
CREATE INDEX ix_ownership_observations_source ON ownership_observations (source);
CREATE INDEX ix_ownership_observations_shareholder_name ON ownership_observations (shareholder_name);
CREATE INDEX ix_ownership_company_date ON ownership_observations (company_id, observation_date);
CREATE INDEX ix_ownership_observations_disclosure_id ON ownership_observations (disclosure_id);
CREATE INDEX ix_ownership_observations_observation_date ON ownership_observations (observation_date);
CREATE INDEX ix_ownership_observations_company_id ON ownership_observations (company_id);
CREATE INDEX ix_capital_structure_observations_disclosure_id ON capital_structure_observations (disclosure_id);
CREATE INDEX ix_capital_structure_observations_company_id ON capital_structure_observations (company_id);
CREATE INDEX ix_capital_structure_observations_observation_date ON capital_structure_observations (observation_date);
CREATE INDEX ix_capital_structure_observations_source ON capital_structure_observations (source);
COMMIT;