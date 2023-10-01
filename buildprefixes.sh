#!/bin/bash
# Script for generating BGP filter for Juniper Routers
# (c) 2023 Lee Hetherington <lee@edgenative.net>


path=/usr/share/junos-irrupdater

# Check if the configuration file 'peers.conf' exists
if [ ! -f $path/config/peers.conf ]; then
    echo "Configuration File 'peers.conf' not found."
    exit 1
fi

# Read the input file line by line
while IFS=',' read -r param1 param2; do
    if [ -n "$param1" ] && [ -n "$param2" ]; then
        # Run bgpq4 to fetch the prefixes, with ASN $param1 and AS-SET $param2 as arguments
        echo "Running BGPQ4 for as$param1 $param2..."
        $path/bin/fetchprefixes.sh "$param1" "$param2"
    fi
done < $path/config/peers.conf

# Check if the configuration file 'sessions.conf' exists
if [ ! -f $path/config/sessions.conf ]; then
    echo "Configuration File 'sessions.conf' not found."
    exit 1
fi

# Read the input file line by line
while IFS=',' read -r param1 param2; do
    if [ -n "$param1" ]; then
        # Run filtergen with ASN $param1 as arguments
        echo "Generating filters for as$param1..."
        python3 $path/bin/junos-filtergen.py "$param1"
    fi
done < $path/config/sessions.conf
