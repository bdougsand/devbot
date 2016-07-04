from http.server import HTTPServer, BaseHTTPRequestHandler
from ipaddress import IPv4Address
import json
import logging
import os
import shutil
import subprocess
import sys

import config


logger = logging.getLogger(__name__)

ip_low = int(IPv4Address(config.IP_RANGE[0]))
ip_high = int(IPv4Address(config.IP_RANGE[1]))

dtach_bin = shutil.which("dtach")
docker = shutil.which("docker")
docker_compose = shutil.which("docker-compose")

required_bins = ((dtach_bin, "dtach"), (docker, "docker"), (docker_compose, "docker-compose"))
for path, name in required_bins:
    assert path, "%s executable not on path" % name


def in_range(ip):
    value = int(IPv4Address(ip))
    return ip_low <= value <= ip_high


def deploy_repo(repo):
    r = config.REPOS[repo]
    start_wd = os.getcwd()
    try:
        if "directory" in r:
            repo_dir = os.path.expanduser(r["directory"])
            os.chdir(repo_dir)
        socket = os.path.join(os.getcwd(), "dtach.sock")

        code = subprocess.call(["git", "pull"])
        if code is not 0:
            return
        # TODO: Error handling
        subprocess.call([docker_compose, "stop"])
        subprocess.call([docker, "pull", repo])
        if repo.get("dtach"):
            subprocess.call([dtach_bin, "-n", socket, docker_compose, "up"])
        else:
            subprocess.call([docker_compose, "-d", "up"])
        # TODO: Check that the server has started
    finally:
        os.chdir(start_wd)



class RequestHandler(BaseHTTPRequestHandler):
    def send_text(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))
        self.wfile.flush()

    def do_GET(self):
        # This must be set by the server!
        client_host, _client_port = self.client_address
        if client_host == "127.0.0.1":
            client_host = self.headers.get("X-Real-IP")

        # This could also be handled by nginx, but eh.
        if not in_range(client_host):
            self.send_text("Invalid request origin " + client_host, status=401)
            return

        try:
            content_length = int(self.headers["Content-length"])
            data = self.rfile.read(content_length)
            json_text = data.decode("utf-8")
            payload = json.loads(json_text)
            repo = payload["repository"]["repo_name"]

            if repo in config.REPOS:
                # TODO: Did deployment succeed?
                deploy_repo(repo)

            self.send_text("OK\n")
        except:
            self.send_text("NOK\n", status=500)


def run():
    httpd = HTTPServer(config.ADDRESS, RequestHandler)
    httpd.serve_forever()


if __name__ == "__main__":
    run()
