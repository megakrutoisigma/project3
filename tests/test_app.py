import unittest
import errno
from unittest.mock import patch

import app


class LoginTests(unittest.TestCase):
    def test_busy_port_has_readable_error(self):
        with patch.object(app, "HOST", "127.0.0.1"), \
             patch.object(app.threading, "Thread") as thread, \
             patch.object(app, "start_server", side_effect=OSError(errno.EADDRINUSE, "busy")):
            with self.assertRaisesRegex(SystemExit, "уже занят"):
                app.run()
            stop = thread.call_args.kwargs['args'][0]
            self.assertTrue(stop.is_set())

    def test_russian_password_reaches_dashboard(self):
        class DashboardReached(Exception):
            pass

        with patch.object(app, "APP_PASSWORD", "пароль-ёж"), \
             patch.object(app, "set_env"), \
             patch.object(app, "web_input", return_value="пароль-ёж"), \
             patch.object(app, "put_html", side_effect=DashboardReached):
            with self.assertRaises(DashboardReached):
                app.main()

    def test_wrong_russian_password_is_rejected(self):
        with patch.object(app, "APP_PASSWORD", "пароль-ёж"), \
             patch.object(app, "set_env"), \
             patch.object(app, "web_input", return_value="неверный") as prompt, \
             patch.object(app, "put_error"), \
             patch.object(app, "put_html") as output:
            app.main()
            self.assertEqual(prompt.call_count, 3)
            output.assert_not_called()
