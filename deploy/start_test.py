"""Start the free Render test service with production security enabled."""
import os
import re
import subprocess
import sys
from pathlib import Path


def configure(env):
    if env.get('FLOWFIX_TEST_DEPLOYMENT') != '1':
        raise RuntimeError('This launcher is restricted to the test deployment')
    if env.get('FLOWFIX_DEV') == '1' or env.get('BILLING_ENABLED') == '1':
        raise RuntimeError('Test deployment requires production security and disabled billing')
    host = env.get('RENDER_EXTERNAL_HOSTNAME', '')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.onrender\.com', host):
        raise RuntimeError('Expected the Render-provided service hostname')
    env.setdefault('DJANGO_ALLOWED_HOSTS', host)
    env.setdefault('PUBLIC_URL', 'https://' + host)


def main():
    configure(os.environ)
    os.chdir(Path(__file__).resolve().parents[1])
    for args in [('check', '--deploy', '--fail-level', 'WARNING'),
                 ('release_check', '--test-deployment'), ('migrate', '--noinput')]:
        subprocess.run([sys.executable, 'manage.py', *args], check=True)
    os.execvp('gunicorn', ['gunicorn', 'saas.wsgi:application', '--bind',
              '0.0.0.0:' + os.getenv('PORT', '8000'), '--workers', '1', '--threads', '2',
              '--timeout', '60', '--limit-request-line', '4094',
              '--limit-request-fields', '50', '--error-logfile', '-', '--no-control-socket'])


if __name__ == '__main__':
    main()
