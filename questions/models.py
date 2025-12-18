# questions/models.py
from django.db import models, transaction
from django.core.exceptions import ValidationError
from requests import session
from reference.models import Trade
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
import re
from registration.models import CAT_CHOICES

User = get_user_model()

def validate_dat_file(value):
    if not value.name.lower().endswith(".dat"):
        raise ValidationError("Only .dat files are allowed.")

# ---------------------------
# Hard-coded trade & distribution config - REMOVED for dynamic question count
# ---------------------------

def _normalize_trade_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip()).upper()

# ------------------------------
# Models (keeps your original structure, adds ExamSession/ExamQuestion)
# ------------------------------
class Question(models.Model):
    class Part(models.TextChoices):
        A = "A", "Part A - MCQ (Single Choice)"
        B = "B", "Part B - MCQ (Multiple Choice)"
        C = "C", "Part C - Short answer (20-30 words)"
        D = "D", "Part D - Fill in the blanks"
        E = "E", "Part E - Long answer (100-120 words)"
        F = "F", "Part F - True/False"

    text = models.TextField()
    part = models.CharField(max_length=1, choices=Part.choices, default="A")
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    options = models.JSONField(blank=True, null=True)
    correct_answer = models.JSONField(blank=True, null=True)
    trade = models.ForeignKey(Trade, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "QP Delete"
        verbose_name_plural = "3 QP Delete"

    def __str__(self):
        return f"[{self.get_part_display()}] {self.text[:60]}..."


class QuestionUpload(models.Model):
    file = models.FileField(upload_to="uploads/questions/", validators=[validate_dat_file])
    uploaded_at = models.DateTimeField(auto_now_add=True)
    decryption_password = models.CharField(max_length=255, default="default123")
    trade = models.ForeignKey(
        Trade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="If set, all imported questions will be tagged with this trade."
    )

    class Meta:
        verbose_name = "QP Upload"
        verbose_name_plural = "1 QP Upload"
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file.name} ({self.uploaded_at.strftime('%Y-%m-%d %H:%M')})"


class QuestionPaper(models.Model):
    PAPER_TYPE_CHOICES = [
        ("Primary", "Primary"),
    ]

    question_paper = models.CharField(
        max_length=20,
        choices=PAPER_TYPE_CHOICES,
        default="Primary",
    )

    # ✅ ADD THIS
    category = models.CharField(
        max_length=50,
        choices=CAT_CHOICES,
        null=True,
        blank=True,
        help_text="Category this paper belongs to"
    )

    is_active = models.BooleanField(default=False, null=True)
    is_common = models.BooleanField(default=False, editable=False)

    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, null=True, blank=True)
    exam_duration = models.DurationField(
        null=True,
        blank=True,
        default=timedelta(hours=3),
    )

    qp_assign = models.ForeignKey(QuestionUpload, on_delete=models.SET_NULL, null=True, blank=True)
    questions = models.ManyToManyField("Question", through="PaperQuestion")


    # Optional (admin editable) override. If empty, hard-coded values will be used.
    part_distribution = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional manual override per paper. If empty, code uses hard-coded trade config."
    )

    class Meta:
        verbose_name = "QP Mapping"
        verbose_name_plural = "2 QP Mappings"
        ordering = ['-id']

    def save(self, *args, **kwargs):
        # Secondary papers are removed, so we assume all papers are Primary (is_common=False)
        # unless explicitly set to be common (e.g., for a general primary paper)
        if self.question_paper == "Primary":
            self.is_common = False
        # else: # If you want to keep the concept of a 'common' paper for Primary, you can adjust this logic
        #     self.is_common = True
        #     self.trade = None
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from .models import PaperQuestion, Question  # local import to avoid circular import
        q_ids = list(PaperQuestion.objects.filter(paper=self).values_list("question_id", flat=True).distinct())
        for qid in q_ids:
            other_rel_count = PaperQuestion.objects.filter(question_id=qid).exclude(paper=self).count()
            if other_rel_count == 0:
                try:
                    Question.objects.filter(id=qid).delete()
                except Exception:
                    pass
        super().delete(*args, **kwargs)

    def __str__(self):
        return self.question_paper

    # ------------------------------
    # Helper methods for using hard-coded config
    # ------------------------------




    # def generate_for_candidate(self, user: User, trade: Trade = None, shuffle_within_parts: bool = True):
    #     """
    #     Create an ExamSession for the given user and populate it with randomly selected questions
    #     according to the paper's distribution OR hard-coded trade config if paper.part_distribution is empty.

    #     Behavior:
    #     - If self.part_distribution is set -> use it.
    #     - Else if self.is_common -> use HARD_CODED_COMMON_DISTRIBUTION (43 qns) UNLESS paper.part_distribution overrides.
    #     - Else try to find HARD_CODED_TRADE_CONFIG for the effective trade (self.trade or passed trade).
    #     - If still not found -> fallback to HARD_CODED_COMMON_DISTRIBUTION.
    #     """
    #     from .models import Question, ExamSession, ExamQuestion  # local import
    #     import random

    #     # choose effective trade:
    #     # For a common paper we purposely IGNORE the passed-in trade so common papers
    #     # always use the common default distribution unless overridden by part_distribution.
    #     if self.is_common:
    #         effective_trade = None
    #     else:
    #         # For primary papers prefer self.trade (paper-level) then the passed trade argument.
    #         effective_trade = self.trade or trade

    #     # choose distribution: explicit -> common-without-trade -> hard-coded trade -> fallback common
    #     if self.part_distribution:
    #         chosen_distribution = self.part_distribution.copy()
    #     else:
    #         # If common paper use global common default (43).
    #         if self.is_common:
    #             chosen_distribution = HARD_CODED_COMMON_DISTRIBUTION.copy()
    #         else:
    #             # try trade-config lookup (effective_trade may be None)
    #             hc = self._get_hardcoded_for_trade(effective_trade)
    #             if hc:
    #                 chosen_distribution = hc[0]
    #             else:
    #                 # fallback to global common distribution
    #                 chosen_distribution = HARD_CODED_COMMON_DISTRIBUTION.copy()

    #     # validate distribution
    #     self._validate_distribution(chosen_distribution)

    #     # Build the session and pick random questions per part
    #     with transaction.atomic():
    #         session = ExamSession.objects.create(
    #             paper=self,
    #             user=user,
    #             trade=effective_trade,
    #             started_at=timezone.now(),
    #             duration=self.exam_duration
    #         )

    #         order_counter = 1
    #         for part_letter, count in (chosen_distribution or {}).items():
    #             cnt = int(count)
    #             if cnt <= 0:
    #                 continue

    #             qset = Question.objects.filter(is_active=True, part=part_letter)
    #             if effective_trade is not None:
    #                 qset = qset.filter(trade=effective_trade)

    #             available_count = qset.count()
    #             if available_count < cnt:
    #                 # fallback: allow questions from any trade for this part to fulfill count (safer)
    #                 qset = Question.objects.filter(is_active=True, part=part_letter)

    #             chosen = list(qset.order_by('?')[:cnt])
    #             if len(chosen) < cnt:
    #                 raise ValidationError(
    #                     f"Not enough active questions for part {part_letter}. Requested {cnt}, found {len(chosen)}."
    #                 )

    #             if shuffle_within_parts:
    #                 random.shuffle(chosen)

    #             for q in chosen:
    #                 ExamQuestion.objects.create(session=session, question=q, order=order_counter)
    #                 order_counter += 1

    #         # update total_questions count on session
    #         session.total_questions = session.examquestion_set.count()
    #         session.save()

    #     return session

    def generate_for_candidate(self, user: User, trade: Trade = None, shuffle_within_parts: bool = True):
        """
        Create an ExamSession for the given user and populate it with ALL questions
        explicitly linked to this QuestionPaper via PaperQuestion.

        This modification removes the hardcoded question limits and distribution logic,
        ensuring that all questions uploaded and assigned to this paper are shown.
        """
        from .models import ExamSession, ExamQuestion  # local import
        import random

        # Determine effective trade:
        # This is primarily for logging/context in ExamSession, not for question selection anymore.
        effective_trade = self.trade or trade

        # 1. Get all questions explicitly linked to this QuestionPaper.
        # We use the PaperQuestion model to get the questions in their assigned order.
        paper_questions = self.paperquestion_set.select_related('question').filter(
            question__is_active=True
        ).order_by('order')

        if not paper_questions.exists():
            raise ValidationError(
                f"QuestionPaper '{self}' has no active questions assigned. Please assign questions to this paper."
            )

        # 2. Extract the questions and their original order
        questions_to_assign = list(paper_questions)

        # 3. Apply shuffling if requested
        if shuffle_within_parts:
            # Shuffle the entire set of questions to randomize the order.
            random.shuffle(questions_to_assign)

        # 4. Build the session and assign all questions
        with transaction.atomic():
            session = ExamSession.objects.create(
                paper=self,
                user=user,
                trade=effective_trade,
                started_at=timezone.now(),
                duration=self.exam_duration
            )

            exam_questions = []
            for index, pq in enumerate(questions_to_assign):
                # The order is the index + 1 for the final display order in the exam session.
                exam_questions.append(
                    ExamQuestion(
                        session=session,
                        question=pq.question,
                        order=index + 1
                    )
                )

            ExamQuestion.objects.bulk_create(exam_questions)
            from results.models import CandidateAnswer
            from registration.models import CandidateProfile  # use your actual Answer model

            # Resolve CandidateProfile from user
            candidate = CandidateProfile.objects.get(user=session.user)

            answers = []
            for eq in exam_questions:
                answers.append(
                    CandidateAnswer(
                        candidate=candidate,        # ✅ REQUIRED
                        paper=self,                 # ✅ REQUIRED
                        question=eq.question,       # ✅ REQUIRED
                        answer="",                  # unanswered
                    )
                )

            CandidateAnswer.objects.bulk_create(answers)


            # update actual total_questions and save
            session.total_questions = len(exam_questions)
            session.save()

        return session




class PaperQuestion(models.Model):
    paper = models.ForeignKey(QuestionPaper, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("paper", "question")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.paper} - Q{self.order}"


class ExamSession(models.Model):
    paper = models.ForeignKey(QuestionPaper, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    trade = models.ForeignKey(Trade, on_delete=models.SET_NULL, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    total_questions = models.PositiveIntegerField(default=0)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"ExamSession: {self.user} - {self.paper} ({self.started_at})"

    @property
    def questions(self):
        return self.examquestion_set.select_related("question").order_by("order")

    def finish(self):
        self.completed_at = timezone.now()
        self.save()


class ExamQuestion(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        unique_together = ("session", "question")

    def __str__(self):
        return f"{self.session} - Q{self.order} ({self.question.pk})"
