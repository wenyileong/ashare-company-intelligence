BEGIN TRANSACTION;
CREATE TABLE adjustment_factors (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	ex_date VARCHAR(20) NOT NULL, 
	prev_close DOUBLE, 
	cash_per_share DOUBLE, 
	share_ratio DOUBLE, 
	rights_ratio DOUBLE, 
	rights_price DOUBLE, 
	reference_price DOUBLE, 
	factor DOUBLE, 
	cumulative DOUBLE, 
	action_ids TEXT, 
	source VARCHAR(40) NOT NULL, 
	computed_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_adjustment_factor UNIQUE (company_id, ex_date, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE capital_reconciliations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	capital_source VARCHAR(100) NOT NULL, 
	t0_date VARCHAR(20) NOT NULL, 
	t1_date VARCHAR(20) NOT NULL, 
	t0_total_shares DOUBLE, 
	t1_total_shares DOUBLE, 
	expected_t1_total_shares DOUBLE, 
	residual DOUBLE, 
	tolerance DOUBLE, 
	status VARCHAR(40) NOT NULL, 
	t0_tradable_shares DOUBLE, 
	t1_tradable_shares DOUBLE, 
	expected_t1_tradable_shares DOUBLE, 
	tradable_residual DOUBLE, 
	tradable_status VARCHAR(40), 
	action_ids TEXT, 
	notes TEXT, 
	run_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_capital_reconciliation_window UNIQUE (company_id, capital_source, t0_date, t1_date), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
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
	validation_status VARCHAR(50), 
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
CREATE TABLE control_edges (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	observation_date VARCHAR(20) NOT NULL, 
	parent_name VARCHAR(300) NOT NULL, 
	child_name VARCHAR(300) NOT NULL, 
	parent_entity_id INTEGER, 
	child_entity_id INTEGER, 
	pct DOUBLE, 
	basis VARCHAR(200), 
	source VARCHAR(100) NOT NULL, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_control_edge UNIQUE (company_id, observation_date, parent_name, child_name, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE control_observations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	observation_date VARCHAR(20) NOT NULL, 
	controlling_shareholder VARCHAR(300), 
	controlling_nature VARCHAR(100), 
	actual_controller VARCHAR(300), 
	controller_nature VARCHAR(100), 
	no_controlling_shareholder BOOLEAN, 
	no_actual_controller BOOLEAN, 
	ownership_type VARCHAR(20), 
	ownership_basis VARCHAR(300), 
	source VARCHAR(100) NOT NULL, 
	source_page INTEGER, 
	raw_value TEXT, 
	extraction_method VARCHAR(50), 
	confidence DOUBLE, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_control_observation UNIQUE (company_id, observation_date, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE corporate_actions (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	action_id VARCHAR(64) NOT NULL, 
	action_group VARCHAR(64), 
	action_type VARCHAR(50) NOT NULL, 
	status VARCHAR(40), 
	announcement_id VARCHAR(100), 
	announcement_date VARCHAR(20), 
	record_date VARCHAR(20), 
	ex_date VARCHAR(20), 
	payment_date VARCHAR(20), 
	listing_date VARCHAR(20), 
	effective_date VARCHAR(20), 
	fiscal_period VARCHAR(20), 
	base_share_count DOUBLE, 
	old_share_count DOUBLE, 
	new_share_count DOUBLE, 
	share_delta DOUBLE, 
	shares_affected DOUBLE, 
	ratio DOUBLE, 
	cash_amount DOUBLE, 
	total_cash_amount DOUBLE, 
	subscription_price DOUBLE, 
	issue_price DOUBLE, 
	currency VARCHAR(8), 
	tax_basis VARCHAR(20), 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	raw_value TEXT, 
	normalised_value TEXT, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	source VARCHAR(100) NOT NULL, 
	retrieved_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_corporate_action_identity UNIQUE (company_id, action_id), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
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
	text_layer VARCHAR(12), 
	source VARCHAR(100), 
	retrieved_at DATETIME NOT NULL, 
	raw_json TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_disclosure_company_announcement UNIQUE (company_id, announcement_id), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE document_pages (
	id INTEGER NOT NULL, 
	disclosure_id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	page INTEGER NOT NULL, 
	text TEXT, 
	document_sha256 VARCHAR(64), 
	indexed_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_page UNIQUE (disclosure_id, page), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE entities (
	id INTEGER NOT NULL, 
	name VARCHAR(300) NOT NULL, 
	normalised_name VARCHAR(300) NOT NULL, 
	credit_code VARCHAR(18), 
	entity_type VARCHAR(30), 
	listed_company_id INTEGER, 
	jurisdiction VARCHAR(20), 
	sources TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(listed_company_id) REFERENCES companies (id)
);
CREATE TABLE entity_aliases (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	alias VARCHAR(300) NOT NULL, 
	normalised_alias VARCHAR(300) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_entity_alias UNIQUE (entity_id, normalised_alias), 
	FOREIGN KEY(entity_id) REFERENCES entities (id)
);
CREATE TABLE esg_observations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	reporting_period VARCHAR(20) NOT NULL, 
	pillar VARCHAR(4) NOT NULL, 
	item VARCHAR(60) NOT NULL, 
	value DOUBLE, 
	value_text VARCHAR(500), 
	unit VARCHAR(30), 
	source VARCHAR(100) NOT NULL, 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	raw_value TEXT, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_esg_observation UNIQUE (company_id, reporting_period, item, source, disclosure_id), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE esg_ratings (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	provider VARCHAR(60) NOT NULL, 
	rating_date VARCHAR(20) NOT NULL, 
	rating VARCHAR(20), 
	score DOUBLE, 
	pillar_e DOUBLE, 
	pillar_s DOUBLE, 
	pillar_g DOUBLE, 
	source VARCHAR(100) NOT NULL, 
	source_document VARCHAR(2000), 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_esg_rating UNIQUE (company_id, provider, rating_date, source), 
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
	source_label VARCHAR(300), 
	source_context VARCHAR(300), 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50) NOT NULL, 
	extraction_note TEXT, 
	retrieved_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_financial_fact_identity UNIQUE (company_id, disclosure_id, reporting_period, period_type, metric, consolidation_scope, extraction_method), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE high_water_marks (
	id INTEGER NOT NULL, 
	source VARCHAR(40) NOT NULL, 
	scope VARCHAR(20) NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	value VARCHAR(20) NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_high_water_mark UNIQUE (source, scope, kind)
);
CREATE TABLE human_capital_observations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	reporting_period VARCHAR(20) NOT NULL, 
	category VARCHAR(20) NOT NULL, 
	item VARCHAR(60) NOT NULL, 
	value DOUBLE, 
	unit VARCHAR(20), 
	label_cn VARCHAR(200), 
	source VARCHAR(100) NOT NULL, 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	raw_value TEXT, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	extraction_note TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_human_capital UNIQUE (company_id, reporting_period, item, source, disclosure_id), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE index_constituents (
	id INTEGER NOT NULL, 
	index_code VARCHAR(20) NOT NULL, 
	index_name VARCHAR(100), 
	security_code VARCHAR(12) NOT NULL, 
	company_id INTEGER, 
	valid_from VARCHAR(20) NOT NULL, 
	valid_to VARCHAR(20), 
	weight DOUBLE, 
	source VARCHAR(100) NOT NULL, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_index_constituent UNIQUE (index_code, security_code, valid_from, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE industry_classifications (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	scheme VARCHAR(40) NOT NULL, 
	effective_date VARCHAR(20) NOT NULL, 
	level1_code VARCHAR(20), 
	level1_name VARCHAR(100), 
	level2_code VARCHAR(20), 
	level2_name VARCHAR(100), 
	level3_code VARCHAR(20), 
	level3_name VARCHAR(100), 
	level4_code VARCHAR(20), 
	level4_name VARCHAR(100), 
	source VARCHAR(100) NOT NULL, 
	source_document VARCHAR(2000), 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	raw_text TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_industry_classification UNIQUE (company_id, scheme, effective_date, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE job_items (
	id INTEGER NOT NULL, 
	job_id INTEGER NOT NULL, 
	item_key VARCHAR(60) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	attempts INTEGER NOT NULL, 
	last_error TEXT, 
	result TEXT, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_job_item UNIQUE (job_id, item_key), 
	FOREIGN KEY(job_id) REFERENCES jobs (id)
);
CREATE TABLE jobs (
	id INTEGER NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	params TEXT, 
	status VARCHAR(12) NOT NULL, 
	total INTEGER NOT NULL, 
	done INTEGER NOT NULL, 
	failed INTEGER NOT NULL, 
	cancel_requested INTEGER NOT NULL, 
	last_error TEXT, 
	created_at DATETIME NOT NULL, 
	started_at DATETIME, 
	finished_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE listing_events (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	event_type VARCHAR(30) NOT NULL, 
	event_date VARCHAR(20), 
	date_basis VARCHAR(30), 
	old_value VARCHAR(300), 
	new_value VARCHAR(300), 
	source VARCHAR(100) NOT NULL, 
	disclosure_id INTEGER, 
	raw_value TEXT, 
	extraction_method VARCHAR(50), 
	confidence DOUBLE, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_listing_event UNIQUE (company_id, event_type, event_date, new_value, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE management_events (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	event_id VARCHAR(64) NOT NULL, 
	event_type VARCHAR(40) NOT NULL, 
	person_name VARCHAR(100), 
	role VARCHAR(40), 
	role_cn VARCHAR(200), 
	event_date VARCHAR(20), 
	effective_date VARCHAR(20), 
	announcement_date VARCHAR(20), 
	reason VARCHAR(60), 
	reason_text VARCHAR(500), 
	remains_with_company BOOLEAN, 
	title_cn VARCHAR(1000), 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	raw_value TEXT, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	source VARCHAR(100) NOT NULL, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id), 
	UNIQUE (event_id)
);
CREATE TABLE management_observations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	observation_date VARCHAR(20) NOT NULL, 
	person_name VARCHAR(100) NOT NULL, 
	role VARCHAR(40) NOT NULL, 
	role_cn VARCHAR(200), 
	gender VARCHAR(4), 
	age INTEGER, 
	tenure_start VARCHAR(20), 
	tenure_end VARCHAR(20), 
	status VARCHAR(20), 
	shares_start DOUBLE, 
	shares_end DOUBLE, 
	remuneration DOUBLE, 
	paid_by_related_party BOOLEAN, 
	source VARCHAR(100) NOT NULL, 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	raw_value TEXT, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	extraction_note TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_management_observation UNIQUE (company_id, observation_date, person_name, role, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE manual_corrections (
	id INTEGER NOT NULL, 
	table_name VARCHAR(60) NOT NULL, 
	row_id INTEGER, 
	natural_key TEXT NOT NULL, 
	field VARCHAR(60) NOT NULL, 
	action VARCHAR(10) NOT NULL, 
	original_value VARCHAR(200), 
	corrected_value VARCHAR(200), 
	reason TEXT, 
	reviewer VARCHAR(100), 
	source VARCHAR(30) NOT NULL, 
	review_item_id INTEGER, 
	superseded INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
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
	volume_unit VARCHAR(30), 
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
	ps DOUBLE, 
	ev DOUBLE, 
	ev_to_ebit DOUBLE, 
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
	validation_status VARCHAR(50), 
	entity_id INTEGER, 
	shareholder_nature VARCHAR(40), 
	extraction_note TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ownership_observation_identity UNIQUE (company_id, observation_date, shareholder_name, source, rank), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE parser_calibration (
	id INTEGER NOT NULL, 
	parser VARCHAR(60) NOT NULL, 
	field VARCHAR(60) NOT NULL, 
	parser_version VARCHAR(20), 
	expected INTEGER NOT NULL, 
	predicted INTEGER NOT NULL, 
	correct INTEGER NOT NULL, 
	wrong INTEGER NOT NULL, 
	missed INTEGER NOT NULL, 
	spurious INTEGER NOT NULL, 
	precision DOUBLE, 
	precision_lower DOUBLE, 
	recall DOUBLE, 
	corpus_name VARCHAR(200), 
	corpus_fingerprint VARCHAR(64), 
	synthetic INTEGER NOT NULL, 
	evaluated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_parser_calibration UNIQUE (parser, field, synthetic)
);
CREATE TABLE person_roles (
	id INTEGER NOT NULL, 
	person_id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	role VARCHAR(40), 
	first_date VARCHAR(20), 
	last_date VARCHAR(20), 
	tenure_start VARCHAR(20), 
	tenure_end VARCHAR(20), 
	observation_ids TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_person_role UNIQUE (person_id, company_id, role), 
	FOREIGN KEY(person_id) REFERENCES persons (id), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE persons (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	gender VARCHAR(4), 
	birth_year INTEGER, 
	resolution VARCHAR(200), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE pledge_events (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	event_type VARCHAR(20) NOT NULL, 
	announcement_date VARCHAR(20), 
	pledgor VARCHAR(300), 
	pledgee VARCHAR(300), 
	is_controlling_shareholder BOOLEAN, 
	shares DOUBLE, 
	pct_of_holding DOUBLE, 
	pct_of_total DOUBLE, 
	start_date VARCHAR(20), 
	end_date VARCHAR(20), 
	cumulative_pledged DOUBLE, 
	raw_value TEXT, 
	source VARCHAR(100) NOT NULL, 
	extraction_method VARCHAR(50), 
	confidence DOUBLE, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_pledge_event UNIQUE (company_id, disclosure_id, event_type, pledgor, shares, source), 
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
CREATE TABLE regulatory_events (
	id INTEGER NOT NULL, 
	company_id INTEGER, 
	disclosure_id INTEGER, 
	event_id VARCHAR(64) NOT NULL, 
	case_key VARCHAR(64), 
	link_basis VARCHAR(200), 
	event_type VARCHAR(50) NOT NULL, 
	event_subtype VARCHAR(80), 
	legal_classification VARCHAR(60) NOT NULL, 
	status VARCHAR(40), 
	authority VARCHAR(40), 
	authority_name VARCHAR(200), 
	affected_security VARCHAR(12), 
	announcement_id VARCHAR(100), 
	announcement_date VARCHAR(20), 
	event_date VARCHAR(20), 
	document_number VARCHAR(200), 
	case_number VARCHAR(200), 
	company_role VARCHAR(30), 
	amount_in_dispute DOUBLE, 
	fine_amount_total DOUBLE, 
	fine_amount_company DOUBLE, 
	confiscation_amount DOUBLE, 
	violation_categories TEXT, 
	cited_provisions TEXT, 
	sanctions TEXT, 
	title_cn VARCHAR(1000), 
	source_document VARCHAR(2000), 
	primary_source_url VARCHAR(2000), 
	document_hash VARCHAR(64), 
	source_page INTEGER, 
	raw_value TEXT, 
	normalised_value TEXT, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	source VARCHAR(100) NOT NULL, 
	retrieved_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_regulatory_event_identity UNIQUE (event_id), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE research_queries (
	id INTEGER NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	name VARCHAR(200), 
	query_text TEXT NOT NULL, 
	query_sha256 VARCHAR(64) NOT NULL, 
	parameters TEXT, 
	database_sha256 VARCHAR(64), 
	row_count INTEGER, 
	output_path VARCHAR(2000), 
	output_sha256 VARCHAR(64), 
	software_version VARCHAR(20), 
	run_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE review_items (
	id INTEGER NOT NULL, 
	item_key VARCHAR(40) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	rule VARCHAR(80), 
	severity VARCHAR(10), 
	company_id INTEGER, 
	table_name VARCHAR(60) NOT NULL, 
	row_id INTEGER, 
	natural_key TEXT, 
	field VARCHAR(60), 
	value VARCHAR(200), 
	confidence DOUBLE, 
	materiality DOUBLE, 
	status VARCHAR(12) NOT NULL, 
	details TEXT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (item_key), 
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
CREATE TABLE security_history (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	security_code VARCHAR(12) NOT NULL, 
	exchange VARCHAR(8), 
	board VARCHAR(40), 
	short_name_cn VARCHAR(100), 
	legal_name_cn VARCHAR(300), 
	listing_status VARCHAR(20) NOT NULL, 
	risk_warning VARCHAR(10), 
	valid_from VARCHAR(20), 
	valid_to VARCHAR(20), 
	source VARCHAR(100) NOT NULL, 
	basis VARCHAR(300), 
	recorded_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE TABLE segment_observations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	reporting_period VARCHAR(20) NOT NULL, 
	dimension VARCHAR(30) NOT NULL, 
	segment_name VARCHAR(200) NOT NULL, 
	region_class VARCHAR(20), 
	revenue DOUBLE, 
	revenue_share DOUBLE, 
	revenue_prior DOUBLE, 
	revenue_yoy DOUBLE, 
	cost DOUBLE, 
	gross_margin DOUBLE, 
	assets DOUBLE, 
	is_total BOOLEAN, 
	unit VARCHAR(20), 
	source VARCHAR(100) NOT NULL, 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	raw_value TEXT, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	extraction_note TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_segment_observation UNIQUE (company_id, reporting_period, dimension, segment_name, source, disclosure_id), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
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
CREATE TABLE subsidiary_observations (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	observation_date VARCHAR(20) NOT NULL, 
	entity_name VARCHAR(300) NOT NULL, 
	relationship VARCHAR(30), 
	principal_place VARCHAR(200), 
	registered_place VARCHAR(200), 
	jurisdiction_class VARCHAR(20), 
	business_nature VARCHAR(500), 
	direct_pct DOUBLE, 
	indirect_pct DOUBLE, 
	total_pct DOUBLE, 
	acquisition_method VARCHAR(60), 
	consolidated BOOLEAN, 
	registered_capital DOUBLE, 
	total_assets DOUBLE, 
	net_assets DOUBLE, 
	revenue DOUBLE, 
	net_profit DOUBLE, 
	source VARCHAR(100) NOT NULL, 
	source_document VARCHAR(2000), 
	source_page INTEGER, 
	raw_value TEXT, 
	extraction_method VARCHAR(50) NOT NULL, 
	confidence DOUBLE, 
	validation_status VARCHAR(50), 
	entity_id INTEGER, 
	extraction_note TEXT, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_subsidiary_observation UNIQUE (company_id, observation_date, entity_name, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE trading_calendar (
	id INTEGER NOT NULL, 
	exchange VARCHAR(8) NOT NULL, 
	trade_date VARCHAR(20) NOT NULL, 
	is_open INTEGER NOT NULL, 
	source VARCHAR(100) NOT NULL, 
	securities_trading INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_trading_day UNIQUE (exchange, trade_date)
);
CREATE TABLE transaction_events (
	id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	disclosure_id INTEGER, 
	event_type VARCHAR(30) NOT NULL, 
	stage VARCHAR(30), 
	case_key VARCHAR(40), 
	announcement_date VARCHAR(20), 
	event_date VARCHAR(20), 
	counterparty VARCHAR(300), 
	subject VARCHAR(300), 
	amount DOUBLE, 
	cumulative_amount DOUBLE, 
	nature VARCHAR(40), 
	approval_body VARCHAR(40), 
	related_party BOOLEAN, 
	overdue BOOLEAN, 
	overdue_amount DOUBLE, 
	proposal VARCHAR(300), 
	votes_for_pct DOUBLE, 
	votes_against_pct DOUBLE, 
	votes_abstain_pct DOUBLE, 
	resolution_passed BOOLEAN, 
	title_cn VARCHAR(500), 
	source VARCHAR(100) NOT NULL, 
	extraction_method VARCHAR(50), 
	confidence DOUBLE, 
	retrieved_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_transaction_event UNIQUE (company_id, disclosure_id, event_type, proposal, source), 
	FOREIGN KEY(company_id) REFERENCES companies (id), 
	FOREIGN KEY(disclosure_id) REFERENCES disclosures (id)
);
CREATE TABLE validation_flags (
	id INTEGER NOT NULL, 
	rule VARCHAR(80) NOT NULL, 
	severity VARCHAR(10) NOT NULL, 
	layer VARCHAR(40) NOT NULL, 
	company_id INTEGER, 
	table_name VARCHAR(60) NOT NULL, 
	row_ids VARCHAR(500) NOT NULL, 
	details TEXT, 
	run_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_validation_flag UNIQUE (rule, table_name, row_ids), 
	FOREIGN KEY(company_id) REFERENCES companies (id)
);
CREATE INDEX ix_companies_org_id ON companies (org_id);
CREATE INDEX ix_companies_security_code ON companies (security_code);
CREATE INDEX ix_company_name_cn ON companies (legal_name_cn);
CREATE INDEX ix_companies_board ON companies (board);
CREATE INDEX ix_companies_exchange ON companies (exchange);
CREATE INDEX ix_companies_status ON companies (status);
CREATE INDEX ix_research_queries_query_sha256 ON research_queries (query_sha256);
CREATE INDEX ix_parser_calibration_parser ON parser_calibration (parser);
CREATE INDEX ix_manual_corrections_table_name ON manual_corrections (table_name);
CREATE INDEX ix_manual_corrections_superseded ON manual_corrections (superseded);
CREATE INDEX ix_trading_calendar_exchange ON trading_calendar (exchange);
CREATE INDEX ix_trading_calendar_trade_date ON trading_calendar (trade_date);
CREATE INDEX ix_persons_name ON persons (name);
CREATE INDEX ix_jobs_status ON jobs (status);
CREATE INDEX ix_jobs_kind ON jobs (kind);
CREATE INDEX ix_securities_security_code ON securities (security_code);
CREATE INDEX ix_securities_company_id ON securities (company_id);
CREATE INDEX ix_disclosures_company_id ON disclosures (company_id);
CREATE INDEX ix_disclosures_announcement_id ON disclosures (announcement_id);
CREATE INDEX ix_disclosures_sec_code ON disclosures (sec_code);
CREATE INDEX ix_disclosures_announcement_date ON disclosures (announcement_date);
CREATE INDEX ix_disclosures_kind ON disclosures (kind);
CREATE INDEX ix_disclosures_sha256 ON disclosures (sha256);
CREATE INDEX ix_disclosure_company_date ON disclosures (company_id, announcement_date);
CREATE INDEX ix_market_bars_source ON market_bars (source);
CREATE INDEX ix_market_bars_trade_date ON market_bars (trade_date);
CREATE INDEX ix_market_bars_adjustment ON market_bars (adjustment);
CREATE INDEX ix_market_bar_company_date ON market_bars (company_id, trade_date);
CREATE INDEX ix_market_bars_company_id ON market_bars (company_id);
CREATE INDEX ix_market_snapshots_trade_date ON market_snapshots (trade_date);
CREATE INDEX ix_market_snapshots_source ON market_snapshots (source);
CREATE INDEX ix_market_snapshots_company_id ON market_snapshots (company_id);
CREATE INDEX ix_capital_reconciliations_company_id ON capital_reconciliations (company_id);
CREATE INDEX ix_capital_reconciliations_status ON capital_reconciliations (status);
CREATE INDEX ix_validation_flags_severity ON validation_flags (severity);
CREATE INDEX ix_validation_flags_layer ON validation_flags (layer);
CREATE INDEX ix_validation_flags_rule ON validation_flags (rule);
CREATE INDEX ix_validation_flags_company_id ON validation_flags (company_id);
CREATE INDEX ix_industry_classifications_scheme ON industry_classifications (scheme);
CREATE INDEX ix_industry_classifications_source ON industry_classifications (source);
CREATE INDEX ix_industry_classifications_effective_date ON industry_classifications (effective_date);
CREATE INDEX ix_industry_classifications_company_id ON industry_classifications (company_id);
CREATE INDEX ix_industry_classifications_level2_code ON industry_classifications (level2_code);
CREATE INDEX ix_industry_classifications_level1_code ON industry_classifications (level1_code);
CREATE INDEX ix_esg_ratings_company_id ON esg_ratings (company_id);
CREATE INDEX ix_esg_ratings_rating_date ON esg_ratings (rating_date);
CREATE INDEX ix_esg_ratings_provider ON esg_ratings (provider);
CREATE INDEX ix_review_items_materiality ON review_items (materiality);
CREATE INDEX ix_review_items_status ON review_items (status);
CREATE INDEX ix_review_items_kind ON review_items (kind);
CREATE INDEX ix_review_items_company_id ON review_items (company_id);
CREATE INDEX ix_security_history_valid_to ON security_history (valid_to);
CREATE INDEX ix_security_history_listing_status ON security_history (listing_status);
CREATE INDEX ix_security_history_valid_from ON security_history (valid_from);
CREATE INDEX ix_security_history_company_id ON security_history (company_id);
CREATE INDEX ix_security_history_security_code ON security_history (security_code);
CREATE INDEX ix_index_constituents_company_id ON index_constituents (company_id);
CREATE INDEX ix_index_constituents_valid_to ON index_constituents (valid_to);
CREATE INDEX ix_index_constituents_valid_from ON index_constituents (valid_from);
CREATE INDEX ix_index_constituents_security_code ON index_constituents (security_code);
CREATE INDEX ix_index_constituents_index_code ON index_constituents (index_code);
CREATE INDEX ix_adjustment_factors_company_id ON adjustment_factors (company_id);
CREATE INDEX ix_adjustment_factors_ex_date ON adjustment_factors (ex_date);
CREATE INDEX ix_control_edges_child_entity_id ON control_edges (child_entity_id);
CREATE INDEX ix_control_edges_parent_entity_id ON control_edges (parent_entity_id);
CREATE INDEX ix_control_edges_observation_date ON control_edges (observation_date);
CREATE INDEX ix_control_edges_company_id ON control_edges (company_id);
CREATE INDEX ix_entities_normalised_name ON entities (normalised_name);
CREATE INDEX ix_entities_listed_company_id ON entities (listed_company_id);
CREATE INDEX ix_entities_credit_code ON entities (credit_code);
CREATE INDEX ix_person_roles_company_id ON person_roles (company_id);
CREATE INDEX ix_person_roles_person_id ON person_roles (person_id);
CREATE INDEX ix_job_items_job_id ON job_items (job_id);
CREATE INDEX ix_job_items_status ON job_items (status);
CREATE INDEX ix_raw_records_sha256 ON raw_records (sha256);
CREATE INDEX ix_raw_records_source_id ON raw_records (source_id);
CREATE INDEX ix_raw_records_company_id ON raw_records (company_id);
CREATE INDEX ix_financial_facts_reporting_period ON financial_facts (reporting_period);
CREATE INDEX ix_financial_facts_metric ON financial_facts (metric);
CREATE INDEX ix_financial_facts_disclosure_id ON financial_facts (disclosure_id);
CREATE INDEX ix_financial_facts_statement_type ON financial_facts (statement_type);
CREATE INDEX ix_financial_facts_period_type ON financial_facts (period_type);
CREATE INDEX ix_financial_fact_company_metric_period ON financial_facts (company_id, metric, reporting_period);
CREATE INDEX ix_financial_facts_company_id ON financial_facts (company_id);
CREATE INDEX ix_ownership_observations_source ON ownership_observations (source);
CREATE INDEX ix_ownership_observations_shareholder_name ON ownership_observations (shareholder_name);
CREATE INDEX ix_ownership_company_date ON ownership_observations (company_id, observation_date);
CREATE INDEX ix_ownership_observations_disclosure_id ON ownership_observations (disclosure_id);
CREATE INDEX ix_ownership_observations_observation_date ON ownership_observations (observation_date);
CREATE INDEX ix_ownership_observations_company_id ON ownership_observations (company_id);
CREATE INDEX ix_ownership_observations_entity_id ON ownership_observations (entity_id);
CREATE INDEX ix_capital_structure_observations_observation_date ON capital_structure_observations (observation_date);
CREATE INDEX ix_capital_structure_observations_company_id ON capital_structure_observations (company_id);
CREATE INDEX ix_capital_structure_observations_source ON capital_structure_observations (source);
CREATE INDEX ix_capital_structure_observations_disclosure_id ON capital_structure_observations (disclosure_id);
CREATE INDEX ix_corporate_actions_action_id ON corporate_actions (action_id);
CREATE INDEX ix_corporate_actions_status ON corporate_actions (status);
CREATE INDEX ix_corporate_actions_disclosure_id ON corporate_actions (disclosure_id);
CREATE INDEX ix_corporate_actions_action_type ON corporate_actions (action_type);
CREATE INDEX ix_corporate_action_company_type_date ON corporate_actions (company_id, action_type, effective_date);
CREATE INDEX ix_corporate_actions_effective_date ON corporate_actions (effective_date);
CREATE INDEX ix_corporate_actions_announcement_date ON corporate_actions (announcement_date);
CREATE INDEX ix_corporate_actions_company_id ON corporate_actions (company_id);
CREATE INDEX ix_corporate_actions_source ON corporate_actions (source);
CREATE INDEX ix_corporate_actions_action_group ON corporate_actions (action_group);
CREATE INDEX ix_corporate_actions_announcement_id ON corporate_actions (announcement_id);
CREATE INDEX ix_corporate_actions_ex_date ON corporate_actions (ex_date);
CREATE INDEX ix_regulatory_events_company_id ON regulatory_events (company_id);
CREATE INDEX ix_regulatory_events_legal_classification ON regulatory_events (legal_classification);
CREATE INDEX ix_regulatory_events_affected_security ON regulatory_events (affected_security);
CREATE INDEX ix_regulatory_events_case_key ON regulatory_events (case_key);
CREATE INDEX ix_regulatory_events_event_date ON regulatory_events (event_date);
CREATE INDEX ix_regulatory_events_status ON regulatory_events (status);
CREATE INDEX ix_regulatory_events_disclosure_id ON regulatory_events (disclosure_id);
CREATE INDEX ix_regulatory_events_announcement_id ON regulatory_events (announcement_id);
CREATE INDEX ix_regulatory_events_authority ON regulatory_events (authority);
CREATE INDEX ix_regulatory_events_event_type ON regulatory_events (event_type);
CREATE INDEX ix_regulatory_events_source ON regulatory_events (source);
CREATE INDEX ix_regulatory_events_document_hash ON regulatory_events (document_hash);
CREATE INDEX ix_regulatory_events_event_id ON regulatory_events (event_id);
CREATE INDEX ix_regulatory_event_company_date ON regulatory_events (company_id, event_date);
CREATE INDEX ix_regulatory_events_announcement_date ON regulatory_events (announcement_date);
CREATE INDEX ix_document_pages_company_id ON document_pages (company_id);
CREATE INDEX ix_document_pages_disclosure_id ON document_pages (disclosure_id);
CREATE INDEX ix_management_events_person_name ON management_events (person_name);
CREATE INDEX ix_management_events_source ON management_events (source);
CREATE INDEX ix_management_events_role ON management_events (role);
CREATE INDEX ix_management_events_company_id ON management_events (company_id);
CREATE INDEX ix_management_events_event_type ON management_events (event_type);
CREATE INDEX ix_management_events_event_date ON management_events (event_date);
CREATE INDEX ix_management_events_disclosure_id ON management_events (disclosure_id);
CREATE INDEX ix_management_observations_observation_date ON management_observations (observation_date);
CREATE INDEX ix_management_observations_disclosure_id ON management_observations (disclosure_id);
CREATE INDEX ix_management_observations_person_name ON management_observations (person_name);
CREATE INDEX ix_management_observations_role ON management_observations (role);
CREATE INDEX ix_management_observations_source ON management_observations (source);
CREATE INDEX ix_management_observations_company_id ON management_observations (company_id);
CREATE INDEX ix_segment_observations_segment_name ON segment_observations (segment_name);
CREATE INDEX ix_segment_observations_company_id ON segment_observations (company_id);
CREATE INDEX ix_segment_observations_reporting_period ON segment_observations (reporting_period);
CREATE INDEX ix_segment_observations_source ON segment_observations (source);
CREATE INDEX ix_segment_observations_disclosure_id ON segment_observations (disclosure_id);
CREATE INDEX ix_segment_observations_dimension ON segment_observations (dimension);
CREATE INDEX ix_subsidiary_observations_entity_id ON subsidiary_observations (entity_id);
CREATE INDEX ix_subsidiary_observations_company_id ON subsidiary_observations (company_id);
CREATE INDEX ix_subsidiary_observations_source ON subsidiary_observations (source);
CREATE INDEX ix_subsidiary_observations_observation_date ON subsidiary_observations (observation_date);
CREATE INDEX ix_subsidiary_observations_disclosure_id ON subsidiary_observations (disclosure_id);
CREATE INDEX ix_subsidiary_observations_entity_name ON subsidiary_observations (entity_name);
CREATE INDEX ix_subsidiary_observations_jurisdiction_class ON subsidiary_observations (jurisdiction_class);
CREATE INDEX ix_subsidiary_observations_relationship ON subsidiary_observations (relationship);
CREATE INDEX ix_human_capital_observations_category ON human_capital_observations (category);
CREATE INDEX ix_human_capital_observations_source ON human_capital_observations (source);
CREATE INDEX ix_human_capital_observations_disclosure_id ON human_capital_observations (disclosure_id);
CREATE INDEX ix_human_capital_observations_item ON human_capital_observations (item);
CREATE INDEX ix_human_capital_observations_reporting_period ON human_capital_observations (reporting_period);
CREATE INDEX ix_human_capital_observations_company_id ON human_capital_observations (company_id);
CREATE INDEX ix_esg_observations_company_id ON esg_observations (company_id);
CREATE INDEX ix_esg_observations_source ON esg_observations (source);
CREATE INDEX ix_esg_observations_reporting_period ON esg_observations (reporting_period);
CREATE INDEX ix_esg_observations_disclosure_id ON esg_observations (disclosure_id);
CREATE INDEX ix_esg_observations_item ON esg_observations (item);
CREATE INDEX ix_esg_observations_pillar ON esg_observations (pillar);
CREATE INDEX ix_listing_events_event_type ON listing_events (event_type);
CREATE INDEX ix_listing_events_event_date ON listing_events (event_date);
CREATE INDEX ix_listing_events_company_id ON listing_events (company_id);
CREATE INDEX ix_pledge_events_company_id ON pledge_events (company_id);
CREATE INDEX ix_pledge_events_event_type ON pledge_events (event_type);
CREATE INDEX ix_pledge_events_pledgor ON pledge_events (pledgor);
CREATE INDEX ix_pledge_events_disclosure_id ON pledge_events (disclosure_id);
CREATE INDEX ix_pledge_events_announcement_date ON pledge_events (announcement_date);
CREATE INDEX ix_control_observations_company_id ON control_observations (company_id);
CREATE INDEX ix_control_observations_ownership_type ON control_observations (ownership_type);
CREATE INDEX ix_control_observations_observation_date ON control_observations (observation_date);
CREATE INDEX ix_control_observations_disclosure_id ON control_observations (disclosure_id);
CREATE INDEX ix_entity_aliases_normalised_alias ON entity_aliases (normalised_alias);
CREATE INDEX ix_entity_aliases_entity_id ON entity_aliases (entity_id);
CREATE INDEX ix_entity_aliases_alias ON entity_aliases (alias);
CREATE INDEX ix_transaction_events_company_id ON transaction_events (company_id);
CREATE INDEX ix_transaction_events_disclosure_id ON transaction_events (disclosure_id);
CREATE INDEX ix_transaction_events_announcement_date ON transaction_events (announcement_date);
CREATE INDEX ix_transaction_events_case_key ON transaction_events (case_key);
CREATE INDEX ix_transaction_events_event_type ON transaction_events (event_type);
CREATE INDEX ix_market_bars_company_date ON market_bars (company_id, adjustment, trade_date);
CREATE INDEX ix_financial_facts_company_metric ON financial_facts (company_id, metric, reporting_period);
CREATE INDEX ix_disclosures_company_date ON disclosures (company_id, announcement_date);
CREATE INDEX ix_disclosures_kind_date ON disclosures (kind, announcement_date);
CREATE INDEX ix_mgmt_obs_company_date ON management_observations (company_id, observation_date);
CREATE INDEX ix_validation_flags_company_rule ON validation_flags (company_id, rule);
CREATE INDEX ix_job_items_job_status ON job_items (job_id, status);
COMMIT;