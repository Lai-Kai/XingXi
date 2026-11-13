from pathlib import Path
import os,shutil,subprocess,json,unittest

ROOT=Path(__file__).resolve().parents[1]
NODE=ROOT/'.deer-flow/local-tools/bin/node'

class NativeDistDirectory(unittest.TestCase):
    def test_production_uses_opted_in_directory(self):
        self.assertEqual(self.load('production','.next-production'),'.next-production')
    def test_development_keeps_its_existing_directory(self):
        self.assertEqual(self.load('development','.next-production'),'.next')
    def test_other_deployments_keep_default_next_directory(self):
        self.assertEqual(self.load('production',None),'.next')
    def load(self,mode,directory):
        node=str(NODE) if NODE.exists() else shutil.which('node')
        if not node:self.skipTest('Node is required to load the real Next.js config')
        env=dict(os.environ,NODE_ENV=mode,SKIP_ENV_VALIDATION='1')
        env.pop('DEERFLOW_FRONTEND_DIST_DIR',None)
        if directory:env['DEERFLOW_FRONTEND_DIST_DIR']=directory
        command="const {default:c}=await import('./next.config.js');console.log(JSON.stringify(c.distDir || '.next'));"
        r=subprocess.run([node,'--input-type=module','-e',command],cwd=ROOT/'frontend',env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

if __name__=='__main__':unittest.main()
