"""Packet handlers for the MITM bot.

Each handler observes one or more protocol message prefixes and updates
the shared :class:`GameState`. Handlers do NOT inject packets directly;
that's the job of the scripting layer via :mod:`dofus_bot.scripting.api`.
"""
