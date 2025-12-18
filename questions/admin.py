from django.db import transaction
from django.db.models import Count
from django.contrib import messages
from urllib import request
from django.contrib import admin
from django.urls import path
from django.http import JsonResponse
from .models import Question, QuestionPaper, PaperQuestion, QuestionUpload
from .forms import QuestionUploadForm, QuestionPaperAdminForm
from django.contrib.admin.sites import NotRegistered
from django.contrib import messages

try:
    admin.site.unregister(Question)
except NotRegistered:
    pass

class PaperQuestionInline(admin.TabularInline):
    model = PaperQuestion
    extra = 1
    autocomplete_fields = ["question"]

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    search_fields = ("text",)
    list_filter = ("trade",)

    # def has_module_permission(self, request):
    #     """Hides from sidebar but still usable for autocomplete"""
    #     return False

class QuestionPaperAdmin(admin.ModelAdmin):
    class Media:
        js = (
            # ensure django.jQuery is available in older/admin contexts
            'admin/js/jquery.init.js',
            # path under static/ : questions/admin/disable_trade.js
            'admin/js/disable_trade.js',
        )
    form = QuestionPaperAdminForm
    list_display = ("question_paper", "category", "trade", "qp_assign", "is_active")
    inlines = [PaperQuestionInline]
    search_fields = ("question_paper",)
    fields = ("question_paper", "category", "trade", "exam_duration", "qp_assign", "is_active")
    readonly_fields = ("is_common",)  # optional: show is_common read-only if you want

    # NOTE: Removed reference to external static admin/js/disable_trade.js
    # to keep this implementation self-contained and avoid staticfiles changes.

    def get_urls(self):
        """
        Add a small admin-only JSON endpoint: /admin/questions/questionpaper/qp-for-trade/
        Accepts GET param 'trade_id' and returns the matching Primary QuestionPaper (id & label).
        """
        urls = super().get_urls()
        custom_urls = [
            path('qp-for-trade/', self.admin_site.admin_view(self.qp_for_trade_view),
                 name='questions-questionpaper-qp-for-trade'),
        ]
        # Ensure custom urls are available under the model admin path
        return custom_urls + urls

    def qp_for_trade_view(self, request):
        """
        JSON view: expects ?trade_id=<id>
        Returns: {"ok": true, "qp": {"id": 123, "label": "Primary - OCC"}} or {"ok": false, "qp": null}
        """
        trade_id = request.GET.get('trade_id')
        if not trade_id:
            return JsonResponse({'ok': False, 'error': 'missing trade_id', 'qp': None})

        try:
            # Find the latest QuestionUpload for this trade
            upload = QuestionUpload.objects.filter(trade_id=trade_id).order_by('-uploaded_at').first()
            if not upload:
                return JsonResponse({'ok': False, 'qp': None})

            return JsonResponse({
                'ok': True,
                'qp': {
                    'id': upload.pk,
                    'label': str(upload)  # will show filename
                }
            })
        except Exception as e:
            return JsonResponse({'ok': False, 'error': str(e), 'qp': None})

    def get_form(self, request, obj=None, **kwargs):
        """
        Override get_form so we can attach an inline onchange JS handler
        to the 'trade' widget. When trade changes, the JS calls the qp-for-trade endpoint
        and sets the 'qp_assign' select value automatically if a primary QP is found.
        """
        Form = super().get_form(request, obj, **kwargs)

        # find the exact field names in the form (in case your form uses different names)
        trade_field_name = None
        qp_assign_field_name = None
        for fname in Form.base_fields:
            if fname == 'trade' or fname.lower().endswith('trade'):
                trade_field_name = fname
            if fname == 'qp_assign' or fname.lower().endswith('qp_assign'):
                qp_assign_field_name = fname

        # Attach inline JS only if both fields exist
        if trade_field_name and qp_assign_field_name:
            # endpoint relative to model admin page (resolved under the same path)
            endpoint = '/admin/questions/questionpaper/qp-for-trade/'


            # Build the JS that will be placed into the trade field's onchange attribute
            js = (
                "(function(el){"
                "  var val = el.value;"
                "  var assign = document.getElementById('id_%(assign)s');"
                "  if(!val){ if(assign){ assign.value = ''; assign.dispatchEvent(new Event('change')); } return; }"
                "  var url = '%(endpoint)s' + '?trade_id=' + encodeURIComponent(val);"
                "  fetch(url, {credentials: 'same-origin'})"
                "    .then(function(r){ return r.json(); })"
                "    .then(function(data){"
                "       if(data && data.ok && data.qp){"
                "           if(assign){ assign.value = data.qp.id; try{ assign.dispatchEvent(new Event('change')); }catch(e){} }"
                "       } else {"
                "           if(assign){ assign.value = ''; try{ assign.dispatchEvent(new Event('change')); }catch(e){} }"
                "       }"
                "    }).catch(function(err){"
                "       console.error('qp-for-trade fetch error', err);"
                "    });"
                "})(this);"
            ) % {'assign': qp_assign_field_name, 'endpoint': endpoint}

            existing = Form.base_fields[trade_field_name].widget.attrs.get('onchange', '')
            if existing:
                Form.base_fields[trade_field_name].widget.attrs['onchange'] = existing + ';' + js
            else:
                Form.base_fields[trade_field_name].widget.attrs['onchange'] = js

            # Optionally run once on initial form render: if an existing trade value is present,
            # the onchange will be triggered on the client when user interacts; if you want it to run
            # on page load to pre-fill qp_assign when editing, it's typically handled by the form initial.
            # (If you need forced run-on-load, we can add a small DOMContentLoaded snippet here.)

        return Form

    def save_model(self, request, obj, form, change):
        """
        Keep previous behavior (auto-linking imported questions if qp_assign is set),
        but use correct field name qp_assign (not obj.upload).
        """
        super().save_model(request, obj, form, change)

        if obj.qp_assign:
            # Link only questions imported from that upload (trade based)
            try:
                # safe: qp_assign may have .trade or be None
                assigned_trade = obj.qp_assign.trade
                if assigned_trade:
                    questions = Question.objects.filter(trade=assigned_trade)
                else:
                    # Fallback: if trade not set, do nothing (or customize as needed)
                    questions = Question.objects.filter(trade=None)
            except Exception:
                questions = Question.objects.none()

            created_count = 0
            for i, q in enumerate(questions, start=1):
                paper_question, created = PaperQuestion.objects.get_or_create(
                    paper=obj,
                    question=q,
                    defaults={"order": i}
                )
                if created:
                    created_count += 1

            if created_count > 0:
                messages.success(request, f"Linked {created_count} questions to this paper")

    def delete_model(self, request, obj):
        """
        Delete a single QuestionPaper instance while:
        - counting how many Questions are exclusive to this paper (so we can report it)
        - calling the model's .delete() (which contains your safe logic)
        - showing an admin message with the count
        """
        # 1) gather question ids linked to this paper
        q_ids = list(PaperQuestion.objects.filter(paper=obj).values_list("question_id", flat=True))

        # 2) compute how many of those questions have no other PaperQuestion rows
        deletable_count = 0
        if q_ids:
            deletable_count = (
                PaperQuestion.objects
                .filter(question_id__in=q_ids)
                .values('question_id')
                .annotate(ref_count=Count('id'))
                .filter(ref_count=1)
                .count()
            )

        # 3) delete inside a transaction to ensure consistency
        with transaction.atomic():
            obj.delete()  # calls your model.delete() safe logic

        # 4) report to admin
        messages.info(request, f"Deleted paper and removed {deletable_count} question(s) that were exclusive to it.")

@admin.register(QuestionUpload)
class QuestionUploadAdmin(admin.ModelAdmin):
    form = QuestionUploadForm

    list_display = ("file", "trade", "uploaded_at", "get_questions_count")
    search_fields = ("file",)
    readonly_fields = ("uploaded_at",)
    ordering = ("-uploaded_at",)
    list_per_page = 20

    fields = ("file", "decryption_password", "trade")

    def get_questions_count(self, obj):
        if obj.uploaded_at:
            return Question.objects.filter(created_at__gte=obj.uploaded_at).count()
        return 0
    get_questions_count.short_description = "Imported Questions"


    def save_model(self, request, obj, form, change):
        # store selected trade on the QuestionUpload instance
        if "trade" in form.cleaned_data:
            obj.trade = form.cleaned_data["trade"]

        super().save_model(request, obj, form, change)

        if not change and obj.trade:
            # Assign trade to all questions created after upload
            Question.objects.filter(created_at__gte=obj.uploaded_at).update(trade=obj.trade)

            messages.info(request,
                f"Questions imported successfully and assigned to trade: {obj.trade.name}")

    def response_add(self, request, obj, post_url_redirect=None):
        response = super().response_add(request, obj, post_url_redirect)
        # Add success message with import status
        if obj:
            try:
                import time
                time.sleep(1)  # Give signals time to process
                questions_count = Question.objects.filter(created_at__gte=obj.uploaded_at).count()
                if questions_count > 0:
                    trade_info = f" to {obj.trade.name}" if obj.trade else ""
                    messages.success(request,
                        f"Successfully imported {questions_count} questions{trade_info} from {obj.file.name}")
                else:
                    messages.warning(request,
                        "Upload completed but no questions were imported. Please check the file format and password.")
            except Exception as e:
                messages.error(request, f"Upload completed but there was an error: {e}")
        return response

# Register QuestionPaper using the customized admin
admin.site.register(QuestionPaper, QuestionPaperAdmin)

