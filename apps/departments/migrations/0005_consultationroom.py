import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('departments', '0004_add_uveitis_dept_code'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ConsultationRoom',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('room_number', models.CharField(help_text='Door/room number as it appears on the door (e.g. 1, 2, 3)', max_length=10)),
                ('label', models.CharField(blank=True, help_text='Custom label e.g. "Consulting Room 2" — auto-filled if blank', max_length=80)),
                ('is_active', models.BooleanField(default=True)),
                ('department', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='departments.department')),
                ('assigned_doctor', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_room',
                    to=settings.AUTH_USER_MODEL,
                    help_text='Doctor currently assigned to this room (update daily as needed)',
                )),
            ],
            options={
                'verbose_name': 'Consultation Room',
                'verbose_name_plural': 'Consultation Rooms',
                'ordering': ['department', 'room_number'],
            },
        ),
        migrations.AddConstraint(
            model_name='consultationroom',
            constraint=models.UniqueConstraint(fields=['department', 'room_number'], name='unique_dept_room'),
        ),
    ]
