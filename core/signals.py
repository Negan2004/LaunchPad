"""Signal handlers for core.

Registered from CoreConfig.ready(), which is the conventional wiring point.
"""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=User, dispatch_uid="core.create_profile_for_new_user")
def create_profile_for_new_user(sender, instance, created, **kwargs):
    """Give every new user a Profile.

    The application assumes a profile exists - base.html reads
    user.profile.avatar on every page, and the dashboard, profile studio and
    public profile all reached for one. Before this, three views papered over
    the gap with get_or_create(), which meant a freshly registered user had no
    Profile row until they happened to visit one of those pages.

    Creating it here covers every path uniformly: registration, the admin,
    createsuperuser, and direct User.objects.create_user() calls.

    get_or_create keeps this idempotent - a second save() of the same user, or
    a fixture that already supplied a profile, will not produce a duplicate.
    The OneToOneField would reject one anyway; this avoids the exception.

    dispatch_uid guards against double registration if the module is imported
    more than once.
    """
    if not created:
        return

    Profile.objects.get_or_create(user=instance)
