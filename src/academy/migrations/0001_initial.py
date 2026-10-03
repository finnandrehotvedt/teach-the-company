import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TrainingProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("public_slug", models.SlugField(blank=True, max_length=150, null=True, unique=True)),
                ("company_name", models.CharField(max_length=120)),
                ("learner_name", models.CharField(max_length=100)),
                ("learner_email", models.EmailField(help_text="Private. Never rendered publicly.", max_length=254)),
                ("role_title", models.CharField(max_length=140)),
                ("agent_name", models.CharField(max_length=100)),
                ("mission", models.TextField(max_length=700)),
                ("public_title", models.CharField(blank=True, max_length=160)),
                ("public_summary", models.TextField(blank=True, max_length=500)),
                ("owner_key_hash", models.CharField(editable=False, max_length=64)),
                ("publication_permission", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("training", "Training"),
                            ("review", "Ready for review"),
                            ("published", "Published"),
                            ("retired", "Retired"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("is_fictional_demo", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="WorkbookEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_slug", models.SlugField(max_length=80)),
                ("title", models.CharField(max_length=150)),
                ("response", models.TextField(max_length=3000)),
                (
                    "safe_to_share",
                    models.BooleanField(
                        default=False,
                        help_text="Only reviewed entries with this flag may appear in a public challenge.",
                    ),
                ),
                ("completed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "project",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="academy.trainingproject"),
                ),
            ],
            options={"ordering": ("completed_at",)},
        ),
        migrations.CreateModel(
            name="ChallengeAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prompt", models.TextField(max_length=600)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("learned", "Learned procedure"),
                            ("approval", "Human approval required"),
                            ("not_learned", "Not learned yet"),
                        ],
                        max_length=20,
                    ),
                ),
                ("response", models.TextField(max_length=1200)),
                ("evidence_titles", models.JSONField(blank=True, default=list)),
                ("source_fingerprint", models.CharField(db_index=True, max_length=64)),
                ("is_private_preview", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="challenges", to="academy.trainingproject"),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="workbookentry",
            constraint=models.UniqueConstraint(fields=("project", "module_slug"), name="unique_project_module"),
        ),
    ]
