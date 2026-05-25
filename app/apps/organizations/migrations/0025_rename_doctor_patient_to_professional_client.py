from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0024_branch_schedule_org_logo_branch_specialists"),
    ]

    operations = [
        # --- Rename models ---
        migrations.RenameModel(old_name="Doctor", new_name="Professional"),
        migrations.RenameModel(old_name="Patient", new_name="Client"),
        migrations.RenameModel(old_name="DoctorSchedule", new_name="ProfessionalSchedule"),
        migrations.RenameModel(old_name="DoctorSpecialty", new_name="ProfessionalSpecialty"),
        migrations.RenameModel(old_name="PendingPatientProfile", new_name="PendingClientProfile"),

        # --- Rename FKs / fields that reference the old model names ---
        migrations.RenameField(model_name="service", old_name="doctor", new_name="professional"),
        migrations.RenameField(model_name="professionalschedule", old_name="doctor", new_name="professional"),
        migrations.RenameField(model_name="scheduleexception", old_name="doctor", new_name="professional"),
        migrations.RenameField(model_name="professionalspecialty", old_name="doctor", new_name="professional"),
        migrations.RenameField(model_name="booking", old_name="doctor", new_name="professional"),
        migrations.RenameField(model_name="booking", old_name="patient", new_name="client"),
        migrations.RenameField(model_name="review", old_name="doctor", new_name="professional"),
        migrations.RenameField(model_name="review", old_name="patient", new_name="client"),
        migrations.RenameField(model_name="review", old_name="patient_avatar", new_name="client_avatar"),
        migrations.RenameField(model_name="professionalaccount", old_name="doctor", new_name="professional"),

        # Doctor.clinic_* -> Professional.organization_*
        migrations.RenameField(model_name="professional", old_name="clinic_name", new_name="organization_name"),
        migrations.RenameField(model_name="professional", old_name="clinic_address", new_name="organization_address"),
    ]
