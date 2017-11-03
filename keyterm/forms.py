from django import forms
class UploadFileForm_file_optional(forms.Form):
    """
    The file is optional.
    """
    # This variable name must not be changed. Used in submissions.views
    file_upload = forms.FileField(
                required=False,
                label="",
                widget=forms.ClearableFileInput(
                    attrs={'multiple': False,
                           'initial_text': "Please upload your image"}),
            )



class UploadFileForm_file_required(forms.Form):
    """
    The file is required.
    """
    # This variable name must not be changed. Used in submissions.views
    file_upload = forms.FileField(
                required=True,
                label="",
                widget=forms.ClearableFileInput(
                    attrs={'multiple': False,
                           'initial_text': "Please upload your image"}),
    )

