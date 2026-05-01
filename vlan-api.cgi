#!/bin/sh

printf 'Content-Type: text/plain\r\n'
printf 'Cache-Control: no-store\r\n'
printf '\r\n'

if [ "$REQUEST_METHOD" = "POST" ]; then
  POST_DATA="$(dd bs=1 count="${CONTENT_LENGTH:-0}" 2>/dev/null)"
  if [ -n "$POST_DATA" ]; then
    QUERY_STRING="${QUERY_STRING:+$QUERY_STRING&}$POST_DATA"
  fi
fi

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
config="$(url_decode "$(query_value config)")"
section="$(url_decode "$(query_value section)")"
type="$(url_decode "$(query_value type)")"
option="$(url_decode "$(query_value option)")"
value="$(url_decode "$(query_value value)")"
name="$(url_decode "$(query_value name)")"
service="$(url_decode "$(query_value service)")"

allow_config() {
  case "$1" in
    network|wireless|dhcp|firewall) return 0 ;;
    *) return 1 ;;
  esac
}

uci_ref() {
  if [ -n "$option" ]; then
    printf '%s.%s.%s' "$config" "$section" "$option"
  else
    printf '%s.%s' "$config" "$section"
  fi
}

case "$action:$path" in
  read:/etc/config/network|read:/etc/config/wireless|read:/etc/config/dhcp|read:/etc/config/firewall|read:/etc/avahi/avahi-daemon.conf)
    if [ -r "$path" ]; then
      cat "$path"
    else
      printf 'File non leggibile: %s\n' "$path" >&2
      exit 1
    fi
    ;;
  file-write:/etc/avahi/avahi-daemon.conf)
    tmp="/tmp/vlan-api-avahi.$$"
    printf '%s' "$value" > "$tmp" && mv "$tmp" "$path"
    printf 'OK\n'
    ;;
  uci-add:*)
    allow_config "$config" || { printf 'Config non consentita\n' >&2; exit 1; }
    [ -n "$type" ] || { printf 'Tipo mancante\n' >&2; exit 1; }
    if [ -n "$name" ]; then
      uci set "$config.$name=$type"
      printf '%s\n' "$name"
    else
      uci add "$config" "$type"
    fi
    ;;
  uci-set:*)
    allow_config "$config" || { printf 'Config non consentita\n' >&2; exit 1; }
    [ -n "$section" ] || { printf 'Sezione mancante\n' >&2; exit 1; }
    [ -n "$option" ] || { printf 'Opzione mancante\n' >&2; exit 1; }
    uci set "$(uci_ref)=$value"
    printf 'OK\n'
    ;;
  uci-delete:*)
    allow_config "$config" || { printf 'Config non consentita\n' >&2; exit 1; }
    [ -n "$section" ] || { printf 'Sezione mancante\n' >&2; exit 1; }
    uci delete "$(uci_ref)" 2>/dev/null || true
    printf 'OK\n'
    ;;
  uci-commit:*)
    allow_config "$config" || { printf 'Config non consentita\n' >&2; exit 1; }
    uci commit "$config"
    printf 'OK\n'
    ;;
  service:*)
    case "$service" in
      network-reload) /etc/init.d/network reload 2>/dev/null || service network reload 2>/dev/null || true ;;
      wifi-reload) wifi reload 2>/dev/null || true ;;
      firewall-restart) /etc/init.d/firewall restart 2>/dev/null || service firewall restart 2>/dev/null || true ;;
      avahi-restart) /etc/init.d/avahi-daemon restart 2>/dev/null || service avahi-daemon restart 2>/dev/null || true ;;
      *) printf 'Servizio non consentito\n' >&2; exit 1 ;;
    esac
    printf 'OK\n'
    ;;
  *)
    printf 'Richiesta non consentita\n' >&2
    exit 1
    ;;
esac
