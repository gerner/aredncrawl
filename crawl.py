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

import requests

import pymx
from pymx import pymx_get

class CrawlException(Exception):
    def __init__(self, *args, retriable=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.retriable = retriable

class Crawler:
    def __init__(self, crawldir):
        self.crawldir = crawldir
        # set of everything we have crawled (for deduping)
        self.crawled = set()
        # queue of stuff to crawl
        self.to_crawl = deque()
        self.error_nodes = deque()
        self.error_count = 0

        self.logger = logging.getLogger("Crawler")

    def pymx_error_nodes(self, q):
        return list(self.error_nodes)

    def pymx_to_crawl(self, q):
        return list(self.to_crawl)

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
            logging.info(f'skipping crawl of {node}')
            f = open(filename, "r")
            result = json.load(f)
            f.close()
        else:
            try:
                response = requests.get(
                    f'http://{node}/cgi-bin/sysinfo.json?link_info=1&lqm=1',
                    proxies=dict(http='socks5h://localhost:5000'),
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

            f = open(filename, "w")
            f.write(response.text)
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
    parser.add_argument("--crawldir", nargs="?", default="/tmp/crawl", help="directory to store crawl files. creates if doesn't exist. skips crawling nodes that have a file here")

    args = parser.parse_args()

    if not os.path.isdir(args.crawldir):
        if os.path.exists(args.crawldir):
            raise Exception("crawldir exists and is not a directory")
        else:
            os.mkdir(args.crawldir)


    # get the starting node's ip address

    crawler = Crawler(crawldir=args.crawldir)
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
