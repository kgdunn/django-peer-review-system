from django import forms
class UploadFileForm_one_file(forms.Form):

    file_upload = forms.FileField(
                widget=forms.ClearableFileInput(
                    attrs={'multiple': False,
                           'initial_text': "Please upload your image"}),
                label="")