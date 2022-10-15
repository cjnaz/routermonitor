#!/usr/bin/env python3
"""Funcs (gen 3)
A collection of support functions for simplifying writing tool scripts.

Functions:
    funcs3_min_version_check - Checker for funcs3 module min version
    setuplogging             - Set up default logger (use if not using loadconfig)
    loadconfig, getcfg       - Config file handlers
    timevalue, retime        - Handling time values used in config files
    requestlock, releaselock - Cross-tool/process safety handshake
    snd_notif, snd_email     - Send text and email messages

    Import this module from the main script as follows:
        from funcs3 import *
      or import specific items as needed:
        from funcs3 import PROGDIR, loadconfig, getcfg, cfg, timevalue, retime, setuplogging, logging, funcs3_min_version_check, funcs3_version, snd_notif, snd_email, requestlock, releaselock, ConfigError, SndEmailError
Globals:
    cfg - Dictionary that contains the info read from the config file
    PROGDIR - A string var that contains the full path to the main
        program directory.  Useful for file IO when running the script
        from a different pwd, such as when running from cron.
"""

funcs3_version = "V1.1 220412"

#==========================================================
#
#  Chris Nelson, 2018-2022
#
# V1.1  220412  Added timevalue and retime
# V1.0  220203  V1.0 baseline
# ...
# V0.1  180520  New
#
# Changes pending
#   
#==========================================================

import sys
import time
import os.path
import io
import smtplib
from email.mime.text import MIMEText
import logging
import tempfile
import re
import __main__

# Configs / Constants
# FILE_LOGGING_FORMAT    = '{asctime}/{module}/{funcName}/{levelname}:  {message}'    # Classic format
FILE_LOGGING_FORMAT    = '{asctime} {module:>15}.{funcName:20} {levelname:>8}:  {message}'
CONSOLE_LOGGING_FORMAT = '{module:>15}.{funcName:20} - {levelname:>8}:  {message}'
DEFAULT_LOGGING_LEVEL  = logging.WARNING

# Project globals
cfg = {}
PROGDIR = os.path.dirname(os.path.realpath(__main__.__file__)) + "/"


#=====================================================================================
#=====================================================================================
#  Module exceptions
#=====================================================================================
#=====================================================================================
class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class ConfigError(Error):
    """Exceptions raised for config file function errors.
    Attributes:
        message -- error message including item in error
    Format:
        ConfigError:  <function> - <message>.
    """
    def __init__(self, message):
        self.message = message

class SndEmailError(Error):
    """Exceptions raised for snd_email and snd_notif errors.
    Attributes:
        message -- error message including item in error
    Format:
        SndEmailError:  <function> - <message>.
    """
    def __init__(self, message):
        self.message = message


#=====================================================================================
#=====================================================================================
#  funcs3 minimum version check
#=====================================================================================
#=====================================================================================
def funcs3_min_version_check(min_version):
    """Compare current funcs3 module version against passed in minimum expected version.

    min_version
        Int or float
    
    Return True if current version >= passed-in min version, else False
    """
    current_version = float(funcs3_version[1:4])
    return True  if current_version >= min_version  else False


#=====================================================================================
#=====================================================================================
#  Logging setup
#=====================================================================================
#=====================================================================================
def setuplogging (loglevel, logfile=None):
    """Set up logging.

    loglevel
        10(DEBUG), 20(INFO), 30(WARNING), 40(ERROR), 50(CRITICAL)
    logfile
        Default None logs to console.  Absolute path or relative path from the
        main program directory may be specified.
    
    Returns nothing
    """

    if logfile == None:
        try:
            log_format = __main__.CONSOLE_LOGGING_FORMAT
        except:
            log_format = CONSOLE_LOGGING_FORMAT
        logging.basicConfig(level=loglevel, format=log_format, style='{')
    else:
        try:
            log_format = __main__.FILE_LOGGING_FORMAT
        except:
            log_format = FILE_LOGGING_FORMAT
        logpath = logfile
        if not os.path.isabs(logpath):
            logpath = os.path.join(PROGDIR, logpath)
        logging.basicConfig(level=loglevel, filename=logpath, format=log_format, style='{')


#=====================================================================================
#=====================================================================================
#  Config file functions loadconfig, getcfg, timevalue, retime
#=====================================================================================
#=====================================================================================
cfgline = re.compile(r"([^\s=:]+)[\s=:]+(.+)")
_config_timestamp = 0
_current_loglevel = None
_current_logfile  = None

def loadconfig(cfgfile      = 'config.cfg',
        cfgloglevel         = DEFAULT_LOGGING_LEVEL,
        cfglogfile          = None,
        cfglogfile_wins     = False,
        flush_on_reload     = False,
        force_flush_reload  = False,
        isimport            = False):
    """Read config file into dictionary cfg, and set up logging.
    
    See README.md loadconfig documentation for important usage details.  Don't call setuplogging if using loadconfig.

    cfgfile
        Default is 'config.cfg' in the program directory.  Absolute path or relative path from
        the main program directory may be specified.
    cfgloglevel
        Sets logging level during config file loading. Default is 30(WARNING).
    cfglogfile
        Log file to open - optional
    cfglogfile_wins
        cfglogfile overrides any LogFile specified in the config file
    flush_on_reload
        If the config file will be reloaded (due to being changed) then clean out cfg first
    force_flush_reload
        Forces cfg to be cleaned out and the config file to be reloaded
    isimport
        Internally set True when handling imports.  Not used by top-level scripts.

    Returns True if cfg has been (re)loaded, and False if not reloaded, so that the
    caller can do processing only if the cfg is freshly loaded.

    A ConfigError is raised if there are file access or parsing issues.
    """
    global _config_timestamp
    global cfg
    global _current_loglevel
    global _current_logfile
    
    # Initial logging will go to the console if no cfglogfile is specified on the initial loadconfig call.
    if _current_loglevel is None:
        setuplogging(cfgloglevel, logfile=cfglogfile)
        _current_loglevel = cfgloglevel
        _current_logfile  = cfglogfile
    
    external_loglevel = logging.getLogger().level           # Save externally set log level for later restore

    if force_flush_reload:
        logging.getLogger().setLevel(cfgloglevel)           # logging within loadconfig is always done at cfgloglevel
        _current_loglevel = cfgloglevel
        logging.debug("cfg dictionary flushed and forced reloaded (force_flush_reload)")
        cfg.clear()
        _config_timestamp = 0

    config = cfgfile
    if not os.path.isabs(config):
        config = os.path.join(PROGDIR, config)

    if not os.path.exists(config):
        _msg = f"Config file <{config}> not found."
        raise ConfigError (_msg)

    try:
        if not isimport:        # Top level config file
            current_timestamp = os.path.getmtime(cfgfile)
            if _config_timestamp == current_timestamp:
                return False

            # Initial load call, or config file has changed.  Do (re)load.
            _config_timestamp = current_timestamp
            logging.getLogger().setLevel(cfgloglevel)   # Set logging level for remainder of loadconfig call
            _current_loglevel = cfgloglevel

            if flush_on_reload:
                cfg.clear()
                logging.debug (f"cfg dictionary flushed and reloaded due to changed config file (flush_on_reload)")

        logging.info (f"Loading {config}")
        with io.open(config, encoding='utf8') as ifile:
            for line in ifile:
                if line.strip().lower().startswith("import"):           # Is an import line
                    line = line.split("#", maxsplit=1)[0].strip()
                    target = os.path.expanduser(line.split()[1])
                    if os.path.exists(target):
                        loadconfig(target, cfgloglevel, isimport=True)
                    else:
                        _msg = f"Could not find and import <{target}>"
                        raise ConfigError (_msg)
                else:                                                   # Is a param/key line
                    _line = line.split("#", maxsplit=1)[0].strip()
                    if len(_line) > 0:
                        out = cfgline.match(_line)
                        if out:
                            key = out.group(1)
                            rol = out.group(2)  # rest of line
                            isint = False
                            try:
                                cfg[key] = int(rol)         # add int to dict
                                isint = True
                            except:
                                pass
                            if not isint:
                                if rol.lower() == "true":   # add bool to dict
                                    cfg[key] = True
                                elif rol.lower() == "false":
                                    cfg[key] = False
                                else:
                                    cfg[key] = rol          # add string to dict
                            logging.debug (f"Loaded {key} = <{cfg[key]}>  ({type(cfg[key])})")
                        else: logging.warning (f"loadconfig:  Error on line <{line}>.  Line skipped.")


    except Exception as e:
        _msg = f"Failed while attempting to open/read config file <{config}>.\n  {e}"
        raise ConfigError (_msg) from None

    # Operations only for finishing a top-level call
    if not isimport:
        if not cfglogfile_wins:
            config_logfile  = getcfg("LogFile", None)
            if config_logfile is not None:
                if not os.path.isabs(config_logfile):
                    config_logfile = os.path.join(PROGDIR, config_logfile)
            logger = logging.getLogger()
            if config_logfile != _current_logfile:
                if config_logfile is None:
                    logging.error("Changing the LogFile from a real file to None (console) is not supported.  Aborting.")
                    sys.exit()
                logger.handlers.clear()
                try:
                    log_format = __main__.FILE_LOGGING_FORMAT
                except:
                    log_format = FILE_LOGGING_FORMAT
                handler = logging.FileHandler(config_logfile, "a")
                handler.setFormatter(logging.Formatter(fmt=log_format, style='{'))
                logger.addHandler(handler)
                _current_logfile = config_logfile
                logging.info (f"Logging file  changed to <{config_logfile}>")

        if getcfg("DontEmail", False):
            logging.info ('DontEmail is set - Emails and Notifications will NOT be sent')
        elif getcfg("DontNotif", False):
            logging.info ('DontNotif is set - Notifications will NOT be sent')

        config_loglevel = getcfg("LogLevel", None)
        if config_loglevel is not None:
            if config_loglevel != _current_loglevel:
                logging.info (f"Logging level changed to <{config_loglevel}> from config file")
                logging.getLogger().setLevel(config_loglevel)       # Restore loglevel from that set by cfgloglevel
                _current_loglevel = config_loglevel
        else:
            if external_loglevel != _current_loglevel:
                logging.info (f"Logging level changed to <{external_loglevel}> from main script")
                logging.getLogger().setLevel(external_loglevel)     # Restore loglevel from that set by cfgloglevel
                _current_loglevel = external_loglevel

    return True


def getcfg(param, default="__nodefault__"):
    """Get a param from the cfg dictionary.

    Returns the value of param from the cfg dictionary.  Equivalent to just referencing cfg[]
    but with handling if the item does not exist.
    
    param
        String name of param/key to be fetched from cfg
    default
        if provided, is returned if the param doesn't exist in cfg

    Raises ConfigError if param does not exist in cfg and no default provided.
    """
    
    try:
        return cfg[param]
    except:
        if default != "__nodefault__":
            return default
    _msg = f"getcfg - Config parameter <{param}> not in cfg and no default."
    raise ConfigError (_msg)


class timevalue():
    def __init__(self, original):
        """Convert short time value string/int/float in resolution seconds, minutes, hours, days,
        or weeks to seconds.
            EG:  20, 30s, 5m, 3D, 2w, 3.1415m.  
        Time unit suffix is case insensitive, and optional (defaults to seconds).

        Instance-specific vars:

        original
            The original passed-in value (type str)
        seconds
            Time value in seconds (type float or int)
        unit_char
            Unit character of the passed-in value ("s", "m", "h", "d", or "w")
        unit_str
            Unit string of the passed-in value ("secs", "mins", "hours", "days", or "weeks")
        
        Months (and longer) are not supported, since months start with 'm', as does minutes, and no practical use.

        Raises ValueError if given an unsupported time unit suffix.
        """
        self.original = str(original)

        if type(original) in [int, float]:              # Case int or float
            self.seconds =  float(original)
            self.unit_char = "s"
            self.unit_str =  "secs"
        else:
            try:
                self.seconds = float(original)          # Case str without units
                self.unit_char = "s"
                self.unit_str = "secs"
                return
            except:
                pass
            self.unit_char =  original[-1:].lower()     # Case str with units
            if self.unit_char == "s":
                self.seconds =  float(original[:-1])
                self.unit_str = "secs"
            elif self.unit_char == "m":
                self.seconds =  float(original[:-1]) * 60
                self.unit_str = "mins"
            elif self.unit_char == "h":
                self.seconds =  float(original[:-1]) * 60*60
                self.unit_str = "hours"
            elif self.unit_char == "d":
                self.seconds =  float(original[:-1]) * 60*60*24
                self.unit_str = "days"
            elif self.unit_char == "w":
                self.seconds =  float(original[:-1]) * 60*60*24*7
                self.unit_str = "weeks"
            else:
                raise ValueError(f"Illegal time units <{self.unit_char}> in time string <{original}>")


def retime(time_sec, unitC):
    """ Convert time value in seconds to unitC resolution, return type float

    time_sec
        Time value in resolution seconds, type int or float.
    unitC
        Target time resolution ("s", "m", "h", "d", or "w")
    
    Raises ValueError if not given an int or float seconds value or given an unsupported unitC time unit suffix.
    """
    if type(time_sec) in [int, float]:
        if unitC == "s":  return time_sec
        if unitC == "m":  return time_sec /60
        if unitC == "h":  return time_sec /60/60
        if unitC == "d":  return time_sec /60/60/24
        if unitC == "w":  return time_sec /60/60/24/7
        raise ValueError(f"Invalid unitC value <{unitC}> passed to retime()")
    else:
        raise ValueError(f"Invalid seconds value <{time_sec}> passed to retime().  Must be type int or float.")


#=====================================================================================
#=====================================================================================
#  Lock file management functions
#=====================================================================================
#=====================================================================================

LOCKFILE_DEFAULT = "funcs3_LOCK"
LOCK_TIMEOUT     = 5                # seconds

def requestlock(caller, lockfile=LOCKFILE_DEFAULT, timeout=LOCK_TIMEOUT):
    """Lock file request.

    caller
        Info written to the lock file and displayed in any error messages
    lockfile
        Lock file name.  Various lock files may be used simultaneously
    timeout
        Default 5s

    Returns
        0:  Lock request successful
       -1:  Lock request failed.  Warning level log messages are generated.
    """
    lock_file = os.path.join(tempfile.gettempdir(), lockfile)

    xx = time.time() + timeout
    while True:
        if not os.path.exists(lock_file):
            try:
                with io.open(lock_file, 'w', encoding='utf8') as ofile:
                    ofile.write(f"Locked by <{caller}> at {time.asctime(time.localtime())}.")
                    logging.debug (f"LOCKed by <{caller}> at {time.asctime(time.localtime())}.")
                return 0
            except Exception as e:
                logging.warning(f"Unable to create lock file <{lock_file}>\n  {e}")
                return -1
        else:
            if time.time() > xx:
                break
        time.sleep(0.1)

    try:
        with io.open(lock_file, encoding='utf8') as ifile:
            lockedBy = ifile.read()
        logging.warning (f"Timed out waiting for lock file <{lock_file}> to be cleared.  {lockedBy}")
    except Exception as e:
        logging.warning (f"Timed out and unable to read existing lock file <{lock_file}>\n  {e}.")
    return -1


def releaselock(lockfile=LOCKFILE_DEFAULT):
    """Lock file release.

    Any code can release a lock, even if that code didn't request the lock.
    Generally, only the requester should issue the releaselock.

    lockfile
        Lock file to remove/release

    Returns
        0:  Lock release successful (lock file deleted)
       -1:  Lock release failed.  Warning level log messages are generated.
    """
    lock_file = os.path.join(tempfile.gettempdir(), lockfile)
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except Exception as e:
            logging.warning (f"Unable to remove lock file <{lock_file}>\n  {e}.")
            return -1
        logging.debug(f"Lock file removed: <{lock_file}>")
        return 0
    else:
        logging.warning(f"Attempted to remove lock file <{lock_file}> but the file does not exist.")
        return -1


#=====================================================================================
#=====================================================================================
#  Notification and email functions
#=====================================================================================
#=====================================================================================

def snd_notif(subj='Notification message', msg='', to='NotifList', log=False):
    """Send a text message using the cfg NotifList.

    subj
        Subject text string
    msg
        Message text string
    to
        To whom to send the message.  'to' may be either an explicit string list of email addresses
        (whitespace or comma separated) or the name of a config file keyword (also listing one
        or more whitespace/comma separated email addresses).  If the 'to' parameter does not
        contain an '@' it is assumed to be a config keyword - default 'NotifList'.
    log
        If True, elevates log level from DEBUG to WARNING to force logging

    cfg NotifList is required in the config file (unless 'to' is always explicitly passed)
    cfg DontNotif and DontEmail are optional, and if == True no text message is sent. Useful for debug.

    Raises SndEmailError on call errors and sendmail errors
    """

    if getcfg('DontNotif', default=False)  or  getcfg('DontEmail', default=False):
        if log:
            logging.warning (f"Notification NOT sent <{subj}> <{msg}>")
        else:
            logging.debug (f"Notification NOT sent <{subj}> <{msg}>")
        return

    snd_email (subj=subj, body=msg, to=to)
    if log:
        logging.warning (f"Notification sent <{subj}> <{msg}>")
    else:
        logging.debug (f"Notification sent <{subj}> <{msg}>")


def snd_email(subj='', body='', filename='', htmlfile='', to='', log=False):
    """Send an email message using email account info from the config file.

    Either body, filename, or htmlfile must be passed.  Call with only one of body, filename, 
    or htmlfile, or results may be bogus.  snd_email does not support multi-part MIME (an 
    html send wont have a plain text part).

    subj
        Email subject text
    body
        A string message to be sent
    filename
        A string full path to the file to be sent.  Default path is the PROGDIR.
        Absolute and relative paths from PROGDIR accepted.
    htmlfile
        A string full path to an html formatted file to be sent.  Default path is the PROGDIR.
        Absolute and relative paths from PROGDIR accepted.
    to
        To whom to send the message.  'to' may be either an explicit string list of email addresses
        (whitespace or comma separated) or the name of a config file keyword (also listing one
        or more whitespace/comma separated email addresses).  If the 'to' parameter does not
        contain an '@' it is assumed to be a config keyword - no default.
    log
        If True, elevates log level from DEBUG to WARNING to force logging of the email subj

    cfg EmailFrom, EmailServer, and EmailServerPort are required in the config file.
        EmailServerPort must be one of the following:
            P25:  SMTP to port 25 without any encryption
            P465: SMTP_SSL to port 465
            P587: SMTP to port 587 without any encryption
            P587TLS:  SMTP to port 587 and with TLS encryption
    cfg EmailUser and EmailPass are optional in the config file.
        Needed if the server requires credentials.  Recommend that these params be in a secure file in 
        one's home dir and import the file via the config file.
    cfg DontEmail is optional, and if == True no email is sent.
        Also blocks snd_notifs.  Useful for debug.
    cfg EmailVerbose = True enables the emailer debug level.

    Raises SndEmailError on call errors and sendmail errors
    """

    if getcfg('DontEmail', default=False):
        if log:
            logging.warning (f"Email NOT sent <{subj}>")
        else:
            logging.debug (f"Email NOT sent <{subj}>")
        return

    # Deal with what to send
    if body != '':
        msg_type = "plain"
        m_text = body
    elif os.path.exists(filename):
        msg_type = "plain"
        with io.open(filename, encoding='utf8') as ifile:
            m_text = ifile.read()
    elif os.path.exists(htmlfile):
        msg_type = "html"
        with io.open(htmlfile, encoding='utf8') as ifile:
            m_text = ifile.read()
    else:
        _msg = f"snd_email - Message subject <{subj}>:  No body and can't find filename <{filename}> or htmlfile <{htmlfile}>."
        raise SndEmailError (_msg)
    m_text += f"\n(sent {time.asctime(time.localtime())})"

    # Deal with 'to'
    def extract_email_addresses(addresses):
        """Return list of email addresses from comma or whitespace separated string 'addresses'.
        """
        if ',' in addresses:
            tmp = addresses.split(',')
            addrs = []
            for addr in tmp:
                addrs.append(addr.strip())
        else:
            addrs = addresses.split()
        return addrs

    if '@' in to:
        To = extract_email_addresses(to)
    else:
        To = extract_email_addresses(getcfg(to, ""))
    if len(To) == 0:
        _msg = f"snd_email - Message subject <{subj}>:  'to' list must not be empty."
        raise SndEmailError (_msg)
    for address in To:
        if '@' not in address:
            _msg = f"snd_email - Message subject <{subj}>:  address in 'to' list is invalid: <{address}>."
            raise SndEmailError (_msg)

    # Send the message
    try:
        msg = MIMEText(m_text, msg_type)
        msg['Subject'] = subj
        msg['From'] = getcfg('EmailFrom')
        msg['To'] = ", ".join(To)

        cfg_server = getcfg('EmailServer')
        cfg_port   = getcfg('EmailServerPort')
        if cfg_port == "P25":
            server = smtplib.SMTP(cfg_server, 25)
        elif cfg_port == "P465":
            server = smtplib.SMTP_SSL(cfg_server, 465)
        elif cfg_port == "P587":
            server = smtplib.SMTP(cfg_server, 587)
        elif cfg_port == "P587TLS":
            server = smtplib.SMTP(cfg_server, 587)
            server.starttls()
        else:
            raise ConfigError (f"Config EmailServerPort <{cfg_port}> is invalid")

        if 'EmailUser' in cfg:
            server.login (getcfg('EmailUser'), getcfg('EmailPass'))
        if getcfg("EmailVerbose", False):
            server.set_debuglevel(1)
        server.sendmail(getcfg('EmailFrom'), To, msg.as_string())
        server.quit()

        if log:
            logging.warning (f"Email sent <{subj}>")
        else:
            logging.debug (f"Email sent <{subj}>")
    except Exception as e:
        _msg = f"snd_email:  Send failed for <{subj}>:\n  <{e}>"
        raise SndEmailError (_msg)


if __name__ == '__main__':

    loadconfig (cfgfile='testcfg.cfg', cfgloglevel=10)

    # # ===== Tests for funcs3_min_version_check =====
    # if not funcs3_min_version_check(2):
    #     print(f"ERROR:  funcs3 module must be at least version 2.0.  Found <{funcs3_version}>.")
    # if funcs3_min_version_check(1):
    #     print(f"funcs3_min_version_check passes.  Found <{funcs3_version}>.")


    # # ===== Tests for loadconfig, getcfg =====
    # # Test config loading exceptions
    # try:
    #     loadconfig("nosuchfile.cfg", cfgloglevel=getcfg("CfgLogLevel", 30))
    # except ConfigError as e:
    #     logging.error (f"In main...  {e}")
    # loadconfig("nosuchfile.cfg")      # This one exercises untrapped error caught by Python

    # # Test config reload - Edit CfgLogLevel, LogLevel, LogFile, and testvar in testcfg.cfg
    # print (f"Initial logging level: {logging.getLogger().level}")
    # while True:
    #     reloaded = loadconfig (cfgfile='testcfg.cfg', cfgloglevel=getcfg("CfgLogLevel", 30), flush_on_reload=True) #, cfglogfile="junk9.txt")#, cfgloglevel=10)
    #     if reloaded:
    #         print ("\nConfig file reloaded")
    #         print (f"Logging level: {logging.getLogger().level}")
    #         logging.debug   ("Debug   level message")
    #         logging.info    ("Info    level message")
    #         logging.warning ("Warning level message")
    #         print ("testvar", getcfg("testvar", None), type(getcfg("testvar", None)))
    #     time.sleep(.5)

    # # Tests for getcfg with/without defaults
    # print (f"Testing getcfg - Not in cfg with default: <{getcfg('NotInCfg', 'My Default Value')}>")
    # try:
    #     getcfg('NotInCfg-NoDef')
    # except ConfigError as e:
    #     print (e)
    # getcfg('NotInCfg-NoDef')          # This one exercises untrapped error caught by Python

    # # Test flush_on_reload, force_flush
    # from pathlib import Path
    # cfg["dummy"] = True
    # print (f"var dummy in cfg: {getcfg('dummy', False)} (should be True)")
    # loadconfig(cfgfile='testcfg.cfg', flush_on_reload=True, cfgloglevel=10)
    # print (f"var dummy in cfg: {getcfg('dummy', False)} (should be True because not reloaded)")
    # Path('testcfg.cfg').touch()
    # loadconfig(cfgfile='testcfg.cfg', cfgloglevel=10)
    # print (f"var dummy in cfg: {getcfg('dummy', False)} (should be True because not flushed on reload)")
    # Path('testcfg.cfg').touch()
    # loadconfig(cfgfile='testcfg.cfg', flush_on_reload=True, cfgloglevel=10)
    # print (f"var dummy in cfg: {getcfg('dummy', False)} (should be False because flush_on_reload)")
    # cfg["dummy"] = True
    # loadconfig(cfgfile='testcfg.cfg', force_flush_reload=True, cfgloglevel=10)
    # print (f"var dummy in cfg: {getcfg('dummy', False)} (should be False because force_flush_reload)")

    # # ==== Tests for timevalue, retime =====
    # def dump(xx):
    #     print (f"Given <{xx}> (type {type(xx)}):")
    #     yy = timevalue(xx)
    #     print (f"    Original:   <{yy.original}>")
    #     print (f"    Seconds:    <{yy.seconds}>")
    #     print (f"    Unit char:  <{yy.unit_char}>")
    #     print (f"    Unit str:   <{yy.unit_str}>")
    #     print (f"    retimed:    <{retime(yy.seconds, yy.unit_char)}> {yy.unit_str}")

    # dump (getcfg("Tint"))
    # dump (getcfg("Tsec"))
    # dump (getcfg("Tmin"))
    # dump (getcfg("Thour"))
    # dump (getcfg("Tday"))
    # dump (getcfg("Tweek"))
    # dump (2/7)
    # dump ("5.123m")
    # # dump ("3y")             # ValueError raised in mytime
    # # retime (12345, "y")     # ValueError raised in retime
    # sleeptime = timevalue("1.9s")
    # print (f"Sleeping {sleeptime.seconds} {sleeptime.unit_str}")
    # time.sleep (sleeptime.seconds)
    # print ("done sleeping")


    # # ===== Tests for snd_notif and snd_email =====
    # # Set debug LogLevel in testcfg.cfg
    # cfg['DontEmail'] = True     # Comment these in/out here or in the testcfg.cfg
    # cfg['DontNotif'] = True
    # snd_email (subj="body to EmailTo", body="To be, or not to be...", to="EmailTo", log=True)
    # snd_email (subj="body to EmailTo - not logged", body="To be, or not to be...", to="EmailTo")
    # snd_email (subj="filename to EmailTo - not logged", filename="LICENSE.txt", to="EmailTo")
    # snd_email (subj="htmlfile to EmailTo", htmlfile="testfile.html", to="EmailTo", log=True)
    # snd_email (subj="body to EmailToMulti", body="To be, or not to be...", to="EmailToMulti", log=True)
    # try:
    #     snd_email (subj="No such file nofile.txt", filename="nofile.txt", to="EmailTo", log=True)
    # except SndEmailError as e:
    #     print (f"snd_email failed:  {e}")
    # try:
    #     snd_email (subj="No to=", body="Hello")
    # except SndEmailError as e:
    #     print (f"snd_email failed:  {e}")
    # try:
    #     snd_email (subj="Invalid to=", body="Hello", to="me@example.com, junkAtexample.com", log=True)
    # except SndEmailError as e:
    #     print (f"snd_email failed:  {e}")
    # snd_notif (subj="This is a test subject - not logged", msg='This is the message body')       # to defaults to cfg["NotifList"]
    # snd_notif (subj="This is another test subject", msg='This is another message body', log=True)


    # # ===== Tests for lock files =====
    # stat = requestlock ("try1")
    # print (f"got back from 1st requestLock.  stat = {stat}")
    # stat = requestlock ("try2")
    # print (f"got back from 2nd requestLock.  stat = {stat}")
    # stat = releaselock ()
    # print (f"got back from 1st releaseLock.  stat = {stat}")
    # stat = releaselock ()
    # print (f"got back from 2nd releaseLock.  stat = {stat}")