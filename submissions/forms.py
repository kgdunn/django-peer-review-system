from django import forms

class UploadFileForm_one_file(forms.Form):

    file_upload = forms.FileField(
                widget=forms.ClearableFileInput(
                    attrs={'multiple': False,
                           'initial_text': "Please upload your submission"}),
                label="Upload your submission")

class UploadFileForm_multiple_file(forms.Form):

    file_upload = forms.FileField(
                widget=forms.ClearableFileInput(
                    attrs={'multiple': True,
                           'initial_text': "Select 1 or more files"}))




