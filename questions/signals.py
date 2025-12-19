from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import QuestionUpload, QuestionPaper, PaperQuestion, Question
from .services import (
    import_questions_from_dicts, 
    is_encrypted_dat, 
    decrypt_dat_content, 
    load_questions_from_excel_data
)
import logging

logger = logging.getLogger(__name__)

@receiver(pre_delete, sender=QuestionPaper)
def delete_linked_questions(sender, instance, **kwargs):
    """
    Ensure all questions linked to the QuestionPaper are deleted when the paper is deleted.
    This covers bulk delete operations from Admin which bypass the model.delete() method.
    """
    try:
        # Get all question IDs linked to this paper
        q_ids = list(
            PaperQuestion.objects.filter(paper=instance)
            .values_list("question_id", flat=True)
            .distinct()
        )
        
        if q_ids:
            # Delete dependent answers first (they might PROTECT Question)
            # We import here to avoid circular imports if models are loaded early
            from results.models import CandidateAnswer
            from exams.models import Answer as ExamAnswer
            from exams.models import ExamAssignment, ExamAttempt
            from django.db.models import Q
            
            # Delete assignments linked to this paper to avoid ProtectedError
            assignments = ExamAssignment.objects.filter(
                Q(primary_paper=instance) | Q(common_paper=instance)
            )
            if assignments.exists():
                ExamAttempt.objects.filter(assignment__in=assignments).delete()
                assignments.delete()
                logger.info(f"Deleted assignments linked to paper {instance}")

            CandidateAnswer.objects.filter(question_id__in=q_ids).delete()
            ExamAnswer.objects.filter(question_id__in=q_ids).delete()
            
            # Now delete the questions
            Question.objects.filter(id__in=q_ids).delete()
            logger.info(f"Deleted {len(q_ids)} questions linked to paper {instance}")
            
    except Exception as e:
        logger.error(f"Error in delete_linked_questions signal for paper {instance}: {e}")

@receiver(post_save, sender=QuestionUpload)
def import_on_upload(sender, instance, created, **kwargs):
    """
    Automatically import questions when a new QuestionUpload is saved
    """
    if not created:
        return

    try:
        # Read the uploaded file
        with instance.file.open("rb") as f:
            file_data = f.read()

        logger.info(f"Processing uploaded file: {instance.file.name}")

        # Validate the file is encrypted
        if not is_encrypted_dat(file_data):
            logger.error(f"File {instance.file.name} is not a valid encrypted DAT file")
            return

        # Decrypt the file using the provided password
        try:
            decrypted_data = decrypt_dat_content(file_data, instance.decryption_password)
            logger.info(f"Successfully decrypted {instance.file.name}")
            
            # Verify it's an Excel file
            if not decrypted_data.startswith(b'PK'):
                logger.error(f"Decrypted data from {instance.file.name} is not a valid Excel file")
                return
            
        except ValueError as e:
            logger.error(f"Decryption failed for {instance.file.name}: {e}")
            return
        except Exception as e:
            logger.error(f"Unexpected error during decryption of {instance.file.name}: {e}")
            return

        # Parse the Excel data to extract questions
        try:
            questions_data = load_questions_from_excel_data(decrypted_data)
            
            if not questions_data:
                logger.warning(f"No questions found in {instance.file.name}")
                return
            
            logger.info(f"Found {len(questions_data)} questions in {instance.file.name}")
            
        except Exception as e:
            logger.error(f"Error parsing Excel data from {instance.file.name}: {e}")
            return

        # Import the questions into the database
        # PASS THE SELECTED TRADE HERE:
        try:
            imported_questions = import_questions_from_dicts(
                questions_data, 
                default_trade=None,
                default_category=instance.category,
                source_upload=instance
            )
            imported_count = len(imported_questions)
            
            logger.info(f"Successfully imported {imported_count} questions from {instance.file.name}")
            
            # Update the instance to track import success
            instance.save()
            
        except Exception as e:
            logger.error(f"Error importing questions from {instance.file.name}: {e}")
            return

    except Exception as e:
        logger.error(f"Unexpected error processing {instance.file.name}: {e}")
        return
