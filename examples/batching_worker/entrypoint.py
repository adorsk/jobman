from pathlib import Path
import tempfile
import textwrap
import time

from jobman.jobman import JobMan


class Entrypoint(object):
    def run(self):
        this_dir = Path(__file__).absolute().parent
        self.scratch_dir = tempfile.mkdtemp(dir=str(Path(this_dir, 'scratch')))
        self.mem_db_uri = 'sqlite://'
        self.jobman = JobMan(
            label='batching_jobman',
            db_uri=self.mem_db_uri,
            worker_specs={
                'batching_worker': {
                    'worker_class': (
                        'jobman.workers.batching_worker:BatchingWorker'
                    ),
                    'worker_params': {
                        'engine_spec': {
                            'engine_class': (
                                'jobman.engines.local_engine:LocalEngine'
                            ),
                            'engine_params': {
                                'scratch_dir': self.scratch_dir,
                                'db_uri': self.mem_db_uri,
                                'cfg': {
                                    'PARALLEL': '/bin/bash'
                                }
                            }
                        },
                    }
                }
            },
        )
        job_specs = [self._generate_job_spec(ctx={'key': i}) for i in range(3)]
        for job_spec in job_specs:
            self.jobman.submit_job_spec(job_spec=job_spec)
        for i in range(7):
            self.jobman.tick()
            time.sleep(.1)
        jobs = self.jobman.dao.query_jobs()
        job_statuses = [job['status'] for job in jobs]
        assert set(job_statuses) == set(['COMPLETED']), set(job_statuses)
        print("done")

    def _generate_job_spec(self, ctx=None):
        jobdir = tempfile.mkdtemp(dir=self.scratch_dir)
        entrypoint_name = 'entrypoint.sh'
        entrypoint_content = textwrap.dedent(
            '''
            #!/bin/bash
            echo "ctx: {ctx}" > output
            '''
        ).lstrip().format(ctx=ctx)
        entrypoint_path = Path(jobdir, entrypoint_name)
        with entrypoint_path.open('w') as f:
            f.write(entrypoint_content)
        entrypoint_path.chmod(0o755)
        job_spec = {
            'batchable': True,
            'dir': jobdir,
            'entrypoint': ('./' + entrypoint_name),
        }
        return job_spec


if __name__ == '__main__':
    Entrypoint().run()
