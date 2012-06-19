#!/usr/bin/env gawk -f
{
  $0=gensub(/@([^@]+)@/,                   "{{\\1}}",   "g")
  $0=gensub( /"\$":([^[:space:]]+)/ ,      "[\\1]",     "g")
  $0=gensub( /"([^"]+)":([^[:space:]]+)/ , "[\\1|\\2]", "g")
  $0=gensub( /<pre><code>/,                "{code}",    "g")
  $0=gensub( /<\/code><\/pre>/,            "{code}",    "g")
  print $0
}
