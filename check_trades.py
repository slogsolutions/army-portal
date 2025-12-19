
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from reference.models import Trade

def check():
    trades = Trade.objects.all()
    print("Existing Trades:")
    for t in trades:
        print(f" - {t.code} ({t.name})")

    if Trade.objects.filter(code="DMR").exists():
        print("\nWARNING: DMR found!")
        Trade.objects.filter(code="DMR").delete()
        print("DMR deleted.")
    
    if Trade.objects.filter(code="DMV").exists():
        print("\nWARNING: DMV found!")
        Trade.objects.filter(code="DMV").delete()
        print("DMV deleted.")

if __name__ == "__main__":
    check()
