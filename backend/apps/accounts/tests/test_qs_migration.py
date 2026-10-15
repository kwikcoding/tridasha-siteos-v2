"""Upgrade and reverse the QS role migration without changing customised roles."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class QSRoleMigration(TransactionTestCase):
    before = [("accounts", "0003_fill_permissions")]
    after = [("accounts", "0004_qs_stage")]

    def test_forward_and_reverse_preserve_other_roles_and_customisations(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        try:
            apps = executor.loader.project_state(self.before).apps
            Role = apps.get_model("accounts", "Role")
            qs = Role.objects.create(key="qs", label="Custom QS label", builtin=True, stages=["tech"],
                                     permissions=["reports.export"], view=["reports"])
            other = Role.objects.create(key="management", label="Management", builtin=True, stages=["mgmt"],
                                        permissions=["indents.view"])
            custom = Role.objects.create(key="custom-qs", label="Custom QS", builtin=False, stages=[])
            snapshots = list(Role.objects.exclude(pk=qs.pk).order_by("pk").values())
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            Role = executor.loader.project_state(self.after).apps.get_model("accounts", "Role")
            migrated = Role.objects.get(pk=qs.pk)
            self.assertEqual(migrated.stages, ["tech", "qs"])
            self.assertEqual(migrated.label, "Custom QS label")
            self.assertEqual(set(migrated.permissions), {"reports.export", "indents.view"})
            self.assertEqual(migrated.view, ["reports", "indents"])
            self.assertEqual(list(Role.objects.exclude(pk=qs.pk).order_by("pk").values()), snapshots)
            executor = MigrationExecutor(connection)
            executor.migrate(self.before)
            Role = executor.loader.project_state(self.before).apps.get_model("accounts", "Role")
            self.assertEqual(Role.objects.get(pk=qs.pk).stages, ["tech"])
            self.assertEqual(list(Role.objects.exclude(pk=qs.pk).order_by("pk").values()), snapshots)
            # Reapplying does not duplicate the stage.
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            self.assertEqual(Role.objects.get(pk=qs.pk).stages, ["tech", "qs"])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
