import json
import ipaddress
from enum import unique, Enum

from sonic_ax_impl import mibs
from ax_interface import MIBMeta, ValueType, MIBUpdater, ContextualMIBEntry, SubtreeMIBEntry
from ax_interface.encodings import OctetString
from ax_interface.util import mac_decimals
from bisect import bisect_right

def ip2tuple(ip):
    return tuple(int(bs) for bs in str(ip).split('.'))

class RouteUpdater(MIBUpdater):
    def __init__(self):
        super().__init__()
        self.tos = 0 # ipCidrRouteTos
        self.db_conn, _, _, _, _, _ = mibs.init_sync_d_interface_tables()
        self.update_data()

    def update_data(self):
        """
        Update redis (caches config)
        Pulls the table references for each interface.
        """
        self.route_dest_map = {}
        self.route_dest_list = []

        self.db_conn.connect(mibs.APPL_DB)
        route_entries = self.db_conn.keys(mibs.APPL_DB, "ROUTE_TABLE:*")

        for route_entry in route_entries:
            routestr = route_entry.decode()
            ipnstr = routestr[len("ROUTE_TABLE:"):]
            if ipnstr == "0.0.0.0/0":
                ipn = ipaddress.ip_network(ipnstr)
                ent = self.db_conn.get_all(mibs.APPL_DB, routestr, blocking=True)
                nexthops = ent[b"nexthop"].decode()
                for nh in nexthops.split(','):
                    sub_id = ip2tuple(ipn.network_address) + ip2tuple(ipn.netmask) + (self.tos,) + ip2tuple(nh)
                    self.route_dest_list.append(sub_id)
                    self.route_dest_map[sub_id] = ipn.network_address.packed

        self.route_dest_list.sort()

    def route_dest(self, sub_id):
        return self.route_dest_map.get(sub_id, None)

    def get_next(self, sub_id):
        right = bisect_right(self.route_dest_list, sub_id)
        if right >= len(self.route_dest_list):
            return None

        return self.route_dest_list[right]

class IpCidrRouteTable(metaclass=MIBMeta, prefix='.1.3.6.1.2.1.4.24.4'):
    """
    'ipCidrRouteDest table in IP Forwarding Table MIB' https://tools.ietf.org/html/rfc4292
    """

    route_updater = RouteUpdater()

    ipCidrRouteDest = \
        SubtreeMIBEntry('1.1', route_updater, ValueType.IP_ADDRESS, route_updater.route_dest)
