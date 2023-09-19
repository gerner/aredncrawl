""" Visualize mesh graph from sysinfo files. 

Nodes in graph are AREDEN nodes, edges are direct neighbor links (dtd, tun,
rf) between them. """

# handy awk to convert a kml export from ... to colored kml:
# cat /tmp/meshmap.kml | awk '/name="stroke"/ { print $0; match($0, "<value>#([a-fA-F0-9]{2})([a-fA-F0-9]{2})([a-fA-F0-9]{2})</value>", a); style=sprintf("<Style><LineStyle><color>ff%s%s%s</color><width>3</width></LineStyle></Style>",a[3], a[2], a[1]); next;} /<LineString>/ { print style; print $0; next; } { print $0 }' > /tmp/meshmap_processed.kml

import sys
import os
import os.path
import re
import json
from collections import defaultdict
import argparse
import logging

import graphviz # type: ignore

def geojson_point(name, lat, lng, feature_id):
    p = {
        "type": "Feature",
        "id": feature_id,
        "properties": {"label": name, "name": feature_id },
        "geometry": {
            "type": "Point",
            "coordinates": [lng, lat]
        }
    }

    return p

def geojson_line(label, s, e, style):
    line = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [s[1], s[0]],
                [e[1], e[0]]
            ]
        },
        "properties": {**{ "label": label }, **style},
    }
    return line

def choose_style(link_type):
    if link_type == "RF":
        return {"stroke": "#ff0000", "stroke-width": 8}
    elif link_type == "DTD":
        return {"stroke": "#99ff99"}
    elif link_type == "TUN":
        return {"stroke": "#9999ff"}
    else:
        return {"stroke": "#999999"}

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
    parser.add_argument("--crawldir", nargs="?", default="/tmp/crawl", help="directory to store crawl files. creates if doesn't exist")
    parser.add_argument("--override-coords", nargs="?", default=None, help="optional file with json map from ip to lat/long coordinate array pair, overriding whatever lat/long is found in crawl data")

    args = parser.parse_args()

    override_coords = {}
    if args.override_coords:
        with open(args.override_coords, "r") as f:
            override_coords = json.load(f)

    # read files
    # each is a node
    # for each link_info entry in file add a node and edges

    geo_features = []
    geojson = {"type": "FeatureCollection", "features": geo_features}
    node_coord_map = {}
    node_links = defaultdict(list)

    g = graphviz.Digraph("mesh")

    file_list = os.listdir(args.crawldir)

    crawled_node_count = 0
    known_nodes = set()

    for filename in file_list:
        crawled_node_count += 1

        node_name = re.sub("_", ".", re.sub(".json$", "", filename))
        known_nodes.add(node_name)

        f = open(os.path.join(args.crawldir, filename), "r")
        result = json.load(f)
        f.close()

        has_ll = False
        if node_name in override_coords:
            has_ll = True
            lat,lng = override_coords[node_name]
        elif "lat" in result and result["lat"] and "lon" in result and result["lon"]:
            has_ll = True
            lat = float(result["lat"])
            lng = float(result["lon"])

        if has_ll:
            geo_features.append(geojson_point(node_name, lat, lng, result["node"]))
            node_coord_map[node_name] = (lat, lng)

        if has_ll:
            extra_label = ""
        else:
            extra_label = " !!"
        if "node" in result:
            g.node(f'{node_name}', label=f'{result["node"]}{extra_label}')
        else:
            g.node(f'{node_name}', label=f'{node_name}{extra_label}')


        if "link_info" not in result:
            continue
        if len(result["link_info"]) == 0:
            continue
        for k,v in result["link_info"].items():
            known_nodes.add(k)
            g.edge(node_name, k, label=v["linkType"])
            node_links[node_name].append( (k, v["linkType"]), )

    g.render("mesh_topo", format="pdf")

    for s,v in node_links.items():
        if s not in node_coord_map:
            continue
        for t in v:
            if t[0] not in node_coord_map:
                continue
            geo_features.append(geojson_line(t[1], node_coord_map[s], node_coord_map[t[0]], choose_style(t[1])))

    f = open("mesh_map.json", "w")
    json.dump(geojson, f)
    f.close()

    logging.info(f'crawled {crawled_node_count} discovered {len(known_nodes)}')

if __name__ == "__main__":
    main()
