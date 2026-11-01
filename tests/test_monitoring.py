import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitoring import private_error_event, initialize_monitoring

class MonitoringTests(unittest.TestCase):
    def test_only_diagnostic_fields_leave_the_application(self):
        source = dict(event_id='a'*32,release='test-release',message='secret-message',
            request={'data':'secret-body','headers':{'Authorization':'secret-header'}},
            user={'email':'secret-user'},extra={'record':'secret-record'},breadcrumbs=[{'message':'secret-breadcrumb'}],
            exception={'values':[{'type':'ValueError','value':'secret-exception','stacktrace':{'frames':[
                {'filename':'/Users/private-person/app.py?token=secret-query','lineno':10,'function':'handler',
                 'vars':{'private':'secret-local'},'pre_context':['secret-source']}]}}]})
        result=private_error_event(source)
        self.assertEqual(result['release'],'test-release')
        frame=result['exception']['values'][0]['stacktrace']['frames'][0]
        self.assertEqual(frame,{'filename':'/user/app.py','lineno':10,'function':'handler'})
        self.assertNotIn('secret-',json.dumps(result))
        self.assertNotIn('private-person',json.dumps(result))
        self.assertEqual(source['message'],'secret-message')

    def test_unconfigured_instance_stays_disabled(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(initialize_monitoring())

if __name__=='__main__':unittest.main()
