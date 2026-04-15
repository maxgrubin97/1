"""Tests for contact parsing and ranking."""

from app.utils.text import classify_title_seniority
from app.parsers.contact_parser import rank_contacts
from app.models.contact import Contact


def test_founder_highest_priority():
    seniority, role, priority = classify_title_seniority("Founder & CEO")
    assert seniority == "executive"
    assert priority == 1


def test_partner_senior():
    seniority, role, priority = classify_title_seniority("Managing Partner")
    assert seniority == "executive"
    assert priority == 1


def test_analyst_low_priority():
    seniority, role, priority = classify_title_seniority("Financial Analyst")
    assert seniority == "junior"
    assert priority == 99


def test_sba_lender_priority():
    seniority, role, priority = classify_title_seniority("VP SBA Lending")
    assert priority <= 3


def test_rank_contacts():
    contacts = [
        Contact(name="Junior", title="Analyst", contact_priority=99),
        Contact(name="Boss", title="Founder", contact_priority=1),
        Contact(name="Mid", title="Manager", contact_priority=4),
    ]
    ranked = rank_contacts(contacts)
    assert ranked[0].name == "Boss"
    assert ranked[-1].name == "Junior"
