from social_native import preview_data


def n(parent=None,**data):return dict(parent_index=parent,**data)


def test_preview_ignores_contact_metadata_outside_native_preview():
    ui=[n(id='root'),n(0,id='android:id/content_preview_container'),n(1,id='android:id/text1',text='Owner (@owner) on X'),n(1,id='android:id/text2',text='Exact 😅 #AI'),n(0,id='android:id/text1',text='Contact (@other) on X')]
    assert preview_data(ui)==dict(handle='@owner',body='Exact 😅 #AI',single_post=True)
    assert preview_data(ui+[n(1,id='android:id/text1',text='Other (@other) on X')]) is None
    assert preview_data([n(0,id='android:id/text1',text='Owner (@owner) on X')]) is None


def test_native_navigation_retries_observation_and_never_chooses_recipient():
    from social_native import read_x_preview
    preview=[n(id='android:id/content_preview_container'),n(0,id='android:id/text1',text='Owner (@owner) on X'),n(0,id='android:id/text2',text='Body')]
    class Client:
        state='detail'
        reads=0
        calls=[]
        def get(self,route):
            if route.endswith('/current_app'):return {'package':'android' if self.state=='chooser' else 'com.twitter.android'}
            if self.state=='chooser':
                self.reads+=1
                return {'elements':[] if self.reads==1 else preview}
            return {'elements':[dict(desc='Share')] if self.state=='detail' else [dict(text='Share via…'),dict(desc='Close sheet')]}
        def post(self,route,data):
            self.calls.append(data)
            if data.get('desc')=='Share':self.state='sheet'
            elif data.get('text')=='Share via…':self.state='chooser'
            elif data.get('key')=='BACK':self.state='sheet'
            elif data.get('desc')=='Close sheet':self.state='detail'
            else:raise AssertionError('Unexpected action')
    c=Client()
    assert read_x_preview(c,'/p')['body']=='Body'
    assert c.state=='detail' and c.reads==2 and len(c.calls)==4
