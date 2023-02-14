#!/usr/bin/env python3
"""Monitor for new devices/clients on the network.

The network dhcp server is queried for currently known DHCP clients.
Any new clients are identified and a notification is sent.  
"""

#==========================================================
#
#  Chris Nelson, 2020 - 2023
#
# 3.0 230215 - Converted to package format, updated to cjnfuncs 2.0
# ...
# 0.1 200426 - New
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
import requests
import signal
from lxml import html as _html

try:
    import importlib.metadata
    __version__ = importlib.metadata.version(__package__ or __name__)
except:
    try:
        import importlib_metadata
        __version__ = importlib_metadata.version(__package__ or __name__)
    except:
        __version__ = "3.0 X"

# from cjnfuncs.cjnfuncs import set_toolname, setup_logging, logging, config_item, getcfg, mungePath, deploy_files, timevalue, retime, requestlock, releaselock,  snd_notif, snd_email
from cjnfuncs.cjnfuncs import set_toolname, logging, config_item, getcfg, mungePath, deploy_files, timevalue, snd_notif


# Configs / Constants
TOOLNAME            = "routermonitor"
CONFIG_FILE         = "routermonitor.cfg"
PRINTLOGLENGTH      = 40
EXIT_GOOD           = 0
EXIT_FAIL           = 1
SORT_MODES          = ['hostname', 'IP', 'first_seen', 'expiry', 'MAC', 'MACOUI', 'notes']
DEFAULT_SORT_MODE   = "hostname"   # If not specified in config file or command line
PY_VERSION          = sys.version_info
# SYSTEM              = platform.system()     # 'Linux', 'Windows', ...


def main():

    logging.getLogger().setLevel(20)  # Set INFO level for interactive use
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
        clients = db_cursor.execute(f"SELECT * FROM {getcfg('DB_TABLE')} WHERE MAC = '{args.MAC}'").fetchall()
        if len(clients) == 1:
            new_note = args.note.replace("'", "''")   # single quotes need to be doubled up in SQL
            clients = get_database_clients()
            logging.info (f"Note added for {args.MAC} / {clients[args.MAC]['hostname']}:  {new_note}")
            db_cursor.execute(f"UPDATE {getcfg('DB_TABLE')} SET notes = '{new_note}' WHERE MAC = '{args.MAC}'")
            db_connection.commit()
            cleanup(EXIT_GOOD)
        elif len(clients) > 1:
            logging.error (f"MAC address <{args.MAC}> found more than once in the database. Aborting.")
            cleanup(EXIT_FAIL)
        else:
            logging.error (f"MAC address <{args.MAC}> not found in the database. Aborting.")
            cleanup(EXIT_FAIL)


    # Delete a client from the database
    if args.delete:
        if args.MAC is None:
            logging.error ("ERROR - Must specify the --MAC when using --delete")
            cleanup(EXIT_FAIL)
        clients = db_cursor.execute(f"SELECT * FROM {getcfg('DB_TABLE')} WHERE MAC = '{args.MAC}'").fetchall()
        if len(clients) == 1:
            clients = get_database_clients()
            logging.info (f"Deleted {args.MAC} / {clients[args.MAC]['hostname']}")
            db_cursor.execute(f"DELETE FROM {getcfg('DB_TABLE')} WHERE MAC = '{args.MAC}'")
            db_connection.commit()
            cleanup(EXIT_GOOD)
        elif len(clients) > 1:
            logging.error (f"MAC address <{args.MAC}> found more than once in the database. Aborting.")
            cleanup(EXIT_FAIL)
        else:
            logging.error (f"MAC address <{args.MAC}> not found in the database. Aborting.")
            cleanup(EXIT_FAIL)


    # Update/refresh the database from the dhcp server
    if args.update:
        do_update()
        cleanup(EXIT_GOOD)

    logging.error ("Nothing to do.  Use one of --list-db, --list-dhcp-server, --update, --add-note, --delete, or --create-db.")
    cleanup(EXIT_FAIL)


def service():
    db_connect()
    next_run = time.time()
    while True:
        if config.loadconfig(call_logfile_wins=logfile_override, flush_on_reload = True):
            logging.warning(f"NOTE - The config file has been reloaded.")
            next_run = time.time()                  # Force immediate update if the config file is touched

        if time.time() > next_run:
            do_update()
            next_run += timevalue(getcfg("UpdateInterval")).seconds
        time.sleep(5)


def db_connect():
    """ Check for database access and populate if not existing """
    global db_connection, db_cursor

    mungePath(tool.data_dir, mkdir=True)    # Force make the data_dir
    _fp = str(mungePath(getcfg("DB_DB"), tool.data_dir).full_path)
    db_connection = sqlite3.connect(_fp)    # _fp must be str on Python 3.6.8
    db_connection.row_factory = sqlite3.Row
    db_cursor = db_connection.cursor()
    found = False
    for row in db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall():
        if getcfg('DB_TABLE') in row['name']:
            found = True
            break
    
    if not found:
        logging.warning ("Network clients database table not found.")
    
    if found and args.create_db:
        logging.warning ("Deleted existing network clients database table.")
        db_cursor.execute(f"DROP TABLE {getcfg('DB_TABLE')}")
        db_connection.commit()
    
    db_fields = "MAC VARCHAR(17), hostname VARCHAR(25), notes VARCHAR(255), first_seen INT, expiry INT, IP VARCHAR(15), MACOUI VARCHAR(255)"
    if not found or args.create_db:
        logging.warning ("Creating network clients database table:")
        dhcp_clients = get_dhcp_clients()
        db_cursor.execute(f"CREATE TABLE {getcfg('DB_TABLE')} ({db_fields})")

        count = 0
        for MAC in dhcp_clients:
            count += 1
            macoui = db_add_client (MAC, dhcp_clients[MAC])
            logging.info (f"  {dhcp_clients[MAC]['hostname']:25}  {dhcp_clients[MAC]['IP']:15}  {MAC}   {macoui}")
        db_connection.commit()
        logging.info  (f"Database table created with  <{count}>  clients.")
        cleanup(EXIT_GOOD)


def do_update():
    """ Update database from dhcp server
    """
    try:
        dhcp_clients = get_dhcp_clients()
        database_clients = get_database_clients()
        for MAC in dhcp_clients:
            if MAC not in database_clients:
                macoui = db_add_client (MAC, dhcp_clients[MAC])
                subject = "New LAN client found"
                msg = f"\n  Hostname:    {dhcp_clients[MAC]['hostname']}\
                        \n  IP address:  {dhcp_clients[MAC]['IP']}\
                        \n  MAC:         {MAC}\
                        \n  MACOUI:      {macoui}"
                try:
                    snd_notif (subj=subject, msg=msg, log=True)
                except Exception as e:
                    logging.warning(f"snd_notif error for <{subject}>:  {e}")
                continue
            if dhcp_clients[MAC]['hostname'] != database_clients[MAC]['hostname']:
                msg = (f"{MAC} / {database_clients[MAC]['hostname']:<20} New hostname: {dhcp_clients[MAC]['hostname']}")
                logging.info(msg)
                db_cursor.execute(f"UPDATE {getcfg('DB_TABLE')} SET hostname = \'{dhcp_clients[MAC]['hostname']}\' WHERE MAC = '{MAC}'")
            if dhcp_clients[MAC]['IP'] != database_clients[MAC]['IP']:
                msg = (f"{MAC} / {database_clients[MAC]['hostname']:<20} New IP:       {dhcp_clients[MAC]['IP']}")
                logging.info(msg)
                db_cursor.execute(f"UPDATE {getcfg('DB_TABLE')} SET IP = \'{dhcp_clients[MAC]['IP']}\' WHERE MAC = '{MAC}'")
            if dhcp_clients[MAC]['expiry'] != database_clients[MAC]['expiry']:
                expiry = datetime.datetime.fromtimestamp(dhcp_clients[MAC]['expiry'])
                msg = (f"{MAC} / {database_clients[MAC]['hostname']:<20} New expiry:   {expiry}")
                logging.info(msg)
                db_cursor.execute(f"UPDATE {getcfg('DB_TABLE')} SET expiry = \'{dhcp_clients[MAC]['expiry']}\' WHERE MAC = '{MAC}'")

        db_connection.commit()
    except Exception as e:
        logging.warning(f"Failed in do_update:\n{e}")


def db_add_client(MAC, record):
    """ Add a single client to the database.
    Returns macoui so that do_update may use if for notification
    """
    macoui = lookup_MAC(MAC)
    cmd = "INSERT INTO {} (MAC, MACOUI, hostname, notes, first_seen, IP, expiry) VALUES (\'{}\', \'{}\', \'{}\', \'{}\', {}, \'{}\', {})".format(
        getcfg('DB_TABLE'),
        MAC,
        macoui,
        record['hostname'],
        "-",
        time.time(),
        record['IP'],
        record['expiry'])
    db_cursor.execute(cmd)
    return macoui


next_lookup = time.time()
def lookup_MAC(MAC):
    """ Given MAC 00:05:cd:8a:22:33, get OUI from https://api.macvendors.com/00:05:cd
    Lookups limited to 2 per seconds without a macvendors.com account
    """
    global next_lookup
    while 1:
        if time.time() > next_lookup:
            break
    macoui = "--none--"
    r = requests.get("https://api.macvendors.com/" + MAC[0:8])
    if r.status_code == 200:
        macoui = r.text
    next_lookup = time.time() + 0.6
    return macoui

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


def get_database_clients(dump=False, search=None):
    """ Get clients currently in the database, return a dictionary of dictionaries, keyed by MAC
        {
            MAC:  { hostname:, IP:, expiry:, first_seen:, notes:, MACOUI: }
        }
    """
    global sort_by

    clients_list = {}
    for row in db_cursor.execute(f"SELECT * FROM {getcfg('DB_TABLE')}").fetchall():
        clients_list[row['MAC']] = {
            "hostname":   row['hostname'],
            "IP":         row['IP'],
            "expiry":     row['expiry'],
            "first_seen": row['first_seen'],
            "notes":      row['notes'],
            "MACOUI":     row['MACOUI'] }

    if dump:
        if sort_by == 'MAC':
            clients_list = collections.OrderedDict(sorted(clients_list.items()))
        elif sort_by in ["first_seen", "expiry"]:
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1][sort_by]))
        else:
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1][sort_by].lower()))
        first=True
        if search == None:
            search = ""
        search = search.lower()
        count = 0
        for MAC in clients_list:

            first_seen = str(datetime.datetime.fromtimestamp(int(clients_list[MAC]['first_seen'])))
            if clients_list[MAC]['expiry'] == 0:
                expiry = "static lease"
            else:
                expiry = str(datetime.datetime.fromtimestamp(int(clients_list[MAC]['expiry'])))

            if search=="" or \
                        search in MAC or \
                        search in clients_list[MAC]['hostname'].lower() or \
                        search in clients_list[MAC]['IP'] or \
                        search in expiry.lower() or \
                        search in first_seen.lower() or \
                        search in clients_list[MAC]['MACOUI'].lower() or \
                        search in clients_list[MAC]['notes'].lower():
                count += 1
                if first:
                    print(f"{'Hostname':<25}  {'First seen':<19}  {'Current IP':<15}  {'IP Expiry':<19}  {'MAC':<17}  "
                        + f"{'MAC Org Unique ID':<{getcfg('MACOUI_field_width', 30)}}  {'Notes'}")                    
                    first = False
                _macoui = clients_list[MAC]['MACOUI'][:getcfg('MACOUI_field_width', 30)]
                print(f"{clients_list[MAC]['hostname']:<25}  {first_seen:<19}  {clients_list[MAC]['IP']:<15}  {expiry:<19}  {MAC:<17}  "
                    + f"{_macoui:<{getcfg('MACOUI_field_width', 30)}}  {clients_list[MAC]['notes']}")
        print (f"  <{count}>  known clients.")

    return clients_list


def get_dhcp_clients(dump=False):
    """ Get leases from the dhcp server, return a sorted dictionary of dictionaries, keyed by MAC
        {
            MAC:  { hostname:, IP:, expiry: }
        }
    """
    clients_list = {}
    clients = ""
    if getcfg("DHCP_SERVER_TYPE").lower() == "pfsense":
        pf_clients = scrape_pfsense_dhcp(getcfg("PF_DHCP_URL"), getcfg("PF_USER"), getcfg("PF_PASS"))
        for row in pf_clients:
            if row["End"] == "n/a":
                expiry_timestamp = 0
            else:
                expiry_timestamp = datetime.datetime.strptime(row["End"], getcfg("PF_DATE_FORMAT")).timestamp()    # '2021/11/07 11:51:44'
            clients_list[row["MAC address"]] = {"hostname":row["Hostname"], "IP":row["IP address"], "expiry":expiry_timestamp}
    
    elif getcfg("DHCP_SERVER_TYPE").lower() == "dd-wrt":
        try:
            _cmd = ["ssh", "root@" + getcfg("DDWRT_IP"), "-o", "ConnectTimeout=1", "-T", "cat", getcfg("DDWRT_DHCP")]
            if PY_VERSION >= (3, 7): #3.7:
                clients = subprocess.run(_cmd, capture_output=True, text=True).stdout.split("\n")
            else:   #Py 3.6 .run does not support capture_output, so use the old method.
                clients = subprocess.run(_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout.split("\n")
        except Exception as e:
            logging.warning("Exception <{}>".format(e))
        # 1587457675 00:0d:c5:5c:82:6d 192.168.1.105 Hopper-ETH0 01:00:0d:c5:5c:82:6d
        line_re = re.compile(r"([\d]+) ([\dabcdef:]+) ([\d.]+) ([\S]+)") # [\dabcdef:]+")
        for line in clients:
            xx = line_re.match(line)
            if xx:
                clients_list[xx.group(2)] = {"hostname":xx.group(4), "IP":xx.group(3), "expiry":int(xx.group(1))}
            else:
                if len(line) > 0:
                    logging.warning ("ERROR in get_dhcp_clients:  This line looks bogus:\n  ", line)
    else:
        logging.error (f"Invalid DHCP_SERVER_TYPE in config: {getcfg('DHCP_SERVER_TYPE')}")
        cleanup(EXIT_FAIL)

    if dump:
        if sort_by == 'MAC':
            clients_list = collections.OrderedDict(sorted(clients_list.items()))
        elif sort_by in ["hostname", "IP"]:
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1][sort_by].lower()))
        elif sort_by == "expiry":
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1][sort_by]))
        else:
            print (f"For --list-dhcp-server, <--sort-by {sort_by}> not supported.  Defaulting to <--sort-by hostname>.")
            clients_list = collections.OrderedDict(sorted(clients_list.items(), key=lambda t:t[1]["hostname"].lower()))

        count = 0
        for client in clients_list:
            count += 1
            if clients_list[client]["expiry"] == 0:
                expiry = "static lease"
            else:
                expiry = str(datetime.datetime.fromtimestamp(int(clients_list[client]["expiry"])))

            print(f"{expiry:<19}  {client}  {clients_list[client]['IP']:<15}  {clients_list[client]['hostname']}")
        print (f"  <{count}>  known clients.")

    return clients_list


def scrape_pfsense_dhcp(url, user, password):
    """Queries the pfsense (+v2.4) dhcp leases status page and returns a list of dictionaries, one for each table row.
    The dictionary keys are the column names, such as "Hostname", "IP address", and "MAC address".
    
    Adapted from Github pletch/scrape_pfsense_dhcp_leases.py (https://gist.github.com/pletch/037a4a01c95688fff65752379534455f), thank you pletch.
    """
    s = requests.session()
    try:
        r = s.get(url,verify = False)
    except:
        logging.error(f"Error attempting to connect to <{url}>.  url and login credentials valid?")
        sys.exit(EXIT_FAIL)

    matchme = 'csrfMagicToken = "(.*)";var'
    csrf = re.search(matchme,str(r.text))
    payload = {'__csrf_magic' : csrf.group(1), 'login' : 'Login', 'usernamefld' : user, 'passwordfld' : password}
    r = s.post(url,data=payload,verify = False)
    r = s.get(url,verify = False)
    tree = _html.fromstring(r.content)

    headers = []
    none_index = 0
    tr_elements = tree.xpath('//tr')
    for header in tr_elements[0]:
        name = header.text
        if name == None:            # Ensure unique name for each column with no name
            name = "None" + str(none_index)
            none_index += 1
        headers.append(name)

    least_list = []
    xpath_base = '//body[1]//div[1]//div[2]//div[2]//table[1]//tbody//tr'
    for row in tree.xpath(xpath_base):
        row_dict = {}
        header_index = 0
        for node in row:
            item_text = node.text
            if item_text != None:
                item_text = item_text.strip()
            row_dict[headers[header_index]] = item_text
            header_index += 1
        least_list.append(row_dict)
    
    return(least_list)


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
    global tool, config, args, logfile_override
    global sort_by

    tool = set_toolname (TOOLNAME)
    parser = argparse.ArgumentParser(description=__doc__ + __version__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('SearchTerm', nargs='?',
                        help="Print database records containing this text.")
    parser.add_argument('--update', '-u', action="store_true",
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
    parser.add_argument('--setup-user', action='store_true',
                        help=f"Install starter files in user space.")
    parser.add_argument('--setup-site', action='store_true',
                        help=f"Install starter files in system-wide space. Run with root prev.")
    parser.add_argument('-V', '--version', action='version', version=f"{tool.toolname} {__version__}",
                        help="Return version number and exit.")
    args = parser.parse_args()


    # Deploy template files
    if args.setup_user:
        deploy_files([
            { "source": CONFIG_FILE,             "target_dir": "USER_CONFIG_DIR", "file_stat": 0o644, "dir_stat": 0o755},
            { "source": "creds_SMTP",            "target_dir": "USER_CONFIG_DIR", "file_stat": 0o600},
            { "source": "creds_routermonitor",   "target_dir": "USER_CONFIG_DIR", "file_stat": 0o600},
            { "source": "routermonitor.service", "target_dir": "USER_CONFIG_DIR", "file_stat": 0o644},
            ]) #, overwrite=True)
        sys.exit()

    if args.setup_site:
        deploy_files([
            { "source": CONFIG_FILE,             "target_dir": "SITE_CONFIG_DIR", "file_stat": 0o644, "dir_stat": 0o755},
            { "source": "creds_SMTP",            "target_dir": "SITE_CONFIG_DIR", "file_stat": 0o600},
            { "source": "creds_routermonitor",   "target_dir": "SITE_CONFIG_DIR", "file_stat": 0o600},
            { "source": "routermonitor.service", "target_dir": "SITE_CONFIG_DIR", "file_stat": 0o644},
            ]) #, overwrite=True)
        sys.exit()


    # Load config file and setup logging
    logfile_override = True  if not args.service  else False
    try:
        config = config_item(args.config_file)
        config.loadconfig(call_logfile_wins=logfile_override)         #, call_logfile=args.log_file, ldcfg_ll=10)
    except Exception as e:
        logging.error(f"Failed loading config file <{args.config_file}>. \
\n  Run with  '--setup-user' or '--setup-site' to install starter files.\n  {e}\n  Aborting.")
        sys.exit(EXIT_FAIL)


    logging.warning (f"========== {tool.toolname} ({__version__}) ==========")
    logging.warning (f"Config file <{config.config_full_path}>")


    # Print log
    if args.print_log:
        try:
            _lf = mungePath(getcfg("LogFile"), tool.log_dir_base).full_path
            print (f"Tail of  <{_lf}>:")
            _xx = collections.deque(_lf.open(), getcfg("PrintLogLength", PRINTLOGLENGTH))
            for line in _xx:
                print (line, end="")
        except Exception as e:
            print (f"Couldn't print the log file.  LogFile defined in the config file?\n  {e}")
        sys.exit()


    sort_by = getcfg("SortBy", DEFAULT_SORT_MODE)
    if args.sort_by:
        sort_by = args.sort_by
    if sort_by not in SORT_MODES:
        logging.error(f"Invalid SortBy value <{getcfg('SortBy')}> in config file")
        sys.exit(EXIT_FAIL)

    if not args.update and not args.list_dhcp_server and not args.print_log and not args.create_db and not args.note and not args.delete and not args.service:
        args.list_db = True     # If operation/mode not specified then default to list_db

    if args.service:
        service()

    sys.exit(main())


if __name__ == '__main__':
    sys.exit(cli())    