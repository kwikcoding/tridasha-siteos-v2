"""Give only the built-in QS role the optional quantity and budget check."""
from django.db import migrations


def forwards(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for role in Role.objects.using(schema_editor.connection.alias).filter(key="qs", builtin=True):
        role.stages = list(role.stages or [])
        if "qs" not in role.stages:
            role.stages.append("qs")
        role.permissions = sorted(set(role.permissions or []) | {"indents.view"})
        role.view = list(role.view or [])
        if "indents" not in role.view:
            role.view.append("indents")
        role.save(using=schema_editor.connection.alias, update_fields=["stages", "permissions", "view"])


def backwards(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for role in Role.objects.using(schema_editor.connection.alias).filter(key="qs", builtin=True):
        role.stages = [s for s in (role.stages or []) if s != "qs"]
        # Keep read permissions: these may have existed before this migration.
        role.save(using=schema_editor.connection.alias, update_fields=["stages"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_fill_permissions")]
    operations = [migrations.RunPython(forwards, backwards)]
