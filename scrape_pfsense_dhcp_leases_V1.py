#!/usr/bin/env python3
"""This python script provides a function to query the pfsense (+v2.4) dhcp leases status page and return a list of 
dictionaries, one for each table row.  The dictionary keys are the column names, such as "Hostname", "IP address", and "MAC address".
To use, ensure LXML is installed via package manager or via pip.
"""

# 16-Dec-2016 - Original release
# 3-Sep-2020  - Minor update to match formatting of leases page in latest pfSense version (2.4.5).
# 9-Sep-2020  - Backported improvements to handle table rows with missing data, use global variables for user/pass/server_ip, 
#               and return list from scrape function as implemented by fryguy04 in fork here:
#                   https://gist.github.com/fryguy04/7d12b789260c47c571f42e5bc733a813
# 9-Sep-2020  - Added parsing of pfSense lease table header.  Discovered that adding element of ClientID in the static dhcp 
#               definitions alters the column sequence.  This modification ensures that the correct columns are found and parsed.
# 9-Sep-2020  - Removed file export function    
# 7-Nov-2121  - cjnaz - V1 - restructured to return a list of dictionaries.  Tested on pfSense+ V 21.05.2-RELEASE (Community Edition ~V2.5.2).


import requests
from lxml import html
import re

url  = "http://192.168.1.1/status_dhcp_leases.php" #change url to match your pfsense machine address. Note http or https!
user = "admin" #'your_username'  #Username for pfSense login
password = 'your_password' #Password for pfSense login


def scrape_pfsense_dhcp(url, user, password):

    s = requests.session()
    r = s.get(url,verify = False)

    matchme = 'csrfMagicToken = "(.*)";var'
    csrf = re.search(matchme,str(r.text))

    payload = {
'__csrf_magic' : csrf.group(1),
'login' : 'Login',
'usernamefld' : user,
'passwordfld' : password
}
    r = s.post(url,data=payload,verify = False)
    r = s.get(url,verify = False)
    tree = html.fromstring(r.content)

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


if __name__ == "__main__":     
    dhcp_list = scrape_pfsense_dhcp(url, user, password)

    for entry in dhcp_list:
            print(entry)
