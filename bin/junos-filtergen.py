#!/usr/bin/env python3
# Script for generating BGP filters for Juniper JunOS
# (c) 2023-2026 Lee Hetherington <lee@edgenative.net>
#
# Safety: a filter is only written when the prefix db for that ASN/AFI exists and
# yields at least one route-filter entry. Otherwise the existing filter file is
# left untouched and the script exits non-zero. A 0-byte db file (disk full, IRR
# outage, unknown AS-SET) used to produce a filter containing only a reject term,
# which junos-irrupdater.py would then push to the router.
#
# The filter is written to a temporary file and atomically renamed into place, so
# a crash or a full disk mid-write can never leave a truncated filter behind.

import os
import sys
import tempfile

# Set the path configuration variable here
path = "/usr/share/junos-irrupdater"

def generate_filter(asn, afi):
    # afi: 4 for IPv4, 6 for IPv6
    max_prefix = 24 if afi == 4 else 48
    db_file = f"{path}/db/{asn}.{afi}.agg"
    policy_name = f"as{asn}-import-ipv{afi}"
    output_dir = f"{path}/filters"
    output_file = f"{output_dir}/{policy_name}.txt"

    if not os.path.isfile(db_file) or os.path.getsize(db_file) == 0:
        print(f"ERROR: {db_file} is missing or empty - not generating {policy_name} (existing filter left untouched)")
        return False

    entries = []
    prefix_set = set()
    with open(db_file, "r") as prefixes:
        for line in prefixes:
            prefix = line.strip()
            if not prefix or prefix in prefix_set:
                continue
            prefix_set.add(prefix)
            masklength = int(prefix.split("/")[1])
            if masklength == max_prefix:
                entries.append(f"\t\t\troute-filter {prefix} exact;\n")
            elif masklength < max_prefix:
                entries.append(f"\t\t\troute-filter {prefix} upto /{max_prefix};\n")

    if not entries:
        print(f"ERROR: {db_file} contained no usable prefixes - not generating {policy_name} (existing filter left untouched)")
        return False

    content = []
    content.append("policy-options {\n")
    content.append(f"policy-statement {policy_name} {{\n")
    content.append("apply-flags omit;\n")
    content.append("\tterm prefixes {\n")
    content.append("\t\tfrom {\n")
    content.extend(entries)
    content.append("\t\t}\n")
    content.append("\t\tthen next policy;\n")
    content.append("\t}\n")
    content.append("\tterm reject {\n")
    content.append("\t\tthen reject;\n")
    content.append("\t}\n")
    content.append("}\n")
    content.append("}\n")

    # Write to a temp file in the same directory, then rename over the old filter.
    fd, tmp_file = tempfile.mkstemp(prefix=f".{policy_name}.", suffix=".tmp", dir=output_dir)
    try:
        with os.fdopen(fd, "w") as f:
            f.writelines(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_file, 0o644)
        os.replace(tmp_file, output_file)
    except OSError as e:
        print(f"ERROR: could not write {output_file}: {e} (existing filter left untouched)")
        try:
            os.unlink(tmp_file)
        except OSError:
            pass
        return False

    print(f"Generated {policy_name} with {len(entries)} route-filter entries")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 junos-filtergen.py <ASN>")
        sys.exit(1)

    asn = sys.argv[1]

    ok4 = generate_filter(asn, 4)
    ok6 = generate_filter(asn, 6)
    sys.exit(0 if (ok4 and ok6) else 1)
