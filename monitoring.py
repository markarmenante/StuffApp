"""Minimal error monitoring; payloads never include collection/request data."""
import os
import re

def private_error_event(event, _hint=None):
    clean = {key:event[key] for key in ('event_id','timestamp','level','platform','release','environment') if key in event}
    values=[]
    for error in event.get('exception',{}).get('values',[]):
        kind=error.get('type','Error')
        kind=kind if re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{0,80}',kind) else 'Error'
        item={'type':kind,'value':'Error details withheld; inspect the stack trace'}
        if error.get('stacktrace'):
            frames=[]
            for frame in error['stacktrace'].get('frames',[]):
                safe={key:frame[key] for key in ('function','lineno','colno','in_app') if key in frame}
                if frame.get('filename'):
                    safe['filename']=re.sub(r'/Users/[^/]+','/user',frame['filename'].split('?')[0].split('#')[0])
                frames.append(safe)
            item['stacktrace']={'frames':frames}
        values.append(item)
    if values:clean['exception']={'values':values}
    return clean

def initialize_monitoring():
    dsn=os.environ.get('SENTRY_DSN')
    if not dsn:return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.threading import ThreadingIntegration
        sentry_sdk.init(dsn=dsn, default_integrations=False,
            integrations=[FlaskIntegration(transaction_style='endpoint'),ThreadingIntegration()],
            send_default_pii=False, traces_sample_rate=0, enable_logs=False,
            max_request_body_size="never", include_local_variables=False, include_source_context=False,
            before_send=private_error_event, release=os.environ.get('RAILWAY_GIT_COMMIT_SHA'),
            environment=os.environ.get('SENTRY_ENVIRONMENT','production'))
        return True
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Sentry configuration unavailable; app remains running")
        return False
