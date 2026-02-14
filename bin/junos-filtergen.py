#!/usr/bin/env python3
# Script for generating BGP filters for Juniper JunOS
# (c) 2023-2026 Lee Hetherington <lee@edgenative.net>
#

import os
import sys

# Set the path configuration variable here
path = "/usr/share/junos-irrupdater"

def generate_filter(asn, afi):
    # afi: 4 for IPv4, 6 for IPv6
    max_prefix = 24 if afi == 4 else 48
    db_file = f"{path}/db/{asn}.{afi}.agg"
    policy_name = f"as{asn}-import-ipv{afi}"
    output_file = f"{path}/filters/{policy_name}.txt"

    prefix_set = set()
    with open(output_file, "w") as f:
        f.write("policy-options {\n")
        f.write(f"policy-statement {policy_name} {{\n")
        f.write("apply-flags omit;\n")
        if os.path.getsize(db_file) > 0:
            f.write("\tterm prefixes {\n")
            f.write("\t\tfrom {\n")
            with open(db_file, "r") as prefixes:
                for line in prefixes:
                    prefix = line.strip()
                    if not prefix or prefix in prefix_set:
                        continue
                    prefix_set.add(prefix)
                    masklength = int(prefix.split("/")[1])
                    if masklength == max_prefix:
                        f.write(f"\t\t\troute-filter {prefix} exact;\n")
                    elif masklength < max_prefix:
                        f.write(f"\t\t\troute-filter {prefix} upto /{max_prefix};\n")
            f.write("\t\t}\n")
            f.write("\t\tthen next policy;\n")
            f.write("\t}\n")
        f.write("\tterm reject {\n")
        f.write("\t\tthen reject;\n")
        f.write("\t}\n")
        f.write("}\n")
        f.write("}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 junos-filtergen.py <ASN>")
        sys.exit(1)

    asn = sys.argv[1]

    generate_filter(asn, 4)
    generate_filter(asn, 6)
