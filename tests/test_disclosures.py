from ashare.disclosures import clean_title, announcement_date, classify_title, document_url, PLATE_MAP, REPORT_CATEGORIES


def test_clean_title():
    assert clean_title('<em>2025年年度报告</em>') == '2025年年度报告'


def test_classification():
    assert classify_title('2025年年度报告') == 'annual_report'
    assert classify_title('2026年半年度报告') == 'interim_report'
    assert classify_title('关于重大资产重组的公告') == 'material_or_risk_announcement'


def test_document_url():
    assert document_url('2026-01/abc.PDF').startswith('https://static.cninfo.com.cn/')
    assert document_url('https://example.com/x.pdf') == 'https://example.com/x.pdf'


def test_query_mappings():
    assert PLATE_MAP['SSE_MAIN'] == ('sse', 'sh')
    assert PLATE_MAP['STAR'] == ('sse', 'shkcp')
    assert PLATE_MAP['SZSE_MAIN'] == ('szse', 'sz')
    assert PLATE_MAP['CHINEXT'] == ('szse', 'szcy')
    assert 'category_ndbg_szsh;' in REPORT_CATEGORIES['reports']


def test_epoch_date():
    assert announcement_date(0) is None
    assert announcement_date('not-a-timestamp') == 'not-a-time'


def test_epoch_converted_to_china_time():
    # 2026-03-31T23:33:20Z is 2026-04-01 in China Standard Time
    assert announcement_date(1775000000000) == "2026-04-01"
