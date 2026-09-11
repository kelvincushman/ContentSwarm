import pytest

from social_delivery import x_post, x_published


def node(text="", desc="", cls="android.widget.TextView", parent=0):
    return dict(text=text, desc=desc, **{"class": cls}, parent_index=parent, enabled=True)


def post(body="Approved text", handle="@owner", age="now"):
    return [node(parent=None), node(handle), node(age), node(body), node(desc="Reply"), node(desc="Repost"), node(desc="Like")]


def test_published_proof_requires_own_fresh_single_post():
    assert x_published(post(), "@owner", "Approved text", 2)
    assert not x_published(post(handle="@other"), "@owner", "Approved text", 2)
    assert not x_published(post(age="11 Jun"), "@owner", "Approved text", 2)
    assert not x_published(post(age="45s"), "@owner", "Approved text", 2)
    assert not x_published(post(body="now", age="11 Jun"), "@owner", "now", 2)
    assert not x_published(post(body="@owner", handle="@other"), "@owner", "@owner", 2)
    quoted = post();quoted.insert(1,node("@other"))
    assert not x_published(quoted, "@owner", "Approved text", 2)
    duplicate = post() + [dict(e, parent_index=7 if e["parent_index"] == 0 else None) for e in post()]
    assert not x_published(duplicate, "@owner", "Approved text", 2)
    malformed = post();malformed[3]["parent_index"] = 3
    assert not x_published(malformed, "@owner", "Approved text", 2)


REVIEW = dict(id="review", revision=3, platform="x", kind="post", phone="phone", account="@owner", reply="Approved text")
FEED = [node(parent=None),node(desc="Show navigation drawer"),node(desc="Home"),node(desc="Post")]


def composer(body="", handle="@owner"):
    return [node(parent=None),node(desc=f"{handle}, Switch accounts"),node(text=body,cls="android.widget.EditText"),node(desc="Post")]


class Client:
    def __init__(self, screens=None, lost_send=False):
        self.screens=list(screens or [FEED,composer(),composer("Approved text"),post()])
        self.calls=[];self.lost_send=lost_send;self.post_taps=0
    def get(self, route):
        if route.endswith('/current_app'):return dict(current_app="Twitter")
        return dict(elements=self.screens.pop(0) if len(self.screens)>1 else self.screens[0])
    def post(self, route, data):
        self.calls.append((route,data))
        if data.get('desc')=='Post':
            self.post_taps+=1
            if self.post_taps==2 and self.lost_send:raise TimeoutError('response lost')
        return {}


def test_deterministic_post_inserts_exact_body_and_verifies():
    client=Client();x_post(client, REVIEW)
    assert [d['text'] for _,d in client.calls if d.get('action')=='type']==['Approved text']
    assert client.post_taps==2  # Composer entry, then one final commit.
    assert client.calls[-1][0]=='/reviews/review/complete'


def test_lost_send_is_never_repeated():
    client=Client(lost_send=True)
    with pytest.raises(TimeoutError):x_post(client, REVIEW)
    assert client.post_taps==2
    assert not any(route.endswith('/complete') for route,_ in client.calls)


@pytest.mark.parametrize('screens', [[composer('An existing draft')], [FEED,composer(handle='@other')], [FEED,composer(),composer('Different body')]])
def test_existing_drafts_wrong_accounts_and_changed_bodies_prevent_send(screens):
    client=Client(screens)
    with pytest.raises(ValueError):x_post(client,REVIEW)
    assert client.post_taps<=1


def test_unproven_post_is_not_completed(monkeypatch):
    monkeypatch.setattr('social_delivery.time.sleep',lambda _:None)
    client=Client([FEED,composer(),composer('Approved text'),post(age='11 Jun')])
    with pytest.raises(ValueError,match='No fresh'):x_post(client,REVIEW)
    assert client.post_taps==2
    assert not any(route.endswith('/complete') for route,_ in client.calls)


def test_account_adapter_validation_and_edit_preservation(tmp_path):
    from phone_agent.social import SocialStore
    store=SocialStore(tmp_path/'social.sqlite3')
    data=dict(name='Owner',platform='x',handle='@owner',soul='Plain',phones=['p'],delivery_adapter='x-accessibility-v1')
    account=store.account(data)
    omitted={k:v for k,v in account.items() if k!='delivery_adapter'}
    edited=store.account(dict(omitted,soul='Direct'))
    assert edited['delivery_adapter']=='x-accessibility-v1'
    disabled=store.account(dict(edited,delivery_adapter=''))
    assert 'delivery_adapter' not in disabled
    for changes in ({'platform':'linkedin'},{'handle':'Owner'},{'delivery_adapter':'unknown'}):
        with pytest.raises(ValueError):store.account(dict(data,**changes))


def test_worker_dispatches_x_adapter_with_private_lease(monkeypatch):
    import social_worker,social_delivery
    review=dict(REVIEW,account_id='account')
    profile=dict(delivery_adapter='x-accessibility-v1',phones=['phone'])
    class ClaimClient:
        api_url='http://test/api/v1'
        headers={'Authorization':'Bearer agent-secret'}
        def get(self,route):return {'account':profile}
        def post(self,route,data):return dict(review,lease_token='private-lease')
    class DeliveryClient:
        def __init__(self,*args):self.headers={};self.status='executing'
        def get(self,route):return {'reviews':[dict(review,status=self.status)]}
        def post(self,route,data):raise AssertionError('No uncertain transition after verified result')
    observed=[]
    def run(client,item):
        assert client.headers['X-ContentSwarm-Lease']=='private-lease'
        assert client.headers['X-ContentSwarm-Review']==review['id']
        assert 'lease_token' not in item
        observed.append(item['id']);client.status='verified'
    monkeypatch.setattr(social_worker,'Client',DeliveryClient)
    monkeypatch.setattr(social_delivery,'x_post',run)
    monkeypatch.setattr(social_worker,'choose_action',lambda *a: (_ for _ in ()).throw(AssertionError('No model needed')))
    social_worker.deliver(ClaimClient(),review)
    assert observed==[review['id']]


@pytest.mark.parametrize("foreign_handle", [None, "@other"])
def test_proof_does_not_borrow_header_from_screen_siblings(foreign_handle):
    elements = [node(parent=None), node("@owner"), node("now"), node(parent=0),
                node("Approved text", parent=3), node(desc="Reply", parent=3),
                node(desc="Repost", parent=3), node(desc="Like", parent=3)]
    if foreign_handle:
        elements.append(node(foreign_handle, parent=3))
    assert not x_published(elements, "@owner", "Approved text", 2)


def test_proof_rejects_foreign_handle_after_body_in_same_post():
    elements = post() + [node("@other")]
    assert not x_published(elements, "@owner", "Approved text", 2)
