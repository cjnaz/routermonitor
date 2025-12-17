# routermonitor

routermonitor logs/monitors DHCP clients (devices) managed by your pfSense DHCPv4 server.
I use pfSense as my home DHCP server and 
find that over time that I've accumulated several devices on my network that I cannot readily identify. routermonitor
watches the DHCP leases and tracks changes in a sqlite3
database.  Any new client found on the network result in a text message notification.

- Clients come and go over time, as family members come and visit, and as DHCP leases expire.  The history of 
known clients is tracked by MAC address.  Clients may be manually deleted from the database (i.e., *That laptop went in the tub with kids!* (long gone)).  No changes are ever made on the dhcp server.
- Some hostnames are ambiguous, such as '*' and 'android-2ab8700dff69dbfd'.  Notes may be manually added for each tracked client. 
- The Organization Unique ID for for each devices' MAC address is looked up and added to the database, often providing enough info to identify strange devices.

Definition of terms:
- _device_ refers to a pfSense(+) DHCP server on your network. pfSense devices are also referred to as the _router_ or _dhcp server_ in this documentation
- _client_ is used in this documentation to refer to a host/client on your network that has requested an IP address via DHCP.

Supports
- Linux and Windows
- Python 3.9+
- pfSense+ 25.07.1 and above, and corresponding pfSense CE versions (2.8.0+?)
- pfSense ISC and Kea servers
- pfSense+ MIM API, UnofficialV2 API, and Status > DHCP Leases page scrape modes

<br/>

---

## Notable changes since prior release V3.1

- Removed support for dd-wrt
- Updated page scrape mode to be compatible with more recent DHCP Leases page layout - Works with both ISC and Kea DHCP servers.
- Added support for the new Nexus multi-instance management (MIM) API
- Added support for the Unofficial V2 API (https://pfrest.org/)
- Added support for last_seen (most recently seen) tracking and reporting

<br/>

---

## Usage
```
$ routermonitor -h
usage: routermonitor [-h] [--update] [--list-db] [--list-dhcp-server] [--sort-by {hostname,ip,first_seen,last_seen,expiry,mac,macoui,notes}] [--create-db] [--note NOTE] [--delete] [--MAC MAC] [--config-file CONFIG_FILE] [--print-log]
                     [--service] [-v] [--setup-user] [--setup-site] [-V]
                     [SearchTerm]

Monitor for new devices/clients on the network.

The network dhcp server is queried for currently known DHCP clients.
Any new clients are identified and a notification is sent.  
4.0

positional arguments:
  SearchTerm            Print database records containing this text.

options:
  -h, --help            show this help message and exit
  --update, -u          Check the dhcp server for new connections and update the database.
  --list-db, -l         Print known clients on the network from the database (default mode).
  --list-dhcp-server, -r
                        Print known clients on the network from the dhcp server.
  --sort-by {hostname,ip,first_seen,last_seen,expiry,mac,macoui,notes}, -s {hostname,ip,first_seen,last_seen,expiry,mac,macoui,notes}
                        Sort --list-db and --list-dhcp-server output. Overrides config SortBy. Default <hostname> if neither specified.
  --create-db           Create a fresh database and populate it with the current dhcp server clients.
  --note NOTE, -n NOTE  Add a note to the db for the specified --MAC.
  --delete              Delete from the db the specified --MAC.
  --MAC MAC, -m MAC     MAC address for --add-note or --delete.
  --config-file CONFIG_FILE, -c CONFIG_FILE
                        Path to the config file (Default <routermonitor.cfg)> in user/site config directory.
  --print-log, -p       Print the tail end of the log file (default last 40 lines).
  --service             Run updates in an endless loop for use as a systemd service.
  -v, --verbose         Print status and activity messages (-vv for debug logging)
  --setup-user          Install starter files in user space.
  --setup-site          Install starter files in system-wide space. Run with root prev.
  -V, --version         Return version number and exit.
```

<br/>

---

## Example output
```
$ routermonitor 
 WARNING:  ========== routermonitor (4.0) ==========
 WARNING:  Config file </path/to/routermonitor.cfg>
hostname                   first_seen           last_seen            ip               expiry               device             mac                macoui                          notes    (Sorted by <last_seen>)
Denon-AVR-X1600H           2020-05-22 18:23:30  2025-11-29 21:29:18  192.168.1.112    2020-05-24 10:42:07  pfsense.mylan      00:05:cd:8a:ab:8d  Denon, Ltd.                     -
Galaxy-S10-jen             2020-05-22 18:23:33  2025-11-30 11:01:02  192.168.1.114    2020-05-22 18:33:29  pfsense.mylan      10:98:c3:80:cd:b2  Murata Manufacturing Co., Ltd.  -
amazon-b6f1c2033           2020-05-23 06:45:05  2025-11-30 11:06:36  192.168.1.118    2020-05-24 12:57:19  pfsense.mylan      38:f7:3d:16:ef:40  Amazon Technologies Inc.        Wife's Kindle Fire
espressif                  2020-05-22 18:23:35  2025-11-30 11:23:37  192.168.2.121    2020-05-24 11:45:03  pfsense.mylan      44:67:55:02:01:7f  Orbit Irrigation                -
Flex5                      2020-05-22 18:23:36  2025-11-30 11:25:41  192.168.1.123    2020-05-24 11:59:32  pfsense.mylan      50:5b:c2:e1:23:ef  Liteon Technology Corporation   -
*                          2020-05-22 18:23:37  2025-11-30 11:31:48  192.168.1.144    2020-05-24 15:21:31  pfsense.mylan      64:52:99:90:45:aa  The Chamberlain Group, Inc      Liftmaster gateway 828LM in office
MyQ-F8C                    2020-05-22 18:23:38  2025-11-30 11:32:15  192.168.1.143    2020-05-24 11:07:13  pfsense.mylan      64:52:99:91:67:51  The Chamberlain Group, Inc      Garage door opener
ESP_48CEBF                 2020-05-22 18:23:40  2025-11-30 11:33:19  192.168.2.146    2020-05-24 08:51:01  pfsense.mylan      80:7d:3a:48:89:bf  Espressif Inc.                  Basement lights smartswitch
*                          2020-05-22 18:23:41  2025-11-30 11:34:23  192.168.2.133    2020-05-24 15:00:59  pfsense.mylan      8c:85:80:1d:ab:69  Smart Innovation LLC            Eufy doorbell
RPi1                       2020-05-22 18:23:42  2025-11-30 11:36:13  192.168.1.31     static lease         pfsense.mylan      b8:27:eb:25:cd:f7  Raspberry Pi Foundation         -
FireStick4k                2020-05-22 18:23:44  2025-11-30 11:37:04  192.168.1.40     static lease         pfsense.mylan      cc:9e:a2:56:ef:c9  Amazon Technologies Inc.        -
...
  <73>  known clients.
```

<br/>

---

## Setup and Usage notes
- Install routermonitor from PyPI (`pip install routermonitor`)
- Install the initial configuration files (`routermonitor --setup-user` places files at `~/.config/routermonitor`).
- Decide on which DHCP clients list lookup method you wish to use (see more details below):
  - `Mode = MIM_API` is the best choice if you are using a Netgate pfSense+ device or have a Plus license - Fast and best information. If using the MIM API you will need to manually install the Netgate pfsense-api (see below).
  - `Mode = Unofficial_APIV2` is second best - Fast.  No `last_seen` or `expiry` info available for static mapped clients.
  - `Mode = Page_Scrape` is is completely functional, but slower than the APIs since pfSense logins can be slow.  Matches `Unofficial_APIV2` results
- Edit/configure `routermonitor.cfg`, `creds_SMTP`, and `creds_routermonitor` as needed.
- Run `routermonitor` once manually to build the devices/clients database.  It will take a few moments for rate-limited MACOUI lookups.
- Do `routermonitor --add-note` runs to annotate client info, as desired.  Example: `routermonitor --MAC 80:7d:3a:48:ce:bf --add-note "Basement lights smartswitch"`.
- `routermonitor --list-db` (equivalent to just `routermonitor`) provides a list of all known clients over time.  `--sort-by hostname` may be useful.  The report may be sorted by _mac, hostname, ip, device, first_seen,
last_seen, expiry, notes, or macoui_.  The default `SortBy` may be set in the config file.
- `routermonitor --list-dhcp-server` provides a list of the currently known DHCP clients on the server. `--sort-by` is supported with fields _mac, hostname, ip, device, last_seen, and expiry_.
- `routermonitor amaz` provides a list of all clients in the database that have the string 'amaz' in any field (two in the above example output) while `routermonitor .2.` lists all clients on my Guest WiFi (192.168.2.*, three in the above example output).  Filtering is supported with `--list-dhcp-server` also.
- `routermonitor --update` finds any new clients on the network, adds them to the database, and sends a text message notification (see routermonitor.cfg).  Any changes in IP address or IP Expiry time are logged to log_routermonitor.txt at the INFO level.  See `LogLevel` in routermonitor.cfg.
- Optionally set up the routermonitor systemd service. A template .service file is provided in the config directory.
- When running in service mode (continuously looping) the config file may be edited and is reloaded when changed. This allows for changing settings without having to restart the service.

<br/>

---

## Using the Netgate Nexus MIM API (pfSense+ devices/appliances only) (`Mode = MIM_API`)

Setup
- Clone the Python interface github distribution to your local filesystem

			cd <my-temp-space>
			git clone https://github.com/Netgate/pfsense-api.git
			# creates ./pfsense-api
			pip install ./pfsense-api/py
			# Once installed the cloned directory <my-temp-space>/pfsense-api may be deleted.
	
- In the pfsense+ GUI set the device to HTTPS access mode
  - The API will not work in HTTP mode
  - System > Advance > Admin Access > Protocol = HTTPS (SSL/TLS) 
    - This uses a self-signed certificate, so your browser may want your approval to connect.
    - For more secure access, see below for setting up a certificate authority. Do this step before enabling Netgate Nexus Controller so that port 8443 is properly set up with the _internally signed 'Server Certificate'_.  If you set up the CA after enabling Netgate Nexus then simply disable and re-enable Netgate Nexus Controller again.

- Enable Netgate Nexus
	- System > Advanced > Netgate Nexus > Enable Netgate Nexus Controller
		- This enables the official Nexus MIM API.  Without paying for a license you can access only the `localhost` device.
		- See https://docs.netgate.com/pfsense/en/latest/nexus/setup.html
		- The user must have full admin privileges (be a member of the admins group), as of 25.07.1 RELEASE.
- **See the routermonitor.cfg starter file for configuring access to the MIM API.**

Notes and considerations

1) A key benefit of using the MIM_API mode is that real DHCP lease start and expiry times are available.  In the other modes all statically mapped clients simply show as "static lease".
1) Netgate Nexus and the MIM API were first released on pfSense+ version 25.07. For older pfSense+ versions and the CE version see the Unofficial V2 API.
1) With the MIM API the `hostname` field comes first from the pfSense+ DHCP static mappings, with fallback to the hostname provided by the client on a DHCP request. The hostname is lower case, as by-spec hostnames are case insensitive.  Windows clients will have a '.' appended to the hostname.
1) Kea DHCP server only issues and logs IP assignments from clients that actively send a DHCP request (this may be true also for the ISC server).  For static mapped clients, Kea issues the specified fixed address, with a 2 hour lease, meaning that a statically mapped clients must periodically request a new IP (and gets back the fixed assignment).  _The MIM API only reports actually requested/issued IP addresses._ Clients with statically assigned addresses but not on the network wont show up in the list. Therefore, long-story-short, _the MIM API may report a subset of the statically assigned IP addresses/clients._ `routermonitor` accumulates the history of connected clients, so the transient nature of the lease list is not a problem.
Note that the other update methods (Unofficial_APIV2 and Page_Scrape) show all static mappings.
1) Netgate Nexus on pfSense+ devices provides the multi-instance management (MIM) API, with specific support for accessing/controlling multiple pfSense+ devices on a network from a single "controller" (the master pfSense+ device).  MIM API accesses have a `device_id` field, which specifies which pfSense+ instance the API request targets.  `routermonitor` supports specifying a series of `Devices` in the config file.  The devices will be accessed in the order listed with all found clients merged into one DHCP clients list.  The default Devices lists is `['localhost']`. If you have a multi-instance network you will need a paid subscription to use Nexus across devices, and then the MIM API can also be used across devices.

<br/>

---

## Using the Unofficial V2 API (`Mode = Unofficial_APIV2`)

Setup
- Install the Unofficial V2 API on your pfSense device.  This API works on both Netgate pfSense+ devices (24.11+) and on CE devices (2.8.0+).  See https://pfrest.org/INSTALL_AND_CONFIG/. The install can be done via an SSH login, using the device console, or using the GUI Diagnostics > Command Prompt > Execute Shell Command. Example for pfSense+ 24.11 (_do install the correct version_):

      pkg-static -C /dev/null add https://github.com/jaredhendrickson13/pfsense-api/releases/latest/download/pfSense-24.11-pkg-RESTAPI.pkg

- To enable the API, briefly, you will need to, at System > REST API > Settings, Enable the API, set Allowed Interfaces, and set up the Authentication Method to `Key`.  On the Keys tab, create a key and save it to the routermonitor config file `API_key`.


Notes and considerations
- This API returns the same information as on the Status > DHCP Leases page, including static mapped clients that are not currently on the network.
- This API runs a whole lot faster than the Page_Scrape mode.
- Static mapped clients will report `static lease` in the `expiry` column.
- `last_seen` and `expiry` are only reported for non-static mapped clients.
- The reported device field will always be the URL to the pfSense device since there is no multi-device support.

<br/>

---

## Using page scrape mode (`Mode = Page_Scrape`)

Setup
- No setup necessary beyond entering your GUI admin login credentials in the routermonitor config file. **Actually, always put credentials in a file hidden from other users and import that file in the routermonitor config.**

- For better security, you may wish to create a limited access user (System > User Manager) with just these privileges:

      WebCfg - Dashboard (all)	Allow access to all pages required for the dashboard.	
      WebCfg - Status: DHCP leases	Allow access to the 'Status: DHCP leases' page.

Notes and considerations
- This method attempts to read and parse the Status > DHCP Leases page.  On first access the Login page is presented and routermonitor proceeds to log in and then access the Leases page.  All of this take several seconds.
- See the Notes and considerations for the Unofficial V2 API, above.

<br/>

---
## Using a Certificate Authority

Each access mode supports verified SSL access by configuring a certificate authority within pfSense. 
In short, to set up certificates for use with routermonitor:

  - Create a _self-signed 'CA certificate'_ (System > Certificates > Authorities), then 'Export CA' to a file.  This is the CA public key.  Set the path to this file in the routermonitor config file `CA_path` param.
  - Create a _internally signed 'Server Certificate'_ (System > Certificates > Certificates) that refers to the new CA certificate (thus not a _self-signed server certificate_), with a Common Name (CN) or SAN entry set to the URL being used to access the device by routermonitor.
  - Change the webGUI (webConfigurator) to use the new internally signed server certificate (System > Advanced > Admin Access > SSL/TLS Certificate).
  Once set, the new server certificate will show as in use by the 'webConfigurator'. Delete the original server cert. Your browser may need some nudging at this point.
  - If applicable, change the MIM API to use the new internally signed server certificate (System > Advanced > Netgate Nexus > TLS Certificate).

Use of a CA is optional.  `CA_path` defaults to False if not defined, which disables SSL verification.


<br/>

---

## Version history
- 4.0 251220 - Remove dd-wrt support, Added MIM_API and Unofficial_APIV2 support.
- 3.1 240106 - Fixed service mode exit when pfsense router is not accessible.  Added retries to lookup_MAC().
  - Adjusted for cjnfuncs V2.1 (module partitioning).
  - Fixed service mode exit when pfsense router is not accessible.
  - Added retries to lookup_MAC().
  - Adjusted pfsense DHCP Leases table parsing (case changes in header) in 23.09-RELEASE.
  - Adjusted pfsense DHCP Leases table parsing for ISC DHCP EOL header warning.


- 3.0.5 230226 - Fixed inclusion of deployment_files
- 3.0 230215 - Converted to package format, updated to cjnfuncs 2.0
- 2.0 221023 - Revamped, moved from mysql to sqlite3
- ...
- 0.1 200426 - New