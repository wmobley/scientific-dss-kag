#!/usr/bin/env python3
"""Create the KAG project on the local OpenSPG server (run with the KAG virtualenv's python).

`knext project create` checks the model endpoints from this process and then POSTs the same config
to the server, which stores it and runs its own check from inside its container. A container cannot
reach the host's gateway at 127.0.0.1, and the host cannot resolve host.docker.internal, so this
wrapper keeps 127.0.0.1 for the local check and swaps in host.docker.internal only in the request
sent to the server. Nothing else about KAG's behaviour or source is changed.

    cd work/kag/project && ../.venv/bin/python ../../../scripts/kag_create_project.py ../kag_config.yaml
"""
import copy
import sys
from urllib.parse import urlsplit, urlunsplit

LOCAL_HOSTS = {"127.0.0.1", "localhost"}
SERVER_VIEW_HOST = "host.docker.internal"


def server_view(node):
    """Deep copy of a config where each loopback base_url points at the host as the server sees it."""
    node = copy.deepcopy(node)

    def walk(value):
        if isinstance(value, dict):
            for key in list(value):
                if key == "base_url":
                    parts = urlsplit(str(value[key]))
                    if parts.hostname == SERVER_VIEW_HOST:
                        continue  # YAML aliases make one dict reachable from several places; it is already swapped
                    if parts.hostname not in LOCAL_HOSTS:
                        raise ValueError(f"base_url host {parts.hostname!r} is not the local gateway")
                    netloc = SERVER_VIEW_HOST + (f":{parts.port}" if parts.port else "")
                    value[key] = urlunsplit(parts._replace(netloc=netloc))
                else:
                    walk(value[key])
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(node)
    return node


def main(config_path):
    import knext.command.sub_command.project as project

    original = project.ProjectClient.create

    def create(self, *args, **kwargs):
        kwargs["config"] = server_view(kwargs["config"])
        return original(self, *args, **kwargs)

    project.ProjectClient.create = create
    project.create_project(config_path=config_path, tmpl=None, delete_cfg=False)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
