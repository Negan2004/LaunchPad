"""Recompute every leaderboard period.

The leaderboard view refreshes itself on read only when the stored data has
aged out, so a burst of visitors does not each pay for a full recomputation.
Running this command on a schedule keeps the rankings current without relying
on someone visiting the page.

    python manage.py refresh_leaderboards
"""

from django.core.management.base import BaseCommand

from core.models import Leaderboard
from core.views import LEADERBOARD_PERIODS, refresh_leaderboards


class Command(BaseCommand):
    help = "Recompute the weekly, monthly and overall leaderboards."

    def handle(self, *args, **options):
        refresh_leaderboards()

        for period in LEADERBOARD_PERIODS:
            count = Leaderboard.objects.filter(period=period).count()
            self.stdout.write(f"  {period:<8} {count} ranked")

        self.stdout.write(self.style.SUCCESS("Leaderboards refreshed."))
