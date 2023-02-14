# routermonitor

routermonitor logs/monitors DHCP clients (devices) managed by your dhcp server - either dd-wrt or pfSense.
I use pfSense as my home dhcp server and 
find that over time that I've accumulated several devices on my network that I cannot readily identify. routermonitor
watches the DHCP leases and tracks changes in a sqlite3
database.  Any new client found on the network result in a text message notification.  

- Clients come and go over time, as family members come and visit, and as DHCP leases expire.  The history of 
known clients is tracked by MAC address.  Clients may be manually deleted from the database (i.e., *That laptop went in the tub with kids!* (long gone)).  No changes are ever made on the dhcp server.
- Some hostnames are ambiguous, such as '*' and 'android-2ab8700dff69dbfd'.  Notes may be manually added 
for each tracked client. 
- The Organization Unique ID for for each devices' MAC address is looked up and added to the database, often providing enough info to identify strange devices.

Note:  _router_ and _dhcp server_ are used somewhat interchangeable in this documentation.  This utility was originally written for dd-wrt, which runs on routers.  Newer versions support pfSense as a dhcp server.  

<br/>

---

## Notable changes since prior release
3.0 - Converted to package format, updated to cjnfuncs 2.0

<br/>

---

## Usage
```
$ routermonitor -h
usage: routermonitor [-h] [--update] [--list-db] [--list-dhcp-server]
                     [--sort-by {hostname,IP,first_seen,expiry,MAC,MACOUI,notes}]
                     [--create-db] [--note NOTE] [--delete] [--MAC MAC]
                     [--config-file CONFIG_FILE] [--print-log] [--service]
                     [--setup-user] [--setup-site] [-V]
                     [SearchTerm]

Monitor for new devices/clients on the network.

The network dhcp server is queried for currently known DHCP clients.
Any new clients are identified and a notification is sent.  
3.0

positional arguments:
  SearchTerm            Print database records containing this text.

optional arguments:
  -h, --help            show this help message and exit
  --update, -u          Check the dhcp server for new connections and update the database.
  --list-db, -l         Print known clients on the network from the database (default mode).
  --list-dhcp-server, -r
                        Print known clients on the network from the dhcp server.
  --sort-by {hostname,IP,first_seen,expiry,MAC,MACOUI,notes}, -s {hostname,IP,first_seen,expiry,MAC,MACOUI,notes}
                        Sort --list-db and --list-dhcp-server output. Overrides config SortBy. Default <hostname> if neither specified.
  --create-db           Create a fresh database and populate it with the current dhcp server clients.
  --note NOTE, -n NOTE  Add a note to the db for the specified --MAC.
  --delete              Delete from the db the specified --MAC.
  --MAC MAC, -m MAC     MAC address for --add-note or --delete.
  --config-file CONFIG_FILE, -c CONFIG_FILE
                        Path to the config file (Default <routermonitor.cfg)> in user/site config directory.
  --print-log, -p       Print the tail end of the log file (default last 40 lines).
  --service             Run updates in an endless loop for use as a systemd service.
  --setup-user          Install starter files in user space.
  --setup-site          Install starter files in system-wide space. Run with root prev.
  -V, --version         Return version number and exit.
```

<br/>

---

## Example output
```
$ routermonitor --list-db
$ ./routermonitor
 WARNING:  ========== routermonitor (3.0) ==========
    INFO:  Config file </path/to/routermonitor.cfg>
Hostname                   First seen           Current IP     IP Expiry            MAC                MAC Org Unique ID               Notes
Denon-AVR-X1600H           2020-05-22 18:23:30  192.168.1.112  2020-05-24 10:42:07  00:05:cd:8a:ab:8d  Denon, Ltd.                     -
Galaxy-S10-jen             2020-05-22 18:23:33  192.168.1.114  2020-05-22 18:33:29  10:98:c3:80:cd:b2  Murata Manufacturing Co., Ltd.  -
amazon-b6f1c2033           2020-05-23 06:45:05  192.168.1.118  2020-05-24 12:57:19  38:f7:3d:16:ef:40  Amazon Technologies Inc.        Wife's Kindle Fire
espressif                  2020-05-22 18:23:35  192.168.2.121  2020-05-24 11:45:03  44:67:55:02:01:7f  Orbit Irrigation                -
Flex5                      2020-05-22 18:23:36  192.168.1.123  2020-05-24 11:59:32  50:5b:c2:e1:23:ef  Liteon Technology Corporation   -
*                          2020-05-22 18:23:37  192.168.1.144  2020-05-24 15:21:31  64:52:99:90:45:aa  The Chamberlain Group, Inc      Liftmaster gateway 828LM in office
MyQ-F8C                    2020-05-22 18:23:38  192.168.1.143  2020-05-24 11:07:13  64:52:99:91:67:51  The Chamberlain Group, Inc      Garage door opener
ESP_48CEBF                 2020-05-22 18:23:40  192.168.2.146  2020-05-24 08:51:01  80:7d:3a:48:89:bf  Espressif Inc.                  Basement lights smartsocket
*                          2020-05-22 18:23:41  192.168.2.133  2020-05-24 15:00:59  8c:85:80:1d:ab:69  Smart Innovation LLC            Eufy doorbell
RPi1                       2020-05-22 18:23:42  192.168.1.31   static lease         b8:27:eb:25:cd:f7  Raspberry Pi Foundation         -
FireStick4k                2020-05-22 18:23:44  192.168.1.40   static lease         cc:9e:a2:56:ef:c9  Amazon Technologies Inc.        -
...
  <23>  known clients.
```

<br/>

---

## Setup and Usage notes
- Install routermonitor from PyPI (`pip install routermonitor`)
- Install the initial configuration files (`routermonitor --setup-user` places files at `~/.config/routermonitor`).
- Edit/configure `routermonitor.cfg`, `creds_SMTP`, and `creds_routermonitor` as needed.
  - If using a dd-wrt router, set up SSH access from your host machine to your router: Enable SSH access on your router, generate a local key (ssh-keygen), and add the content of the `~/.ssh/id_rsa.pub` file into the dd-wrt GUI ssh access config.
- Run `routermonitor` manually to build the devices/clients database.
- Do `routermonitor --add-note` runs to annotate client info, as desired.  Example: `routermonitor --MAC 80:7d:3a:48:ce:bf --add-note "Basement lights smartsocket"`.
- `routermonitor --list-db` (equivalent to just `routermonitor`) provides a list of all known clients over time.  `--sort-by hostname` may be useful.  The report may be sorted by MAC, hostname, IP, first_seen, expiry, notes, or MACOUI (default `SortBy` may be set in the config file).
- `routermonitor --list-dhcp-server` provides a list of the currently known DHCP clients on the server. `--sort-by` is supported with fields MAC, hostname, IP, and expiry (MACOUI is not reported by the server).
- `routermonitor amaz` provides a list of all clients in the database that have the string 'amaz' in any field (two in the above example output) while `routermonitor .2.` lists all clients on my Guest WiFi (192.168.2.*, three in the above example output).
- `routermonitor --update` finds any new clients on the network, adds them to the database, and sends a text message notification (see routermonitor.cfg).  Any changes in IP address or IP Expiry time are logged to log_routermonitor.txt at the INFO level.  See `LogLevel` in routermonitor.cfg.
- Optionally set up the routermonitor systemd service. A template .service file is provided in the config directory.
- When running in service mode (continuously looping) the config file may be edited and is reloaded when changed. This allows for changing settings without having to restart the service.
- Supported on Python3.6+ on Linux and Windows.

<br/>

---

## Version history
- 3.0 230215 - Converted to package format, updated to cjnfuncs 2.0
- 2.0 221023 - Revamped, moved from mysql to sqlite3
- ...
- 0.1 200426 - New