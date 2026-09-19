"""The command bar's client picker is the browser's client picker.

The browser used to carry a second, independent one down its left side, so the
shell could be on one client while the browser showed another.
"""


def test_changing_the_client_in_the_command_bar_loads_it_in_the_browser(main_window):
    # Start on whichever client isn't the target, so the switch below is a
    # real change and actually fires currentIndexChanged.
    other_index = main_window.client_combo.findData("OTHERCL")
    main_window.client_combo.setCurrentIndex(other_index)

    loaded = []
    main_window.session_browser.load_client = loaded.append

    index = main_window.client_combo.findData("TESTCL")
    main_window.client_combo.setCurrentIndex(index)

    assert loaded == ["TESTCL"]


def test_the_browser_has_no_client_selector_of_its_own(main_window):
    assert not hasattr(main_window.session_browser, "client_selector")
