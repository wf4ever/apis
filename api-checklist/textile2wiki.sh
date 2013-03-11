#!/bin/bash
#
# Run AWK conversion script to convergy textile source to Confluence wiki source.

awk -f textile2wiki.awk <checklist-api.textile >checklist-api.wiki 

# End.