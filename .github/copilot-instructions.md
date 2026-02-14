<!-- Copied/updated by AI assistant -->
# Copilot / AI agent instructions for junos-irrupdater

Purpose
- Help contributors and automated agents understand how to generate and push JunOS routing policies

Quick architecture summary
- Primary scripts live in `bin/` and expect to be installed into `/usr/share/junos-irrupdater` (see `path` variable in scripts).
- Data sources: aggregated prefix files are in `db/` named `{ASN}.4.agg` and `{ASN}.6.agg`.
- Filter output: generated policy files are written to `filters/` as `as<ASN>-import-ipv4.txt` and `as<ASN>-import-ipv6.txt`.
- Config: `config/routers.conf`, `config/peers.conf`, `config/sessions.conf`, `config/other-policies.conf`, and `config/email.conf` drive behavior.
- Push flow: `buildprefixes.sh` -> `junos-filtergen.py` -> `pushfilters.sh` / `push-other-policies.sh` -> `bin/junos-irrupdater.py` which uses Junos PyEZ to apply policies.

Key workflows (commands and examples)
- Generate filters for an ASN:

```bash
python3 bin/junos-filtergen.py 35008
```

- Build all prefixes and filters (reads `config/peers.conf` and `config/sessions.conf`):

```bash
./buildprefixes.sh
```

- Push generated filters to routers (reads `config/sessions.conf`):

```bash
./pushfilters.sh
```

- Push non-generated policies listed in `config/other-policies.conf`:

```bash
./push-other-policies.sh
```

Important file-level conventions (do not change without updating scripts)
- Filter files must be plain-text JunOS policy fragments, filename (without `.txt`) is used as the policy name. Example: `filters/example-filter.txt` -> policy `example-filter`.
- Generated filter names follow `as<ASN>-import-ipv4` and `as<ASN>-import-ipv6`.
- `junos-filtergen.py` writes `policy-options { policy-statement <name> { ... } }` blocks and always includes a `term reject` fallback.
- `junos-irrupdater.py` compares normalized text of the policy (strips leading/trailing lines) and uses exclusive configure mode: it deletes the existing `policy-options policy-statement <name>` and re-inserts the file content before committing.

Runtime & environment notes
- Scripts assume Python 3 and these dependencies: `py-junos-eznc` (Juniper PyEZ) and `bgpq4` installed on host.
- The `path` variable at top of scripts is hard-coded to `/usr/share/junos-irrupdater`. For local development change `path` in the script or run from a system-installed location.
- Email notifications are configured via `config/email.conf`. Keys looked for: `send_updates`, `send_errors`, `smtp_server`, `sender_email`, `receiver_email`.

Pointers for contributors / agents
- When modifying filter generation, update `bin/junos-filtergen.py` — it contains the IPv4/IPv6 logic and mask-length handling (/24 and /48 limits).
- When changing how policies are applied, update `bin/junos-irrupdater.py`. Note: it uses `jnpr.junos.Device` and `jnpr.junos.utils.config.Config` with `mode='exclusive'` and `format='text'` for loading policies.
- For adding new workflows, keep CLI parity: `junos-filtergen.py <ASN>` and `junos-irrupdater.py <hostname> <filtername>` are the public CLI surfaces used by the shell wrappers.

Testing & running locally
- To test a single router update without installing to `/usr/share`: set `path` at top of the scripts to the repository root and run the Python scripts directly.
- To simulate a change-detection run locally, create a small `filters/` file and a local `config/routers.conf` with a non-production device or mock.

What the agent should not do
- Do not attempt to push to production routers unless credentials and network access are validated and the user explicitly requests that action.

Questions for the maintainer
- Confirm preferred default `path` and whether CI/testing harness exists for dry-run (mocking JunOS connections).

If anything here is unclear, tell me which area you want expanded (examples, config keys, or policy-format examples).
