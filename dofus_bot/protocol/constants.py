"""Protocol constants for Dofus 1.29 Retro.

References:
- https://github.com/kralamoure/retroproto
- https://github.com/HydreIO/dofus-protocol-1.29
- https://github.com/jomisoac/Bot-Dofus-1.29.1
- https://cadernis.fr/ (various threads on protocol analysis)

The Dofus Retro wire protocol is text-based: each message starts with a
2 or 3 character prefix identifying the message type, followed by the
payload. Sub-fields are usually pipe-delimited (``|``).
"""

# Character set used by Dofus for its custom base-64-like encoding of
# passwords and movement paths. Order matters.
HASH_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789-_"
)

# Known message prefixes grouped by subsystem. This list is NOT exhaustive;
# it's a practical subset used by the handlers. Three-letter prefixes are
# tried first during routing, two-letter prefixes as fallback.

# Auth / account
HELLO_CONNECT = "HC"          # server -> client, contains hash key
ACCOUNT_PREFIX = "Ax"         # family of account-related messages
ACCOUNT_LOGIN_OK = "Ad"       # account authenticated OK
ACCOUNT_LOGIN_ERROR = "AlEx"  # login error (family)
ACCOUNT_PSEUDO = "Af"         # account queue / pseudo info
ACCOUNT_QUEUE = "Af"
SERVER_SELECT = "AX"          # client -> server: select world
SERVER_TICKET = "AYK"         # server -> client: ticket + game host/port

# Game server
HELLO_GAME = "HG"
AUTH_TICKET = "AT"
AUTH_TICKET_OK = "ATK"
CHAR_LIST = "ALK"
CHAR_SELECT = "AS"
CHAR_SELECT_OK = "ASK"
GAME_CREATE = "GC"            # enter game world (GCK|1|)

# Map / world
MAP_DATA = "GDM"              # map id, date, key
MAP_ACTORS = "GM"             # actors on map (players, monsters, NPCs)
MAP_CHANGE = "GA"             # movement / map transitions use GA

# Combat
GAME_ACTION = "GA"            # GA<actionId>;<args> - everything from movement to spells
FIGHT_START = "GJK"           # fight joined
FIGHT_PLACEMENT = "GP"        # placement cells
FIGHT_READY = "GR"            # ready state
FIGHT_TURNS = "GT"            # turn order
FIGHT_TURN_START = "GTS"      # turn start for an entity
FIGHT_TURN_MID = "GTM"        # mid-turn update
FIGHT_TURN_END = "GTE"        # turn end
FIGHT_END = "GE"              # fight end (rewards)
FIGHT_CLOSE = "GF"            # close fight result screen

# Action IDs used inside GA messages
ACTION_MOVEMENT = 1           # GA0;1;charId;encodedPath
ACTION_CAST_SPELL = 300       # GA300;spellId;targetCell
ACTION_FIGHT_REQUEST = 900    # GA900;monsterGroupId
ACTION_FIGHT_END_TURN = 903   # GA903 - pass turn

# Chat / notifications
BASIC_NOTIFICATION = "BN"
INFO_MESSAGE = "Im"
CHAT_MESSAGE = "cMK"
