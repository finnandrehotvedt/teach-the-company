from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academy", "0009_trustedknowledgesource_last_etag_and_more")]

    operations = [
        migrations.AddField(
            model_name="knowledgereview",
            name="approved_lesson_versions",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="knowledgereview",
            name="claimed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="knowledgereview",
            name="claimed_by",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="knowledgereview",
            name="draft_prepared_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="knowledgereview",
            name="draft_prepared_by",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AddField(
            model_name="knowledgereview",
            name="review_commit",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="knowledgereview",
            name="review_notes",
            field=models.TextField(blank=True, max_length=2000),
        ),
        migrations.AddField(
            model_name="knowledgereview",
            name="reviewed_by",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="knowledgereview",
            name="status",
            field=models.CharField(
                choices=[
                    ("needs_review", "Needs editorial review"),
                    ("in_review", "Claimed for editorial review"),
                    ("conflict", "Conflicting evidence"),
                    ("accepted", "Accepted for source update"),
                    ("rejected", "Rejected"),
                    ("published", "Published in a reviewed release"),
                ],
                db_index=True,
                default="needs_review",
                max_length=20,
            ),
        ),
    ]
