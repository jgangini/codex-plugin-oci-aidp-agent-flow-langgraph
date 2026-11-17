---
name: aidp-runtime-credentials
description: Inspect and safely ensure Oracle AIDP Credential Store entries for aidputils runtime OCI credentials, service accounts or environment-sourced tokens using the local aidp-agent-flow helper. Use for credential binding and setup; not for rotating secrets, provisioning IAM users or changing shared runtime credentials.
---

# AIDP Agent Credential Store

Use the plugin's `aidp-agent-flow credentials` commands for a bounded list or
plan/apply operation. Read [the credential contract](references/credentials.md)
before applying. Installing or loading this skill executes nothing.

Discover the installed command with `aidp-agent-flow credentials --help` and
reuse the project's protected target/auth configuration. Keep the selected
authentication mode. A service-account entry requires a selected API-key OCI
profile; an existing session token cannot substitute for its private key.
Do not edit an agent repository or populate its `.oci/` as an installation side
effect. Do not start compute, run an agent or publish production to verify a
credential setup request.

Run the matching ensure command without `--apply` first. Plans inspect only
credential summaries; they do not open OCI configuration/private-key files or
read an environment token. Use `ensure-runtime` for the established aidputils
OCI runtime layout: this is a `SECRET_TOKEN` with the keys `tenancy`, `user`,
`fingerprint`, `region`, `private_key`. `ensure-service-account` creates the
distinct `SERVICE_ACCOUNT` schema for consumers that actually require it.
Establish the exact platform, name, expected type
and ownership from the authorized setup request before using `--apply`.
Prefer a dedicated credential name. Never rotate, delete, overwrite or silently
repurpose the existing shared OCI runtime credential.

Display names are not unique. Reuse requires exactly one ACTIVE exact-name
entry of the expected type across the complete bounded listing. Multiple
matches, a type collision, an incomplete listing or an inactive entry stop the
operation. On service-account apply, compare the selected profile's public
identity with the actual credential details before reuse. Runtime reuse
requires the exact five-pair layout and returned public values matching that
identity; omitted or masked public identity stops the operation. A simple token
requires its requested pair key. These checks do not verify hidden values.

For creation, load secrets only on apply and keep them in memory. Read tokens
from the named environment variable, never a command-line value. The helper
checks a newly loaded API key's public fingerprint before sending its PEM.
Never print or persist PEM, tokens, passphrases, full response details or secret
request bodies. Use only the helper's allowlisted metadata as evidence.

Creation records a protected nonsecret operation intent with a stable retry
token before sending one POST. If a response or readback is uncertain, stop
and reconcile the actual credential by key/name and the existing operation
record. Do not delete the ledger, mint a new token or retry a create to escape
an uncertain result. The helper performs no automatic mutation retry.

Accept success only after the helper reads back a unique ACTIVE resource and
validates its details. Save its returned key through the project's existing
binding workflow only when that edit is authorized. Credential creation,
runtime authorization, native TEST and production publication are separate
outcomes. Report offline test evidence and any unverified live behavior
explicitly; a fake-client pass does not establish tenancy acceptance.
