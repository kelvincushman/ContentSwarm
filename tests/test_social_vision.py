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
