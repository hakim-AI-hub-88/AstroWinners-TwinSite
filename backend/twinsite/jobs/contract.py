"""Thin adapter over C0's frozen `contracts.validation` (Draft 2020-12).

If `jsonschema` is unavailable the server still starts; a minimal structural
check guards mission requests and `schema_validation_available()` reports the
degraded mode so tests/status can say so honestly.
"""
import sys

from twinsite.storage.config import WORKSPACE_ROOT


class ContractError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def _contracts():
    try:
        from contracts import validation
    except ImportError:
        if str(WORKSPACE_ROOT) not in sys.path:
            sys.path.append(str(WORKSPACE_ROOT))
        try:
            from contracts import validation
        except ImportError:
            return None
    return validation


def schema_validation_available():
    validation = _contracts()
    if validation is None:
        return False
    try:
        import jsonschema  # noqa: F401
        import referencing  # noqa: F401
    except ImportError:
        return False
    return True


def _minimal_mission_request(value):
    if not isinstance(value, dict):
        raise ContractError('Request body must be a JSON object', None)
    for key in ('schema_version', 'data_status', 'mission', 'sites'):
        if key not in value:
            raise ContractError(f"'{key}' is a required property", key)
    if value['schema_version'] != '1.0':
        raise ContractError('schema_version must be "1.0"', 'schema_version')
    if value['data_status'] not in ('synthetic', 'measured'):
        raise ContractError('data_status must be synthetic or measured', 'data_status')
    if not isinstance(value['mission'], dict):
        raise ContractError('mission must be an object', 'mission')
    if not isinstance(value['sites'], list):
        raise ContractError('sites must be an array', 'sites')


def validate(name, value):
    """Raise ContractError on violation. Returns True if full schema validation ran."""
    validation = _contracts()
    if validation is not None and schema_validation_available():
        from jsonschema import ValidationError
        try:
            validation.validate(name, value)
        except ValidationError as error:
            path = '/'.join(str(p) for p in error.absolute_path) or None
            raise ContractError(error.message[:500], path) from None
        except ValueError as error:
            raise ContractError(str(error)[:500], None) from None
        return True
    if name == 'mission_request':
        _minimal_mission_request(value)
    return False


def digest(value):
    validation = _contracts()
    if validation is not None:
        return validation.digest(value)
    from twinsite.storage.db import canonical_sha256
    return canonical_sha256(value)
