import uuid

import pytest
from pydantic import ValidationError

from app.auth.schema import UserIN, UserOUT


def make(**overrides) -> dict:
    data = {"name": "Dr. Test", "password": "Str0ng!Passw0rd"}
    data.update(overrides)
    return data


class TestPassword:
    def test_strong_password_ok(self):
        assert UserIN(**make()).password == "Str0ng!Passw0rd"

    @pytest.mark.parametrize(
        "pw",
        [
            "Sh0rt!a",  # < 8 chars
            "alllowercase1!",  # no uppercase
            "ALLUPPERCASE1!",  # no lowercase
            "NoDigitsHere!!",  # no digit
            "NoSpecial1234",  # no special char
        ],
    )
    def test_weak_passwords_rejected(self, pw):
        with pytest.raises(ValidationError):
            UserIN(**make(password=pw))

    def test_any_special_character_is_allowed(self):
        assert UserIN(**make(password="Abcdefg1#_-")).password

    def test_max_length(self):
        with pytest.raises(ValidationError):
            UserIN(**make(password="Aa1!" + "x" * 130))


class TestEmailAndPhone:
    def test_email_is_lowercased(self):
        assert UserIN(**make(email="Mixed.Case@Example.COM")).email == "mixed.case@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            UserIN(**make(email="not-an-email"))

    def test_email_and_phone_are_optional(self):
        u = UserIN(**make())
        assert u.email is None and u.phone is None

    def test_phone_separators_are_stripped(self):
        assert UserIN(**make(phone="+91 98765-43210")).phone == "+919876543210"

    @pytest.mark.parametrize("phone", ["123", "abcdefghijk", "+1234567890123456", "98765 4321 0x"])
    def test_invalid_phone_rejected(self, phone):
        with pytest.raises(ValidationError):
            UserIN(**make(phone=phone))


class TestName:
    def test_name_is_trimmed(self):
        assert UserIN(**make(name="  Asha  ")).name == "Asha"

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_name_rejected(self, name):
        with pytest.raises(ValidationError):
            UserIN(**make(name=name))

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            UserIN(**make(name="a" * 256))


class TestRoleCannotBeChosen:
    def test_role_field_is_ignored(self):
        user = UserIN(**make(role="docbro"))
        assert not hasattr(user, "role")
        assert "role" not in user.model_dump()


class TestUserOut:
    def test_never_exposes_password_hash(self):
        class Row:
            id = uuid.uuid4()
            name = "A"
            email = "a@b.com"
            phone = None
            role = "patient"
            is_admin = False
            is_verified = False
            password_hash = "should-not-leak"

        dumped = UserOUT.model_validate(Row()).model_dump()
        assert "password_hash" not in dumped
        assert "should-not-leak" not in str(dumped)

    def test_rejects_unknown_role(self):
        with pytest.raises(ValidationError):
            UserOUT(id=uuid.uuid4(), name="A", role="hacker", is_admin=False, is_verified=False)
