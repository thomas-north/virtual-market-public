from decimal import Decimal

import pytest

from vmarket.errors import InsufficientCashError
from vmarket.services.cash_service import deposit, get_all_balances, withdraw


def test_deposit_increases_balance(session):
    deposit(session, Decimal("1000"), "GBP")
    session.commit()
    balances = get_all_balances(session)
    assert balances["GBP"] == Decimal("1000")


def test_multiple_deposits_accumulate(session):
    deposit(session, Decimal("500"), "GBP")
    deposit(session, Decimal("300"), "GBP")
    session.commit()
    balances = get_all_balances(session)
    assert balances["GBP"] == Decimal("800")


def test_withdraw_reduces_balance(session):
    deposit(session, Decimal("1000"), "GBP")
    withdraw(session, Decimal("400"), "GBP")
    session.commit()
    balances = get_all_balances(session)
    assert balances["GBP"] == Decimal("600")


def test_cannot_over_withdraw(session):
    deposit(session, Decimal("100"), "GBP")
    session.commit()
    with pytest.raises(InsufficientCashError):
        withdraw(session, Decimal("200"), "GBP")


def test_multi_currency_balances(session):
    deposit(session, Decimal("1000"), "GBP")
    deposit(session, Decimal("500"), "USD")
    session.commit()
    balances = get_all_balances(session)
    assert balances["GBP"] == Decimal("1000")
    assert balances["USD"] == Decimal("500")
