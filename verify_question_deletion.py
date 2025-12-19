import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from questions.models import QuestionPaper, Question, PaperQuestion, QuestionUpload
from django.contrib.auth import get_user_model

def verify_deletion():
    print("Creating test data...")
    # Create dummy question
    q = Question.objects.create(text="Test Question for Deletion", part="A", marks=1)
    
    # Create dummy paper
    qp = QuestionPaper.objects.create(question_paper="IT Trophy")
    
    # Link them
    PaperQuestion.objects.create(paper=qp, question=q, order=1)
    
    print(f"Created QP: {qp.id}, Question: {q.id}")
    
    # Verify exist
    assert QuestionPaper.objects.filter(id=qp.id).exists()
    assert Question.objects.filter(id=q.id).exists()
    
    print("Deleting QuestionPaper...")
    # Using queryset delete to simulate bulk delete which bypasses model.delete()
    # But triggers pre_delete signal
    QuestionPaper.objects.filter(id=qp.id).delete()
    
    print("Verification...")
    if not QuestionPaper.objects.filter(id=qp.id).exists():
        print("QP deleted successfully.")
    else:
        print("ERROR: QP still exists.")
        
    if not Question.objects.filter(id=q.id).exists():
        print("SUCCESS: Question deleted successfully.")
    else:
        print("ERROR: Question still exists! Signal did not work or was not triggered.")

if __name__ == "__main__":
    verify_deletion()
