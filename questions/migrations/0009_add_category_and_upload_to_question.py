from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('questions', '0008_add_category_to_questionupload'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='category',
            field=models.CharField(max_length=255, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='question',
            name='upload',
            field=models.ForeignKey(related_name='questions', to='questions.questionupload', null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL),
        ),
    ]

