"""Phase filters retain Owned defaults and expose every pending phase."""
from html.parser import HTMLParser
import os
from pathlib import Path
import sys
import tempfile
import types
from urllib.parse import parse_qs, urlsplit

REPO=Path(__file__).resolve().parents[1]
os.chdir(REPO);sys.path.insert(0,str(REPO))
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='stuffapp-status-')
os.environ['EBAY_SYNC_WORKER']='0';os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuffapp
client=stuffapp.app.test_client()

class StatusPill(HTMLParser):
    def __init__(self,text):
        super().__init__();self.label='';self.href=None;self.title='';self.active=False;self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a' and attrs.get('title','').startswith('Cycle status:'):
            self.href=attrs['href'];self.title=attrs['title'];self.active=True
    def handle_endtag(self,tag):
        if tag=='a':self.active=False
    def handle_data(self,text):
        if self.active:self.label+=text

with stuffapp.app.app_context():
    db=stuffapp.get_db()
    for i,status in enumerate(('Own','Ordered','Shipped','Delivered','Sold')):
        db.execute('INSERT INTO art(id,title,status) VALUES (?,?,?)',(str(i),'Fixture '+status+' Piece',status))
    db.commit()

def page(path):
    response=client.get(path)
    assert response.status_code==200,(path,response.status_code)
    text=response.get_data(as_text=True)
    return text,StatusPill(text)

def next_filter(pill):
    return parse_qs(urlsplit(pill.href).query).get('filter',[None])[0]

# Existing default remains Owned. Every next link is verified through the full cycle.
for phase,label,next_phase in [(None,'Owned','ordered'),('ordered','Ordered','shipped'),
                              ('shipped','Shipped','delivered'),('delivered','Delivered','all'),
                              ('all','Status: All','own'),('own','Owned','ordered')]:
    text,pill=page('/art'+('?filter='+phase if phase else ''))
    assert pill.label==label,(phase,pill.label)
    assert next_filter(pill)==next_phase,(phase,pill.href)
    for status in ('Own','Ordered','Shipped','Delivered','Sold'):
        visible=('Fixture '+status+' Piece') in text
        assert visible==(phase=='all' or status.lower()==(phase or 'own')),(phase,status,visible)

# A search still bypasses Owned default and can recover sold records.
text,_=page('/art?q_art=Fixture Sold')
assert 'Fixture Sold Piece' in text

# All-first collections rotate through all four acquisition phases.
for phase,label,next_phase in [(None,'Status: All','ordered'),('ordered','Ordered','shipped'),
                              ('shipped','Shipped','delivered'),('delivered','Delivered','own'),
                              ('own','Owned',None)]:
    _,pill=page('/cameras'+('?filter='+phase if phase else ''))
    assert (pill.label,next_filter(pill))==(label,next_phase),(phase,pill.label,pill.href)
_,pill=page('/vehicles?filter=delivered')
assert next_filter(pill)=='all'

# Watches retain Commissioned/Purchased semantics and the old filter sequence.
for phase,label,next_phase in [(None,'Status: All','own'),('own','Own','ordered'),('ordered','Commissioned',None)]:
    _,pill=page('/watches'+('?filter='+phase if phase else ''))
    assert (pill.label,next_filter(pill))==(label,next_phase),(phase,pill.label,pill.href)
    assert 'Shipped' not in pill.title and 'Delivered' not in pill.title
print('STATUS FILTER CYCLES OK: effective phases, Owned defaults, All and watch workflow preserved')
