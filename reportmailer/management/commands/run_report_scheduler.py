"""Run one tenant-aware worker; shared SQL claims also support multiple workers."""
import signal
import time
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, close_old_connections
from reportmailer.service import tick

HEARTBEAT=Path('/tmp/financee-report-worker-heartbeat')


class Command(BaseCommand):
    help='Run the company report-mail delivery loop, or check its heartbeat.'

    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true')
        parser.add_argument('--health',action='store_true')
        parser.add_argument('--tick-seconds',type=int,default=60)

    def handle(self,*args,**options):
        if options['health']:
            if not HEARTBEAT.exists() or time.time()-HEARTBEAT.stat().st_mtime>180:
                raise CommandError('Report worker heartbeat is stale.')
            return
        stopped=False
        def stop(*_):
            nonlocal stopped
            stopped=True
        def heartbeat(): HEARTBEAT.write_text(str(time.time()))
        signal.signal(signal.SIGTERM,stop)
        signal.signal(signal.SIGINT,stop)
        while not stopped:
            try:
                close_old_connections()
                tick(heartbeat=heartbeat)
                heartbeat()
            except Exception as exc:
                self.stderr.write(f'Report worker tick failed: {type(exc).__name__}')
                connection.close()
                if options['once']: raise CommandError('Report worker tick failed.') from None
            if options['once']: return
            for _ in range(max(5,options['tick_seconds'])):
                if stopped: break
                time.sleep(1)
