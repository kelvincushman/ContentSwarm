import json
from types import SimpleNamespace

import pytest
from social_vision import read_post

PNG = b'\x89PNG\r\n\x1a\nimage'
OBS = dict(handle='@owner',body='Exact 😅 #AI',timestamp='11:28 • 08 Sept 26',single_post=True)


def output(observation=OBS, **changes):
    event=dict(type='result',subtype='success',is_error=False,structured_output=observation)
    event.update(changes)
    return SimpleNamespace(returncode=0,stdout=json.dumps(event))


def test_reader_is_blind_tool_free_and_drops_phone_credentials(monkeypatch):
    monkeypatch.setenv('CONTENTSWARM_API_TOKEN','private-agent')
    monkeypatch.setenv('CONTENTSWARM_LEASE_TOKEN','private-lease')
    def run(command, **kwargs):
        assert command[command.index('--tools')+1]==''
        assert '--strict-mcp-config' in command
        assert not any(k.startswith('CONTENTSWARM_') for k in kwargs['env'])
        assert 'Exact' not in kwargs['input'] and '@owner' not in kwargs['input']
        assert json.loads(kwargs['input'])['message']['content'][1]['source']['media_type']=='image/png'
        return output()
    monkeypatch.setattr('social_vision.subprocess.run',run)
    assert read_post(PNG)==OBS


@pytest.mark.parametrize('result', [output(subtype='error_max_budget_usd'),output(is_error=True),output(observation={}),output(observation=dict(OBS,single_post='true')),output(observation=dict(OBS,body=['text'])),SimpleNamespace(returncode=1,stdout=''),SimpleNamespace(returncode=0,stdout='')])
def test_incomplete_and_invalid_model_results_are_rejected(monkeypatch,result):
    monkeypatch.setattr('social_vision.subprocess.run',lambda *a,**k:result)
    with pytest.raises(ValueError):read_post(PNG)


def test_ambiguous_screenshot_remains_an_observation(monkeypatch):
    observation=dict(handle=None,body=None,timestamp=None,single_post=False)
    monkeypatch.setattr('social_vision.subprocess.run',lambda *a,**k:output(observation))
    assert read_post(PNG)==observation


def test_invalid_image_never_reaches_model(monkeypatch):
    monkeypatch.setattr('social_vision.subprocess.run',lambda *a,**k:pytest.fail('No model call'))
    with pytest.raises(ValueError):read_post(b'not an image')

from social_vision import match_x_observation, x_detail_timestamp, verify_x_detail

STAMP='19:30 • 11 Sept 26'
BEFORE='2026-09-11T19:29:59+01:00'
AFTER='2026-09-11T19:30:50+01:00'
CURRENT=dict(OBS,timestamp=STAMP)
DETAIL=[dict(desc=d,text='',**{'class':'View'}) for d in ('Back','Post options','Reply','Repost','Like')]+[dict(text='Post'),dict(text=STAMP+' • 4 Views')]


def test_visual_match_preserves_unicode_and_checks_actual_device_time():
    assert match_x_observation(CURRENT,STAMP,'@owner','Exact 😅 #AI',BEFORE,AFTER)
    for changes in ({'body':'Exact & #AI'},{'body':'Exact 😅 #Al'},{'handle':'@other'},{'single_post':False},{'timestamp':'19:29 • 11 Sept 26'}):
        assert not match_x_observation(dict(CURRENT,**changes),STAMP,'@owner','Exact 😅 #AI',BEFORE,AFTER)
    for second in (0,1,20,59):
        assert not match_x_observation(CURRENT,STAMP,'@owner','Exact 😅 #AI',f'2026-09-11T19:30:{second:02d}+01:00','2026-09-11T19:31:01+01:00')
    assert not match_x_observation(CURRENT,STAMP,'@owner','Exact 😅 #AI',BEFORE,'2026-09-11T19:30:50+02:00')
    assert not match_x_observation(CURRENT,STAMP,'@owner','Exact 😅 #AI',BEFORE,'2026-09-11T19:40:00+01:00')


def test_detail_timestamp_rejects_multiple_posts_and_composers():
    assert x_detail_timestamp(DETAIL)==STAMP
    empty_reply=dict(id='post-detail-reply-text-field',text='',**{'class':'EditText'})
    assert x_detail_timestamp(DETAIL+[empty_reply])==STAMP
    with pytest.raises(ValueError):x_detail_timestamp(DETAIL+[dict(empty_reply,text='Draft reply')])
    for extra in ([dict(desc='Reply')],[dict(text=STAMP+' • 8 Views')],[dict(**{'class':'EditText'})]):
        with pytest.raises(ValueError):x_detail_timestamp(DETAIL+extra)


def test_visual_detail_uses_one_navigation_and_blind_read(monkeypatch):
    calls=[]
    class Client:
        def post(self,route,data):calls.append((route,data))
        def get(self,route,**kwargs):
            if route.endswith('/clock'):return {'iso':AFTER}
            return SimpleNamespace(content=PNG)
    def reader(image):
        assert image==PNG
        return CURRENT
    monkeypatch.setattr('social_vision.read_post',reader)
    screens=iter([[dict(text='Exact 😅 #AI')],DETAIL,DETAIL])
    evidence=verify_x_detail(Client(),'/phones/p','@owner','Exact 😅 #AI',BEFORE,lambda:next(screens))
    assert len(calls)==1 and calls[0][1]==dict(action='tap',text='Exact 😅 #AI',confirm=True)
    assert 'SHA256' in evidence


def test_old_post_rejected_before_model_call(monkeypatch):
    class Client:
        def post(self,*args):pass
        def get(self,route,**kwargs):return {'iso':AFTER} if route.endswith('/clock') else SimpleNamespace(content=PNG)
    monkeypatch.setattr('social_vision.read_post',lambda *a:pytest.fail('Stale content needs no model'))
    stale=[dict(e,text=e.get('text','').replace('11 Sept','10 Sept')) for e in DETAIL]
    screens=iter([[dict(text='Exact 😅 #AI')],stale,stale])
    with pytest.raises(ValueError,match='outside'):verify_x_detail(Client(),'/phones/p','@owner','Exact 😅 #AI',BEFORE,lambda:next(screens))
