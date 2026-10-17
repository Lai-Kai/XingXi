from __future__ import annotations

import hashlib
import json
import posixpath
import shlex
import socket
import uuid
from contextlib import contextmanager
from pathlib import Path

from .config import TERMINAL, ReconstructionConfig


class SSHRemote:
    def __init__(self, config: ReconstructionConfig):
        self.config = config

    @staticmethod
    def socket(host, port):
        # Some Windows TUN routes need an explicit local-interface binding.
        try:
            addresses = [None, *socket.gethostbyname_ex(socket.gethostname())[2]]
        except OSError:
            addresses = [None]
        for address in addresses:
            connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                connection.settimeout(8)
                if address:
                    connection.bind((address, 0))
                connection.connect((host, port))
                if connection.recv(1024, socket.MSG_PEEK).startswith(b"SSH-"):
                    return connection
            except OSError:
                pass
            connection.close()
        raise ConnectionError("SSH 连接不可用")

    @contextmanager
    def connection(self):
        import paramiko

        settings = json.loads(self.config.ssh_config.read_text(encoding="utf-8-sig"))
        client = paramiko.SSHClient()
        client.load_host_keys(str(self.config.known_hosts))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                hostname=settings["host"],
                port=int(settings.get("port", 22)),
                username=settings.get("username") or settings.get("user"),
                password=settings.get("password"),
                key_filename=settings.get("key_filename"),
                timeout=20,
                banner_timeout=20,
                auth_timeout=20,
                allow_agent=False,
                look_for_keys=False,
                sock=self.socket(settings["host"], int(settings.get("port", 22))),
            )
            transport = client.get_transport()
            if transport:
                transport.set_keepalive(15)
            with client.open_sftp() as sftp:
                sftp.get_channel().settimeout(60)
                yield client, sftp
        finally:
            client.close()

    def root(self, job_id):
        if str(uuid.UUID(job_id)) != job_id:
            raise ValueError("无效任务标识")
        return posixpath.join(self.config.remote_root, job_id)

    @staticmethod
    def mkdir(sftp, path):
        try:
            sftp.stat(path)
        except FileNotFoundError:
            SSHRemote.mkdir(sftp, posixpath.dirname(path))
            try:
                sftp.mkdir(path, mode=0o700)
            except OSError:
                sftp.stat(path)

    @staticmethod
    def read_json(sftp, path):
        try:
            with sftp.open(path, "rb") as stream:
                return json.loads(stream.read(256 * 1024))
        except FileNotFoundError:
            return {}

    @staticmethod
    def exists(sftp, path):
        try:
            sftp.stat(path)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def write_json(sftp, path, data):
        temporary = path + "." + uuid.uuid4().hex + ".part"
        with sftp.open(temporary, "w") as stream:
            stream.write(json.dumps(data))
        sftp.posix_rename(temporary, path)

    def submit(self, job, directory: Path):
        root = self.root(job["id"])
        with self.connection() as (client, sftp):
            self.mkdir(sftp, root)
            if not self.exists(sftp, root + "/.started"):
                self.mkdir(sftp, root + "/source")
                for item in job["files"]:
                    destination = root + "/source/" + item["stored_name"]
                    temporary = destination + "." + uuid.uuid4().hex + ".part"
                    sftp.put(str(directory / "source" / item["stored_name"]), temporary)
                    sftp.posix_rename(temporary, destination)
                config = {"executable": self.config.executable, "quality": job["quality"], "input": job["files"][0]["stored_name"] if job["input_type"] == "video" else "."}
                self.write_json(sftp, root + "/config.json", config)
                temporary = root + "/runner." + uuid.uuid4().hex + ".part"
                sftp.put(str(Path(__file__).with_name("runner.py")), temporary)
                sftp.posix_rename(temporary, root + "/runner.py")
                if job.get("cancel_requested"):
                    with sftp.open(root + "/cancel.request", "w"):
                        pass
            command = "nohup python3 " + shlex.quote(root + "/runner.py") + " " + shlex.quote(root) + " >/dev/null 2>&1 </dev/null &"
            _, stdout, stderr = client.exec_command(command, timeout=20)
            if stdout.channel.recv_exit_status() != 0:
                raise RuntimeError("远程启动失败")
        return self.inspect(job["id"])

    def inspect(self, job_id):
        root = self.root(job_id)
        with self.connection() as (_, sftp):
            result = self.read_json(sftp, root + "/status.json")
            if not result:
                result = {"status": "running", "stage": "starting"}
            try:
                projects = sftp.listdir(root + "/projects")
            except FileNotFoundError:
                projects = []
            if len(projects) == 1 and "/" not in projects[0]:
                state = self.read_json(sftp, root + "/projects/" + projects[0] + "/state.json")
                if result["status"] not in TERMINAL and state.get("stage"):
                    result["stage"] = str(state["stage"])[:100]
            try:
                with sftp.open(root + "/runner.log", "rb") as log:
                    log.seek(max(0, log.stat().st_size - 16000))
                    result["log"] = log.read(16000).decode("utf-8", errors="replace")
            except FileNotFoundError:
                result["log"] = ""
            return result

    def cancel(self, job_id):
        root = self.root(job_id)
        with self.connection() as (_, sftp):
            self.mkdir(sftp, root)
            with sftp.open(root + "/cancel.request", "w"):
                pass
            if not self.exists(sftp, root + "/.started"):
                self.write_json(sftp, root + "/status.json", {"status": "cancelled", "stage": "cancelled"})
        return self.inspect(job_id)

    def download(self, job_id, artifact, destination: Path):
        root = self.root(job_id)
        relative = artifact["relative_path"]
        path = posixpath.normpath(root + "/" + relative)
        if not path.startswith(root + "/projects/") or not path.endswith(".ply") or not 0 < artifact["size"] <= 8 * 1024**3:
            raise ValueError("无效结果路径或大小")
        temporary = destination.with_suffix("." + uuid.uuid4().hex + ".part")
        try:
            with self.connection() as (_, sftp), sftp.open(path, "rb") as remote, temporary.open("wb") as local:
                digest = hashlib.sha256()
                size = 0
                while block := remote.read(1024 * 1024):
                    size += len(block)
                    if size > artifact["size"]:
                        raise ValueError("结果大小与记录不一致")
                    digest.update(block)
                    local.write(block)
            if size != artifact["size"] or digest.hexdigest() != artifact["sha256"]:
                raise ValueError("结果完整性校验失败")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
