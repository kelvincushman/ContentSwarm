from phone_agent.adb.device import parse_foreground


def test_native_chooser_is_not_misidentified_as_underlying_x():
    info=parse_foreground('  mCurrentFocus=Window{123 u0 android/com.android.internal.app.ChooserActivity}\n  mFocusedApp=ActivityRecord{456 u0 com.twitter.android/.MainActivity}')
    assert info==dict(current_app='System Home',package='android')


def test_null_focus_does_not_fall_back_to_background_activity():
    assert parse_foreground('mCurrentFocus=null\nmFocusedApp=ActivityRecord{a u0 com.twitter.android/.MainActivity}')['package'] is None


def test_exact_package_mapping():
    assert parse_foreground('mCurrentFocus=Window{a u0 com.twitter.android/.MainActivity}')['package']=='com.twitter.android'
    assert parse_foreground('mCurrentFocus=Window{a u0 com.twitter.android.fake/.MainActivity}')['current_app']=='System Home'
