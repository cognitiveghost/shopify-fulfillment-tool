from gui.log_follow import FollowState


def test_starts_following_with_nothing_pending():
    state = FollowState()
    assert state.following is True
    assert state.pending == 0


def test_appending_while_following_counts_nothing():
    state = FollowState()
    state.appended()
    state.appended()
    assert state.pending == 0


def test_scrolling_up_stops_following():
    state = FollowState()
    state.scrolled(at_bottom=False)
    assert state.following is False


def test_arrivals_after_a_scroll_up_are_counted():
    state = FollowState()
    state.scrolled(at_bottom=False)
    state.appended()
    state.appended()
    state.appended()
    assert state.pending == 3


def test_scrolling_back_to_the_bottom_resumes_and_clears():
    state = FollowState()
    state.scrolled(at_bottom=False)
    state.appended()
    state.scrolled(at_bottom=True)
    assert state.following is True
    assert state.pending == 0


def test_jump_to_latest_resumes_and_clears():
    state = FollowState()
    state.scrolled(at_bottom=False)
    state.appended()
    state.jumped_to_latest()
    assert state.following is True
    assert state.pending == 0
