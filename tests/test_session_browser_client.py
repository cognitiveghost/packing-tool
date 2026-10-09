"""The command bar's client picker is the Sessions page's client picker.

The Qt browser once carried a second, independent one down its left side, so
the shell could be on one client while the browser showed another.
"""


def test_changing_the_client_in_the_command_bar_loads_it_in_sessions(main_window):
    # Start on whichever client isn't the target, so the switch below is a
    # real change and actually fires currentIndexChanged.
    other_index = main_window.client_combo.findData("OTHERCL")
    main_window.client_combo.setCurrentIndex(other_index)

    loaded = []
    main_window.sessions.load_client = loaded.append

    index = main_window.client_combo.findData("TESTCL")
    main_window.client_combo.setCurrentIndex(index)

    assert loaded == ["TESTCL"]
