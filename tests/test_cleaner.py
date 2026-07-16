from ingestion.cleaner import PIIRedactor


def test_finds_ssn():
    r = PIIRedactor()
    matches = r.find("SSN: 523-11-8890")
    assert any(m.pii_type == "SSN" for m in matches)


def test_redacts_ssn():
    r = PIIRedactor()
    text, matches = r.redact("SSN: 523-11-8890 on file")
    assert "523-11-8890" not in text
    assert "[REDACTED:SSN]" in text
    assert len(matches) == 1


def test_credit_card_luhn_filters_false_positives():
    r = PIIRedactor()
    # Fails the Luhn checksum -> should not be flagged as a credit card number.
    matches = r.find("Tracking number: 1234567890123456")
    assert not any(m.pii_type == "CREDIT_CARD" for m in matches)


def test_credit_card_valid_luhn_detected():
    r = PIIRedactor()
    # Well-known valid test Visa number (passes Luhn).
    matches = r.find("Card: 4111111111111111")
    assert any(m.pii_type == "CREDIT_CARD" for m in matches)


def test_routing_number_checksum_filters_false_positives():
    r = PIIRedactor()
    matches = r.find("routing 123456789")  # fails ABA checksum
    assert not any(m.pii_type == "ROUTING_NUMBER" for m in matches)


def test_routing_number_valid_checksum_detected():
    r = PIIRedactor()
    matches = r.find("routing number 071000013")  # valid ABA routing number
    assert any(m.pii_type == "ROUTING_NUMBER" for m in matches)


def test_no_false_positive_on_plain_sentence():
    r = PIIRedactor()
    matches = r.find("The quick brown fox jumps over the lazy dog.")
    assert matches == []


def test_email_and_phone_detected():
    r = PIIRedactor()
    matches = r.find("Contact us at test@example.com or 555-123-4567")
    types = {m.pii_type for m in matches}
    assert "EMAIL" in types
    assert "PHONE" in types


def test_phone_redaction_leaves_no_stray_punctuation():
    r = PIIRedactor()
    text, _ = r.redact("Call (312) 555-0148 for details")
    assert "(" not in text and ")" not in text
