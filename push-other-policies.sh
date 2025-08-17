#!/bin/bash
# (c) 2023-2025 Lee Hetherington <lee@edgenative.net>
#
# Create your policies in the filters directory, ending in .txt
# Edit the config/other-policies.conf file to list router,policyname (Without the .txt)
# This script will loop through and ensure the router config matches what's in the filters directory.
#

path=/usr/share/junos-irrupdater

# Check if the configuration file exists
if [ ! -f $path/config/other-policies.conf ]; then
    echo "Configuration File 'other-policies.conf' not found."
    exit 1
fi

# Read the input file line by line
while IFS=',' read -r param1 param2; do
    if [ -n "$param1" ] && [ -n "$param2" ]; then
        # Run the irrupdater script, pushing policies per the configuration
	python3 $path/bin/junos-irrupdater.py $param1 $param2
    fi
done < $path/config/other-policies.conf
