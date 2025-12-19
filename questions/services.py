import pickle
from django.db import transaction
from .models import Question, QuestionUpload
from reference.models import Trade
import hashlib
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# Constants matching your converter
SALT_SIZE = 16
IV_SIZE = 12
PBKDF2_ITERATIONS = 100000

def derive_key(password: str, salt: bytes) -> bytes:
    """Derive AES-256 key using PBKDF2-HMAC-SHA256 (matches Next.js converter)"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256-bit key
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend()
    )
    return kdf.derive(password.encode())

def is_encrypted_dat(file_data: bytes) -> bool:
    """Check if file has proper structure for encrypted data"""
    # Should have at least: salt(16) + iv(12) + some ciphertext
    return len(file_data) >= (SALT_SIZE + IV_SIZE + 16)

def decrypt_dat_content(encrypted_data: bytes, password: str) -> bytes:
    """Decrypt DAT file using AES-GCM (matching your Next.js converter)"""
    if len(encrypted_data) < (SALT_SIZE + IV_SIZE + 16):
        raise ValueError("File too short to be valid encrypted data")
    
    # Extract salt, iv, and ciphertext
    salt = encrypted_data[:SALT_SIZE]
    iv = encrypted_data[SALT_SIZE:SALT_SIZE + IV_SIZE]
    ciphertext_with_tag = encrypted_data[SALT_SIZE + IV_SIZE:]
    
    # Split auth tag (last 16 bytes) from ciphertext
    if len(ciphertext_with_tag) < 16:
        raise ValueError("Invalid ciphertext length")
    
    auth_tag = ciphertext_with_tag[-16:]
    ciphertext = ciphertext_with_tag[:-16]
    
    # Derive key
    key = derive_key(password, salt)
    
    # Decrypt using AES-GCM
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv, auth_tag), backend=default_backend())
    decryptor = cipher.decryptor()
    
    try:
        decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()
        return decrypted_data
    except Exception as e:
        raise ValueError(f"Decryption failed - invalid password or corrupted file: {str(e)}")

def load_questions_from_excel_data(excel_data: bytes):
    """Load questions from decrypted Excel data"""
    import openpyxl
    from io import BytesIO
    
    def convert_to_float(value):
        """Convert various formats to float"""
        if value is None:
            return 1.0
        
        # If already a number
        if isinstance(value, (int, float)):
            return float(value)
        
        # Convert string representations
        value_str = str(value).strip().lower()
        
        # Handle word numbers
        word_to_num = {
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'half': 0.5, 'quarter': 0.25
        }
        
        if value_str in word_to_num:
            return float(word_to_num[value_str])
        
        # Try direct conversion
        try:
            return float(value_str)
        except ValueError:
            # Extract numbers from string (e.g., "6 marks" -> 6)
            import re
            numbers = re.findall(r'\d+\.?\d*', value_str)
            if numbers:
                return float(numbers[0])
            return 1.0  # Default fallback
    
    try:
        # Load Excel workbook from bytes
        workbook = openpyxl.load_workbook(BytesIO(excel_data))
        sheet = workbook.active
        
        questions = []
        
        # Skip header row, process data rows
        for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) < 2:  # Need at least part and question_text
                continue
            
            try:
                # Your Excel structure: part | question_text | opt_a | opt_b | opt_c | opt_d | Answers | Max. Marks
                part = str(row[0] or 'A').strip().upper()
                question_text = str(row[1] or '').strip()
                
                # Skip if no question text
                if not question_text:
                    continue
                
                # Get marks from column H (index 7)
                marks = convert_to_float(row[7] if len(row) > 7 else 1)
                
                # Validate part is valid
                if part not in ['A', 'B', 'C', 'D', 'E', 'F']:
                    part = 'A'
                
                question_data = {
                    'text': question_text,
                    'part': part,
                    'marks': marks,
                    'options': None,
                    'correct_answer': None,
                    'trade': None  # Not present in your Excel
                }
                
                # Build options for MCQ questions (A, B, C)
                if part in ['A', 'B'] and len(row) > 5:
                    choices = []
                    # Get opt_a, opt_b, opt_c, opt_d (columns C, D, E, F - indices 2, 3, 4, 5)
                    for i in range(2, 6):  # indices 2, 3, 4, 5
                        if len(row) > i and row[i] and str(row[i]).strip():
                            choices.append(str(row[i]).strip())
                    
                    if choices:
                        question_data['options'] = {'choices': choices}
                
                # Handle True/False questions
                elif part == 'F' and len(row) > 5:
                    # For True/False, use TRUE/FALSE from the options
                    choices = []
                    for i in range(2, 4):  # Just first two options for T/F
                        if len(row) > i and row[i] and str(row[i]).strip():
                            choices.append(str(row[i]).strip())
                    
                    if not choices:
                        choices = ['TRUE', 'FALSE']  # Default T/F options
                    question_data['options'] = {'choices': choices}
                
                # Get correct answer from column G (index 6)
                if len(row) > 6 and row[6]:
                    answer = str(row[6]).strip()
                    if answer:
                        question_data['correct_answer'] = answer
                
                # Add the question
                questions.append(question_data)
                print(f"Processed question {row_num}: {question_text[:50]}...")
                    
            except Exception as e:
                print(f"Error processing row {row_num}: {e}")
                continue
        
        if not questions:
            raise ValueError("No valid questions found in Excel file")
        
        print(f"Successfully parsed {len(questions)} questions from Excel")
        return questions
        
    except Exception as e:
        raise ValueError(f"Error parsing Excel data: {str(e)}")

@transaction.atomic
def import_questions_from_dicts(records, default_trade=None, default_category=None, source_upload: QuestionUpload = None):
    """Import questions from list of dictionaries, skipping duplicates"""
    created = []
    skipped = []
    
    for q in records:
        try:
            # Prefer the trade selected on the upload form
            trade = default_trade
            category = default_category
            
            # Fallback: try to detect from the record itself (if your Excel ever carries it)
            if trade is None and q.get("trade"):
                trade = Trade.objects.filter(name__icontains=q["trade"]).first()
            
            # Check if a question with the same text already exists
            # Use case-insensitive comparison to catch duplicates with different casing
            existing = Question.objects.filter(text__iexact=q["text"]).first()
            
            if existing:
                # Question already exists, skip it
                skipped.append(existing)
                continue
            
            # Create new question only if it doesn't exist
            obj, was_created = Question.objects.get_or_create(
                text=q["text"],
                defaults={
                    "part": q.get("part", "A"),
                    "marks": q.get("marks", 1),
                    "options": q.get("options"),
                    "correct_answer": q.get("correct_answer"),
                    "trade": trade,
                    "category": category,
                    "upload": source_upload,
                }
            )
            
            if was_created:
                created.append(obj)
            else:
                skipped.append(obj)
                
        except Exception as e:
            print(f"Error creating question: {e}")
            continue
    
    return created
