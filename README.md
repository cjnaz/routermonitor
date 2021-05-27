# routermonitor

routermonitor logs/monitors DHCP clients (devices) managed by your router.  I use dd-wrt on my home router and 
find over time that I've accumulated several devices on my network that I cannot identify. routermonitor
watches the DHCP leases file on the router (/tmp/dnsmasq.leases with dd-wrt) and tracks changes in a mysql
database.  Any new clients found on the network result in a text message notification.  

- Clients come and go over time, as family members come and visit, and as DHCP leases expire.  The history of 
known clients is tracked by MAC address.  Clients may be manually deleted from the database (i.e., *That laptop went in the tub with kids!* (long gone)).  No changes are ever made on the router.
- Some hostnames are ambiguous, such as '*' and 'android-2ab8700dff69dbfd'.  Notes may be manually added 
for each tracked client. 
- The Organization Unique ID for for each devices' MAC address is looked up and added to the database, often providing enough info to identify strange devices.

## Usage
```
$ ./routermonitor -h
usage: routermonitor [-h] [-u] [-l] [-r]
                     [-s {hostname,IP,first_seen,expiry,MAC,MACOUI,notes}]
                     [--create-db] [-a ADD_NOTE] [--delete] [-M MAC]
                     [--config-file CONFIG_FILE] [--log-file LOG_FILE]
                     [--service] [--swizzle-db] [--swizzle-commit] [-V]
                     [SearchTerm]

Monitor for new devices/clients on the network.

The dd-wrt-based network router is queried for known DHCP clients using 
    $ ssh root@<ROUTER_IP> cat /tmp/dnsmasq.leases
Any new clients are identified and a notification is sent.  
See the README.md for setup requirements.
V0.7 210523

positional arguments:
  SearchTerm            Print database records containing this text.

optional arguments:
  -h, --help            show this help message and exit
  -u, --update          Check the router for new connections and update database.
  -l, --list-db         Print known clients on the network from the database.
  -r, --list-router     Print known clients on the network from the router.
  -s {hostname,IP,first_seen,expiry,MAC,MACOUI,notes}, --sort-by {hostname,IP,first_seen,expiry,MAC,MACOUI,notes}
                        Sort --list-db and --list-router output (Default 'MAC').
  --create-db           Create a fresh database and populate it with the current clients.
  -a ADD_NOTE, --add-note ADD_NOTE
                        Add a note to the db for the specified --MAC.
  --delete              Delete from the db the specified --MAC.
  -M MAC, --MAC MAC     MAC address for --add-note or --delete.
  --config-file CONFIG_FILE
                        Path to the config file (Default <<install directory>/routermonitor.cfg)>.
  --log-file LOG_FILE   Path to log file (Default <<install directory>/log_routermonitor.txt>).
  --service             Run updates in an endless loop for use as a systemd service.
  --swizzle-db          Upgrade db structure/content.
  --swizzle-commit      Make db upgrade permanent (else temporary).
  -V, --version         Return version number and exit.
```

## Example output
```
$ routermonitor --list-db
Hostname                   First seen                Current IP     IP Expiry                 MAC                MAC Org Unique ID               Notes
Denon-AVR-X1600H           Fri May 22 18:23:30 2020  192.168.1.112  Sun May 24 10:42:07 2020  00:05:cd:8a:17:8d  Denon, Ltd.                     -
Galaxy-S10-jen             Fri May 22 18:23:33 2020  192.168.1.114  Fri May 22 18:33:29 2020  10:98:c3:80:bf:b2  Murata Manufacturing Co., Ltd.  -
amazon-b6f1c2033           Sat May 23 06:45:05 2020  192.168.1.118  Sun May 24 12:57:19 2020  38:f7:3d:16:f0:40  Amazon Technologies Inc.        Wife's Kindle Fire
espressif                  Fri May 22 18:23:35 2020  192.168.2.121  Sun May 24 11:45:03 2020  44:67:55:02:c6:7f  Orbit Irrigation                -
Flex5                      Fri May 22 18:23:36 2020  192.168.1.123  Sun May 24 11:59:32 2020  50:5b:c2:e1:bf:ef  Liteon Technology Corporation   -
*                          Fri May 22 18:23:37 2020  192.168.1.144  Sun May 24 15:21:31 2020  64:52:99:90:18:aa  The Chamberlain Group, Inc      Liftmaster gateway 828LM in office
MyQ-F8C                    Fri May 22 18:23:38 2020  192.168.1.143  Sun May 24 11:07:13 2020  64:52:99:91:8c:51  The Chamberlain Group, Inc      Garage door opener
ESP_48CEBF                 Fri May 22 18:23:40 2020  192.168.2.146  Sun May 24 08:51:01 2020  80:7d:3a:48:ce:bf  Espressif Inc.                  Basement lights smartsocket
*                          Fri May 22 18:23:41 2020  192.168.2.133  Sun May 24 15:00:59 2020  8c:85:80:1d:60:69  Smart Innovation LLC            Eufy doorbell
RPi1                       Fri May 22 18:23:42 2020  192.168.1.31   static lease              b8:27:eb:25:df:f7  Raspberry Pi Foundation         -
FireStick4k                Fri May 22 18:23:44 2020  192.168.1.40   static lease              cc:9e:a2:56:b2:c9  Amazon Technologies Inc.        -
...
  <23>  known clients.
```
## Setup and Usage notes
- Supported on Python3 only.  Developed on Centos 7.8 with Python 3.6.8+.  This tool _may_ work on Windows - not  tested or supported.
- Install the Python mysql-connector and requests libraries.
- Set up SSH access from your host machine to your router - Enable SSH access on your router, generate a local key (ssh-keygen), and push it to the router (ssh-copy-id).
- Edit/enter the config info in the `routermonitor.cfg` file.
- Set up a mysql/mariadb login and create a database `router` with access permissions, per your `DB_*` settings in routermonitor.cfg.  Recommend putting DB_USER and DB_PASS is a private credentials file in your home directory.
- On first run the database will be populated.
- Do `./routermonitor --add-note` runs to annotate client info, as desired.  Example: `./routermonitor --MAC 80:7d:3a:48:ce:bf --add-note "Basement lights smartsocket"`.
- `./routermonitor --list-db` provides a list of all known clients over time.  `--sort-by hostname` may be useful.  The report may be sorted by MAC, hostname, IP, first_seen, expiry, notes, or MACOUI (default sort by MAC address).
- `./routermonitor --list-router` provides a list of the currently known DHCP clients on the router.  `--sort-by` is supported with fields MAC, hostname, IP, and expiry (MACOUI is not reported by the router).
- `./routermonitor amaz` provides a list of all clients in the database that have the string 'amaz' in any field - two in the above example output. `./log_routermonitor .2.` lists all clients on my Guest WiFi (192.168.2.*, three in the above example output).
- `./routermonitor --update` finds any new clients on the network, adds them to the database, and sends a text message notification (see routermonitor.cfg).  Any changes in IP or IP Expiry time are logged to log_routermonitor.txt at the INFO level.  See `LoggingLevel` in routermonitor.cfg.
- Set up a CRON job to run `routermonitor --update` periodically, such as hourly.
- Alternately, install routermonitor as a systemd service, which periodically does updates.  An example `routermonitor.service` file is provided.  Control the update interval in your routermonitor.cfg file.  


## Known issues:
- None

## Version history
- 210523 V0.7   New device message tweaks, Requires funcs3 V0.7 min for import of credentials file and config reload.
  Added --config-file and --log-file switches
- 210215 V0.6   Added --swizzle-db, --swizzle-commit, and reworked first_seen and expiry to Int storage.
- 210125 V0.5   Added `--service` mode.
- 200715 v0.4   Added `--sort-by`.
- 200530 v0.3   Added database record search.
- 200527 v0.2.2 Bug fix for single line lookup_MAC response losing last letter.
- 200526 v0.2.1 Bug fix for finding not just first new device on an update run.
- 200523 v0.2  Track host name changes, support single quotes in notes, support older subprocess.run() output capture.
- 200426 v0.1  New