from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academy", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="trainingproject",
            name="creator_fingerprint",
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=64),
        ),
    ]
