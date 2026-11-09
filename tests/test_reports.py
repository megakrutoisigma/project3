import unittest
from reports import html_report


class ReportTests(unittest.TestCase):
    def test_report_html_escapes_text(self):
        data = {
            'date': '01.01.2026', 'system': {'Name': '<script>x</script>'},
            'cpu': {}, 'memory': {}, 'disks': [],
            'diagnostics': [('success', 'OK')],
        }
        report = html_report(data)
        self.assertNotIn('<script>x</script>', report)
        self.assertIn('&lt;script&gt;', report)


if __name__ == '__main__':
    unittest.main()
