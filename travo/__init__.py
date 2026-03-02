"""
Travo — Smart travel expense optimizer for Australian families.

Travo is a personal CLI tool that tracks flight prices, calculates
the true family cost (including bags, seats, and infant fees), applies
school holiday calendar awareness, and produces one clear recommendation:
Book Now / Wait / Monitor.

Usage:
    travo setup        # first-time family profile wizard
    travo scout        # find best date windows before committing
    travo watch        # start tracking a specific trip
    travo status       # morning digest of all tracked trips
    travo check <id>   # full recommendation + AI insight
    travo poll         # cron target: refresh all active trips
"""

__version__ = "0.1.0"
__app_name__ = "travo"
