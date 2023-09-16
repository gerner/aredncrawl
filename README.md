# aredncrawl
crawler for aredn meshes

Inspired by [kn6plv/MeshInfo](https://github.com/kn6plv/MeshInfo) which is in
node.js

# Quickstart

You probably want a virtual environment (or whatever you use)

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
