from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [("payments", "0041")]
    operations = [
        migrations.AddField("Order", "payment_token",
                           default=""),
    ]
