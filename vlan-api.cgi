#!/bin/sh

printf 'Content-Type: text/plain\r\n'
printf 'Cache-Control: no-store\r\n'
printf '\r\n'

url_decode() {
  local data="${1//+/ }"
  printf '%b' "$(printf '%s' "$data" | sed 's/%/\\x/g')"
}

query_value() {
  local key="$1"
  printf '%s' "$QUERY_STRING" | tr '&' '\n' | awk -F= -v k="$key" '$1 == k { print $2; exit }'
}

action="$(query_value action)"
path="$(url_decode "$(query_value path)")"

case "$action:$path" in
  read:/etc/config/network|read:/etc/config/wireless|read:/etc/config/dhcp|read:/etc/config/firewall|read:/etc/avahi/avahi-daemon.conf)
    if [ -r "$path" ]; then
      cat "$path"
    else
      printf 'File non leggibile: %s\n' "$path" >&2
      exit 1
    fi
    ;;
  *)
    printf 'Richiesta non consentita\n' >&2
    exit 1
    ;;
esac
