#!/usr/bin/env python3
"""Monitor for new devices/clients on the network.

The network dhcp server is queried for currently known DHCP clients.
Any new clients are identified and a notification is sent.  
"""

#==========================================================
#
#  Chris Nelson, 2020 - 2024
#
#==========================================================

import argparse
import subprocess
import sys
import re
import time
import datetime
import os.path
import collections
# import html       # Needed for alternate MACOUI lookup implementation
import sqlite3
import urllib3
import requests
import signal
import base64
import json
from lxml import html as _html
from pathlib import Path

#
# Controller APIs
#
from pfapi.models import *
from pfapi.api.login import login, refresh_access_token
from pfapi.types import Response

from pfapi.api.mim import get_controlled_devices
from pfapi import Client, AuthenticatedClient

#
# Per-device api
#
# from pfapi.api.system import get_status, get_system_update_info
# from pfapi.api.aliases import firewall_get_aliases
from pfapi.api.services import get_dhcp_leases

try:
    import importlib.metadata
    __version__ = importlib.metadata.version(__package__ or __name__)
except:
    try:
        import importlib_metadata
        __version__ = importlib_metadata.version(__package__ or __name__)
    except:
        __version__ = "3.1 X"

from cjnfuncs.core import logging, set_toolname, set_logging_level
from cjnfuncs.configman import config_item
from cjnfuncs.timevalue import timevalue
from cjnfuncs.mungePath import mungePath
from cjnfuncs.deployfiles import deploy_files
from cjnfuncs.SMTP import snd_notif
import cjnfuncs.core as core



# Configs / Constants
TOOLNAME            = 'routermonitor'
CONFIG_FILE         = 'routermonitor.cfg'
PRINTLOGLENGTH      = 40
EXIT_GOOD           = 0
EXIT_FAIL           = 1
# SORT_MODES          = ['hostname', 'IP', 'first_seen', 'last_seen', 'expiry', 'MAC', 'MACOUI', 'notes']
SORT_MODES          = ['hostname', 'ip', 'first_seen', 'last_seen', 'expiry', 'mac', 'macoui', 'notes']
DEFAULT_SORT_MODE   = 'hostname'   # If not specified in config file or command line
# PY_VERSION          = sys.version_info
# SYSTEM              = platform.system()     # 'Linux', 'Windows', ...


#=====================================================================================
#=====================================================================================
#   m a i n
#=====================================================================================
#=====================================================================================

def main():

    if args.verbose in [1, 2]:
        set_logging_level (['not possible', logging.INFO, logging.DEBUG][args.verbose], save=False)

    # logging.getLogger().setLevel(20)  # Set INFO level (20) for interactive use.  Set to 10 for debugging.
    db_connect()

    # List known clients from database
    if args.list_db or args.SearchTerm != None:
        get_database_clients(dump=True, search=args.SearchTerm)
        cleanup(EXIT_GOOD)


    # List known clients from dhcp server
    if args.list_dhcp_server:
        get_dhcp_clients(dump=True)
        cleanup(EXIT_GOOD)


    # Add a note for a client to the database
    if args.note is not None:
        if args.MAC is None:
            logging.error ("Must specify the --MAC when using --add-note")
            cleanup(EXIT_FAIL)
        clients = db_cursor.execute(f"SELECT * FROM {config.getcfg('DB_Table')} WHERE MAC = '{args.MAC}'").fetchall()
        if len(clients) == 1:
            new_note = args.note.replace("'", "''")   # single quotes need to be doubled up in SQL
            clients = get_database_clients()
            logging.info (f"Note added for {args.MAC} / {clients[args.MAC]['hostname']}:  {new_note}")
            db_cursor.execute(f"UPDATE {config.getcfg('DB_Table')} SET notes = '{new_note}' WHERE MAC = '{args.MAC}'")
            db_connection.commit()
            cleanup(EXIT_GOOD)
        elif len(clients) > 1:
            logging.error (f"MAC address <{args.MAC}> found more than once in the database - Aborting")
            cleanup(EXIT_FAIL)
        else:
            logging.error (f"MAC address <{args.MAC}> not found in the database - Aborting")
            cleanup(EXIT_FAIL)


    # Delete a client from the database
    if args.delete:
        if args.MAC is None:
            logging.error ("ERROR - Must specify the --MAC when using --delete")
            cleanup(EXIT_FAIL)
        clients = db_cursor.execute(f"SELECT * FROM {config.getcfg('DB_Table')} WHERE MAC = '{args.MAC}'").fetchall()
        if len(clients) == 1:
            clients = get_database_clients()
            logging.info (f"Deleted {args.MAC} / {clients[args.MAC]['hostname']}")
            db_cursor.execute(f"DELETE FROM {config.getcfg('DB_Table')} WHERE MAC = '{args.MAC}'")
            db_connection.commit()
            cleanup(EXIT_GOOD)
        elif len(clients) > 1:
            logging.error (f"MAC address <{args.MAC}> found more than once in the database - Aborting")
            cleanup(EXIT_FAIL)
        else:
            logging.error (f"MAC address <{args.MAC}> not found in the database - Aborting")
            cleanup(EXIT_FAIL)


    # Update/refresh the database from the dhcp server
    if args.update:
        do_update()
        cleanup(EXIT_GOOD)

    logging.error ("Nothing to do.  Use one of --list-db, --list-dhcp-server, --update, --add-note, --delete, or --create-db.")
    cleanup(EXIT_FAIL)


#=====================================================================================
#=====================================================================================
#   s e r v i c e
#=====================================================================================
#=====================================================================================

def service():
    db_connect()
    next_run = time.time()
    while True:
        if config.loadconfig(call_logfile_wins=logfile_override, flush_on_reload = True):
            logging.warning(f"NOTE - The config file has been reloaded.")
            next_run = time.time()                  # Force immediate update if the config file is touched

        if time.time() > next_run:
            do_update()
            next_run += timevalue(config.getcfg('UpdateInterval')).seconds
        time.sleep(5)


#=====================================================================================
#=====================================================================================
#   d b _ c o n n e c t
#=====================================================================================
#=====================================================================================

def db_connect():
    """ Check for database access and populate if not existing """
    global db_connection, db_cursor

    mungePath(core.tool.data_dir, mkdir=True)    # Force make the data_dir
    _fp = str(mungePath(config.getcfg('DB_File'), core.tool.data_dir).full_path)
    db_connection = sqlite3.connect(_fp)    # _fp must be str on Python 3.6.8
    db_connection.row_factory = sqlite3.Row
    db_cursor = db_connection.cursor()
    found = False
    for row in db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall():
        if config.getcfg('DB_Table') in row['name']:
            found = True
            break
    
    if not found:
        logging.warning ("Network clients database table not found.")
    
    if found and args.create_db:
        logging.warning ("Deleted existing network clients database table.")
        db_cursor.execute(f"DROP TABLE {config.getcfg('DB_Table')}")
        db_connection.commit()
    
    db_fields = 'MAC VARCHAR(17), hostname VARCHAR(25), notes VARCHAR(255), first_seen INT, last_seen INT, expiry INT, ip VARCHAR(15), MACOUI VARCHAR(255)'
    if not found or args.create_db:
        logging.warning ("Creating network clients database table:")
        try:
            dhcp_clients = get_dhcp_clients()

            db_cursor.execute(f"CREATE TABLE {config.getcfg('DB_Table')} ({db_fields})")

            count = 0
            for MAC in dhcp_clients:
                count += 1
                macoui = db_add_client (MAC, dhcp_clients[MAC])
                logging.info (f"  {dhcp_clients[MAC]['hostname']:25}  {dhcp_clients[MAC]['ip']:15}  {MAC}   {macoui}")
            db_connection.commit()
            logging.info  (f"Database table created with  <{count}>  clients.")
            cleanup(EXIT_GOOD)
        except Exception as e:
            logging.error  (f"Database table creation failed - Aborting\n  {type(e).__name__}:  {e}")  # TODO type
            cleanup(EXIT_FAIL)


#=====================================================================================
#=====================================================================================
#   d o _ u p d a t e
#=====================================================================================
#=====================================================================================

def do_update():
    """ Update database from dhcp server
    """
    try:
        dhcp_clients = get_dhcp_clients()
        database_clients = get_database_clients()
        for MAC in dhcp_clients:
            if MAC not in database_clients:
                macoui = db_add_client (MAC, dhcp_clients[MAC])
                subject = 'New LAN client found'
                msg = f"\n  Hostname:    {dhcp_clients[MAC]['hostname']}\
                        \n  IP address:  {dhcp_clients[MAC]['ip']}\
                        \n  MAC:         {MAC}\
                        \n  MACOUI:      {macoui}"
                try:
                    snd_notif (subj=subject, msg=msg, log=True, smtp_config=config)
                except Exception as e:
                    logging.warning(f"snd_notif error for <{subject}>\n  {type(e).__name__}:  {e}")
                continue
            if dhcp_clients[MAC]['hostname'] != database_clients[MAC]['hostname']:
                msg = (f"{MAC} / {database_clients[MAC]['hostname']:<20} New hostname:   {dhcp_clients[MAC]['hostname']}")
                logging.info(msg)
                db_cursor.execute(f"UPDATE {config.getcfg('DB_Table')} SET hostname = \'{dhcp_clients[MAC]['hostname']}\' WHERE MAC = '{MAC}'")
            if dhcp_clients[MAC]['ip'] != database_clients[MAC]['ip']:
                msg = (f"{MAC} / {database_clients[MAC]['hostname']:<20} New IP:         {dhcp_clients[MAC]['ip']}")
                logging.info(msg)
                db_cursor.execute(f"UPDATE {config.getcfg('DB_Table')} SET IP = \'{dhcp_clients[MAC]['ip']}\' WHERE MAC = '{MAC}'")
            if dhcp_clients[MAC]['last_seen'] != database_clients[MAC]['last_seen']:
                last_seen = datetime.datetime.fromtimestamp(dhcp_clients[MAC]['last_seen'])
                msg = (f"{MAC} / {database_clients[MAC]['hostname']:<20} New last_seen:  {last_seen}")
                logging.info(msg)
                db_cursor.execute(f"UPDATE {config.getcfg('DB_Table')} SET last_seen = \'{dhcp_clients[MAC]['last_seen']}\' WHERE MAC = '{MAC}'")
            if dhcp_clients[MAC]['expiry'] != database_clients[MAC]['expiry']:
                expiry = datetime.datetime.fromtimestamp(dhcp_clients[MAC]['expiry'])
                msg = (f"{MAC} / {database_clients[MAC]['hostname']:<20} New expiry:     {expiry}")
                logging.info(msg)
                db_cursor.execute(f"UPDATE {config.getcfg('DB_Table')} SET expiry = \'{dhcp_clients[MAC]['expiry']}\' WHERE MAC = '{MAC}'")

        db_connection.commit()
    except Exception as e:
        logging.warning(f"Update failed:\n  {type(e).__name__}:  {e}")


#=====================================================================================
#=====================================================================================
#   d o _ a d d _ c l i e n t
#=====================================================================================
#=====================================================================================

def db_add_client(MAC, record):
    """ Add a single client to the database.
    Returns macoui so that do_update may use if for notification
    """
    macoui = lookup_MAC(MAC)
    cmd = "INSERT INTO {} (MAC, MACOUI, hostname, notes, first_seen, last_seen, IP, expiry) VALUES (\'{}\', \'{}\', \'{}\', \'{}\', \'{}\', {}, \'{}\', {})".format(
        config.getcfg('DB_Table'),
        MAC,
        macoui,
        record['hostname'],
        '-',
        int(time.time()),
        record['last_seen'],
        record['ip'],
        record['expiry'])
    db_cursor.execute(cmd)
    return macoui


#=====================================================================================
#=====================================================================================
#   l o o k u p _ M A C
#=====================================================================================
#=====================================================================================

MAC_LOOKUP_RATE = 0.75
next_lookup = time.time()
def lookup_MAC(MAC):
    """ Given MAC 00:05:cd:8a:22:33, get OUI from https://api.macvendors.com/00:05:cd
    Lookups limited to 2 per seconds without a macvendors.com account
    
    macvendors.com returns:
      200:  found macoui
      404:  No macoui found (potentially overlaps with general webpage problem)
      429:  "detail":"Too Many Requests","message":"Please slow down your requests or upgrade your plan at https://macvendors.com"
    """

    global next_lookup

    for _ in range(3):
        while 1:
            time.sleep(0.1)
            if time.time() > next_lookup:
                break
        r = requests.get('https://api.macvendors.com/' + MAC[0:8])
        next_lookup = time.time() + MAC_LOOKUP_RATE

        logging.debug (f"r.status_code: {r.status_code}, r.text: {r.text}")
        if r.status_code == 429:
            logging.warning (f"MAC lookup rate warning for <{MAC}>")
        if r.status_code == 200  and  '\\' not in r.text:
            return r.text
    return '--none--'

    # Remnant implementation using https://oidsearch.s.dd-wrt.com
    # # Given MAC 00:05:cd:8a:22:33, web page returns
    # #   <h2>Result for OID 00:05:cd</h2>
    # #   Denon, Ltd.<br><br>35-1, Sagamiono 7-chome,<br />
    # #   Kanagawa    228-8505<br />
    # # lookup_MAC() returns "Denon, Ltd."
    # r = requests.get("https://oidsearch.s.dd-wrt.com/search/" + MAC[0:8])
    # if r.status_code == 200:
    #     _next = False
    #     for line in r.text.split("\n"):
    #         if _next:
    #             break
    #         if "<h2>" in line:
    #             _next = True
    #     if _next:
    #         if "<br>" in line:
    #             search_result = line[0:line.find("<br>")]
    #         else:
    #             search_result = line
    #         if search_result == "":
    #             search_result = "--none--"
    # else:
    #     search_result = "OID search failed"

    # # return (search_result)
    # return html.unescape(search_result)


#=====================================================================================
#=====================================================================================
#   g e t _ d a t a b a s e _ c l i e n t s
#=====================================================================================
#=====================================================================================

def get_database_clients(dump=False, search=None):
    """ Get clients currently in the database, return a dictionary of dictionaries, keyed by MAC
        {
            MAC:  { hostname:, IP:, expiry:, first_seen:, notes:, MACOUI: }
        }
    """
    global sort_by

    clients_list = {}
    for row in db_cursor.execute(f"SELECT * FROM {config.getcfg('DB_Table')}").fetchall():
        clients_list[row['mac']] = {
            'hostname':   row['hostname'],
            'ip':         row['ip'],
            'expiry':     row['expiry'],
            'first_seen': row['first_seen'],
            'last_seen':  row['last_seen'],
            'notes':      row['notes'],
            'macoui':     row['macoui'] }

    if dump:
        if sort_by == 'mac':
            clients_list = collections.OrderedDict(sorted(clients_list.items()))
        elif sort_by in ['first_seen', 'last_seen', 'expiry']:
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1][sort_by]))
        else:
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1][sort_by].lower()))
        first=True
        if search == None:
            search = ''
        search = search.lower()
        count = 0
        for MAC in clients_list:

            first_seen =    str(datetime.datetime.fromtimestamp(int(clients_list[MAC]['first_seen'])))
            last_seen =     str(datetime.datetime.fromtimestamp(int(clients_list[MAC]['last_seen'])))  if clients_list[MAC]['last_seen'] != 0  else ''
            expiry =        str(datetime.datetime.fromtimestamp(int(clients_list[MAC]['expiry'])))     if clients_list[MAC]['expiry'] != 0     else 'static lease'

            if search=='' or \
                        search in MAC or \
                        search in clients_list[MAC]['hostname'].lower() or \
                        search in clients_list[MAC]['ip'] or \
                        search in expiry.lower() or \
                        search in first_seen.lower() or \
                        search in last_seen.lower() or \
                        search in clients_list[MAC]['macoui'].lower() or \
                        search in clients_list[MAC]['notes'].lower():
                count += 1
                if first:
                    print(f"{'Hostname':<25}  {'First seen':<19}  {'Last seen':<19}  {'Current IP':<15}  {'IP Expiry':<19}  {'mac':<17}  "
                        + f"{'MAC Org Unique ID':<{config.getcfg('MACOUI_field_width', 30)}}  {'Notes'}")                    
                    first = False
                _macoui = clients_list[MAC]['macoui'][:config.getcfg('MACOUI_field_width', 30)]
                print(f"{clients_list[MAC]['hostname']:<25}  {first_seen:<19}  {last_seen:<19}  {clients_list[MAC]['ip']:<15}  {expiry:<19}  {MAC:<17}  "
                    + f"{_macoui:<{config.getcfg('MACOUI_field_width', 30)}}  {clients_list[MAC]['notes']}")
        print (f"  <{count}>  known clients.")

    return clients_list


#=====================================================================================
#=====================================================================================
#   g e t _ d h c p _ c l i e n t s
#=====================================================================================
#=====================================================================================

def get_dhcp_clients(dump=False):
    """ Get leases from the dhcp server, return sorted dictionary of dictionaries keyed by MAC
        {
            MAC:  { hostname:<str>, IP:<str>, last_seen<timestamp or 0>:, expiry<timestamp or 0>: }
        }
    
    dump = True forces a pretty print output of the clients_list dictionary
        
    Exceptions are logged and raised to caller.  TODO True?
    """
    clients_list = {}
    sources = config.getcfg('Sources', False)
    if not sources:
        logging.error (f"<Sources> not found in config - Aborting")
        sys.exit(EXIT_FAIL)

    for source in sources:
        if source not in config.sections():
            logging.error (f"Missing source section <{source}> - Aborting")  # TODO log and raise
            cleanup(EXIT_FAIL)
        mode = config.getcfg('Mode', False, section=source)
        if mode == False  or  mode not in ['MIM_API', 'Unofficial_APIV2', 'Page_Scrape']:
            logging.error (f"Missing or invalid Mode for source <{source}> - Aborting")  # TODO log and raise
            cleanup(EXIT_FAIL)

        logging.debug (f"Getting leases for source <{source}>, mode <{mode}>")
        try:
            if mode == 'MIM_API':
                _clients_list = get_leases_MIM_api(source)
        
            elif mode == 'Unofficial_APIV2':
                _clients_list = get_leases_unofficialV2_api(source)

            else: # mode == 'Page_Scrape':
                _clients_list = scrape_pfsense_dhcp_page(source)

        except Exception as e:
            logging.error (f"Error while getting clients_list for Source <{source}> - Aborting\n  {type(e).__name__}:  {e}")  # TODO log and raise
            cleanup(EXIT_FAIL)

        clients_list.update(_clients_list)


    if dump:
        if sort_by == 'mac':
            clients_list = collections.OrderedDict(sorted(clients_list.items()))
        elif sort_by in ['hostname', 'ip']:
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1][sort_by].lower()))
        elif sort_by in ['last_seen', 'expiry']:
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1][sort_by]))
        else:
            print (f"For --list-dhcp-server, <--sort-by {sort_by}> not supported.  Defaulting to <--sort-by hostname>.")
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1]['hostname'].lower()))

        count = 0
        print(f"{'mac':<19}  {'ip':<15}  {'hostname':<25}  {'last_seen':<20}  {'expiry'}")
        for client in clients_list:
            count += 1
            last_seen = ''              if clients_list[client]['last_seen'] == 0  else  str(datetime.datetime.fromtimestamp(int(clients_list[client]['last_seen'])))
            expiry =    'static lease'  if clients_list[client]['expiry'] == 0     else  str(datetime.datetime.fromtimestamp(int(clients_list[client]['expiry'])))

            print(f"{client:<19}  {clients_list[client]['ip']:<15}  {clients_list[client]['hostname']:<25}  {last_seen:<20}  {expiry}")
        print (f"  <{count}>  known clients.")


    return clients_list


#=====================================================================================
#=====================================================================================
#   g e t _ l e a s e s _ M I M _ a p i
#=====================================================================================
#=====================================================================================

def get_leases_MIM_api(source):
    """Queries the pfSense+ multi-instance management (MIM) "Controller" API get_dhcp_leases

    The returned DHCP clients list contains the merged list of clients from all `DEVICES`, with
    just one entry for each MAC.
 
    ### Config params:

    `Mode` (str)
    - 'MIM_API' for this operational mode

    `CONTROLLER_URL` (str)
    - URL of the pfsense device serving the MIM API, eg https://pfsense.mylan:8443

    `DEVICES` (str or list, default ['localhost'])
    - Typically a list of pfSense+ devices managed by the `CONTROLLER_URL`
    - if 'all' (case insensitive) then the list of managed devices is fetched from the `CONTROLLER_URL`

    `CERT_PATH` (str)
    - Path to the certificate file downloaded from the `CONTROLLER_URL` GUI System > Certificates > Certificates > Export Certificate
    - Set to False to disable cert verification

    `USER` (str)
    - username of admin privileged user
    - Should be imported from a user-read-only credentials file

    `PASS` (str)
    - password for `USER`
    - Should be imported from a user-read-only credentials file

    ### Returns
    - A dictionary of dictionaries.  The top level dictionary is the MAC addresses of the found clients.  
    - Each client dictionary contains:
        {'ip':item['ip'], 'hostname':item['host'], 'last_seen':last_seen_timestamp, 'expiry':expiry_timestamp, 'device':device}

      - 'last_seen' is the when the lease was last renewed
      - 'device' is the pfSense device that issued the lease (TODO save latest info across all devices)
    """
    from pfapi import Client, AuthenticatedClient

    controller_url =    config.getcfg('CONTROLLER_URL', section=source)
    devices =           config.getcfg('DEVICES', ['localhost'], section=source, types=[str, list])
    user =              config.getcfg('USER', section=source)
    password =          config.getcfg('PASS', section=source)
    cert_path =         config.getcfg('CERT_PATH', False, section=source)

    client = Client(base_url=controller_url+'/api',
                    verify_ssl=cert_path,
                    headers={'Content-Type': 'application/json'})

    _username = base64.b64encode(user.encode('utf-8')).decode('utf-8')
    _password = base64.b64encode(password.encode('utf-8')).decode('utf-8')
    loginCred = LoginCredentials(username=_username, password=_password)
    resp = login.sync(client=client, body=loginCred)

    # Successful login will return a token in LoginReponse; keep it to create Authenticated client
    if not isinstance(resp, LoginResponse):
        raise ValueError (f"Login failed:  {resp}")

    token = resp.token
    sessInfo = json.loads(base64.b64decode(token.split('.')[1].encode('utf-8') + b'==').decode('utf-8'))
    # expires = time.localtime(sessInfo['exp'])

    # Must call refresh_access_token to continue to access API
    # Cookie jar contains the 24-hour refresh token, which is used to refresh the session access token (via API: /login/refresh)
    cookies = client.get_httpx_client().cookies

    # Create an authenticated client, which will send the bearer (access) token for all API requests to the controller
    client = AuthenticatedClient(base_url=controller_url+'/api',
                    verify_ssl=cert_path,
                    headers={'Content-Type': 'application/json'},
                    cookies=cookies,
                    token=token)

    # if DEVICES = 'all', build list of devices from controller
    if isinstance(devices, str)  and  devices.lower() == 'all':
        devices = []
        resp = get_controlled_devices.sync(client=client)
        for dev in resp.devices:
            logging.debug (f"{dev.name}, device_id: {dev.device_id}, state: {dev.state}") #, Product version: {device.product_version}")
            if dev.auth:
                logging.debug(f"VPN address: {dev.auth.vpn_address}")
            if dev.state != 'online':
                logging.info(f"Device <{dev.device_id}> is offline, skipping...")
                continue
            devices.append(dev.device_id)
        logging.debug (f"All devices: <{devices}>")


    lease_dict = {}
    for device in devices:
        devApi = AuthenticatedClient(base_url=controller_url+f'/api/device/pfsense/{device}/api',
                    verify_ssl=cert_path,
                    headers={'Content-Type': 'application/json'},
                    cookies=cookies,
                    token=token)

        # Get leases
        leases = get_dhcp_leases.sync(client=devApi).to_dict()
        if not 'v4leases' in leases:
            raise ValueError ("Leases read failed - v4leases not found in server response - Aborting")

        for item in leases['v4leases']:
            last_seen_timestamp =   datetime.datetime.strptime(item['cltt'][0:19],  '%Y-%m-%d %H:%M:%S').timestamp()
            expiry_timestamp =      datetime.datetime.strptime(item['end'],         '%Y/%m/%d %H:%M:%S').timestamp()
            mac =                   item['mac']
            lease_dict[mac] =       {'ip':item['ip'], 'hostname':item['host'], 'last_seen':last_seen_timestamp, 'expiry':expiry_timestamp, 'device':device}
            logging.debug (f"Lease entry:  <{mac}>:  <{lease_dict[mac]}>")

    return lease_dict


#=====================================================================================
#=====================================================================================
#   g e t _ l e a s e s _ u n o f f i c i a l V 2 _ a p i
#=====================================================================================
#=====================================================================================

def get_leases_unofficialV2_api(source): # device='localhost'):
    """Queries the pfSense Unofficial V2 status/dhcp_server/leases of the specified device (appliance/host)

    Typical api response:
        {'id': 0, 'ip': '192.168.1.90', 'mac': '12:34:56:78:90:ab', 'hostname': 'Template', 'if': 'lan', 'starts': '', 'ends': '', 'active_status': 'static', 'online_status': 'idle/offline', 'descr': 'Template <staticmap> entry'}
        ...
        {'id': 5, 'ip': '192.168.1.100', 'mac': '70:88:6b:86:aa:bb', 'hostname': 'somehost', 'if': None, 'starts': '2025/11/28 18:15:41', 'ends': '2025/11/28 20:15:41', 'active_status': 'active', 'online_status': 'active/online', 'descr': None}
    """

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url =       config.getcfg('URL', section=source)
    api_key =   config.getcfg('API_KEY', section=source)

    headers = {
        'X-API-KEY': api_key,
        'Accept': 'application/json'
        }

    resp = requests.get(f'{url}/api/v2/status/dhcp_server/leases',
                        headers=headers,
                        verify=False)  # Or path to CA cert  TODO

    resp.raise_for_status()
    leases = resp.json().get('data', [])

    if len(leases) == 0:
        raise ValueError ("No leases found on the server")

    lease_dict = {}
    for item in leases:
        last_seen_timestamp =   datetime.datetime.strptime(item['starts'],      '%Y/%m/%d %H:%M:%S').timestamp()  if item['starts']  else 0
        expiry_timestamp =      datetime.datetime.strptime(item['ends'],        '%Y/%m/%d %H:%M:%S').timestamp()  if item['ends']    else 0
        mac =                   item['mac']
        lease_dict[mac] =       {'ip':item['ip'], 'hostname':item['hostname'], 'last_seen':last_seen_timestamp, 'expiry':expiry_timestamp}
        logging.debug (f"Lease entry:  <{mac}>:  <{lease_dict[mac]}>")

    return lease_dict


#=====================================================================================
#=====================================================================================
#   s c r a p e _ p f s e n s e _ d h c p _ p a g e
#=====================================================================================
#=====================================================================================

def scrape_pfsense_dhcp_page(source):
    """Queries the pfSense Plus 25.07.1 RELEASE / pfSense CE 2.8.0 Status > DHCP Leases page and returns a list of dictionaries, 
    one dict for each table row.
    """

    # Given Status > DHCP Leases page (25.07.1 RELEASE):
    """
    <div class="panel panel-default">
        <div class="panel-heading"><h2 class="panel-title">Leases</h2></div>
        <div class="panel-body table-responsive">
            <table class="table table-striped table-hover table-condensed sortable-theme-bootstrap" data-sortable>
                <thead>
                    <tr>
                        <th data-sortable="false"><!-- icon --></th>
                        <th>IP Address</th>
                        <th>MAC Address</th>
                        <th>Hostname</th>
                        <th>Description</th>
                        <th>Start</th>
                        <th>End</th>
                        <th data-sortable="false">Actions</th>
                    </tr>
                </thead>
                <tbody id="leaselist">
                    <tr>
                        <td>
                            <i class="fa-solid fa-user act" title="static"></i>
                            <i class="fa-solid fa-arrow-down online" title="idle/offline"></i>
                        </td>
                        <td>192.168.66.77</td>
                        <td>e4:fa:c4:11:22:33</td>
                        <td><i class="fa-solid fa-globe" title="Registered with the DNS Resolver"></i>hostname_gws</td>
                        <td></td>
                        <td>n/a</td>  or  <td>2025/11/28 16:39:47<\td>
                        <td>n/a</td>  or  <td>2025/11/28 18:39:47<\td>
                        <td>
                            <a class="fa-solid fa-plus-square" title="Add WOL mapping" href="services_wol_edit.php?if=opt6&amp;mac=e4:fa:c4:8d:8a:f1&amp;descr=gwsBed5"></a>
                            <a class="fa-solid fa-power-off" title="Send WOL packet" href="services_wol.php?if=opt6&amp;mac=e4:fa:c4:8d:8a:f1" usepost></a>
                            <a class="fa-solid fa-pencil"	title="Edit static mapping" href="services_dhcp_edit.php?if=opt6&amp;id=6"></a>
                        </td>
                    </tr>
    """

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    s = requests.session()
    s.verify = False
    # s.verify = config.getcfg('PF_PUBCERT_PATH', False)
    # print (s.verify)
    # public_cert_path = config.getcfg('PF_PUBCERT_PATH', False)
    # priv_key_path = config.getcfg('PF_PRIVKEY_PATH', False)

    # xx = (public_cert_path, priv_key_path)  if public_cert_path  else None

    url =               config.getcfg('URL', section=source)
    login_page =        url + '/index.php'
    dhcpleases_page =   url + '/status_dhcp_leases.php'
    page_timeout =      timevalue(config.getcfg('Page_timeout', section=source)).seconds
    user =              config.getcfg('USER', section=source)
    password =          config.getcfg('PASS', section=source)

    try:
        # r = s.get(url, verify=True, cert=xx)
        # r = s.get(url, verify=False)
        r = s.get(login_page, timeout=page_timeout)                 # Bring up login page, get csrf
        
        # exit()
    # except:
    #     logging.error(f"Error attempting to connect to <{url}>.  url and login credentials valid?")
    #     raise IOError("Could not read DHCP clients from the pfsense router")
    #     # sys.exit(EXIT_FAIL)

    # try:
        matchme = 'csrfMagicToken = "(.*)";var'
        csrf = re.search(matchme,str(r.text))
        payload = {'__csrf_magic' : csrf.group(1), 'login' : 'Login', 'usernamefld' : user, 'passwordfld' : password}
        # r = s.post(url,data=payload,verify = cert_path)
        # r = s.get(url,verify = cert_path)
        r = s.post(login_page, data=payload, timeout=page_timeout)  # login
        r = s.get (dhcpleases_page, timeout=page_timeout)           # get DHCP leases page


        # Find the <h2 class="panel-title"> with text "Leases", then up to the surrounding panel
        tree = _html.fromstring(r.content)
        column_names = []
        none_index = 0
        leases_panel = tree.xpath('//h2[@class="panel-title" and text()="Leases"]/ancestor::div[contains(@class,"panel")]')

        if not leases_panel:
            raise ValueError ("Failed reading Status > DHCP Leases page")


        # Index to the table inside this panel
        table = leases_panel[0].xpath('.//table')[0]


        # Build list of column names
        column_names = []
        none_index = 0
        for th in table.xpath('.//thead/tr/th'):
            _col = th.text_content()
            if _col is None  or  _col == '':   # Ensure unique name for each column with no name
                colname = 'None' + str(none_index)
                none_index += 1
            else:
                colname = _col.strip()
            column_names.append(colname)
        logging.debug (f"Column names: <{column_names}>")


        # Extract rows
        lease_dict = {}
        for tr in table.xpath('.//tbody/tr'):
            row_dict = {}
            _row = [td.text_content().strip() for td in tr.xpath('td')]
            for colname, item in zip(column_names, _row):
                row_dict[colname] = item

            last_seen_timestamp = 0  if row_dict['Start'] == 'n/a'  else  datetime.datetime.strptime(row_dict['Start'], '%Y/%m/%d %H:%M:%S').timestamp()
            expiry_timestamp =    0  if row_dict['End'] == 'n/a'    else  datetime.datetime.strptime(row_dict['End'],   '%Y/%m/%d %H:%M:%S').timestamp()

            # logging.debug (f"mac {row_dict['MAC Address']}, 'IP':{row_dict['IP Address']}, hostname':{row_dict['Hostname']}, 'last_seen':{last_seen_timestamp}, 'expiry':{expiry_timestamp}")
            mac = row_dict['MAC Address']
            lease_dict[mac] = {'ip':row_dict['IP Address'], 'hostname':row_dict['Hostname'], 'last_seen':last_seen_timestamp, 'expiry':expiry_timestamp}
            logging.debug (f"Lease entry:  <{mac}>:  <{lease_dict[mac]}>")
            # lease_dict[row_dict['MAC Address']] = {'IP':row_dict['IP Address'], 'hostname':row_dict['Hostname'], 'last_seen':last_seen_timestamp, 'expiry':expiry_timestamp}
            # logging.debug (f"<{row_dict['MAC Address']}>:  <{lease_dict[row_dict['MAC Address']]}>")

        return lease_dict

    except Exception as e:
        logging.error(f"Failed to connect to or get DHCP data from <{url}>.\n  {type(e).__name__}:  {e}")
        raise ConnectionError("pfsense router access error")


#=====================================================================================
#=====================================================================================
#   template functions
#=====================================================================================
#=====================================================================================

def cleanup(exit_code):
    if exit_code == EXIT_FAIL:
        logging.warning (f"Cleanup and exit({exit_code})")
    if db_cursor:
        db_cursor.close()
    if db_connection:
        db_connection.close()
    sys.exit(exit_code)
    pass


def int_handler(signal, frame):
    logging.warning(f"Signal {signal} received.  Exiting.")
    cleanup(EXIT_FAIL)

signal.signal(signal.SIGINT,  int_handler)      # Ctrl-C
signal.signal(signal.SIGTERM, int_handler)      # kill


def cli():
    global config, args, logfile_override
    global sort_by

    set_toolname (TOOLNAME)
    parser = argparse.ArgumentParser(description=__doc__ + __version__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('SearchTerm', nargs='?',
                        help="Print database records containing this text.")
    parser.add_argument('--update', '-u', action='store_true',
                        help="Check the dhcp server for new connections and update the database.")
    parser.add_argument('--list-db', '-l', action='store_true',
                        help="Print known clients on the network from the database (default mode).")
    parser.add_argument('--list-dhcp-server', '-r', action='store_true',
                        help="Print known clients on the network from the dhcp server.")
    parser.add_argument('--sort-by', '-s', choices=SORT_MODES,
                        help=f"Sort --list-db and --list-dhcp-server output. Overrides config SortBy. Default <{DEFAULT_SORT_MODE}> if neither specified.")
    parser.add_argument('--create-db', action='store_true',
                        help="Create a fresh database and populate it with the current dhcp server clients.")
    parser.add_argument('--note', '-n', type=str,
                        help="Add a note to the db for the specified --MAC.")
    parser.add_argument('--delete', action='store_true',
                        help="Delete from the db the specified --MAC.")
    parser.add_argument('--MAC', '-m', type=str,
                        help="MAC address for --add-note or --delete.")
    parser.add_argument('--config-file', '-c', type=str, default=CONFIG_FILE,
                        help=f"Path to the config file (Default <{CONFIG_FILE})> in user/site config directory.")
    parser.add_argument('--print-log', '-p', action='store_true',
                        help=f"Print the tail end of the log file (default last {PRINTLOGLENGTH} lines).")
    parser.add_argument('--service', action='store_true',
                        help="Run updates in an endless loop for use as a systemd service.")
    parser.add_argument('-v', '--verbose', action='count',
                        help="Print status and activity messages (-vv for debug logging)")
    parser.add_argument('--setup-user', action='store_true',
                        help=f"Install starter files in user space.")
    parser.add_argument('--setup-site', action='store_true',
                        help=f"Install starter files in system-wide space. Run with root prev.")
    parser.add_argument('-V', '--version', action='version', version=f'{core.tool.toolname} {__version__}',
                        help="Return version number and exit.")
    args = parser.parse_args()


    # Deploy template files
    if args.setup_user:
        deploy_files([
            { 'source': CONFIG_FILE,             'target_dir': 'USER_CONFIG_DIR', 'file_stat': 0o644, 'dir_stat': 0o755},
            { 'source': 'creds_SMTP',            'target_dir': 'USER_CONFIG_DIR', 'file_stat': 0o600},
            { 'source': 'creds_routermonitor',   'target_dir': 'USER_CONFIG_DIR', 'file_stat': 0o600},
            { 'source': 'routermonitor.service', 'target_dir': 'USER_CONFIG_DIR', 'file_stat': 0o644},
            ]) #, overwrite=True)
        sys.exit()

    if args.setup_site:
        deploy_files([
            { 'source': CONFIG_FILE,             'target_dir': 'SITE_CONFIG_DIR', 'file_stat': 0o644, 'dir_stat': 0o755},
            { 'source': 'creds_SMTP',            'target_dir': 'SITE_CONFIG_DIR', 'file_stat': 0o600},
            { 'source': 'creds_routermonitor',   'target_dir': 'SITE_CONFIG_DIR', 'file_stat': 0o600},
            { 'source': 'routermonitor.service', 'target_dir': 'SITE_CONFIG_DIR', 'file_stat': 0o644},
            ]) #, overwrite=True)
        sys.exit()


    # Load config file and setup logging
    logfile_override = True  if not args.service  else False
    try:
        config = config_item(args.config_file)
        config.loadconfig(call_logfile_wins=logfile_override)         #, call_logfile=args.log_file, ldcfg_ll=10)
    except Exception as e:
        logging.error(f"Failed loading config file <{args.config_file}>. \
\n  Run with  '--setup-user' or '--setup-site' to install starter files - Aborting\n  {type(e).__name__}:  {e}")
        sys.exit(EXIT_FAIL)


    logging.warning (f"========== {core.tool.toolname} ({__version__}) ==========")
    logging.warning (f"Config file <{config.config_full_path}>")


    # Print log
    if args.print_log:
        try:
            _lf = mungePath(config.getcfg('LogFile'), core.tool.log_dir_base).full_path
            print (f"Tail of  <{_lf}>:")
            _xx = collections.deque(_lf.open(), config.getcfg('PrintLogLength', PRINTLOGLENGTH))
            for line in _xx:
                print (line, end='')
        except Exception as e:
            print (f"Couldn't print the log file.  LogFile defined in the config file?\n  {type(e).__name__}:  {e}")
        sys.exit()


    sort_by = config.getcfg('SortBy', DEFAULT_SORT_MODE)
    if args.sort_by:
        sort_by = args.sort_by
    if sort_by not in SORT_MODES:
        logging.error(f"Invalid SortBy value <{config.getcfg('SortBy')}> in config file")
        sys.exit(EXIT_FAIL)

    if not args.update and not args.list_dhcp_server and not args.print_log and not args.create_db and not args.note and not args.delete and not args.service:
        args.list_db = True     # If operation/mode not specified then default to list_db

    if args.service:
        service()

    main()


if __name__ == '__main__':
    sys.exit(cli())    