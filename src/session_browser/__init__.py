"""Session Browser package — v2.0 (registry-backed, client-first)

Provides a fast session browser backed by per-client registry_index.json files.
Session load time is < 1 second regardless of total session count.
"""

from .client_selector_widget import ClientSelectorWidget
from .session_browser_widget import SessionBrowserWidget
from .sessions_list_widget import SessionsListWidget

__all__ = [
    'ClientSelectorWidget',
    'SessionBrowserWidget',
    'SessionsListWidget',
]
