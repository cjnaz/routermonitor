# routermonitor

routermonitor logs/monitors DHCP clients (devices) managed by your router.  I use dd-wrt on my home router and 
find over time that I've accumulated several devices on my network that I cannot identify. routermonitor
watches the DHCP leases file on the router (/tmp/dnsmasq.leases with dd-wrt) and tracks changes in a mysql
database.  Any new clients found on the network result in a text message notification.  

- Clients come and go over time, as family members come and visit, and as DHCP leases expire.  The history of 
known clients is tracked by MAC address.  Clients may be manually deleted from the database (i.e., *That laptop went in the tub with kids!* (long gone)).  No changes are ever made on the router.
- Some hostnames are ambiguous, such as '*' and 'android-2ab8700dff69dbfd'.  Notes may be manually added 
for each tracked client. 

## Usage
```
$ ./routermonitor -h
usage: routermonitor [-h] [-u] [-l] [--list-router] [--create-db]
                     [--add-note ADD_NOTE] [--delete] [--MAC MAC] [-V]

Monitor for new devices/clients on the network.

The dd-wrt-based network router is queried for known DHCP clients using 
    $ ssh root@<ROUTER_IP> cat /tmp/dnsmasq.leases
and any new clients are identified and a notification is sent.  
Setup requirements:
    ssh access to the router must be enabled (ssh_keygen, ssh-copy-id).

optional arguments:
  -h, --help           show this help message and exit
  -u, --update         Check the router for new connections and update database.
  -l, --list-db        Print known clients on the network from the database.
  --list-router        Print known clients on the network from the router.
  --create-db          Create a fresh database and populate it with the current clients.
  --add-note ADD_NOTE  Add a note to the db for the specified --MAC.
  --delete             Delete from the db the specified --MAC.
  --MAC MAC            MAC address in the database to be modified or deleted.
  -V, --version        Return version number and exit.
```

## Example output
```
$ ./routermonitor -l
MAC                Hostname                        First seen                 IP Expiry                  Current IP     Notes
00:05:cd:8a:17:8d  Denon-AVR-X1600H                Sat Apr 25 14:30:21 2020   Mon Apr 27 10:41:50 2020   192.168.1.112  -
00:18:61:13:7f:e9  Ooma                            Sat Apr 25 14:30:21 2020   static lease               192.168.1.3    -
00:22:4d:e9:1a:cd  android-2ab8700dff69dbfd        Sat Apr 25 14:30:21 2020   Mon Apr 27 05:29:05 2020   192.168.1.136  What the hell is this? ***
00:95:69:db:4a:2a  lierda_liLink_db4a2a            Sat Apr 25 17:21:05 2020   Sun Apr 26 16:58:33 2020   192.168.1.106  ProTemp BBQ thermometer
44:67:55:02:c6:7f  Orbit_Irrigation_Bhyve          Sat Apr 25 14:30:21 2020   static lease               192.168.1.41   -
64:52:99:90:18:aa  *                               Sat Apr 25 14:30:21 2020   Mon Apr 27 07:12:27 2020   192.168.1.143  Liftmaster gateway 828LM in office
80:7d:3a:48:ce:bf  ESP_48CEBF                      Sat Apr 25 14:30:21 2020   Mon Apr 27 06:58:43 2020   192.168.2.146  Basement lights smartsocket
...
  <23>  known clients.
```
## Setup and Usage notes
- Install the Python mysql-connector library
- Set up SSH access from your host machine to your router - Enable SSH access on your router, generate a local key (ssh-keygen), and push it to the router (ssh-copy-id).
- Enter config info in the `config.cfg` file.
- Set up a mysql/mariadb login and create a database `router` with access permissions, per your settings in config.cfg.
- On first run the database will be populated.
- Do `--add-note` runs to annotate client info, as desired.  Example: `./routermonitor --MAC 80:7d:3a:48:ce:bf --add-note "Basement lights smartsocket"`
- Set up a CRON job to run `routermonitor --update` periodically, such as hourly.
- `./routermonitor --list-db` provides a dump of all known clients over time.
- `./routermonitor --list-router` provides a dump of the currently known clients on the router.
- When run with `--update`, any new clients on the network are added to the database and a text message notification is sent (see config.cfg).  Any changes in IP or IP Expiry time are logged to log.txt at the INFO level.  See `LoggingLevel` in config.cfg.


## Known issues:
- This code was developed and tested, and is supported only on Python 3.7+ on Linux.  'f' strings and newer subprocess module features are utilized in the code.  It may work on Windows.
- Considering... Adding MAC lookup data (i.e., https://oidsearch.s.dd-wrt.com/search/00:22:4D) to the new-client-on-network notification.


## Version history

- 200426 v0.1   New