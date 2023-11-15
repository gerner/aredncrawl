""" Crawl an AREDN network

want to extract the entire network graph
"""

import sys
import os.path
import logging
import re
import json
from collections import deque
import argparse
import socket

import requests
import dns.resolver
import dns.reversename

import pymx
from pymx import pymx_get

def merge(a: dict, b: dict, path=[]):
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path + [str(key)])
            else:
                a[key] = b[key]
        else:
            a[key] = b[key]
    return a

class CrawlException(Exception):
    def __init__(self, *args, retriable=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.retriable = retriable

class Crawler:
    def __init__(self, crawldir, proxy_url=None, dns_server=None, use_olsrd=False):
        self.crawldir = crawldir

        if proxy_url:
            self.proxy_dict = dict(http=proxy_url) # socks5h://localhost:5000'
        else:
            self.proxy_dict = dict()

        # set of everything we have crawled (for deduping)
        self.crawled = set()
        # queue of stuff to crawl
        self.to_crawl = deque()
        self.error_nodes = deque()
        self.error_count = 0

        self.resolver = dns.resolver.Resolver()
        if dns_server:
            dns_server = socket.gethostbyname(dns_server)
            self.resolver.nameservers = [dns_server]

        self.use_olsrd = use_olsrd

        self.logger = logging.getLogger("Crawler")

    def pymx_error_nodes(self, q):
        return list(self.error_nodes)

    def pymx_to_crawl(self, q):
        return list(self.to_crawl)

    def reverse_lookup(self, ip):
        # TODO: what if this fails?
        self.logger.info(ip)
        addr = dns.reversename.from_address(ip)
        try:
            response = self.resolver.resolve(addr,"PTR")
        except dns.resolver.NXDOMAIN:
            return ip
        return re.sub(r'\.$', "", str(response[0]))

    def ip_lookup(self, hostname):
        # TODO: what if this fails?
        self.logger.info(hostname)
        try:
            response = self.resolver.resolve(hostname, "A")
        except dns.resolver.NXDOMAIN:
            # TODO: is this ok? we're expecting an ip address
            # I guess it's ok if it came in as an ip address, but otherwise...
            return hostname
        return str(response[0])

    def get_olsr_interface_type(self, iface):
        if re.match("wlan", iface):
            return "RF"
        elif re.match("eth", iface):
            return "DTD"
        elif re.match("tun", iface):
            return "TUN"
        return "UNKNOWN"

    def olsrd_to_link_info(self, olsrd_response):
        """ converts an olsrd response to sysinfo.json?link_info=1 response.

        We need to do this because some nodes don't respond with all their
        links. I think this was a bug that got fixed in later (3.23) AREDN
        versions.
        """

        # this is heavily inspired by olsr.lua getCurrentNeighbors
        info = {}
        for v in olsrd_response["links"]:
            ip = v["remoteIP"]
            hostname = self.reverse_lookup(ip)
            hostname = re.sub(r'mid\d+.', "", hostname)
            hostname = re.sub(r'dtdlink\.', "", hostname)
            hostname = re.sub(r'\.local\.mesh$', "", hostname)
            mainip = self.ip_lookup(hostname)
            info[mainip] = {}
            info[mainip]["hostname"] = hostname

            info[mainip]['olsrInterface']=v['olsrInterface']
            info[mainip]['linkType']= self.get_olsr_interface_type(v['olsrInterface'])
            info[mainip]['linkQuality']=v['linkQuality']
            info[mainip]['neighborLinkQuality']=v['neighborLinkQuality']

            info[mainip]['validityTime']=v['validityTime']
            info[mainip]['symmetryTime']=v['symmetryTime']
            info[mainip]['asymmetryTime']=v['asymmetryTime']
            info[mainip]['vtime']=v['vtime']
            info[mainip]['currentLinkStatus']=v['currentLinkStatus']
            info[mainip]['previousLinkStatus']=v['previousLinkStatus']
            info[mainip]['hysteresis']=v['hysteresis']
            info[mainip]['pending']=v['pending']
            info[mainip]['lostLinkTime']=v['lostLinkTime']
            info[mainip]['helloTime']=v['helloTime']
            info[mainip]['lastHelloTime']=v['lastHelloTime']
            info[mainip]['seqnoValid']=v['seqnoValid']
            info[mainip]['seqno']=v['seqno']
            info[mainip]['lossHelloInterval']=v['lossHelloInterval']
            info[mainip]['lossTime']=v['lossTime']
            info[mainip]['lossMultiplier']=v['lossMultiplier']
            info[mainip]['linkCost']=v['linkCost']

            # unfortunately there is additional RF link info we can't get
            # including signal/noise levels, tx/rx rates, and bandwith
        return info

    def run(self):
        while len(self.to_crawl) + len(self.error_nodes) > 0:

            if len(self.to_crawl) == 0:
                logging.info(f'retrying error nodes. error_count={self.error_count}')
                self.to_crawl.extend(self.error_nodes)
                self.error_nodes.clear()
                self.error_count += 1

            logging.info(f'crawled:\t{len(self.crawled)}\tto_crawl:\t{len(self.to_crawl)}\terror_nodes:\t{len(self.error_nodes)}\terror_count:\t{self.error_count}')
            next_node = self.to_crawl.pop()

            try:
                neighbors = self.crawl(next_node)
            except CrawlException as e:
                if e.retriable:
                    self.error_nodes.appendleft(next_node)
                continue

            self.crawled.add(next_node)
            for neighbor in neighbors:
                if neighbor in self.crawled:
                    logging.info(f'skipping {neighbor}')
                    continue

                if neighbor in self.to_crawl:
                    continue

                self.to_crawl.appendleft(neighbor)

    def crawl(self, node):
        """ Crawls a node and returns the neighbors.

        also saves the sysinfo result to file.
        """

        logging.info(f'crawling {node}')

        # fetch sysinfo with link_info and lqm
        # http://192.168.1.150/cgi-bin/sysinfo.json?link_info=1&lqm=1

        filesafe = re.sub("\.", "_", node)
        filename = os.path.join(self.crawldir, f'{filesafe}.json')
        if os.path.isfile(filename):
            logging.info(f'using crawl file {filename} for {node}')
            f = open(filename, "r")
            result = json.load(f)
            f.close()
        else:
            try:
                response = requests.get(
                    f'http://{node}/cgi-bin/sysinfo.json?link_info=1&lqm=1',
                    proxies=self.proxy_dict,
                    timeout=60,
                )
            except Exception as e:
                logging.warning(f'{node} failed to get sysinfo {e}')
                raise CrawlException(e)

            # TODO: error handling
            if response.status_code != 200:
                logging.warning(f'{node} gave status code {response.status_code}')
                raise CrawlException()

            try:
                result = response.json()
            except Exception as e:
                logging.warning(f'{node} gave bad json {e}')
                raise CrawlException(e)

            if self.use_olsrd:
                try:
                    olsrd_response = requests.get(
                        f'http://{node}:9090/links',
                        proxies=self.proxy_dict,
                        timeout=60,
                    )
                except Exception as e:
                    logging.warning(f'{node} failed to get olsrd links {e}')
                    raise CrawlException(e)

                if olsrd_response.status_code != 200:
                    logging.warning(f'{node} gave olsrd links status code {olsrd_response.status_code}')
                    raise CrawlException()

                try:
                    olsrd_result = olsrd_response.json()
                except Exception as e:
                    logging.warning(f'{node} gave olsrd links bad json {e}')
                    raise CrawlException(e)

                olsrd_link_info = self.olsrd_to_link_info(olsrd_result)

                # merge translated response into existing link_info
                if "link_info" not in result:
                    result["link_info"] = {}
                result["link_info"] = merge(olsrd_link_info, result["link_info"])

            f = open(filename, "w")
            json.dump(result, f)
            f.close()

        neighbors = set()

        if "link_info" not in result:
            logging.warning(f'{node} had no link_info')
            raise CrawlException(retriable=False)

        if len(result["link_info"]) > 0:
            for k,v in result["link_info"].items():
                logging.info(f'neighbor {k}')
                neighbors.add(k)

        return neighbors

def main():
    logging.basicConfig(
            format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
            stream=sys.stderr,
            level=logging.INFO
    )

    parser = argparse.ArgumentParser(
        prog='crawl',
        description='Crawls an AREDN mesh',
        #epilog='Text at the bottom of help'
    )
    parser.add_argument("--crawldir", nargs="?", default="/tmp/crawl", help="directory to store crawl files. creates if doesn't exist. skips crawling nodes that have a file here. default /tmp/crawl")
    parser.add_argument("--proxy", nargs="?", default=None, help="proxy url (e.g. \"socks5h://localhost:5000\") to use for requests to mesh nodes. default no proxy")
    parser.add_argument("--dns", nargs="?", default=None, help="dns server to use for mesh hostnames (e.g. \"KK7LZM-ar300m16-2.lan\") default is standard name resolution")
    parser.add_argument("--olsrd", action="store_true", help="use olsrd directly to enhance sysinfo.json's link_info (sysinfo.json wins for ambiguous link_info entries)")

    args = parser.parse_args()

    if not os.path.isdir(args.crawldir):
        if os.path.exists(args.crawldir):
            raise Exception("crawldir exists and is not a directory")
        else:
            os.mkdir(args.crawldir)


    # get the starting node's ip address

    crawler = Crawler(crawldir=args.crawldir, proxy_url=args.proxy, dns_server=args.dns, use_olsrd=args.olsrd)
    for node_name in sys.stdin:
        node_name = node_name.strip()
        crawler.to_crawl.appendleft(node_name)

    # start pymx management interface
    pymx.register_get(crawler.pymx_error_nodes, "/error_nodes")
    pymx.register_get(crawler.pymx_to_crawl, "/to_crawl")
    pymx.start()

    crawler.run()

if __name__ == "__main__":
    main()

"""
# $HOST:9090/link gives olsr link info
# ifName gives link type: wlan -> RF, eth -> DTD, tun -> TUN
# reverse dns lookup:
from dns import resolver,reversename
addr=reversename.from_address(IP_ADDR_AS_STRING)
r = resolver.Resolver()
r.nameservers = [NAMESERVER]
hostname = str(resolver.resolve(addr,"PTR")[0])
"""
