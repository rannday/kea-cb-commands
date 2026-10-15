"""Run a SQL/packet harness in a disposable, loopback-only Linux network."""

# SPDX-License-Identifier: MPL-2.0
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--inside":
        uid, gid, host_namespace = sys.argv[2:5]
        assert os.readlink("/proc/self/ns/net") != host_namespace
        assert {name for _, name in socket.if_nameindex()} == {"lo"}
        subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
        os.environ["KEA_PACKET_HOST_NETNS"] = host_namespace
        # PostgreSQL refuses uid 0. Nest a user namespace mapping our real uid
        # back to itself after the private loopback has been brought up. No
        # privileged host operation or physical network is involved.
        os.execvp("unshare", ["unshare", "--user", "--map-user", uid,
                             "--map-group", gid, sys.executable, "-B", *sys.argv[5:]])
    if not all(shutil.which(program) for program in ("unshare", "ip")):
        print("SKIP: isolated packet tests require Linux unshare and ip")
        return 77
    if os.getuid() == 0:
        print("SKIP: isolated SQL/packet harness requires a non-root host user")
        return 77
    return subprocess.run([
        "unshare", "--user", "--map-root-user", "--net", sys.executable, "-B",
        str(Path(__file__).resolve()), "--inside", str(os.getuid()), str(os.getgid()),
        os.readlink("/proc/self/ns/net"),
        *sys.argv[1:]], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
