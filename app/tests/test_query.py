from datetime import datetime

import pytest

from backend.query import WIB, parse

NOW = datetime(2026, 9, 29, 18, 0, tzinfo=WIB)


@pytest.mark.parametrize("q,label,days", [
    ("invoice refund minggu lalu", "7 hari terakhir", 7),
    ("receipt from last week", "7 hari terakhir", 7),
    ("tagihan bulan lalu", "31 hari terakhir", 31),
    ("struk 3 hari terakhir", "3 hari terakhir", 3),
    ("photos last 10 days", "10 hari terakhir", 10),
])
def test_relative_dates(q, label, days):
    pq = parse(q, NOW)
    assert pq.date_label == label
    assert (NOW.replace(hour=0, minute=0, second=0, microsecond=0) - pq.date_from).days == days


def test_yesterday_is_bounded_both_sides():
    pq = parse("bukti transfer kemarin", NOW)
    assert pq.date_from == datetime(2026, 9, 28, tzinfo=WIB)
    assert pq.date_to == datetime(2026, 9, 29, tzinfo=WIB)


def test_today_and_this_month():
    assert parse("struk hari ini", NOW).date_from == datetime(2026, 9, 29, tzinfo=WIB)
    assert parse("laporan bulan ini", NOW).date_from == datetime(2026, 9, 1, tzinfo=WIB)


@pytest.mark.parametrize("q,channel", [
    ("bukti transfer via wa", "whatsapp"),
    ("foto produk dari instagram", "instagram"),
    ("penawaran laptop dari email", "email"),
    ("katalog di ig", "instagram"),
])
def test_channel(q, channel):
    assert parse(q, NOW).channel == channel


def test_channel_name_without_preposition_is_content():
    pq = parse("kontrak whatsapp api berapa lama", NOW)
    assert pq.channel is None and "whatsapp" in pq.text


def test_channel_word_inside_other_word_is_ignored():
    assert parse("jawaban customer", NOW).channel is None  # 'wa' inside 'jawaban'


@pytest.mark.parametrize("q,t", [
    ("foto anjing di rumput", "image"),
    ("struk bensin", "image"),
    ("invoice refund", "document"),
    ("pdf kontrak", "document"),
    ("anjing di rumput", None),
])
def test_type_hint(q, t):
    assert parse(q, NOW).type_hint == t


def test_semantic_text_is_cleaned_but_keeps_content_words():
    pq = parse("tolong cari foto struk bensin yang dikirim via wa minggu lalu", NOW)
    assert pq.text == "struk bensin"
    assert pq.channel == "whatsapp" and pq.date_label and pq.type_hint == "image"


def test_query_that_is_only_filters_falls_back_to_raw():
    pq = parse("foto", NOW)
    assert pq.text == "foto"


def test_fixed_now_env(monkeypatch):
    monkeypatch.setenv("QUERY_NOW", "2026-01-10T10:00:00+07:00")
    assert parse("hari ini").date_from == datetime(2026, 1, 10, tzinfo=WIB)
