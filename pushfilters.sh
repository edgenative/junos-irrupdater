#!/bin/bash
# Script for generating BGP filters for Juniper Routers
# (c) 2023-2025 Lee Hetherington <lee@edgenative.net>

path=/usr/share/junos-irrupdater

# Check if the configuration file exists
if [ ! -f $path/config/sessions.conf ]; then
    echo "Configuration File 'sessions.conf' not found."
    exit 1
fi

# Read the input file line by line
while IFS=',' read -r param1 param2 param3; do
    if [ -n "$param1" ] && [ -n "$param2" ]; then
        if [ -n "$param3" ]; then
            if [ "$param3" = "ipv4" ]; then
                # Run for IPv4 only
                python3 $path/bin/junos-irrupdater.py $param2 as$param1-import-ipv4
            elif [ "$param3" = "ipv6" ]; then
                # Run for IPv6 only
                python3 $path/bin/junos-irrupdater.py $param2 as$param1-import-ipv6
            else
                echo "Invalid value for affinity: $param3"
            fi
        else
            # Run for both IPv4 and IPv6
            python3 $path/bin/junos-irrupdater.py $param2 as$param1-import-ipv4
            python3 $path/bin/junos-irrupdater.py $param2 as$param1-import-ipv6
        fi
    fi
done < $path/config/sessions.conf
