from django.db import migrations, models
import django.db.models.deletion


def backfill_initial_keys(apps, schema_editor):
    TrainingProject = apps.get_model("academy", "TrainingProject")
    ProjectAccessKey = apps.get_model("academy", "ProjectAccessKey")
    for project in TrainingProject.objects.all().iterator():
        ProjectAccessKey.objects.get_or_create(
            project_id=project.pk,
            token_hash=project.owner_key_hash,
            defaults={"purpose": "initial", "active": True},
        )


class Migration(migrations.Migration):
    dependencies = [("academy", "0006_accessrequest_notification_eligible")]

    operations = [
        migrations.CreateModel(
            name="ProjectAccessKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("purpose", models.CharField(choices=[("initial", "Initial browser"), ("handoff", "Domain handoff"), ("recovery", "Owner recovery")], default="initial", max_length=20)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="access_keys", to="academy.trainingproject")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="ProjectHandoff",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("access_key", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="handoff", to="academy.projectaccesskey")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="handoffs", to="academy.trainingproject")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.RunPython(backfill_initial_keys, migrations.RunPython.noop),
    ]
