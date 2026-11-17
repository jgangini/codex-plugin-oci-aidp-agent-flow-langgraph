"""Bounded, non-rotating AIDP Credential Store operations.

The caller owns authentication and the protected operation ledger. Request
bodies exist only in memory; outputs contain credential metadata only.
"""

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import quote, urlencode


class CredentialStoreError(RuntimeError):
    """A safe-to-display Credential Store failure."""


class _RuntimeIdentityUnavailable(CredentialStoreError):
    """The service returned the layout but omitted every public value."""


_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,254}\Z")
_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,255}\Z")
_ENV = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_FINGERPRINT = re.compile(r"(?:[0-9a-fA-F]{2}:){15}[0-9a-fA-F]{2}\Z")
_TYPES = {"SECRET_TOKEN", "SERVICE_ACCOUNT", "VAULT_REFERENCE"}
_STATES = {"ACTIVE", "CREATING", "UPDATING", "DELETING"}
_MAX_PAGES = 20
_MAX_ITEMS = 2000
_MAX_PRIVATE_KEY_BYTES = 65536
_MAX_TOKEN_BYTES = 65536
_DEFAULT_DESCRIPTION = "Credential for the selected AIDP agent"


def _valid_name(name):
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise CredentialStoreError("Credential name must begin with a letter and contain only letters, digits or underscores (maximum 255).")
    return name


def _request(client, method, path, body=None, headers=None):
    try:
        result, response_headers = client.request(method, path, body=body, headers=headers)
    except Exception:
        # SDK and transport exceptions may contain request bodies or secret values.
        raise CredentialStoreError("Credential Store request failed; reconcile the protected operation state before retrying a create.") from None
    if not isinstance(result, dict) or not isinstance(response_headers, dict):
        raise CredentialStoreError("Credential Store returned an unsupported response shape.")
    return result, {str(k).lower(): v for k, v in response_headers.items()}


def _metadata(item, detail=False):
    if not isinstance(item, dict):
        raise CredentialStoreError("Credential Store returned invalid credential metadata.")
    key, name = item.get("key"), item.get("displayName")
    kind = item.get("type" if detail else "credentialType")
    state = item.get("lifecycleState" if detail else "lifeCycleState")
    if (not isinstance(key, str) or not _KEY.fullmatch(key)
            or not isinstance(name, str) or not _NAME.fullmatch(name)
            or not isinstance(kind, str) or kind not in _TYPES
            or not isinstance(state, str) or state not in _STATES):
        raise CredentialStoreError("Credential Store returned incomplete or unsupported credential metadata.")
    return {"key": key, "displayName": name, "credentialType": kind, "lifeCycleState": state}


def list_credentials(client, name=None, limit=100):
    """Read exact-name summaries across bounded pages, excluding all details.

    ``limit`` is the API page size, not a guarantee of a complete listing.
    ``complete`` must be true before an ensure operation can proceed.
    """
    if name is not None:
        _valid_name(name)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise CredentialStoreError("Credential page size must be an integer from 1 to 1000.")
    items, page, visited, scanned = [], None, set(), 0
    for page_count in range(1, _MAX_PAGES + 1):
        query = {"limit": limit}
        if name is not None:
            query["displayName"] = name
        if page is not None:
            query["page"] = page
        result, headers = _request(client, "GET", "/credentials?" + urlencode(query))
        batch = result.get("items")
        if not isinstance(batch, list) or len(batch) > limit:
            raise CredentialStoreError("Credential Store returned an invalid credential page.")
        scanned += len(batch)
        if scanned > _MAX_ITEMS:
            raise CredentialStoreError("Credential listing exceeded the bounded item count; narrow the name filter.")
        for item in batch:
            metadata = _metadata(item)
            if name is None or metadata["displayName"] == name:
                items.append(metadata)
        page = headers.get("opc-next-page")
        if not page:
            return {"items": items, "complete": True, "pageCount": page_count, "nextPage": None}
        if not isinstance(page, str) or len(page) > 1024 or page in visited:
            raise CredentialStoreError("Credential Store returned invalid or repeated pagination state.")
        visited.add(page)
    return {"items": items, "complete": False, "pageCount": _MAX_PAGES, "nextPage": page}


def _existing(client, name, kind):
    listing = list_credentials(client, name=name)
    if not listing["complete"]:
        raise CredentialStoreError("Credential listing is incomplete; creation and reuse are refused.")
    matches = listing["items"]
    if len(matches) > 1:
        raise CredentialStoreError("Multiple credentials have the exact display name; select and reconcile them by key before continuing.")
    if not matches:
        return None
    existing = matches[0]
    if existing["credentialType"] != kind:
        raise CredentialStoreError("The exact credential name is already used by a different credential type.")
    if existing["lifeCycleState"] != "ACTIVE":
        raise CredentialStoreError("The existing credential is not ACTIVE; creation and reuse are refused.")
    return existing


def _details(client, summary):
    result, _ = _request(client, "GET", "/credentials/" + quote(summary["key"], safe=""))
    if _metadata(result, detail=True) != summary:
        raise CredentialStoreError("Credential metadata changed during verification; creation and reuse are refused.")
    details = result.get("credentialDetails")
    if not isinstance(details, dict) or details.get("credentialType") != summary["credentialType"]:
        raise CredentialStoreError("Credential details do not match the expected type.")
    return details


def _description(description):
    if description is None:
        return _DEFAULT_DESCRIPTION
    if not isinstance(description, str) or len(description) > 255:
        raise CredentialStoreError("Credential description must be at most 255 characters.")
    return description


def _plan(name, kind, existing, action):
    result = {"action": action, "applied": False, "displayName": name, "credentialType": kind}
    if existing:
        result["credential"] = existing
    return result


def _service_account_config(config_path, profile):
    # The SDK supplies profile inheritance and config validation. It is imported
    # only on apply; a plan never opens a config, key file or environment secret.
    try:
        import oci

        config = oci.config.from_file(file_location=str(config_path), profile_name=profile)
        if config.get("security_token_file") or config.get("authentication_type") not in (None, "api_key"):
            raise ValueError("API-key config required")
        oci.config.validate_config(config)
        identity = {
            "userId": config["user"], "fingerprint": config["fingerprint"].lower(),
            "tenancy": config["tenancy"], "region": config["region"], "isReadOnly": False,
        }
        if (not isinstance(identity["fingerprint"], str)
                or not _FINGERPRINT.fullmatch(identity["fingerprint"])
                or any(not isinstance(identity[k], str) or not identity[k] for k in ("userId", "tenancy", "region"))
                or not config.get("key_file")):
            raise ValueError("Incomplete API-key identity")
    except Exception:
        raise CredentialStoreError("Cannot load the selected API-key OCI profile; session-token authentication cannot supply a service-account credential.") from None
    return config, identity


def _private_key(config, identity):
    try:
        import oci
        from cryptography.hazmat.primitives import serialization

        key_path = Path(config["key_file"]).expanduser()
        with key_path.open("rb") as key_stream:
            pem = key_stream.read(_MAX_PRIVATE_KEY_BYTES + 1)
        if len(pem) > _MAX_PRIVATE_KEY_BYTES:
            raise ValueError("Oversized key")
        private_key = oci.signer.load_private_key(pem, config.get("pass_phrase"))
        public_der = private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        # OCI API-key fingerprints are MD5 digests of DER public keys; MD5 is
        # used for this protocol identifier, not as a cryptographic verifier.
        digest = hashlib.md5(public_der, usedforsecurity=False).hexdigest()
        fingerprint = ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))
        if fingerprint != identity["fingerprint"]:
            raise ValueError("Public key fingerprint differs")
        # Send the decrypted key; the Credential Store request schema has no
        # private-key passphrase field. No decrypted material is written to disk.
        return private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode("ascii")
    except Exception:
        raise CredentialStoreError("Cannot load or verify the API private key against the selected profile fingerprint.") from None


def _verify_identity(details, identity):
    if any(details.get(k) != v for k, v in identity.items()):
        raise CredentialStoreError("Existing service-account public identity differs from the selected profile; reuse is refused.")


def _secret_pairs(details, expected_keys):
    pairs = details.get("secretTokenPair")
    if (not isinstance(pairs, list) or len(pairs) != len(expected_keys)
            or any(not isinstance(pair, dict) or not isinstance(pair.get("secretKey"), str) for pair in pairs)):
        raise CredentialStoreError("Stored token key layout is missing or differs from the requested layout; reuse is refused.")
    by_key = {pair["secretKey"]: pair for pair in pairs}
    if len(by_key) != len(pairs) or set(by_key) != set(expected_keys):
        raise CredentialStoreError("Stored token key layout is missing or differs from the requested layout; reuse is refused.")
    return by_key


def _verify_runtime_identity(details, identity):
    pairs = _secret_pairs(details, {*identity, "private_key"})
    if all(pairs[key].get("secretValue") is None for key in identity):
        raise _RuntimeIdentityUnavailable("Stored runtime public identity is unavailable; native verification is required before reuse.")
    if any(pairs[key].get("secretValue") != value for key, value in identity.items()):
        raise CredentialStoreError("Stored runtime public identity is unavailable or differs from the selected profile; reuse is refused.")


def _create(client, name, kind, description, details, public_identity):
    operation_key = "credential-create:" + kind + ":" + name
    try:
        token = client.prepare_operation(operation_key, public_identity)
    except Exception:
        raise CredentialStoreError("Cannot establish a protected create operation; reconcile any prior submitted or uncertain attempt before retrying.") from None
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", token):
        raise CredentialStoreError("A protected, stable retry token is required before credential creation.")
    body = {"displayName": name, "type": kind, "credentialDescription": description, "credentialDetails": details}
    _request(client, "POST", "/credentials", body, {"opc-retry-token": token})
    # Create completes synchronously, but its documented response has no body.
    # Read the actual resource rather than manufacturing success from the plan.
    created = _existing(client, name, kind)
    if created is None:
        raise CredentialStoreError("Create returned without a uniquely readable ACTIVE credential; the operation remains uncertain.")
    readback = _details(client, created)
    if kind == "SERVICE_ACCOUNT":
        _verify_identity(readback, public_identity["serviceAccount"])
    elif "runtimeIdentity" in public_identity:
        try:
            _verify_runtime_identity(readback, public_identity["runtimeIdentity"])
        except _RuntimeIdentityUnavailable:
            try:
                client.defer_operation(operation_key, public_identity, created["key"])
            except Exception:
                raise CredentialStoreError("Credential exists, but its native-verification state could not be recorded; reconcile before retrying.") from None
            return {"action": "created-pending-native-verification", "applied": True,
                    "credential": created, "publicIdentityVerified": False, "secretValueVerified": False,
                    "nativeVerificationRequired": True}
    else:
        _secret_pairs(readback, {public_identity["secretKey"]})
    try:
        client.complete_operation(operation_key, public_identity, created["key"])
    except Exception:
        raise CredentialStoreError("Credential was read back, but its protected operation state could not be completed; reconcile before retrying.") from None
    result = {"action": "created", "applied": True, "credential": created, "secretValueVerified": False}
    return result


def ensure_service_account(client, name, oci_config_path, profile="DEFAULT", apply=False, description=None):
    """Plan or create an API-key credential; never update an existing key."""
    _valid_name(name)
    description = _description(description)
    existing = _existing(client, name, "SERVICE_ACCOUNT")
    if not apply:
        result = _plan(name, "SERVICE_ACCOUNT", existing, "validate-existing" if existing else "create")
        result["validationPending"] = "Selected API-key profile identity is checked on apply; private-key fingerprint is checked before creation."
        return result
    config, identity = _service_account_config(oci_config_path, profile)
    if existing:
        _verify_identity(_details(client, existing), identity)
        return {"action": "reused", "applied": False, "credential": existing, "secretValueVerified": False}
    details = {"credentialType": "SERVICE_ACCOUNT", **identity, "privateKey": _private_key(config, identity)}
    public_identity = {"displayName": name, "credentialType": "SERVICE_ACCOUNT", "serviceAccount": identity}
    return _create(client, name, "SERVICE_ACCOUNT", description, details, public_identity)


def ensure_secret_token(client, name, env_name, key_name="token", apply=False, description=None):
    """Plan or create an environment-sourced token; never compare or rotate it."""
    _valid_name(name)
    if not isinstance(env_name, str) or not _ENV.fullmatch(env_name):
        raise CredentialStoreError("Token source must be an environment variable name.")
    if not isinstance(key_name, str) or not _NAME.fullmatch(key_name):
        raise CredentialStoreError("Token key name must begin with a letter and contain only letters, digits or underscores (maximum 255).")
    description = _description(description)
    existing = _existing(client, name, "SECRET_TOKEN")
    if existing:
        if apply:
            _secret_pairs(_details(client, existing), {key_name})
            return {"action": "reused", "applied": False, "credential": existing, "secretValueVerified": False}
        result = _plan(name, "SECRET_TOKEN", existing, "validate-existing")
        result["validationPending"] = "Stored token key layout is checked on apply; its hidden value is not compared."
        return result
    if not apply:
        return _plan(name, "SECRET_TOKEN", None, "create")
    token = os.environ.get(env_name)
    try:
        valid_token = bool(token) and len(token.encode("utf-8")) <= _MAX_TOKEN_BYTES
    except UnicodeError:
        valid_token = False
    if not valid_token:
        raise CredentialStoreError("The selected environment variable must contain a nonempty token of at most 65536 UTF-8 bytes.")
    details = {"credentialType": "SECRET_TOKEN", "secretTokenPair": [{"secretKey": key_name, "secretValue": token}]}
    public_identity = {"displayName": name, "credentialType": "SECRET_TOKEN", "secretKey": key_name}
    return _create(client, name, "SECRET_TOKEN", description, details, public_identity)


def ensure_runtime_credential(client, name, oci_config_path, profile="DEFAULT", apply=False, description=None):
    """Ensure the aidputils runtime's established five-pair SECRET_TOKEN shape.

    Existing shared entries are never overwritten. If public values are masked
    or omitted in GET, runtime identity cannot be established and reuse fails.
    """
    _valid_name(name)
    description = _description(description)
    existing = _existing(client, name, "SECRET_TOKEN")
    if not apply:
        result = _plan(name, "SECRET_TOKEN", existing, "validate-existing" if existing else "create")
        result["validationPending"] = "Selected API-key identity and stored runtime pair layout are checked on apply; private-key fingerprint is checked before creation."
        result["layout"] = "aidputils-runtime"
        return result
    config, service_identity = _service_account_config(oci_config_path, profile)
    runtime_identity = {"tenancy": service_identity["tenancy"], "user": service_identity["userId"],
                        "fingerprint": service_identity["fingerprint"], "region": service_identity["region"]}
    if existing:
        _verify_runtime_identity(_details(client, existing), runtime_identity)
        return {"action": "reused", "applied": False, "credential": existing,
                "layout": "aidputils-runtime", "secretValueVerified": False}
    private_key = _private_key(config, service_identity)
    pairs = [{"secretKey": key, "secretValue": value} for key, value in runtime_identity.items()]
    pairs.append({"secretKey": "private_key", "secretValue": private_key})
    details = {"credentialType": "SECRET_TOKEN", "secretTokenPair": pairs}
    public_identity = {"displayName": name, "credentialType": "SECRET_TOKEN", "runtimeIdentity": runtime_identity}
    result = _create(client, name, "SECRET_TOKEN", description, details, public_identity)
    result["layout"] = "aidputils-runtime"
    return result
