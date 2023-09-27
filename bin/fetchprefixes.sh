#!/bin/bash
# Script for generating BGP filters for Junos
# (c) 2023 Lee Hetherington <lee@edgenative.net>

path=/usr/share/junos-irrupdater

bgpq4 -F '%n/%l \n' -4 -A $2 > $path/db/$1.4.agg
bgpq4 -F '%n/%l \n' -6 -A $2 > $path/db/$1.6.agg
