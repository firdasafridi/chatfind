from backend.sparse import doc_vector, query_vector, tokens


def test_tokens_drop_stopwords_and_normalise_suffix():
    assert tokens("Tolong cari barangnya yang dikirim dari Bandung") == ["barang", "dikirim", "bandung"]


def test_short_words_keep_suffix():
    assert tokens("punya") == ["punya"]  # len <= 5, not stripped


def test_doc_and_query_share_ids():
    d, q = doc_vector("invoice refund sepatu"), query_vector("refund")
    assert set(q.indices) <= set(d.indices)


def test_tf_saturates():
    one = doc_vector("refund").values[0]
    many = doc_vector(" ".join(["refund"] * 20)).values[0]
    assert many > one and many < 20 * one


def test_query_weights_are_binary_and_unique():
    q = query_vector("refund refund sepatu")
    assert len(q.indices) == 2 and set(q.values) == {1.0}


def test_empty_text_is_valid_vector():
    assert doc_vector("").indices == [0]
    assert query_vector("dan yang").values == [0.0]
