"""Trota Fleet agent: connects a Trota OS Server, Cloud or Kiosk device to a
Trota Fleet panel.

The device calls the panel (never the other way round), so it works behind
NAT and firewalls with no open port. At each check-in it sends a short status
report and receives the commands queued for it. Only a fixed list of commands
exists (see commands.py): the panel can never run arbitrary programs.
"""

__version__ = "1.0"
