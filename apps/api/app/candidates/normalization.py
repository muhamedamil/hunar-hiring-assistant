"""Normalization helpers for Candidate profile and contact identity fields."""

from __future__ import annotations

from importlib import import_module


def normalize_required_text(value: object) -> object:
    """Trim a required string while leaving non-string values for Pydantic to reject."""

    if isinstance(value, str):
        return value.strip()
    return value


def normalize_optional_text(value: object) -> object:
    """Trim an optional string and convert whitespace-only values to ``None``."""

    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value


def normalize_phone_e164(value: object) -> object:
    """Validate an international phone and return canonical E.164 representation.

    ``phonenumbers`` is imported lazily so non-phone Candidate workflows can still be
    inspected in restricted environments where optional package installation is blocked.
    The project dependency guarantees the library is installed in the supported runtime.
    """

    if value is None:
        return None
    if not isinstance(value, str):
        return value

    normalized = value.strip()
    if not normalized:
        return None
    if not normalized.startswith("+"):
        raise ValueError("Phone number must include an international country code, for example +91")

    try:
        phonenumbers = import_module("phonenumbers")
    except ImportError as exc:  # pragma: no cover - supported runtime installs this dependency.
        raise RuntimeError(
            "Phone normalization requires the 'phonenumbers' package. Install backend dependencies."
        ) from exc

    try:
        parsed = phonenumbers.parse(normalized, None)
    except phonenumbers.NumberParseException as exc:
        raise ValueError("Phone number is not a valid international number") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Phone number is not a valid international number")

    return str(phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164))


def phone_library_available() -> bool:
    """Return whether the optional phone library is importable in the current environment."""

    try:
        import_module("phonenumbers")
    except ImportError:
        return False
    return True
