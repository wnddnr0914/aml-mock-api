"""IBM 데이터가 아닌, 직접 만든 3일/24거래 연동용 합성 표본."""
from datetime import datetime, timezone
from decimal import Decimal

from models import Account, ScoredTransaction, Transaction


def account(label: str) -> Account:
    bank = "BANK02" if label in {"E", "F", "Y"} else "BANK01"
    return Account(account_id=f"{bank}:{label}", bank_id=bank, account_number=label)


def fixture_transactions() -> list[ScoredTransaction]:
    rows = [
        ("A", "HUB", "1000.10", "USD", .91),
        ("B", "HUB", "2000.20", "USD", .84),
        ("C", "HUB", "3000.30", "EUR", .35),
        ("HUB", "D", "1200.00", "USD", .93),
        ("HUB", "E", "1300.00", "EUR", .81),
        ("HUB", "F", "1400.00", "USD", .29),
        ("A", "HUB", "100.01", "USD", .15),  # 같은 계좌 쌍의 별도 거래
        ("X", "Y", "80.00", "EUR", .05),
    ]
    return [
        ScoredTransaction(
            transaction=Transaction(
                transaction_id=f"tx-{day:02d}-{index + 1:03d}",
                timestamp=datetime(2026, 10, day, 9, index * 5, tzinfo=timezone.utc),
                source=account(source), target=account(target),
                amount=Decimal(amount), currency=currency,
            ), suspicion_score=score, is_detected=False,
        )
        for day in range(1, 4)
        for index, (source, target, amount, currency, score) in enumerate(rows)
    ]
