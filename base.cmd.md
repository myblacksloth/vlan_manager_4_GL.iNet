
# ssh

```bash
ssh root@192.168.8.1
```

# Info sistema e switch type

```bash
cat /etc/openwrt_release
```

```bash
cat /proc/version
```

```bash
uname -a
```

# Struttura UCI network attuale

```bash
uci show network
```

```bash
cat /etc/config/network
```

# Switch e VLAN

```bash
ls /sys/class/net/
```

```bash
swconfig list 2>/dev/null || echo "NO swconfig"
```

```bash
swconfig dev switch0 show 2>/dev/null | head -60
```

```bash
bridge vlan show 2>/dev/null || echo "NO bridge vlan (DSA)"
```

# Firewall

```bash
uci show firewall
```

```bash
cat /etc/config/firewall
```

# DHCP

```bash
uci show dhcp
```

```bash
cat /etc/config/dhcp
```

# Interfacce attive

```bash
ip link show
```

```bash
ip addr show
```

```bash
brctl show 2>/dev/null
```

# ubus: servizi disponibili

```bash
ubus list
```

```bash
ubus list network.*
```

```bash
ubus list uci
```

# Avahi

```bash
which avahi-daemon 2>/dev/null || echo "NO avahi"
```

```bash
cat /etc/avahi/avahi-daemon.conf 2>/dev/null || echo "NO avahi conf"
```

```bash
opkg list-installed | grep avahi
```

# WiFi / SSID

```bash
uci show wireless
```

```bash
cat /etc/config/wireless
```

# Storage

```bash
df -h
```

```bash
df -h /www
```

```bash
ls -la /www/
```


<!-- 
# z

```bash
```

```bash
```

# z

```bash
```

```bash
```

# z

```bash
```

```bash
```

# z

```bash
```

```bash
``` -->
