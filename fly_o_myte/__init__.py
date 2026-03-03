"""
Fly-O-Myte — Smart travel expense optimizer for Australian families.

Fly-O-Myte is a personal CLI tool that tracks flight prices, calculates
the true family cost (including bags, seats, and infant fees), applies
school holiday calendar awareness, and produces one clear recommendation:
Book Now / Wait / Monitor.

Usage:
    fom setup        # first-time family profile wizard
    fom scout        # find best date windows before committing
    fom watch        # start tracking a specific trip
    fom status       # morning digest of all tracked trips
    fom check <id>   # full recommendation + AI insight
    fom poll         # cron target: refresh all active trips
"""

__version__ = "0.1.0"
__app_name__ = "fly-o-myte"
