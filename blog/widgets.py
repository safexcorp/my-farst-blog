from django import forms


class RichTextWidget(forms.Textarea):
    """Word-like editor (fonts, sizes, lists, native browser spellcheck) for a TextField.

    Stores sanitized HTML in the underlying TextField; see
    WorkAssignmentAdminForm.clean_task() for the bleach sanitization pass.
    """

    class Media:
        css = {"all": (
            "vendor/quill/quill.snow.css",
            "css/richtext_content.css",
        )}
        js = (
            "vendor/quill/quill.min.js",
            "js/richtext_widget.js",
        )

    def __init__(self, attrs=None):
        default_attrs = {"data-richtext": "1"}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
