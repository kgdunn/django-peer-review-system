from django.http import HttpResponse

def test(request):
    HttpResponse(content='Hi there')