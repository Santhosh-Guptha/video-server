import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.deployment_readiness import report, enforce_deployment_mode


class DeploymentReadinessTests(unittest.TestCase):
    def settings(self, **overrides):
        values = dict(deployment_mode='onprem', recording_storage_limit_gb=50,
                      enable_retention=True, default_retention_days=30,
                      turn_server_url='turn:private.example', turn_server_credential='private-secret',
                      mediamtx_api_url='http://127.0.0.1:9997')
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_good_configuration_does_not_hide_unimplemented_security(self):
        result = report(self.settings())
        self.assertFalse(result['ready'])
        checks = {c['id']: c for c in result['checks']}
        self.assertEqual(checks['identity']['status'], 'blocked')
        self.assertEqual(checks['media_authorization']['status'], 'blocked')
        self.assertEqual(checks['tls']['status'], 'unverified')
        self.assertEqual(checks['storage']['status'], 'pass')

    def test_hosted_requires_isolation_and_refuses_start(self):
        settings = self.settings(deployment_mode='hosted')
        self.assertIn('tenant_isolation', [c['id'] for c in report(settings, 'hosted')['checks']])
        with self.assertRaisesRegex(RuntimeError, 'Hosted deployment blocked'):
            enforce_deployment_mode(settings)
        enforce_deployment_mode(self.settings())

    def test_invalid_mode_cannot_bypass_gate(self):
        with self.assertRaises(RuntimeError):
            enforce_deployment_mode(self.settings(deployment_mode='hostedd'))
        with self.assertRaises(ValueError):
            report(self.settings(), 'hostedd')

    def test_report_never_exports_private_settings(self):
        text = json.dumps(report(self.settings(mediamtx_api_url='http://admin:secret@private.example:9997')))
        for secret in ('private-secret', 'private.example', 'admin:secret'):
            self.assertNotIn(secret, text)

    def test_defaults_and_unbounded_storage_are_visible(self):
        checks = {c['id']: c for c in report(self.settings(recording_storage_limit_gb=0,
            enable_retention=False, turn_server_credential='vms_turn_password'))['checks']}
        self.assertEqual(checks['storage']['status'], 'warning')
        self.assertEqual(checks['retention']['status'], 'warning')
        self.assertEqual(checks['turn']['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
