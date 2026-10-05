class Headers:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        response=self.get_response(request)
        response['Content-Security-Policy']=getattr(response, 'marketing_csp', None) or "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        # Browsers also check the destination of a redirected form submission.
        if request.path == '/auth/google/':
            response['Content-Security-Policy'] = response['Content-Security-Policy'].replace("form-action 'self'", "form-action 'self' https://accounts.google.com")
        response['Cache-Control']='no-store'
        response['Referrer-Policy']='same-origin'
        response['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        return response
