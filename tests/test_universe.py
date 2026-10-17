from ashare.universe import (
    clean_code, infer_exchange, infer_board, is_a_share
)

def test_code_normalisation():
    assert clean_code("600519") == "600519"
    assert clean_code(1) == "000001"

def test_exchange():
    assert infer_exchange("600519") == "SSE"
    assert infer_exchange("688981") == "SSE"
    assert infer_exchange("000001") == "SZSE"
    assert infer_exchange("300750") == "SZSE"

def test_board():
    assert infer_board("SSE", "600519") == "SSE_MAIN"
    assert infer_board("SSE", "688981") == "STAR"
    assert infer_board("SZSE", "000001") == "SZSE_MAIN"
    assert infer_board("SZSE", "300750") == "CHINEXT"

def test_excludes_b_shares():
    assert not is_a_share("900901")
    assert not is_a_share("200001")
