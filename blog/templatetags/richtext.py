from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def rich_text(value):
    """Render WorkAssignment.task: sanitized rich HTML (current editor) or
    plain text (legacy rows, pre-dating the editor).

    SECURITY: this marks its input safe/unescaped. Only ever pass it a value
    that was written through WorkAssignmentAdminForm.clean_task() (which
    runs blog.admin_forms.sanitize_task_html()) - never raw user input from
    any other field or source, or this becomes a stored-XSS hole.
    """
    value = value or ""
    if "<" in value:
        return format_html('<div class="ql-editor rich-readonly">{}</div>', mark_safe(value))
    return format_html(
        '<div class="rich-readonly">{}</div>',
        mark_safe(escape(value).replace("\n", "<br>")),
    )
