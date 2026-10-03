from __future__ import annotations

from django import forms

from .models import AccessRequest, LearningSource, PublicSuggestion, TrainingProject, WorkbookEntry


class StartProjectForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = TrainingProject
        fields = ("learner_name", "learner_email", "agent_name")
        labels = {
            "learner_name": "Your name",
            "learner_email": "Email",
            "agent_name": "Name your agent",
        }
        help_texts = {
            "learner_email": "Private. It is never shown on public demo pages.",
            "agent_name": "For example: Workshop Apprentice or Project Librarian.",
        }

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Unable to accept this request.")
        return value


class AccessRequestForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = AccessRequest
        fields = ("name", "email", "use_case")
        labels = {
            "name": "Your name",
            "email": "Email",
            "use_case": "What would you teach your agent?",
        }
        widgets = {
            "use_case": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Our manuals and corrections, so it can prepare service checklists."}
            )
        }

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Unable to accept this request.")
        return value


class PublicSuggestionForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = PublicSuggestion
        fields = ("kind", "title", "detail", "source_url")
        labels = {
            "kind": "What are you sharing?",
            "title": "Short title",
            "detail": "What is missing, incorrect or useful?",
            "source_url": "Public source link (optional)",
        }
        help_texts = {
            "detail": "Do not include names, customer information, credentials or private records.",
            "source_url": "Links are treated as untrusted references and reviewed before use.",
        }
        widgets = {
            "detail": forms.Textarea(attrs={"rows": 6, "placeholder": "Explain the proposed correction or lesson…"})
        }

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Unable to accept this suggestion.")
        return value


class SchoolCompositionForm(forms.Form):
    GOALS = (
        ("understand", "Understand AI and its limits"),
        ("teach-agent", "Teach one useful agent"),
        ("workplace", "Design a workplace workflow"),
        ("secure", "Build a safer bounded agent"),
        ("evaluate", "Evaluate and govern an agent"),
        ("self-host", "Prepare a portable self-hosted setup"),
    )
    LEVELS = (("beginner", "Beginner"), ("practitioner", "Practitioner"), ("advanced", "Advanced"))
    PROVIDERS = (
        ("neutral", "Provider-neutral"),
        ("openai-compatible", "OpenAI-compatible tools"),
        ("local", "Local model tools"),
        ("mixed", "A reviewed mix"),
    )
    HOSTING = (
        ("unspecified", "Decide later"),
        ("local", "Local computer"),
        ("self-hosted", "Self-hosted server"),
        ("hosted", "Hosted service"),
    )
    PRIVACY = (
        ("minimal", "Use only non-sensitive material"),
        ("standard", "Minimize and redact ordinary work data"),
        ("local-sensitive", "Sensitive material must stay local"),
    )
    AUTONOMY = (
        ("draft-only", "Draft only"),
        ("approval", "Prepare work; a person approves every action"),
        ("bounded", "Bounded low-risk actions with explicit stop conditions"),
    )

    goal = forms.ChoiceField(choices=GOALS)
    experience_level = forms.ChoiceField(choices=LEVELS)
    subjects = forms.MultipleChoiceField(choices=(), required=False, widget=forms.CheckboxSelectMultiple)
    use_case = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Example: prepare a reviewable meeting summary from approved notes."}),
        help_text="Optional and never included in the shareable link. Do not enter private or secret material.",
    )
    provider = forms.ChoiceField(choices=PROVIDERS)
    hosting = forms.ChoiceField(choices=HOSTING)
    privacy = forms.ChoiceField(choices=PRIVACY)
    autonomy = forms.ChoiceField(choices=AUTONOMY)
    tools = forms.CharField(
        max_length=200,
        required=False,
        help_text="Optional generic tool names only; never paste keys, tokens or account details.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .school_content import LESSONS

        self.fields["subjects"].choices = [(lesson.lesson_id, lesson.title) for lesson in LESSONS]

    def clean_subjects(self):
        values = list(dict.fromkeys(self.cleaned_data.get("subjects", [])))
        if len(values) > 20:
            raise forms.ValidationError("Choose no more than twenty subjects.")
        return values

    def clean_tools(self):
        value = self.cleaned_data.get("tools", "").strip()
        if any(marker in value.lower() for marker in ("password", "secret=", "token=", "api_key")):
            raise forms.ValidationError("Do not include credentials or secret values.")
        return value


class LearningSourceForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = LearningSource
        fields = ("kind", "title", "source_url", "content_text", "uploaded_file")
        labels = {
            "kind": "What are you teaching?",
            "title": "File name",
            "source_url": "Link (optional)",
            "content_text": "Knowledge, example or correction",
            "uploaded_file": "Document (optional)",
        }
        help_texts = {
            "title": "A clear name becomes a versioned file in the agent classroom.",
            "source_url": "A public HTTP or HTTPS page. Private network addresses are blocked.",
            "content_text": "Paste text, add a link, upload a document, or combine them.",
            "uploaded_file": "TXT, Markdown, YAML, CSV, JSON or PDF; maximum 5 MB.",
        }
        widgets = {
            "content_text": forms.Textarea(
                attrs={"rows": 7, "placeholder": "Tell the agent what it should remember…"}
            )
        }

    def clean_uploaded_file(self):
        uploaded = self.cleaned_data.get("uploaded_file")
        if not uploaded:
            return uploaded
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Documents must be 5 MB or smaller.")
        if not uploaded.name.lower().endswith((".txt", ".md", ".yaml", ".yml", ".csv", ".json", ".pdf")):
            raise forms.ValidationError("Use a TXT, Markdown, YAML, CSV, JSON or PDF document.")
        return uploaded

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Unable to accept this lesson.")
        return value

    def clean(self):
        cleaned = super().clean()
        if not any((cleaned.get("source_url"), cleaned.get("content_text"), cleaned.get("uploaded_file"))):
            raise forms.ValidationError("Paste knowledge, add a link, or upload a document.")
        return cleaned


class AgentQuestionForm(forms.Form):
    prompt = forms.CharField(
        min_length=8,
        max_length=1200,
        label="Test what the agent has learned",
        widget=forms.Textarea(
            attrs={"rows": 5, "placeholder": "Based only on the approved files, explain or prepare…"}
        ),
    )
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Unable to accept this task.")
        return value


class TrainingAnswerForm(forms.Form):
    answer = forms.CharField(
        max_length=3000,
        label="Explain in your own words",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Add context, an exception, or your own answer…"}
        ),
    )


class WorkbookEntryForm(forms.ModelForm):
    """Compatibility form for legacy course projects during the migration window."""

    class Meta:
        model = WorkbookEntry
        fields = ("title", "response", "safe_to_share")
        labels = {
            "title": "Name this training artifact",
            "response": "Your practical answer",
            "safe_to_share": "This summary is safe for a public demonstration",
        }
        help_texts = {
            "safe_to_share": "Leave this off for internal methods, private sources, customer information, or anything uncertain.",
        }
        widgets = {"response": forms.Textarea(attrs={"rows": 10, "data-counter": "workbook-count"})}


class ChallengeForm(forms.Form):
    prompt = forms.CharField(
        min_length=12,
        max_length=600,
        label="Give the agent a simulated task",
        help_text="Do not enter personal, customer, confidential, or live operational information.",
        widget=forms.Textarea(
            attrs={"rows": 5, "placeholder": "A conveyor motor stops with an overload. What should I check first?"}
        ),
    )
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Unable to accept this challenge.")
        return value
