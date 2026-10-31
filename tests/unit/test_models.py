from sqlalchemy import inspect
from sqlalchemy.orm import configure_mappers

from app.auth.model import User, UserRole
from app.staff.model import Staff
from db.base import Base


def test_mappers_configure_without_errors():
    configure_mappers()


def test_all_tables_registered():
    assert {"users", "refresh_tokens", "staff", "invitation", "addresses"} <= set(
        Base.metadata.tables
    )


def test_new_users_defaults():
    users = Base.metadata.tables["users"]
    for column in ("is_superuser", "is_verified"):
        assert users.c[column].default.arg is False
        assert users.c[column].server_default.arg == "false"
    # every registrant is an admin by default (product decision)
    assert users.c["is_admin"].default.arg is True
    assert users.c["is_admin"].server_default.arg == "true"
    assert users.c["role"].server_default.arg == "patient"


def test_unique_login_identifiers():
    users = Base.metadata.tables["users"]
    assert users.c["email"].unique and users.c["phone"].unique


def test_refresh_token_is_unique_and_indexed_by_user():
    table = Base.metadata.tables["refresh_tokens"]
    assert table.c["token"].unique
    assert table.c["user_id"].index


def test_user_roles():
    assert {r.value for r in UserRole} == {"doctor", "medical", "patient", "docbro"}


def test_staff_has_separate_user_and_doctor_links():
    assert {"user", "doctor"} <= set(inspect(Staff).relationships.keys())
    fks = {fk.parent.name for fk in Base.metadata.tables["staff"].foreign_keys}
    assert fks == {"user_id", "doctor_id"}


def test_staff_user_id_is_unique():
    constraint_names = {c.name for c in Base.metadata.tables["staff"].constraints}
    assert "uq_staff_user_id" in constraint_names


def test_user_relationships_exist():
    assert {"refresh_tokens", "invitation", "staff_profile", "staff_members", "addresses"} <= set(
        inspect(User).relationships.keys()
    )


def test_invitation_stores_token_hash_with_expiry():
    cols = Base.metadata.tables["invitation"].c
    assert cols["token_hash"].unique and not cols["token_hash"].nullable
    assert not cols["expires_at"].nullable
    assert cols["accepted_at"].nullable
    assert cols["status"].server_default.arg == "pending"


def test_addresses_required_fields():
    cols = Base.metadata.tables["addresses"].c
    assert not cols["address_line1"].nullable
    assert cols["address_line2"].nullable
    assert cols["pincode"].type.length == 10


def test_enum_names_are_snake_case():
    names = {
        c.type.name
        for table in Base.metadata.tables.values()
        for c in table.c
        if hasattr(c.type, "enums")
    }
    assert names == {"user_role", "designation", "role_assign", "invitation_status", "address_type"}


def test_cascade_delete_foreign_keys():
    for table, column in [
        ("refresh_tokens", "user_id"),
        ("addresses", "user_id"),
        ("staff", "user_id"),
        ("staff", "doctor_id"),
        ("invitation", "invited_by_user_id"),
    ]:
        fk = next(iter(Base.metadata.tables[table].c[column].foreign_keys))
        assert fk.ondelete == "CASCADE", f"{table}.{column}"
