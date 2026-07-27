"""
notification_watcher.py
------------------------
Silently disabled — winsdk's UserNotificationListener.get_current()
is broken on most Windows setups. AutoReplyEngine handles everything
via screen monitoring instead. This file is kept so the import in
main.py doesn't break.
"""

class WatchedNotification:
    def __init__(self, app="", title="", message="", raw_id=0):
        self.app     = app
        self.title   = title
        self.message = message
        self.raw_id  = raw_id


class NotificationWatcher:
    def __init__(self, on_notification=None, target_apps=None, poll_interval=2.0):
        self.on_notification = on_notification
        print("[NotificationWatcher] ℹ️ Disabled — using screen monitoring instead.")

    async def start(self):
        # Just sleep forever without doing anything.
        # The poll loop in AutoReplyEngine handles everything.
        import asyncio
        while True:
            await asyncio.sleep(3600)

    def stop(self):
        pass