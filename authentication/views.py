from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home:home')
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            password = request.POST.get('password')

            if not username or not password:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Please enter both username and password.'
                })

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return JsonResponse({
                    'status': 'success',
                    'message': f'Welcome back, {user.username}!'
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid username or password.'
                })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'An unexpected error occurred: {str(e)}'
            })

    return render(request, 'authentication_templates/login_template.html')


@login_required
def logout_view(request):
    try:
        logout(request)
        return redirect('authentication:login')
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Logout failed: {str(e)}'
        })



@login_required
def current_user(request):
    data = {
        "username": request.user.username,
    }
    return JsonResponse(data)
