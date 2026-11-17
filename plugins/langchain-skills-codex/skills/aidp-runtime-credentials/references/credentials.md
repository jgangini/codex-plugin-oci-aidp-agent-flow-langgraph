# Credential helper contract

## Commands and inputs

The root flags precede `credentials`; `--project` selects an existing project.
These examples contain only nonsecret identifiers and paths:

```text
aidp-agent-flow --project <project-directory> --json credentials list --name AgentApiKey
aidp-agent-flow --project <project-directory> --json credentials ensure-runtime --name AidpRuntime
aidp-agent-flow --project <project-directory> --json credentials ensure-service-account --name AgentApiKey
aidp-agent-flow --project <project-directory> --json credentials ensure-token --name AgentToken --env AGENT_TOKEN --key-name token
```

Append `--apply` to the reviewed ensure command only when creation is within
the authorized request. Get details from
`aidp-agent-flow credentials --help` and the selected subcommand's help:

- `list`: read safe metadata, optionally filtered by exact name.
- `ensure-runtime`: plan the established aidputils runtime `SECRET_TOKEN`
  layout. On `--apply`, compare public OCI identity before reuse or create
  the five-pair entry from the selected API-key OCI profile.
- `ensure-service-account`: plan by default; on `--apply`, use an existing OCI
  API-key config path and selected profile, never private-key text in an argument.
- `ensure-token`: plan by default; on `--apply`, read a named environment
  variable and submit one token pair under the requested nonsecret key name.

Do not type a real token into a shell command or place one in a checked-in
environment file. Use the organization's existing protected environment/secret
injection route. The helper does not provision IAM users, upload their public
API keys, grant IAM policy, rotate entries or change credential consumers.

The Python exports in `scripts/aidp_agent_flow/credential_store.py` are:

```python
list_credentials(client, name=None, limit=100)
ensure_runtime_credential(client, name, oci_config_path, profile="DEFAULT",
                          apply=False, description=None)
ensure_service_account(client, name, oci_config_path, profile="DEFAULT",
                       apply=False, description=None)
ensure_secret_token(client, name, env_name, key_name="token",
                    apply=False, description=None)
```

The caller supplies the authenticated, platform-scoped client and protected
operation state. `request(method, relative_path, body=None, headers=None)`
returns a JSON object and response headers. Empty successful create responses
are normalized to `{}` by the transport. The helper never selects a different
platform, workspace or authentication mode.

`aidp-agent.toml` selects `[oci] config_file` and `profile` for both request
authentication and service-account creation. A relative config path resolves
under the selected project. `[native] endpoint` and `platform_id` select the
current Workbench API target. A session-token config remains usable for
supported authenticated reads/token setup; it cannot supply an API-key
service-account credential. There is no PEM or token command-line flag.

## Verified wire contract

Checked against Oracle's current REST documentation on 2026-11-01:

| Operation | Contract used by the helper | Source |
|---|---|---|
| List | `GET /20260430/aiDataPlatforms/{aiDataPlatformId}/credentials`; exact `displayName` filter; `limit` and `page`; `items` collection and `opc-next-page` header | [List credentials](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-credentials-get.html) |
| Summary | `key`, `displayName`, `credentialType`, `lifeCycleState`; names need not be unique | [List response schema](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-credentials-get.html) |
| Get | `GET .../credentials/{credentialKey}`; detail uses `type`, `lifecycleState`, `credentialDetails` | [Get credential](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-credentials-credentialkey-get.html) |
| Create | `POST .../credentials`; envelope `displayName`, `type`, `credentialDescription`, `credentialDetails`; nested discriminator `credentialType`; synchronous completion followed by list/get readback | [Create credential](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-credentials-post.html) |
| Retry identity | `opc-retry-token`, at most 64 characters; documented expiry after 24 hours, potentially earlier invalidation | [Create request headers](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-credentials-post.html) |

The helper's explicit nested shapes are:

```text
SERVICE_ACCOUNT:
  credentialType, userId, fingerprint, tenancy, region, isReadOnly, privateKey
SECRET_TOKEN:
  credentialType, secretTokenPair: [{secretKey, secretValue}]

aidputils runtime (SECRET_TOKEN pair keys):
  tenancy, user, fingerprint, region, private_key
```

These subtype field names are corroborated by the installed official Oracle
Workbench Engineer Agent's `aidp-credentials` SDK field mapping. The rendered
current REST pages expose the envelope and discriminator but omit the expanded
subtype schemas. Their live service acceptance remains unverified until an
authorized creation/readback succeeds. Do not substitute the older
`20240831/dataLakes` route or its historical 400 response for evidence about the
current endpoint. This helper's fake-client tests establish local behavior only.

The runtime five-pair layout matches the inspected
`AidpClient._credential_payload` path used by the existing agent standard.
Native consumers retrieve these pairs with
`aidputils.secrets.get(name=<credential-name>, key=<pair-key>)`. A
`SERVICE_ACCOUNT` entry is a different representation; do not substitute it
for `AidpRuntime` or change an existing consumer's layout without an authorized
consumer migration. The helper never rotates or overwrites an existing entry.

## Reuse and secret handling

The listing is bounded at 20 pages and 2,000 scanned records. `limit` is the
per-page size (1–1,000, default 100). `complete: false` or malformed/repeated
pagination prevents an ensure. Public output contains only credential key,
display name, type and state, plus operation status. It omits descriptions,
raw details, request bodies and secret values.

All exact-name matches are considered, including other types and lifecycle
states. Exactly one ACTIVE entry of the expected type is required for reuse.
The summary's `lifeCycleState` is deliberately distinct from GET detail's
`lifecycleState`. A changed key, name, type or state during readback stops the
operation.

Service-account apply loads the selected profile with the installed OCI SDK,
including its normal profile inheritance. It rejects session-token profiles
and requires `user`, `tenancy`, `region`, `fingerprint` and `key_file`.
The helper uses `isReadOnly: false` and compares that field along with the public
identity on reuse; this is a credential schema value, not proof of IAM grants.
For creation it loads the private key via OCI's signer, checks the MD5 digest
of its DER SubjectPublicKeyInfo against the configured fingerprint, and sends
an unencrypted PKCS#8 PEM in memory over the authenticated HTTPS request. The
configured passphrase is used locally and never submitted or persisted.
For reuse, the private-key file is not opened: only the configured public
identity is compared with GET details.

Runtime apply uses the same selected API-key config and key fingerprint check
as service-account creation, but stores the established five secret-token
pairs. Reuse requires exactly those five unique keys and actual returned
`tenancy`, `user`, `fingerprint`, `region` values matching the selected profile.
The `private_key` value is never printed or compared. Missing, masked,
conflicting or otherwise unknown public identity fails closed and requires
explicit reconciliation; it is never silently adopted based on the name
`AidpRuntime`. New creation must also read back matching public values. If the
service masks them, readback cannot establish acceptance and the operation
remains uncertain. Dry-run reports pending layout/identity verification.

Token creation reads its value only on apply. Reusing an existing token never
compares its hidden value or rotates it; `secretValueVerified: false` is
intentional. Apply requires exactly one pair with the requested `secretKey`,
and refuses a missing or different key layout. Dry-run leaves that validation
pending without reading details. If callers require a different token value
or key pair, use a separately authorized rotation workflow or a distinct
credential name. An existing credential's ACTIVE state alone does not
establish that an agent's tool invocation will be authorized.

## Protected operation state and uncertain creates

Before POST the client must provide:

```python
prepare_operation(operation_key, public_identity)  # stable retry token
complete_operation(operation_key, public_identity, credential_key)
```

The operation key is `credential-create:TYPE:NAME`, scoped by the caller's
selected project/platform context. Public identity contains name/type and,
for service accounts, the public fields above; for tokens it contains only
the nonsecret pair key. Runtime intents contain only the four public OCI
identity fields. Store this intent, retry token and state in the
project-private ignored ledger. Do not hash or serialize secret request
bodies into the ledger. The transport marks an intent submitted before
network dispatch and does not follow redirects or retry a mutation.

The helper refuses creation if protected state cannot be established. It sends
one POST, lists by exact name, requires one ACTIVE match, reads that key and
validates its expected details before completing the ledger. A timeout,
transport error, absent/multiple/nonactive readback, identity mismatch or
ledger completion failure leaves a result requiring reconciliation. A restart
must inspect/reconcile the existing ledger and resource; it must refuse a
prior submitted/uncertain create when no matching resource can be established.
Retry-token expiry is not permission to create a replacement automatically.
The current CLI has no journal-reconciliation mutation command. A later ensure
may safely recognize an existing entry, but does not close an old uncertain
journal automatically. Preserve that record and report reconciliation pending;
do not represent reuse as completion of the earlier uncertain create.

Display-name uniqueness is not a server guarantee; another independent actor
may race a create. This helper detects ambiguity visible during its readback,
but cannot reserve a name or prove the value of a token omitted by the service.
Use project ownership and resource keys when binding consumers. Live platform
compatibility and native TEST remain separate acceptance steps.

## Omitted values after a newly created runtime credential

A target-verified GA service returns the five pair names but omits every value
from credential GET. A new create with unique ACTIVE readback and the correct
layout is reported as `created-pending-native-verification`, with
`nativeVerificationRequired: true` and `publicIdentityVerified: false`. Its
protected journal stays pending; no second create is submitted. This distinguishes
a confirmed resource creation from successful native consumption.

Verify the selected technical identity inside the native runtime and exercise
its intended bounded call before reconciling that pending receipt. Keep the
nonsecret identity check and its evidence in the owning project. A pre-existing
credential with unavailable identity still cannot be silently adopted by this
helper; mismatches and partially masked/conflicting values remain failures.
Neither an omitted-value readback nor this pending state proves secret equality.
