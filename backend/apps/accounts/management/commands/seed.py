"""Create / refresh the built-in roles, and the first administrator login.

    python manage.py seed
    ADMIN_MOBILE=98xxxxxxxx ADMIN_PASSWORD='…' ADMIN_NAME='…' python manage.py seed

Existing roles keep the admin's edits (only missing roles are added) unless --reset-roles is given.
The admin login is only created when no administrator exists yet.
"""
import os

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.accounts.roles import BUILTIN_ROLES


class Command(BaseCommand):
    help = "Seed built-in roles and the first administrator."

    def add_arguments(self, parser):
        parser.add_argument("--reset-roles", action="store_true", help="Overwrite built-in roles with the defaults.")

    def handle(self, *args, **opts):
        for key, r in BUILTIN_ROLES.items():
            fields = dict(label=r["label"], description=r["description"], color=r["color"], permissions=r["permissions"],
                          stages=r["stages"], step_actions=r["step_actions"], can_approve=r.get("can_approve", False),
                          all_sites=r.get("all_sites", False), builtin=True)
            role, created = Role.objects.get_or_create(key=key, defaults=fields)
            if not created and (opts["reset_roles"] or key == "admin"):
                for k, v in fields.items():
                    setattr(role, k, v)
                role.save()
            self.stdout.write(f"{'+' if created else '='} role {key}")

        mobile, password = os.environ.get("ADMIN_MOBILE"), os.environ.get("ADMIN_PASSWORD")
        has_admin = User.objects.filter(role__key="admin", is_active=True).exists() or \
            User.objects.filter(is_superuser=True).exists()
        if has_admin:
            self.stdout.write("= administrator already exists")
        elif mobile and password:
            if len(password) < 8:
                raise CommandError("ADMIN_PASSWORD must be at least 8 characters.")
            User.objects.create_superuser(mobile, password, name=os.environ.get("ADMIN_NAME", "Administrator"))
            self.stdout.write(self.style.SUCCESS(f"+ administrator {mobile}"))
        else:
            self.stdout.write(self.style.WARNING("No administrator yet — set ADMIN_MOBILE and ADMIN_PASSWORD and run seed again."))
