# views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.views.decorators.cache import never_cache
from django.db.models import Count, Q
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.http import FileResponse, Http404
import os, tempfile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.pdfencrypt import StandardEncryption

from .models import CandidateProfile
from reference.models import Trade
from .forms import CandidateRegistrationForm
from questions.models import QuestionPaper, Question, PaperQuestion, ExamSession
from results.models import CandidateAnswer


@login_required
def candidate_dashboard(request):
    candidate_profile = get_object_or_404(CandidateProfile, user=request.user)
    exams_scheduled, upcoming_exams, completed_exams, results = [], [], [], []
    return render(request, "registration/dashboard.html", {
        "candidate": candidate_profile,
        "exams_scheduled": exams_scheduled,
        "upcoming_exams": upcoming_exams,
        "completed_exams": completed_exams,
        "results": results,
    })


def register_candidate(request):
    """
    Handle candidate registration with strict validation.
    """
    if request.method == "POST":
        form = CandidateRegistrationForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    candidate = form.save()
                    messages.success(
                        request, 
                        f"Registration successful for {candidate.name} (Army No: {candidate.army_no}). Please log in with your credentials."
                    )
                    return redirect("login")
            except Exception as e:
                messages.error(request, f"Registration failed: {str(e)}")
                print(f"Registration error: {e}")
        else:
            # Display form errors
            for field, errors in form.errors.items():
                for error in errors:
                    if field == '__all__':
                        messages.error(request, f"{error}")
                    else:
                        field_label = form.fields.get(field).label if field in form.fields else field
                        messages.error(request, f"{field_label}: {error}")
            print("Registration form invalid:", form.errors)
    else:
        form = CandidateRegistrationForm()
    
    return render(request, "registration/register_candidate.html", {"form": form})


@never_cache
@login_required
def exam_interface(request):
    """
    Starts (or resumes) an ExamSession for the logged-in candidate and serves
    the randomized questions assigned to that session.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    candidate_profile = get_object_or_404(CandidateProfile, user=request.user)

    # Determine candidate trade and category
    trade_obj = getattr(candidate_profile, "trade", None)
    candidate_category = getattr(candidate_profile, "cat", None)
    
    logger.info(f"Exam interface accessed by candidate: {candidate_profile.army_no}, "
                f"Category: {candidate_category}, Trade: {trade_obj}")

    # Paper selection priority (Category-based mapping):
    # 1) Match category + is_active=True (PRIMARY: category-based mapping)
    # 2) Match category + trade + is_active=True (more specific if both match)
    # 3) Match trade + is_active=True (fallback: trade-based for backward compatibility)
    # 4) Any active paper with questions (last resort fallback)
    
    paper = None
    
    # Priority 1: Category + Active (PRIMARY - category-based mapping)
    # This is the main mapping method - candidates see papers based on their category
    if candidate_category:
        papers = QuestionPaper.objects.filter(
            category=candidate_category,
            is_active=True
        ).annotate(
            num_qs=Count("paperquestion", filter=Q(paperquestion__question__is_active=True))
        ).filter(num_qs__gt=0).order_by("-id")
        
        if papers.exists():
            paper = papers.first()
            logger.info(f"Found paper (Priority 1 - Category-based): {paper.id} with {paper.num_qs} questions for category {candidate_category}")
    
    # Priority 2: Category + Trade + Active (more specific match if both category and trade match)
    if not paper and candidate_category and trade_obj:
        papers = QuestionPaper.objects.filter(
            category=candidate_category,
            trade=trade_obj,
            is_active=True
        ).annotate(
            num_qs=Count("paperquestion", filter=Q(paperquestion__question__is_active=True))
        ).filter(num_qs__gt=0).order_by("-id")
        
        if papers.exists():
            paper = papers.first()
            logger.info(f"Found paper (Priority 2 - Category+Trade): {paper.id} with {paper.num_qs} questions")
    
    # Priority 3: Trade + Active (fallback: trade-based for backward compatibility)
    if not paper and trade_obj:
        papers = QuestionPaper.objects.filter(
            trade=trade_obj,
            is_active=True
        ).annotate(
            num_qs=Count("paperquestion", filter=Q(paperquestion__question__is_active=True))
        ).filter(num_qs__gt=0).order_by("-id")
        
        if papers.exists():
            paper = papers.first()
            logger.info(f"Found paper (Priority 3 - Trade-based fallback): {paper.id} with {paper.num_qs} questions")
    
    # Priority 4: Any active paper with questions (last resort fallback)
    if not paper:
        papers = QuestionPaper.objects.filter(
            is_active=True
        ).annotate(
            num_qs=Count("paperquestion", filter=Q(paperquestion__question__is_active=True))
        ).filter(num_qs__gt=0).order_by("-id")
        
        if papers.exists():
            paper = papers.first()
            logger.info(f"Found paper (Priority 4 - Any active): {paper.id} with {paper.num_qs} questions")

    if not paper:
        # Log detailed information for debugging
        all_papers = QuestionPaper.objects.filter(is_active=True)
        logger.warning(f"No paper found. Active papers count: {all_papers.count()}")
        for p in all_papers:
            q_count = p.paperquestion_set.filter(question__is_active=True).count()
            logger.warning(f"Paper {p.id}: category={p.category}, trade={p.trade}, questions={q_count}")
        
        messages.error(
            request, 
            f"No exam papers are available for your profile (Category: {candidate_category or 'Not set'}, "
            f"Trade: {trade_obj or 'Not set'}). Please contact admin."
        )
        return redirect("candidate_dashboard")

    # 2) Try to find an existing session for this user + paper (resume) OR create a new randomized session
    session = ExamSession.objects.filter(paper=paper, user=request.user).order_by("-started_at").first()
    if not session:
        try:
            session = paper.generate_for_candidate(user=request.user, trade=trade_obj)
        except ValidationError as e:
            print(f"Validation error generating exam session: {e}")
            return render(request, "registration/exam_not_started.html", {
                "message": f"Exam cannot be started: {e}"
            })
        except Exception as e:
            print(f"Unexpected error generating exam session: {e}")
            return render(request, "registration/exam_not_started.html", {
                "message": f"Unexpected error trying to start exam: {e}"
            })

    # Prevent reopening after submission
    session_finished = bool(session.completed_at)

    if session_finished:
        if request.method == "POST":
            messages.info(request, "Your exam has already been submitted. You cannot resubmit.")
            try:
                logout(request)
            except Exception:
                pass
            return redirect("exam_success")

        messages.info(request, "You have already submitted this exam. You cannot restart it.")
        return redirect("exam_success")

    # 3) Get questions from the session
    exam_questions_qs = session.questions
    questions = [eq.question for eq in exam_questions_qs if eq.question.is_active]
    
    # Validate that we have questions
    if not questions:
        logger.error(f"Session {session.id} has no active questions. Paper: {paper.id}")
        messages.error(
            request, 
            "No questions are available for this exam. Please contact admin."
        )
        return redirect("candidate_dashboard")

    duration_seconds = int(session.duration.total_seconds()) if session.duration else (
        int(paper.exam_duration.total_seconds()) if paper.exam_duration else 7200
    )

    # POST: candidate submitting answers
    if request.method == "POST":
        # Verify CSRF token explicitly
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
        
        if session.completed_at:
            messages.info(request, "Your exam has already been submitted.")
            try:
                logout(request)
            except Exception:
                pass
            return redirect("exam_success")

        # Verify session_id matches to prevent tampering
        submitted_session_id = request.POST.get("session_id")
        if submitted_session_id and str(submitted_session_id) != str(session.id):
            logger.warning(f"Session ID mismatch: expected {session.id}, got {submitted_session_id}")
            messages.error(request, "Invalid session. Please restart the exam.")
            return redirect("candidate_dashboard")

        with transaction.atomic():
            for key, value in request.POST.items():
                if key.startswith("question_"):
                    _, qid = key.split("_", 1)
                    try:
                        question = Question.objects.get(id=qid, is_active=True)
                    except Question.DoesNotExist:
                        logger.warning(f"Question {qid} not found or inactive")
                        continue

                    CandidateAnswer.objects.update_or_create(
                        candidate=candidate_profile,
                        paper=session.paper,
                        question=question,
                        defaults={"answer": value.strip() if isinstance(value, str) else value}
                    )

            # Mark session finished
            try:
                if hasattr(session, "finish") and callable(session.finish):
                    session.finish()
                else:
                    session.completed_at = timezone.now()
                    session.save(update_fields=["completed_at"])
            except Exception as e:
                logger.error(f"Error finishing session: {e}")
                try:
                    session.completed_at = timezone.now()
                    session.save(update_fields=["completed_at"])
                except Exception as e2:
                    logger.error(f"Failed to save completed_at: {e2}")
                    pass

        try:
            logout(request)
        except Exception:
            pass
        return redirect("exam_success")

    # GET: render exam interface
    return render(request, "registration/exam_interface.html", {
        "candidate": candidate_profile,
        "paper": session.paper,
        "session": session,
        "questions": questions,
        "duration_seconds": duration_seconds,
    })


@never_cache
def exam_success(request):
    return render(request, "registration/exam_success.html")


@never_cache
def exam_goodbye(request):
    return render(request, "registration/exam_goodbye.html")


def export_answers_pdf(request, candidate_id):
    try:
        answers = CandidateAnswer.objects.filter(candidate_id=candidate_id).select_related(
            "candidate", "paper", "question"
        )
        if not answers.exists():
            raise Http404("No answers found for this candidate.")

        candidate = answers[0].candidate
        army_no = getattr(candidate, "army_no", candidate.user.username)
        candidate_name = candidate.user.get_full_name()

        filename = f"{army_no}_answers.pdf"
        tmp_path = os.path.join(tempfile.gettempdir(), filename)

        enc = StandardEncryption(
            userPassword=army_no,
            ownerPassword="sarthak",
            canPrint=1,
            canModify=0,
            canCopy=0,
            canAnnotate=0
        )

        c = canvas.Canvas(tmp_path, pagesize=A4, encrypt=enc)
        width, height = A4
        c.setFont("Helvetica-Bold", 16)
        c.drawString(1 * inch, height - 1 * inch, "Candidate Answers Export")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, height - 1.5 * inch, f"Army No: {army_no}")
        c.drawString(1 * inch, height - 1.8 * inch, f"Name: {candidate_name}")
        c.drawString(1 * inch, height - 2.1 * inch, f"Trade: {candidate.trade}")
        c.drawString(1 * inch, height - 2.4 * inch, f"Paper: {answers[0].paper.title}")

        y = height - 3 * inch
        c.setFont("Helvetica", 11)
        for idx, ans in enumerate(answers, start=1):
            question_text = (ans.question.text[:80] + "...") if len(ans.question.text) > 80 else ans.question.text
            c.drawString(1 * inch, y, f"Q{idx}: {question_text}")
            y -= 0.3 * inch
            c.drawString(1.2 * inch, y, f"Answer: {ans.answer}")
            y -= 0.5 * inch
            if y < 1.5 * inch:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = height - 1 * inch

        c.save()
        return FileResponse(open(tmp_path, "rb"), as_attachment=True, filename=filename)

    except Exception as e:
        raise Http404(f"Error exporting candidate answers: {e}")


@login_required
@never_cache
@login_required
def clear_shift_and_start_exam(request):
    """
    Clear the shift assignment and redirect to exam interface.
    Enforces shift timing before allowing start.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        candidate = get_object_or_404(CandidateProfile, user=request.user)
        logger.info(f"Starting exam for candidate: {candidate.army_no}")
        
        # Enforce shift window
        if candidate.shift and not candidate.can_start_exam:
            logger.warning(f"Candidate {candidate.army_no} tried to start exam outside shift window.")
            messages.error(request, "You cannot start the exam outside the scheduled time window.")
            return redirect("candidate_dashboard")
        
        # Clear shift to allow exam start
        candidate.shift = None
        candidate.save(update_fields=['shift'])
        
        logger.info(f"Shift cleared for candidate: {candidate.army_no}, redirecting to exam")
        return redirect("exam_interface")
    except Exception as e:
        logger.error(f"Error in clear_shift_and_start_exam: {e}", exc_info=True)
        messages.error(request, f"Error starting exam: {str(e)}")
        return redirect("candidate_dashboard")