# Codebook

All panel variables (`ashare-cli panel-variables` lists them too). A panel's own codebook, written beside it, adds coverage by year for that panel.

Identifiers: `code` (current security code), `name` (short name on the measurement date), `period` (fiscal period end or row date), `measure_date`, `cutoff` (latest publication date used), `universe_basis` (why the company is in the row: LISTING_RECORD, its listing record covers the date; REPORT_EVIDENCE, its listing record is incomplete but it published a periodic report for that year).

## revenue

*revenue (营业收入)* (CNY; financial)

- Definition: 营业收入, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cost_of_revenue

*cost_of_revenue (营业成本)* (CNY; financial)

- Definition: 营业成本, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## operating_profit

*operating_profit (营业利润)* (CNY; financial)

- Definition: 营业利润, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## profit_before_tax

*profit_before_tax (利润总额)* (CNY; financial)

- Definition: 利润总额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## income_tax

*income_tax (所得税费用)* (CNY; financial)

- Definition: 所得税费用, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## net_profit

*net_profit (净利润)* (CNY; financial)

- Definition: 净利润, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## net_profit_parent

*net_profit_parent (归属于母公司所有者的净利润)* (CNY; financial)

- Definition: 归属于母公司所有者的净利润, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_assets

*total_assets (资产总计)* (CNY; financial)

- Definition: 资产总计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_liabilities

*total_liabilities (负债合计)* (CNY; financial)

- Definition: 负债合计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## equity

*equity (所有者权益合计)* (CNY; financial)

- Definition: 所有者权益合计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash

*cash (货币资金)* (CNY; financial)

- Definition: 货币资金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## accounts_receivable

*accounts_receivable (应收账款)* (CNY; financial)

- Definition: 应收账款, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## inventory

*inventory (存货)* (CNY; financial)

- Definition: 存货, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## operating_cash_flow

*operating_cash_flow (经营活动产生的现金流量净额)* (CNY; financial)

- Definition: 经营活动产生的现金流量净额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## investing_cash_flow

*investing_cash_flow (投资活动产生的现金流量净额)* (CNY; financial)

- Definition: 投资活动产生的现金流量净额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## financing_cash_flow

*financing_cash_flow (筹资活动产生的现金流量净额)* (CNY; financial)

- Definition: 筹资活动产生的现金流量净额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## rd_expense

*rd_expense (研发费用)* (CNY; financial)

- Definition: 研发费用, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## net_profit_parent_ex_nonrecurring

*net_profit_parent_ex_nonrecurring (归属于上市公司股东的扣除非经常性损益的净利润)* (CNY; financial)

- Definition: 归属于上市公司股东的扣除非经常性损益的净利润, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## employees

*employees (员工人数)* (PERSON; financial)

- Definition: 员工人数, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## settlement_reserves

*settlement_reserves (结算备付金)* (CNY; financial)

- Definition: 结算备付金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## lending_funds

*lending_funds (拆出资金)* (CNY; financial)

- Definition: 拆出资金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## trading_financial_assets

*trading_financial_assets (交易性金融资产)* (CNY; financial)

- Definition: 交易性金融资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## derivative_assets

*derivative_assets (衍生金融资产)* (CNY; financial)

- Definition: 衍生金融资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## notes_receivable

*notes_receivable (应收票据)* (CNY; financial)

- Definition: 应收票据, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## receivables_financing

*receivables_financing (应收款项融资)* (CNY; financial)

- Definition: 应收款项融资, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## prepayments

*prepayments (预付款项)* (CNY; financial)

- Definition: 预付款项, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_receivables

*other_receivables (其他应收款)* (CNY; financial)

- Definition: 其他应收款, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## contract_assets

*contract_assets (合同资产)* (CNY; financial)

- Definition: 合同资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## held_for_sale_assets

*held_for_sale_assets (持有待售资产)* (CNY; financial)

- Definition: 持有待售资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## non_current_assets_due_within_one_year

*non_current_assets_due_within_one_year (一年内到期的非流动资产)* (CNY; financial)

- Definition: 一年内到期的非流动资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_current_assets

*other_current_assets (其他流动资产)* (CNY; financial)

- Definition: 其他流动资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_current_assets

*total_current_assets (流动资产合计)* (CNY; financial)

- Definition: 流动资产合计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## debt_investments

*debt_investments (债权投资)* (CNY; financial)

- Definition: 债权投资, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_debt_investments

*other_debt_investments (其他债权投资)* (CNY; financial)

- Definition: 其他债权投资, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## long_term_receivables

*long_term_receivables (长期应收款)* (CNY; financial)

- Definition: 长期应收款, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## long_term_equity_investments

*long_term_equity_investments (长期股权投资)* (CNY; financial)

- Definition: 长期股权投资, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_equity_instrument_investments

*other_equity_instrument_investments (其他权益工具投资)* (CNY; financial)

- Definition: 其他权益工具投资, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_non_current_financial_assets

*other_non_current_financial_assets (其他非流动金融资产)* (CNY; financial)

- Definition: 其他非流动金融资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## investment_property

*investment_property (投资性房地产)* (CNY; financial)

- Definition: 投资性房地产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## fixed_assets

*fixed_assets (固定资产)* (CNY; financial)

- Definition: 固定资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## construction_in_progress

*construction_in_progress (在建工程)* (CNY; financial)

- Definition: 在建工程, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## productive_biological_assets

*productive_biological_assets (生产性生物资产)* (CNY; financial)

- Definition: 生产性生物资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## right_of_use_assets

*right_of_use_assets (使用权资产)* (CNY; financial)

- Definition: 使用权资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## intangible_assets

*intangible_assets (无形资产)* (CNY; financial)

- Definition: 无形资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## development_expenditure

*development_expenditure (开发支出)* (CNY; financial)

- Definition: 开发支出, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## goodwill

*goodwill (商誉)* (CNY; financial)

- Definition: 商誉, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## long_term_prepaid_expenses

*long_term_prepaid_expenses (长期待摊费用)* (CNY; financial)

- Definition: 长期待摊费用, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## deferred_tax_assets

*deferred_tax_assets (递延所得税资产)* (CNY; financial)

- Definition: 递延所得税资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_non_current_assets

*other_non_current_assets (其他非流动资产)* (CNY; financial)

- Definition: 其他非流动资产, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_non_current_assets

*total_non_current_assets (非流动资产合计)* (CNY; financial)

- Definition: 非流动资产合计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## short_term_borrowings

*short_term_borrowings (短期借款)* (CNY; financial)

- Definition: 短期借款, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## trading_financial_liabilities

*trading_financial_liabilities (交易性金融负债)* (CNY; financial)

- Definition: 交易性金融负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## derivative_liabilities

*derivative_liabilities (衍生金融负债)* (CNY; financial)

- Definition: 衍生金融负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## notes_payable

*notes_payable (应付票据)* (CNY; financial)

- Definition: 应付票据, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## accounts_payable

*accounts_payable (应付账款)* (CNY; financial)

- Definition: 应付账款, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## advances_from_customers

*advances_from_customers (预收款项)* (CNY; financial)

- Definition: 预收款项, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## contract_liabilities

*contract_liabilities (合同负债)* (CNY; financial)

- Definition: 合同负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## employee_benefits_payable

*employee_benefits_payable (应付职工薪酬)* (CNY; financial)

- Definition: 应付职工薪酬, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## taxes_payable

*taxes_payable (应交税费)* (CNY; financial)

- Definition: 应交税费, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_payables

*other_payables (其他应付款)* (CNY; financial)

- Definition: 其他应付款, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## held_for_sale_liabilities

*held_for_sale_liabilities (持有待售负债)* (CNY; financial)

- Definition: 持有待售负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## non_current_liabilities_due_within_one_year

*non_current_liabilities_due_within_one_year (一年内到期的非流动负债)* (CNY; financial)

- Definition: 一年内到期的非流动负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_current_liabilities

*other_current_liabilities (其他流动负债)* (CNY; financial)

- Definition: 其他流动负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_current_liabilities

*total_current_liabilities (流动负债合计)* (CNY; financial)

- Definition: 流动负债合计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## long_term_borrowings

*long_term_borrowings (长期借款)* (CNY; financial)

- Definition: 长期借款, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## bonds_payable

*bonds_payable (应付债券)* (CNY; financial)

- Definition: 应付债券, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## lease_liabilities

*lease_liabilities (租赁负债)* (CNY; financial)

- Definition: 租赁负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## long_term_payables

*long_term_payables (长期应付款)* (CNY; financial)

- Definition: 长期应付款, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## provisions

*provisions (预计负债)* (CNY; financial)

- Definition: 预计负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## deferred_income

*deferred_income (递延收益)* (CNY; financial)

- Definition: 递延收益, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## deferred_tax_liabilities

*deferred_tax_liabilities (递延所得税负债)* (CNY; financial)

- Definition: 递延所得税负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_non_current_liabilities

*other_non_current_liabilities (其他非流动负债)* (CNY; financial)

- Definition: 其他非流动负债, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_non_current_liabilities

*total_non_current_liabilities (非流动负债合计)* (CNY; financial)

- Definition: 非流动负债合计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## share_capital

*share_capital (实收资本（或股本）)* (CNY; financial)

- Definition: 实收资本（或股本）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_equity_instruments

*other_equity_instruments (其他权益工具)* (CNY; financial)

- Definition: 其他权益工具, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## capital_reserve

*capital_reserve (资本公积)* (CNY; financial)

- Definition: 资本公积, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## treasury_shares

*treasury_shares (减：库存股)* (CNY; financial)

- Definition: 减：库存股, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_comprehensive_income

*other_comprehensive_income (其他综合收益)* (CNY; financial)

- Definition: 其他综合收益, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## special_reserve

*special_reserve (专项储备)* (CNY; financial)

- Definition: 专项储备, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## surplus_reserve

*surplus_reserve (盈余公积)* (CNY; financial)

- Definition: 盈余公积, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## general_risk_reserve

*general_risk_reserve (一般风险准备)* (CNY; financial)

- Definition: 一般风险准备, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## retained_earnings

*retained_earnings (未分配利润)* (CNY; financial)

- Definition: 未分配利润, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## equity_parent

*equity_parent (归属于母公司所有者权益（或股东权益）合计)* (CNY; financial)

- Definition: 归属于母公司所有者权益（或股东权益）合计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## minority_interests

*minority_interests (少数股东权益)* (CNY; financial)

- Definition: 少数股东权益, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_liabilities_and_equity

*total_liabilities_and_equity (负债和所有者权益（或股东权益）总计)* (CNY; financial)

- Definition: 负债和所有者权益（或股东权益）总计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_operating_revenue

*total_operating_revenue (营业总收入)* (CNY; financial)

- Definition: 营业总收入, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_operating_costs

*total_operating_costs (营业总成本)* (CNY; financial)

- Definition: 营业总成本, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## taxes_and_surcharges

*taxes_and_surcharges (税金及附加)* (CNY; financial)

- Definition: 税金及附加, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## selling_expenses

*selling_expenses (销售费用)* (CNY; financial)

- Definition: 销售费用, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## administrative_expenses

*administrative_expenses (管理费用)* (CNY; financial)

- Definition: 管理费用, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## finance_expenses

*finance_expenses (财务费用)* (CNY; financial)

- Definition: 财务费用, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## interest_expense

*interest_expense (其中：利息费用)* (CNY; financial)

- Definition: 其中：利息费用, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## interest_income

*interest_income (利息收入)* (CNY; financial)

- Definition: 利息收入, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_income

*other_income (其他收益)* (CNY; financial)

- Definition: 其他收益, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## investment_income

*investment_income (投资收益（损失以“－”号填列）)* (CNY; financial)

- Definition: 投资收益（损失以“－”号填列）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## fair_value_change_gains

*fair_value_change_gains (公允价值变动收益（损失以“－”号填列）)* (CNY; financial)

- Definition: 公允价值变动收益（损失以“－”号填列）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## credit_impairment_losses

*credit_impairment_losses (信用减值损失（损失以“-”号填列）)* (CNY; financial)

- Definition: 信用减值损失（损失以“-”号填列）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## asset_impairment_losses

*asset_impairment_losses (资产减值损失（损失以“-”号填列）)* (CNY; financial)

- Definition: 资产减值损失（损失以“-”号填列）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## asset_disposal_gains

*asset_disposal_gains (资产处置收益（损失以“－”号填列）)* (CNY; financial)

- Definition: 资产处置收益（损失以“－”号填列）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## non_operating_income

*non_operating_income (营业外收入)* (CNY; financial)

- Definition: 营业外收入, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## non_operating_expenses

*non_operating_expenses (营业外支出)* (CNY; financial)

- Definition: 营业外支出, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## net_profit_continuing

*net_profit_continuing (持续经营净利润（净亏损以“－”号填列）)* (CNY; financial)

- Definition: 持续经营净利润（净亏损以“－”号填列）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## net_profit_discontinued

*net_profit_discontinued (终止经营净利润（净亏损以“－”号填列）)* (CNY; financial)

- Definition: 终止经营净利润（净亏损以“－”号填列）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## minority_profit

*minority_profit (少数股东损益（净亏损以“-”号填列）)* (CNY; financial)

- Definition: 少数股东损益（净亏损以“-”号填列）, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_comprehensive_income_net

*other_comprehensive_income_net (其他综合收益的税后净额)* (CNY; financial)

- Definition: 其他综合收益的税后净额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## total_comprehensive_income

*total_comprehensive_income (综合收益总额)* (CNY; financial)

- Definition: 综合收益总额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## eps_basic

*eps_basic (（一）基本每股收益(元/股))* (CNY_PER_SHARE; financial)

- Definition: （一）基本每股收益(元/股), consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## eps_diluted

*eps_diluted (（二）稀释每股收益(元/股))* (CNY_PER_SHARE; financial)

- Definition: （二）稀释每股收益(元/股), consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_from_sales

*cash_from_sales (销售商品、提供劳务收到的现金)* (CNY; financial)

- Definition: 销售商品、提供劳务收到的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## tax_refunds_received

*tax_refunds_received (收到的税费返还)* (CNY; financial)

- Definition: 收到的税费返还, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_operating_cash_in

*other_operating_cash_in (收到其他与经营活动有关的现金)* (CNY; financial)

- Definition: 收到其他与经营活动有关的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## operating_cash_inflow

*operating_cash_inflow (经营活动现金流入小计)* (CNY; financial)

- Definition: 经营活动现金流入小计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_paid_for_goods

*cash_paid_for_goods (购买商品、接受劳务支付的现金)* (CNY; financial)

- Definition: 购买商品、接受劳务支付的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_paid_to_employees

*cash_paid_to_employees (支付给职工及为职工支付的现金)* (CNY; financial)

- Definition: 支付给职工及为职工支付的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## taxes_paid

*taxes_paid (支付的各项税费)* (CNY; financial)

- Definition: 支付的各项税费, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## other_operating_cash_out

*other_operating_cash_out (支付其他与经营活动有关的现金)* (CNY; financial)

- Definition: 支付其他与经营活动有关的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## operating_cash_outflow

*operating_cash_outflow (经营活动现金流出小计)* (CNY; financial)

- Definition: 经营活动现金流出小计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_from_investment_recovery

*cash_from_investment_recovery (收回投资收到的现金)* (CNY; financial)

- Definition: 收回投资收到的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_from_investment_income

*cash_from_investment_income (取得投资收益收到的现金)* (CNY; financial)

- Definition: 取得投资收益收到的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_from_asset_disposals

*cash_from_asset_disposals (处置固定资产、无形资产和其他长期资产收回的现金净额)* (CNY; financial)

- Definition: 处置固定资产、无形资产和其他长期资产收回的现金净额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## investing_cash_inflow

*investing_cash_inflow (投资活动现金流入小计)* (CNY; financial)

- Definition: 投资活动现金流入小计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## capex

*capex (购建固定资产、无形资产和其他长期资产支付的现金)* (CNY; financial)

- Definition: 购建固定资产、无形资产和其他长期资产支付的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_paid_for_investments

*cash_paid_for_investments (投资支付的现金)* (CNY; financial)

- Definition: 投资支付的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## investing_cash_outflow

*investing_cash_outflow (投资活动现金流出小计)* (CNY; financial)

- Definition: 投资活动现金流出小计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_from_capital_contributions

*cash_from_capital_contributions (吸收投资收到的现金)* (CNY; financial)

- Definition: 吸收投资收到的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_from_borrowings

*cash_from_borrowings (取得借款收到的现金)* (CNY; financial)

- Definition: 取得借款收到的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## financing_cash_inflow

*financing_cash_inflow (筹资活动现金流入小计)* (CNY; financial)

- Definition: 筹资活动现金流入小计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_paid_for_debt

*cash_paid_for_debt (偿还债务支付的现金)* (CNY; financial)

- Definition: 偿还债务支付的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_paid_for_dividends_interest

*cash_paid_for_dividends_interest (分配股利、利润或偿付利息支付的现金)* (CNY; financial)

- Definition: 分配股利、利润或偿付利息支付的现金, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## financing_cash_outflow

*financing_cash_outflow (筹资活动现金流出小计)* (CNY; financial)

- Definition: 筹资活动现金流出小计, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## fx_effect_on_cash

*fx_effect_on_cash (汇率变动对现金及现金等价物的影响)* (CNY; financial)

- Definition: 汇率变动对现金及现金等价物的影响, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## net_change_in_cash

*net_change_in_cash (现金及现金等价物净增加额)* (CNY; financial)

- Definition: 现金及现金等价物净增加额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_at_beginning

*cash_at_beginning (期初现金及现金等价物余额)* (CNY; financial)

- Definition: 期初现金及现金等价物余额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cash_at_end

*cash_at_end (期末现金及现金等价物余额)* (CNY; financial)

- Definition: 期末现金及现金等价物余额, consolidated, as reported
- Formula: reported value (single quarter for flow items in quarterly panels)
- Source: financial_facts (XBRL > CSV import > statement table > PDF text); manual corrections applied
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ttm_revenue

*TTM revenue* (CNY; derived)

- Definition: trailing twelve months of revenue
- Formula: YTD(q) + FY(y−1) − YTD(y−1, q)
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ttm_net_profit

*TTM net_profit* (CNY; derived)

- Definition: trailing twelve months of net_profit
- Formula: YTD(q) + FY(y−1) − YTD(y−1, q)
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ttm_net_profit_parent

*TTM net_profit_parent* (CNY; derived)

- Definition: trailing twelve months of net_profit_parent
- Formula: YTD(q) + FY(y−1) − YTD(y−1, q)
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ttm_operating_profit

*TTM operating_profit* (CNY; derived)

- Definition: trailing twelve months of operating_profit
- Formula: YTD(q) + FY(y−1) − YTD(y−1, q)
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ttm_operating_cash_flow

*TTM operating_cash_flow* (CNY; derived)

- Definition: trailing twelve months of operating_cash_flow
- Formula: YTD(q) + FY(y−1) − YTD(y−1, q)
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## non_recurring_items

*non-recurring items* (CNY; derived)

- Definition: net profit to the parent minus the same excluding non-recurring items
- Formula: net_profit_parent − net_profit_parent_ex_nonrecurring
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## roa

*return on assets* (RATIO; ratio)

- Definition: return on assets
- Formula: net_profit / total_assets
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## roe

*return on equity* (RATIO; ratio)

- Definition: return on equity
- Formula: net_profit_parent / equity attributable to the parent (total equity if absent)
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## net_margin

*net margin* (RATIO; ratio)

- Definition: net margin
- Formula: net_profit / revenue
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## gross_margin

*gross margin* (RATIO; ratio)

- Definition: gross margin
- Formula: 1 − cost_of_revenue / revenue
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## leverage

*liabilities to assets* (RATIO; ratio)

- Definition: liabilities to assets
- Formula: total_liabilities / total_assets
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## rd_intensity

*R&D intensity* (RATIO; ratio)

- Definition: R&D intensity
- Formula: rd_expense / revenue
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## cfo_to_assets

*operating cash flow to assets* (RATIO; ratio)

- Definition: operating cash flow to assets
- Formula: operating_cash_flow / total_assets
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## sales_growth

*revenue growth* (RATIO; ratio)

- Definition: revenue growth
- Formula: revenue / revenue of the same period a year earlier − 1
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## asset_growth

*asset growth* (RATIO; ratio)

- Definition: asset growth
- Formula: total_assets / total_assets a year earlier − 1
- Source: financial_facts
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## market_cap

*market capitalisation* (CNY; market)

- Definition: market capitalisation
- Formula: close × total shares
- Source: market_bars, capital_structure_observations, financial_facts
- Point in time: close on the last trading day on or before the measurement date (missing if none in the month before); financials published on or before the cut-off
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## float_market_cap

*free-float market capitalisation* (CNY; market)

- Definition: free-float market capitalisation
- Formula: close × tradable shares
- Source: market_bars, capital_structure_observations, financial_facts
- Point in time: close on the last trading day on or before the measurement date (missing if none in the month before); financials published on or before the cut-off
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## pe

*price to earnings (TTM)* (RATIO_X; market)

- Definition: price to earnings (TTM)
- Formula: market_cap / TTM net_profit_parent
- Source: market_bars, capital_structure_observations, financial_facts
- Point in time: close on the last trading day on or before the measurement date (missing if none in the month before); financials published on or before the cut-off
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## pb

*price to book* (RATIO_X; market)

- Definition: price to book
- Formula: market_cap / equity attributable to the parent
- Source: market_bars, capital_structure_observations, financial_facts
- Point in time: close on the last trading day on or before the measurement date (missing if none in the month before); financials published on or before the cut-off
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ps

*price to sales (TTM)* (RATIO_X; market)

- Definition: price to sales (TTM)
- Formula: market_cap / TTM revenue
- Source: market_bars, capital_structure_observations, financial_facts
- Point in time: close on the last trading day on or before the measurement date (missing if none in the month before); financials published on or before the cut-off
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ev

*enterprise value* (CNY; market)

- Definition: enterprise value
- Formula: market_cap + interest-bearing debt − cash
- Source: market_bars, capital_structure_observations, financial_facts
- Point in time: close on the last trading day on or before the measurement date (missing if none in the month before); financials published on or before the cut-off
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## close

*closing price* (CNY; market)

- Definition: closing price
- Formula: unadjusted close
- Source: market_bars, capital_structure_observations, financial_facts
- Point in time: close on the last trading day on or before the measurement date (missing if none in the month before); financials published on or before the cut-off
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ret

*stock return over the period* (RATIO; market)

- Definition: buy-and-hold return over the row's period
- Formula: adjusted close(end) / adjusted close(start) − 1, own adjustment factors
- Source: market_bars, adjustment_factors
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## volatility

*return volatility (annualised)* (RATIO; market)

- Definition: standard deviation of daily returns over the period × √244
- Source: market_bars, adjustment_factors
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## board_size

*board size* (COUNT; governance)

- Definition: board size
- Source: management_observations, management_events
- Point in time: roster at the measurement date, used only once the report that gave it was published
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## independence_ratio

*share of independent directors* (RATIO; governance)

- Definition: share of independent directors
- Source: management_observations, management_events
- Point in time: roster at the measurement date, used only once the report that gave it was published
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## female_directors

*number of female directors* (COUNT; governance)

- Definition: number of female directors
- Source: management_observations, management_events
- Point in time: roster at the measurement date, used only once the report that gave it was published
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ceo_duality

*chair is also general manager (1/0)* (COUNT; governance)

- Definition: chair is also general manager (1/0)
- Source: management_observations, management_events
- Point in time: roster at the measurement date, used only once the report that gave it was published
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## employees_total

*employees* (PERSON; human_capital)

- Definition: employees
- Source: human_capital_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## rd_staff

*R&D staff* (PERSON; human_capital)

- Definition: R&D staff
- Source: human_capital_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## rd_staff_share

*R&D staff share* (RATIO; human_capital)

- Definition: R&D staff share
- Source: human_capital_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## postgraduate_share

*postgraduate share* (RATIO; human_capital)

- Definition: postgraduate share
- Source: human_capital_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## product_hhi

*product revenue concentration (HHI)* (RATIO; segments)

- Definition: sum of squared product shares
- Formula: Σ share²
- Source: segment_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## industry_hhi

*industry revenue concentration (HHI)* (RATIO; segments)

- Definition: sum of squared industry shares
- Formula: Σ share²
- Source: segment_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## overseas_share

*overseas revenue share* (RATIO; segments)

- Definition: revenue outside the Mainland / total
- Source: segment_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## top1_pct

*largest shareholder's stake* (RATIO; ownership)

- Definition: ownership share of the largest holder
- Source: ownership_observations
- Point in time: latest observation on or before the measurement date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## in_csi300

*constituent of CSI300* (DUMMY; index)

- Definition: index 000300 member (1/0)
- Source: index_constituents
- Point in time: membership on the measurement date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## in_csi500

*constituent of CSI500* (DUMMY; index)

- Definition: index 000905 member (1/0)
- Source: index_constituents
- Point in time: membership on the measurement date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## in_sse180

*constituent of SSE180* (DUMMY; index)

- Definition: index 000010 member (1/0)
- Source: index_constituents
- Point in time: membership on the measurement date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## in_star50

*constituent of STAR50* (DUMMY; index)

- Definition: index 000688 member (1/0)
- Source: index_constituents
- Point in time: membership on the measurement date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## listed_years

*years since listing* (YEARS; listing)

- Definition: years from listing to the measurement date
- Source: companies
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## risk_warning

*under ST or *ST (1/0)* (DUMMY; listing)

- Definition: risk warning in force
- Source: security_history
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## board

*listing board* (TEXT; listing)

- Definition: board on the measurement date
- Source: security_history
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## csrc_section

*CSRC 2012 section* (TEXT; industry)

- Definition: CSRC industry section (letter)
- Source: industry_classifications
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## sw_level1

*Shenwan 2021 level 1* (TEXT; industry)

- Definition: Shenwan level-1 industry
- Source: industry_classifications
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## penalties

*administrative and disciplinary penalties* (COUNT; regulatory)

- Definition: penalties dated in the 12 months (3 for quarters) to the measurement date
- Source: regulatory_events
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## fines_company

*fines on the company* (CNY; regulatory)

- Definition: fines on the company in the same window
- Source: regulatory_events
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## ownership_type

*ownership type* (TEXT; control)

- Definition: CENTRAL_SOE, LOCAL_SOE, PRIVATE, FOREIGN, COLLECTIVE, NO_CONTROLLER or UNKNOWN, from the actual controller
- Source: control_observations
- Point in time: latest report published by the cut-off
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## soe

*state-owned (1/0)* (DUMMY; control)

- Definition: actual controller is a central or local state body
- Source: control_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## top10_pct

*top-10 holders' combined stake* (RATIO; ownership)

- Definition: sum of the top-10 holders' stakes
- Source: ownership_observations (top-10 tables)
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class

## top_holder_pledged

*largest holder's pledged share* (RATIO; ownership)

- Definition: pledged shares of the largest holder / its shares
- Source: ownership_observations
- Point in time: value published on or before the row's cut-off date
- Confidence: carries the confidence class of its inputs; filtered by --min-class
