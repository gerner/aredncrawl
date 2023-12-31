# aredncrawl
crawler for aredn meshes

Inspired by [kn6plv/MeshInfo](https://github.com/kn6plv/MeshInfo) which is in
node.js

# Quickstart

*Requirements:*

* python
* pip
* virtualenv (if you want to use virtualenv)

on Debian-based systems you could try (probably with sudo?):

```
apt-get install python python-pip python-venv
```

You probably want a virtual environment (or whatever you use). You'll need virtual env

```
python -mvenv .venv
. .venv/bin/activate
```

Install requirements

```
pip install -r requirements.txt
```

Run the crawler. It reads ip addresses to seed the crawler from stdin:

```
echo $FIRST_NODE_IP | python crawler.py
```

Crawl files are saved (by default) in `/tmp/crawl`

Run the visualization tool:

```
python viz.py
```

It'll create (at least) two files: `mesh_topo.pdf` and `mesh_map.json`. The
first is the network graph. The second is a geojson file mapping nodes that
share their location. You can import the geojson file into something like
[geojson.io](http://geojson.io).

For example:

* [network graph sample](https://drive.google.com/file/d/1Vv7_DbaxTrAeFWTOGYOCA-0MPRsvDM4o/view?usp=sharing)
* [map visualization](https://www.google.com/maps/d/u/0/edit?hl=en&mid=1HVMqIbpGF-_S0uNXjV1F1TclkIVBcXM&ll=40.60170599060227%2C-98.72273750000002&z=5) (the geojson was converted to kml because I couldn't quickly find a service that'll host imported geojson)

# Advanced Operation

This is all kinda advanced, but there are some options. Try checking help:

```
python crawler.py --help
```

Some selected options:

* `--crawldir CRAWLDIR` Directory to save crawl files in. These are the complete successful responses we get from nodes (sysinfo.json).
* `--proxy PROXYURL` Proxy url to use when talking to nodes. Maybe you can't route directly to mesh nodes, but can make a SOCKS proxy to one node that can? (that's how I do it)


## Setting up a SOCKS proxy via SSH

If you can ssh into your nodes (you'll need to set this up somehow)

in a new terminal:

```
ssh -D 5000 root@192.168.1.150 -p 2222 -N
```

crawl command to use the proxy:

```
echo $FIRST_NODE_IP | python crawler.py --proxy socks5h://localhost:5000
```
