import os
import textwrap

from .base_batch_jobdir_builder import BaseBatchJobdirBuilder


class BashBatchJobdirBuilder(BaseBatchJobdirBuilder):
    class InvalidPreambleError(Exception):
        def __init__(self, msg=None, preamble=None):
            msg = msg or ''
            hr = '-' * 10
            msg += "\n".join(["Preamble was:", hr, preamble, hr])
            super().__init__(msg)

    DEFAULT_PREAMBLE = 'PARALLEL=/bin/bash'

    def __init__(self, *args, default_preamble=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_preamble = default_preamble or self.DEFAULT_PREAMBLE
        self.subjob_commands_path = os.path.join(self.jobdir, 'subjob_commands')

    def _get_preamble_errors(self, preamble=None):
        errors = []
        if 'PARALLEL=' not in preamble:
            errors.append("A line like 'PARALLEL=<your parallel cmd>' must be"
                          " present in preamble. It will be called like"
                          " '$PARALLEL < commands' .")
        return errors

    def _build_batch_jobdir(self, preamble=None):
        self._write_subjob_commands()
        self._write_entrypoint(preamble=preamble)
        jobdir_meta = {
            'dir': self.jobdir,
            'entrypoint': self.entrypoint_path,
            'std_log_file_names': self.std_log_file_names,
        }
        return jobdir_meta

    def _write_subjob_commands(self):
        with open(self.subjob_commands_path, 'w') as f:
            f.write(self._generate_subjob_commands_content())

    def _generate_subjob_commands_content(self):
        subjob_commands = []
        for subjob in self.subjobs:
            subjob_commands.append(self._generate_subjob_command(subjob=subjob))
        return "\n".join(subjob_commands)

    def _generate_subjob_command(self, subjob=None):
        return "pushd {dir}; {entrypoint}; popd".format(
            dir=subjob['jobdir_meta']['dir'],
            entrypoint=subjob['jobdir_meta']['entrypoint']
        )

    def _write_entrypoint(self, preamble=None):
        with open(self.entrypoint_path, 'w') as f:
            f.write(self._generate_entrypoint_content(preamble=preamble))
        os.chmod(self.entrypoint_path, 0o755)

    def _generate_entrypoint_content(self, preamble=None):
        if not preamble: preamble = self._get_preamble()
        self._validate_preamble(preamble=preamble)
        return textwrap.dedent(
            """
            #!/bin/bash
            {preamble}
            $PARALLEL < {commands_file}
            """
        ).lstrip().format(
            preamble=preamble,
            commands_file=self.subjob_commands_path
        )

    def _get_preamble(self):
        try: return self._generate_preamble()
        except NotImplementedError: return self.default_preamble

    def _generate_preamble(self): raise NotImplementedError

    def _validate_preamble(self, preamble=None):
        errors = self._get_preamble_errors(preamble=preamble)
        if errors:
            raise self.InvalidPreambleError(preamble=preamble,
                                            msg="\n".join(errors))

