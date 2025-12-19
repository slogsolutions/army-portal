
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from reference.models import Trade
from django.db import transaction

def run():
    with transaction.atomic():
        # 1. Remove DMV
        try:
            dmv = Trade.objects.get(code="DMV")
            print(f"Found DMV (id={dmv.id}), deleting...")
            dmv.delete()
        except Trade.DoesNotExist:
            print("DMV not found in database.")

        try:
            dmv_name = Trade.objects.get(name="DMV")
            print(f"Found Trade with name='DMV' (id={dmv_name.id}), deleting...")
            dmv_name.delete()
        except Trade.DoesNotExist:
            pass

        # 2. Add DVR MT
        dvr, created = Trade.objects.get_or_create(code="DVR MT", defaults={"name": "DVR MT"})
        if created:
            print("Created DVR MT.")
        else:
            print("DVR MT already exists.")
            # Ensure name is correct
            if dvr.name != "DVR MT":
                dvr.name = "DVR MT"
                dvr.save()

        # 3. Add DR
        dr, created = Trade.objects.get_or_create(code="DR", defaults={"name": "DR"})
        if created:
            print("Created DR.")
        else:
            print("DR already exists.")
            if dr.name != "DR":
                dr.name = "DR"
                dr.save()

        print("Trade fix completed.")

if __name__ == "__main__":
    run()
