import collections
from pathlib import Path
import textwrap
import unittest
from unittest.mock import call, MagicMock, patch

from .. import local_engine


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = local_engine.LocalEngine(
            process_runner=MagicMock(),
            dao=MagicMock()
        )
        self.job = collections.defaultdict(MagicMock)
        self.job['job_spec'] = collections.defaultdict(MagicMock, **{
            'dir': 'some_job_dir',
        })
        self.extra_cfgs = MagicMock()

    def mockify_engine_attrs(self, attrs=None):
        for attr in attrs:
            setattr(self.engine, attr, MagicMock())

    def mockify_module_attrs(self, attrs=None, module=local_engine):
        mocks = {}
        for attr in attrs:
            patcher = patch.object(module, attr)
            self.addCleanup(patcher.stop)
            mocks[attr] = patcher.start()
        return mocks


class SubmitJobTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.mockify_engine_attrs(attrs=['_write_engine_entrypoint',
                                         '_execute_engine_entrypoint'])
        self.result = self.engine.submit_job(job=self.job,
                                             extra_cfgs=self.extra_cfgs)

    def test_writes_engine_entrypoint(self):
        self.assertEqual(
            self.engine._write_engine_entrypoint.call_args,
            call(job=self.job, extra_cfgs=self.extra_cfgs)
        )

    def test_executes_engine_entrypoint(self):
        self.assertEqual(
            self.engine._execute_engine_entrypoint.call_args,
            call(entrypoint_path=(self.engine._write_engine_entrypoint
                                  .return_value),
                 job=self.job,
                 extra_cfgs=self.extra_cfgs)
        )

    def test_creates_job_record(self):
        self.assertEqual(
            self.engine.dao.create_job.call_args,
            call(job={'status': self.engine.JOB_STATUSES.EXECUTED})
        )

    def test_returns_engine_meta(self):
        engine_job = self.engine.dao.create_job.return_value
        self.assertEqual(self.result, {'key': engine_job['key']})


class _GenerateEngineEntrypointPreambleTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.mockify_engine_attrs(attrs=['resolve_cfg_item',
                                         '_generate_env_vars_for_cfg_specs'])
        self.result = self.engine._generate_engine_entrypoint_preamble(
            job=self.job, extra_cfgs=self.extra_cfgs)

    def test_gets_engine_preamble_from_cfg(self):
        self.assertEqual(self.engine.resolve_cfg_item.call_args,
                         call(key='ENGINE_PREAMBLE', spec={'default': ''}))

    def test_generates_env_vars_for_cfg_specs(self):
        self.assertEqual(
            self.engine._generate_env_vars_for_cfg_specs.call_args,
            call(job=self.job, extra_cfgs=self.extra_cfgs)
        )

    def test_returns_expected_preamble_content(self):
        expected_content = textwrap.dedent(
            '''
            # start preamble
            # engine_preamble
            {engine_preamble}
            # env_vars_for_cfg_specs
            {env_vars_for_cfg_specs}
            # end preamble
            '''
        ).lstrip().format(
            engine_preamble=self.engine.resolve_cfg_item.return_value,
            env_vars_for_cfg_specs=(
                self.engine._generate_env_vars_for_cfg_specs.return_value
            )
        )
        self.assertEqual(self.result, expected_content)


class _GenerateEnvVarsForCfgSpecsTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.mockify_engine_attrs(attrs=['resolve_job_cfg_specs',
                                         '_kvp_to_env_var_block'])
        self.engine.resolve_job_cfg_specs.return_value = {'key_i': MagicMock()
                                                          for i in range(3)}
        self.engine._kvp_to_env_var_block.return_value = 'some_block'
        self.result = self.engine._generate_env_vars_for_cfg_specs(
            job=self.job, extra_cfgs=self.extra_cfgs)

    def test_resolves_cfg_specs(self):
        self.assertEqual(self.engine.resolve_job_cfg_specs.call_args,
                         call(job=self.job, extra_cfgs=self.extra_cfgs))

    def test_writes_resolved_specs_as_env_vars(self):
        expected_resolved_cfgs = self.engine.resolve_job_cfg_specs.return_value
        self.assertEqual(
            self.engine._kvp_to_env_var_block.call_args_list,
            [call(kvp={'key': k, 'value': v})
             for k, v in expected_resolved_cfgs.items()]
        )
        self.assertEqual(
            self.result,
            "\n".join([self.engine._kvp_to_env_var_block.return_value
                       for cfg_item in expected_resolved_cfgs.items()])
        )


class _KvpToEnvVarBlock(BaseTestCase):
    def test_generates_expected_block(self):
        kvp = {'key': 'SOME_KEY', 'value': 'SOME_VALUE'}
        result = self.engine._kvp_to_env_var_block(kvp=kvp)
        expected_block = textwrap.dedent(
            '''
            read -d '' {key} << EOF
            {value}
            EOF
            export {key}=${key}
            '''
        ).lstrip().format(key=kvp['key'], value=kvp['value'].lstrip())
        self.assertEqual(result, expected_block)


class _ExecuteEngineEntrypointTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.mockify_engine_attrs(attrs=['_generate_engine_entrypoint_cmd',
                                         '_execute_engine_entrypoint_cmd'])
        self.entrypoint_path = MagicMock()
        self.engine._execute_engine_entrypoint(
            entrypoint_path=self.entrypoint_path,
            job=self.job, extra_cfgs=self.extra_cfgs)

    def test_generates_entrypoint_cmd(self):
        self.assertEqual(
            self.engine._generate_engine_entrypoint_cmd.call_args,
            call(entrypoint_path=self.entrypoint_path,
                 job=self.job, extra_cfgs=self.extra_cfgs)
        )

    def test_executes_entrypoint_cmd(self):
        self.assertEqual(
            self.engine._execute_engine_entrypoint_cmd.call_args,
            call(
                entrypoint_cmd=(self.engine._generate_engine_entrypoint_cmd
                                .return_value),
                job=self.job
            )
        )


class _GenerateEngineEntrypointCmdTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.entrypoint_path = '/some/dir/some/entrypoint'
        self.result = self.engine._generate_engine_entrypoint_cmd(
            entrypoint_path=self.entrypoint_path, job=self.job)

    def test_returns_expected_cmd(self):
        expected_cmd = (
            '{entrypoint_path} {stdout_redirect} {stderr_redirect}'
        ).format(
            entrypoint_path=self.entrypoint_path,
            **self.engine._get_std_log_redirects(job=self.job)
        )
        self.assertEqual(self.result, expected_cmd)


class _GetStdLogRedirectsTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.mockify_engine_attrs(attrs=['_get_std_log_paths'])
        self.engine._get_std_log_paths.return_value = {
            'stdout': '/some/path/for/stdout',
            'stderr': '/some/path/for/stderr',
        }
        self.result = self.engine._get_std_log_redirects(job=self.job)

    def test_returns_expected_redirects(self):
        expected_std_log_paths = self.engine._get_std_log_paths(job=self.job)
        expected_redirects = {
            'stdout_redirect': '>> %s' % expected_std_log_paths['stdout'],
            'stderr_redirect': '2>> %s' % expected_std_log_paths['stderr'],
        }
        self.assertEqual(self.result, expected_redirects)


class _GetStdLogPathsTestCase(BaseTestCase):
    def test_returns_expected_paths(self):
        self.job = {
            'job_spec': {
                'dir': 'some_dir',
                'std_log_file_names': {
                    'log_%s' % i: 'log_%s_file_name_' % i for i in range(3)
                }
            }
        }
        result = self.engine._get_std_log_paths(job=self.job)
        expected_paths = {
            log_key: str(
                Path(self.job['job_spec']['dir'], log_file_name).absolute()
            )
            for log_key, log_file_name in ({
                **self.engine.DEFAULT_STD_LOG_FILE_NAMES,
                **self.job['job_spec'].get('std_log_file_names', {}),
            }).items()
        }
        self.assertEqual(result, expected_paths)


class _ExecuteEngineEntrypointCmdTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.entrypoint_cmd = MagicMock()

    def _execute_engine_entrypoint_cmd(self):
        self.engine._execute_engine_entrypoint_cmd(
            entrypoint_cmd=self.entrypoint_cmd,
            job=self.job
        )

    def test_runs_cmd(self):
        self._execute_engine_entrypoint_cmd()
        self.assertEqual(self.engine.process_runner.run_process.call_args,
                         call(cmd=self.entrypoint_cmd, check=True, shell=True))

    def test_raises_submission_error_for_execution_error(self):
        class MockProcessError(Exception):
            stdout = 'some stdout'
            stderr = 'some stderr'

        self.engine.process_runner.CalledProcessError = MockProcessError
        self.engine.process_runner.run_process.side_effect = (
            self.engine.process_runner.CalledProcessError)
        with self.assertRaises(self.engine.SubmissionError):
            self._execute_engine_entrypoint_cmd()
