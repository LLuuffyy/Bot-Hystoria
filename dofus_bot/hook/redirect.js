/**
 * Frida script — redirect Dofus game-server connections to the local
 * MITM proxy.
 *
 * Hooks ws2_32.dll!connect and rewrites the sockaddr_in when the
 * destination matches REAL_IP:REAL_PORT.  The replacement values
 * (PROXY_IP, PROXY_PORT) are injected by the Python launcher via
 * string substitution before the script is loaded.
 *
 * Placeholders replaced at load time:
 *   %%REAL_IP%%    e.g. "162.19.127.155"
 *   %%PROXY_IP%%   e.g. "127.0.0.1"
 *   %%REAL_PORT%%  e.g. 5555
 *   %%PROXY_PORT%% e.g. 5555
 */

'use strict';

var REAL_IP   = '%%REAL_IP%%';
var PROXY_IP  = '%%PROXY_IP%%';
var REAL_PORT = %%REAL_PORT%%;
var PROXY_PORT = %%PROXY_PORT%%;

/* Convert dotted-quad string to 4-byte array. */
function ipToBytes(ip) {
    return ip.split('.').map(function (s) { return parseInt(s, 10); });
}

var realBytes  = ipToBytes(REAL_IP);
var proxyBytes = ipToBytes(PROXY_IP);

/* ws2_32.dll!connect(SOCKET s, const sockaddr *name, int namelen) */
var pConnect = Module.getExportByName('ws2_32.dll', 'connect');

Interceptor.attach(pConnect, {
    onEnter: function (args) {
        var sa   = args[1];            /* pointer to sockaddr    */
        var family = sa.readU16();     /* sa_family (AF_INET=2)  */

        if (family !== 2) return;      /* only handle IPv4       */

        /* sockaddr_in layout (after family):
         *   [2..3]  port   (network byte order = big-endian)
         *   [4..7]  IPv4 address                              */
        var portHi = sa.add(2).readU8();
        var portLo = sa.add(3).readU8();
        var port   = (portHi << 8) | portLo;

        var ip = [
            sa.add(4).readU8(),
            sa.add(5).readU8(),
            sa.add(6).readU8(),
            sa.add(7).readU8()
        ].join('.');

        send('[hook] connect() -> ' + ip + ':' + port);

        /* Rewrite if destination matches the real game server. */
        if (ip === REAL_IP && port === REAL_PORT) {
            send('[hook] REDIRECTING -> ' + PROXY_IP + ':' + PROXY_PORT);

            /* Overwrite IP bytes */
            sa.add(4).writeU8(proxyBytes[0]);
            sa.add(5).writeU8(proxyBytes[1]);
            sa.add(6).writeU8(proxyBytes[2]);
            sa.add(7).writeU8(proxyBytes[3]);

            /* Overwrite port (big-endian) */
            sa.add(2).writeU8((PROXY_PORT >> 8) & 0xff);
            sa.add(3).writeU8(PROXY_PORT & 0xff);
        }
    }
});

send('[hook] ws2_32!connect hook installed.  Waiting for connections...');
