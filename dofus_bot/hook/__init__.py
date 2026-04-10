"""Frida-based hook to redirect the Dofus client's game-server
connection to the local MITM proxy.

The Hystoria V5 client is an Electron app wrapping a Flash Player
(pepperflash). The Flash plugin opens raw TCP sockets via Chromium's
network stack, which bypasses Node.js's ``net`` module entirely.
Patching ``preloader.js`` or the hosts file cannot intercept these
connections.

Instead we use `Frida <https://frida.re>`_ to inject a tiny script
into the running ``Dofus Retro.exe`` process that hooks
``ws2_32.dll!connect`` at the Winsock level. When Dofus tries to
connect to the real game-server IP, the hook rewrites the
``sockaddr_in`` structure in-place so the connection lands on
``127.0.0.1`` (our MITM proxy) instead. The proxy then forwards
traffic to the real server.

Usage (standalone)::

    python -m dofus_bot.hook --target "Dofus Retro.exe"

Or integrated with the proxy::

    python -m dofus_bot --proxy --hook
"""
