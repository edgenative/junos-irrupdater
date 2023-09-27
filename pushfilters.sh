#!/bin/bash
# Script for generating BGP filters for Juniper Routers
# (c) 2023 Lee Hetherington <lee@edgenative.net>

path=/usr/share/junos-irrupdater

# Check if the configuration file exists
if [ ! -f $path/config/sessions.conf ]; then
    echo "Configuration File 'sessions.conf' not found."
    exit 1
fi

# Read the input file line by line
while IFS=',' read -r param1 param2; do
    if [ -n "$param1" ] && [ -n "$param2" ]; then
        # Run bgpq4 to fetch the prefixes, with ASN $param1 and AS-SET $param2 as arguments
	python3 $path/bin/junos-irrupdater.py $param2 as$param1-import-ipv4
	python3 $path/bin/junos-irrupdater.py $param2 as$param1-import-ipv6
    fi
done < $path/config/sessions.conf
