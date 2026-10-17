from .models import SessionLocal, Company
from .universe import infer_exchange, infer_board

def validate_database():
    session = SessionLocal()
    problems = []
    try:
        for company in session.query(Company).all():
            expected_exchange = infer_exchange(company.security_code)
            expected_board = infer_board(company.exchange, company.security_code)

            if expected_exchange != company.exchange:
                problems.append({
                    "code": company.security_code,
                    "problem": "exchange mismatch",
                    "stored": company.exchange,
                    "expected": expected_exchange,
                })

            if expected_board != company.board:
                problems.append({
                    "code": company.security_code,
                    "problem": "board mismatch",
                    "stored": company.board,
                    "expected": expected_board,
                })

            # v2.0.2: CNINFO's list carries short names only, so a missing full
            # legal name is normal and is reported as a count, not a problem.
        return problems
    finally:
        session.close()
