from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import QuestionUpload
from .services import (
    import_questions_from_dicts, 
    is_encrypted_dat, 
    decrypt_dat_content, 
    load_questions_from_excel_data
)
import logging

logger = logging.getLogger(__name__)

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
