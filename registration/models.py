# models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import datetime

RANK_CHOICES = [
    ('Sigmn', 'Sigmn'),
    ('LNk', 'LNk'),
    ('Nk', 'Nk'),
    ('Hav', 'Hav'),
    ('CHM', 'CHM'),
    ('CQMH', 'CQMH'),
    ('RHM', 'RHM'),
    ('Nb Sub', 'Nb Sub'),
    ('Sub', 'Sub'),
    ('Sub Maj', 'Sub Maj'),
    ('L|Hav', 'L|Hav'),
    ('AV', 'AV'),
    ('Loc Hav', 'Loc Hav'),
    ('Loc Nk', 'Loc Nk'),
]

TRADE_TYPE_CHOICES = [
    ('Tech', 'Tech'),
    ('Non-Tech', 'Non-Tech'),
]

CAT_CHOICES = [
    ('JCOs (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)', 'JCOs (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)'),
    ('OR (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)', 'OR (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)'),
    ('JCOs/OR (Dvr MT,DR,EFS,Lmn and Tdn)', 'JCOs/OR (Dvr MT,DR,EFS,Lmn and Tdn)'),
]

from exams.models import Shift

class CandidateProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="candidate_profile"
    )
    
    army_no = models.CharField(max_length=50, unique=True)
    rank = models.CharField(max_length=50, choices=RANK_CHOICES)
    name = models.CharField(max_length=150)
    trade_type = models.CharField(max_length=50, choices=TRADE_TYPE_CHOICES, default='Tech')
    trade = models.ForeignKey('reference.Trade', on_delete=models.SET_NULL, null=True, blank=True)
    dob = models.CharField(max_length=10, verbose_name="Date of Birth")
    doe = models.DateField(verbose_name="Date of Enrolment")
    unit = models.CharField(max_length=50, blank=True, null=True)
    med_cat = models.CharField(max_length=100, blank=True, null=True)
    cat = models.CharField(
        max_length=255,
        choices=CAT_CHOICES,
        default='OR (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)'
    )

    from centers.models import COMD_CHOICES

    command = models.CharField(
        max_length=20,
        choices=COMD_CHOICES,
        blank=True,
        null=True,
    )

    nsqf_level = models.CharField(max_length=50, blank=True)
    exam_center = models.CharField(max_length=150, blank=True, null=True)
    training_center = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)

    primary_qualification = models.CharField(max_length=150, blank=True, null=True)
    primary_duration = models.CharField(max_length=50, blank=True, null=True)
    primary_credits = models.CharField(max_length=50, blank=True, null=True)

    primary_viva_marks = models.IntegerField(null=True, blank=True)
    primary_practical_marks = models.IntegerField(null=True, blank=True)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    TRADE_MARKS = {
        "TTC": {'primary': {'prac': 30, 'viva': 10}},
        "OCC": {'primary': {'prac': 20, 'viva': 5}},
        "DTMN": {'primary': {'prac': 30, 'viva': 10}},
        "EFS": {'primary': {'prac': 30, 'viva': 10}},
        "DMV": {'primary': {'prac': 20, 'viva': 5}},
        "LMN": {'primary': {'prac': 30, 'viva': 10}},
        "CLK SD": {'primary': {'prac': 30, 'viva': 10}},
        "STEWARD": {'primary': {'prac': 30, 'viva': 10}},
        "WASHERMAN": {'primary': {'prac': 30, 'viva': 10}},
        "HOUSE KEEPER": {'primary': {'prac': 30, 'viva': 10}},
        "CHEFCOM": {'primary': {'prac': 30, 'viva': 10}},
        "MESS KEEPER": {'primary': {'prac': 30, 'viva': 10}},
        "SKT": {'primary': {'prac': 30, 'viva': 10}},
        "MUSICIAN": {'primary': {'prac': 30, 'viva': 10}},
        "ARTSN WW": {'primary': {'prac': 30, 'viva': 10}},
        "HAIR DRESSER": {'primary': {'prac': 30, 'viva': 10}},
        "SP STAFF": {'primary': {'prac': 30, 'viva': 10}},
        "JE NE": {'primary': {'prac': 30, 'viva': 10}},
        "JE SYS": {'primary': {'prac': 30, 'viva': 10}},
        "OP CIPH": {'primary': {'prac': 30, 'viva': 10}},
        "OSS": {'primary': {'prac': 30, 'viva': 10}},
    }

    def _normalized_trade(self):
        if not self.trade:
            return ""
        trade = self.trade.name.strip().upper()

        if "WASHERMAN" in trade:
            return "WASHERMAN"
        elif "HOUSE KEEPER" in trade:
            return "HOUSE KEEPER"
        elif "MUSICIAN" in trade:
            return "MUSICIAN"
        elif "HAIR DRESSER" in trade:
            return "HAIR DRESSER"
        elif "SP STAFF" in trade:
            return "SP STAFF"
        elif "MESS KEEPER" in trade:
            return "MESS KEEPER"
        else:
            return trade

    def get_marks_limits(self):
        normalized_trade = self._normalized_trade()
        if not normalized_trade:
            return None, None, None, None

        trade_rules = self.TRADE_MARKS.get(normalized_trade)
        if not trade_rules:
            return 30, 10, 30, 10

        primary_prac = trade_rules.get("primary", {}).get("prac")
        primary_viva = trade_rules.get("primary", {}).get("viva")
        secondary_prac = trade_rules.get("secondary", {}).get("prac")
        secondary_viva = trade_rules.get("secondary", {}).get("viva")

        return primary_prac, primary_viva, secondary_prac, secondary_viva

    def clean(self):
        super().clean()

        primary_prac_max, primary_viva_max, secondary_prac_max, secondary_viva_max = self.get_marks_limits()

        if primary_prac_max is not None and self.primary_practical_marks is not None and self.primary_practical_marks > primary_prac_max:
            raise ValidationError({"primary_practical_marks": f"Primary practical marks cannot exceed {primary_prac_max} for {self.trade} trade."})

        if primary_viva_max is not None and self.primary_viva_marks is not None and self.primary_viva_marks > primary_viva_max:
            raise ValidationError({"primary_viva_marks": f"Primary viva marks cannot exceed {primary_viva_max} for {self.trade} trade."})

        if self.primary_practical_marks is not None and self.primary_practical_marks < 0:
            raise ValidationError({"primary_practical_marks": "Marks cannot be negative."})

        if self.primary_viva_marks is not None and self.primary_viva_marks < 0:
            raise ValidationError({"primary_viva_marks": "Marks cannot be negative."})

    @property
    def can_start_exam(self):
        if not self.shift:
            return False
        shift_datetime = datetime.combine(self.shift.date, self.shift.start_time)
        shift_datetime = timezone.make_aware(shift_datetime, timezone.get_current_timezone())
        return timezone.now() >= shift_datetime

    def __str__(self):
        return f"{self.army_no} - {self.name}"