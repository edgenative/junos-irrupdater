#!/usr/bin/env python3
# Script for generating BGP filters for Juniper JunOS
# (c) 2023 Lee Hetherington <lee@edgenative.net>
#

import os
import sys

# Set the path configuration variable here
path = "/usr/share/junos-irrupdater"

def generate_ipv4_filter(asn):
    prefix_set = set()  # Create a set to store unique prefixes
    with open(f"{path}/filters/as{asn}-import-ipv4.txt", "w") as f:
        f.write("policy-options {\n")
        f.write(f"policy-statement as{asn}-import-ipv4 {{\n")
        f.write("apply-flags omit;\n")
        f.write("	term prefixes {\n")
        f.write("		from {\n")
        with open(f"{path}/db/{asn}.4.agg", "r") as prefixes:
            for prefix in prefixes:
                prefix = prefix.strip()
                masklength = int(prefix.split("/")[1])
                if prefix not in prefix_set:  # Check if the prefix is not in the set
                    prefix_set.add(prefix)  # Add the prefix to the set
                    if masklength == 24:
                        f.write(f"			route-filter {prefix} exact;\n")
                    elif masklength < 24:
                        f.write(f"			route-filter {prefix} upto /24;\n")
        f.write("		}\n")
        f.write("		then next policy;\n")
        f.write("	}\n")
        f.write("	term reject {\n")
        f.write("		then reject;\n")
        f.write("	}\n")
        f.write("}\n")
        f.write("}\n")

def generate_ipv6_filter(asn):
    prefix_set = set()  # Create a set to store unique prefixes
    with open(f"{path}/filters/as{asn}-import-ipv6.txt", "w") as f:
        f.write("policy-options {\n")
        f.write(f"policy-statement as{asn}-import-ipv6 {{\n")
        f.write("apply-flags omit;\n")
        f.write("  term prefixes {\n")
        f.write("		from {\n")
        with open(f"{path}/db/{asn}.6.agg", "r") as prefixes6:
            for prefix6 in prefixes6:
                prefix6 = prefix6.strip()
                masklength6 = int(prefix6.split("/")[1])
                if prefix6 not in prefix_set:  # Check if the prefix is not in the set
                    prefix_set.add(prefix6)  # Add the prefix to the set
                    if masklength6 == 48:
                        f.write(f"			route-filter {prefix6} exact;\n")
                    elif masklength6 < 48:
                        f.write(f"			route-filter {prefix6} upto /48;\n")
        f.write("		}\n")
        f.write("		then next policy;\n")
        f.write("  }\n")
        f.write("  term reject {\n")
        f.write("          then reject;\n")
        f.write("  }\n")
        f.write("}\n")
        f.write("}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 junos-filtergen.py <ASN>")
        sys.exit(1)

    asn = sys.argv[1]

    generate_ipv4_filter(asn)
    generate_ipv6_filter(asn)
