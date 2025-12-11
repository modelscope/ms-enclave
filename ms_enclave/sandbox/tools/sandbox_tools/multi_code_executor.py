"""Multi-language code execution tool with runtime env tuning and optional C++ flags detection."""

import os
import re
import uuid
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from ms_enclave.sandbox.model import ExecutionStatus, SandboxType, ToolResult
from ms_enclave.sandbox.tools.base import register_tool
from ms_enclave.sandbox.tools.sandbox_tool import SandboxTool
from ms_enclave.sandbox.tools.tool_info import ToolParams

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import DockerSandbox


@register_tool('multi_code_executor')
class MultiCodeExecutor(SandboxTool):
    """Execute code in multiple languages in an isolated Docker environment."""

    _name = 'multi_code_executor'
    _sandbox_type = SandboxType.DOCKER
    _description = 'Execute code in various languages (python, cpp, csharp, go, java, nodejs, ts, rust, php, bash, pytest, jest, go_test, lua, r, perl, d_ut, ruby, scala, julia, kotlin_script, verilog, lean, swift, racket) with runtime tuning'  # noqa: E501
    _parameters = ToolParams(
        type='object',
        properties={
            'language': {
                'type':
                'string',
                'description':
                'Language to execute (python, cpp, csharp, go, java, nodejs, ts, rust, php, bash, pytest, jest, go_test, lua, r, perl, d_ut, ruby, scala, julia, kotlin_script, verilog, lean, swift, racket)'  # noqa: E501
            },
            'code': {
                'type': 'string',
                'description': 'Source code to execute'
            },
            'files': {
                'type': 'object',
                'additionalProperties': {
                    'type': 'string'
                },
                'description': 'Optional additional files to write before execution (filename -> content)'
            },
            'compile_timeout': {
                'type': 'integer',
                'description': 'Compile timeout in seconds (omit to disable compilation timeout)'
            },
            'run_timeout': {
                'type': 'integer',
                'description': 'Run timeout in seconds',
                'default': 30
            }
        },
        required=['language', 'code']
    )

    # cache for optional C++ runtime flags detected in the running container
    _cpp_rt_flags_cache: Optional[List[str]] = None

    # Centralized language-to-main-file mapping for easier extension
    LANG_MAIN_FILES: Dict[str, str] = {
        'python': 'main.py',
        'pytest': 'test_main.py',
        'cpp': 'main.cpp',
        'csharp': 'Program.cs',
        'go': 'main.go',
        'go_test': 'main_test.go',
        'java': 'Main.java',
        'junit': 'Main.java',
        'nodejs': 'main.js',
        'js': 'main.js',
        'ts': 'main.ts',
        'typescript': 'main.ts',
        'rust': 'main.rs',
        'php': 'main.php',
        'bash': 'main.sh',
        'jest': 'main.test.ts',
        'lua': 'main.lua',
        'r': 'main.R',
        'perl': 'main.pl',
        'd_ut': 'main.d',
        'ruby': 'main.rb',
        'scala': 'Main.scala',
        'julia': 'main.jl',
        'kotlin_script': 'main.kts',
        'verilog': 'main.sv',
        'lean': 'Main.lean',
        'swift': 'main.swift',
        'racket': 'main.rkt',
    }

    # Languages that benefit from a tuned Python PATH prefix
    LANGS_REQUIRE_PY_ENV = {'python', 'pytest'}
    # Include all jars under /root/sandbox/runtime/java and the current dir in the classpath
    JAVA_RUNTIME_CP: str = '/root/sandbox/runtime/java/*:.'

    async def execute(
        self,
        sandbox_context: 'DockerSandbox',
        language: str,
        code: str,
        files: Optional[Dict[str, str]] = None,
        compile_timeout: Optional[int] = None,
        run_timeout: Optional[int] = 30
    ) -> ToolResult:
        """Execute code by preparing a per-run workdir under /tmp and issuing build/run commands."""
        if not language or not code.strip():
            return ToolResult(tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='Invalid input')

        lang = language.lower().strip()
        unique_prefix = f'mce_{uuid.uuid4().hex}'
        workdir = f'/tmp/{unique_prefix}'

        try:
            await self._ensure_dir(sandbox_context, workdir)

            if files:
                for fname, content in files.items():
                    safe_name = os.path.basename(fname)
                    await self._write_file_to_container(sandbox_context, os.path.join(workdir, safe_name), content)

            # Pre-build setup (e.g., initialize a C# project)
            prebuild_error = await self._prebuild_setup(sandbox_context, lang, workdir, compile_timeout)
            if prebuild_error:
                return prebuild_error

            # Write main file
            main_filename = self._main_file_for_language(language)
            if main_filename is None:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.ERROR,
                    output='',
                    error=f'Unsupported language: {language}'
                )
            main_path = os.path.join(workdir, main_filename)
            await self._write_file_to_container(sandbox_context, main_path, code)

            # Detect Scala classname early to provide a clear error
            scala_classname: Optional[str] = None
            if lang == 'scala':
                scala_classname = self._find_scala_classname(code)
                if not scala_classname:
                    return ToolResult(
                        tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='Object name not found.'
                    )

            # Detect optional C++ link flags when needed
            if lang == 'cpp' and MultiCodeExecutor._cpp_rt_flags_cache is None:
                MultiCodeExecutor._cpp_rt_flags_cache = await self._get_cpp_rt_flags(
                    sandbox_context, workdir, compile_timeout
                )

            # Build env prefix for python/pytest if available (best-effort)
            env_prefix = await self._python_env_prefix(sandbox_context) if lang in self.LANGS_REQUIRE_PY_ENV else ''

            # Compute build and run commands
            build_cmd, run_cmd = self._commands_for_language(lang, os.path.basename(main_path), code, scala_classname)
            build_cmd, run_cmd = self._apply_env_prefix(build_cmd, run_cmd, env_prefix)

            # Compile/build phase if required
            compile_output = ''
            if build_cmd:
                build_res = await self._exec_in_dir(sandbox_context, workdir, build_cmd, timeout=compile_timeout)
                if build_res.exit_code != 0:
                    return ToolResult(
                        tool_name=self.name,
                        status=ExecutionStatus.ERROR,
                        output=build_res.stdout,
                        error=build_res.stderr or 'Compilation failed'
                    )
                compile_output = build_res.stdout

            # Run phase
            run_res = await self._exec_in_dir(sandbox_context, workdir, run_cmd, timeout=run_timeout or 30)
            status = ExecutionStatus.SUCCESS if run_res.exit_code == 0 else ExecutionStatus.ERROR
            return ToolResult(
                tool_name=self.name,
                status=status,
                output='\n'.join([s for s in [compile_output, run_res.stdout] if s]),
                error=run_res.stderr if run_res.stderr else None
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Execution failed: {str(e)}'
            )

    async def _exec_in_dir(self, sandbox_context: 'DockerSandbox', workdir: str, cmd: str, timeout: Optional[int]):
        """Execute a command in the given workdir using a POSIX shell so 'cd' works."""
        # Use /bin/sh -lc to ensure shell builtins and env prefixing operate correctly.
        sh_cmd = f'/bin/sh -lc "cd {workdir} && {cmd}"'
        return await sandbox_context.execute_command(sh_cmd, timeout=timeout)

    async def _ensure_dir(self, sandbox_context: 'DockerSandbox', dir_path: str) -> None:
        """Create a directory inside the container if it does not exist."""
        # Use POSIX mkdir -p for idempotency
        res = await sandbox_context.execute_command(f'mkdir -p {dir_path}')
        if res.exit_code != 0:
            raise RuntimeError(f'Failed to create workdir: {dir_path} ({res.stderr})')

    async def _write_file_to_container(self, sandbox_context: 'DockerSandbox', file_path: str, content: str) -> None:
        """Write content to a file in the container using a tar archive; creates parent dir if missing."""
        import io
        import tarfile

        dir_name = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)

        # Ensure parent directory exists
        await self._ensure_dir(sandbox_context, dir_name)

        with io.BytesIO() as tar_stream:
            with tarfile.TarFile(fileobj=tar_stream, mode='w') as tar:
                data = content.encode('utf-8')
                tarinfo = tarfile.TarInfo(name=base_name)
                tarinfo.size = len(data)
                tar.addfile(tarinfo, io.BytesIO(data))
                tar_stream.seek(0)
                sandbox_context.container.put_archive(dir_name, tar_stream.getvalue())

    async def _python_env_prefix(self, sandbox_context: 'DockerSandbox') -> str:
        """Best-effort Python PATH adjustment similar to get_python_rt_env('sandbox-runtime')."""
        # Prefer miniconda at /root/miniconda3 when present; avoid noisy activation errors.
        # Strategy:
        # - If miniconda exists, try to activate sandbox-runtime (ignore failures), then use which python.
        # - Else fall back to which python.
        # - Build PATH by placing the discovered python bin first and filtering unwanted entries.
        python_dir = None

        probe_cmd = (
            '/bin/sh -lc "'
            'if [ -x /root/miniconda3/bin/conda ]; then '
            '  . /root/miniconda3/bin/activate sandbox-runtime >/dev/null 2>&1 || true; '
            '  which python || echo /root/miniconda3/bin/python; '
            'else '
            '  which python; '
            'fi"'
        )
        res = await sandbox_context.execute_command(probe_cmd, timeout=5)
        if res.exit_code == 0 and res.stdout.strip():
            python_dir = os.path.dirname(res.stdout.strip())

        # Get current PATH from the container
        path_res = await sandbox_context.execute_command('printenv PATH', timeout=5)
        current_path = path_res.stdout.strip() if path_res.exit_code == 0 else ''
        parts = [p for p in current_path.split(':') if '/envs/sandbox/' not in p and p]
        if python_dir:
            # Put chosen python bin at the front
            parts.insert(0, python_dir)
        new_path = ':'.join(parts) if parts else current_path

        if not new_path:
            return ''
        return f'export PATH="{new_path}";'

    async def _get_cpp_rt_flags(self, sandbox_context: 'DockerSandbox', workdir: str,
                                timeout: Optional[int]) -> List[str]:
        """Detect available optional gcc link flags by compiling a tiny program."""
        optional_flags = ['-lcrypto', '-lssl', '-lpthread']
        # Write a tiny C++ file
        test_file = os.path.join(workdir, 'mce_rt_probe.cpp')
        await self._write_file_to_container(sandbox_context, test_file, 'int main(){return 0;}')

        detected: List[str] = []
        for flag in optional_flags:
            cmd = f'g++ {os.path.basename(test_file)} -o mce_rt_probe {flag}'
            res = await self._exec_in_dir(sandbox_context, workdir, cmd, timeout=timeout)
            if res.exit_code == 0:
                detected.append(flag)
        return detected

    def _main_file_for_language(self, language: str) -> Optional[str]:
        """Return the primary filename to use for the given language."""
        lang = language.lower().strip()
        return self.LANG_MAIN_FILES.get(lang)

    def _apply_env_prefix(self, build_cmd: Optional[str], run_cmd: str, env_prefix: str) -> Tuple[Optional[str], str]:
        """Apply an environment prefix to build and run commands if provided."""
        if not env_prefix:
            return build_cmd, run_cmd
        prefixed_build = f'{env_prefix} {build_cmd}' if build_cmd else None
        prefixed_run = f'{env_prefix} {run_cmd}'
        return prefixed_build, prefixed_run

    async def _prebuild_setup(
        self, sandbox_context: 'DockerSandbox', lang: str, workdir: str, compile_timeout: Optional[int]
    ) -> Optional[ToolResult]:
        """Run language-specific pre-build setup. Return ToolResult on error, else None."""
        if lang != 'csharp':
            return None
        init_res = await self._exec_in_dir(sandbox_context, workdir, 'dotnet new console -o .', timeout=compile_timeout)
        if init_res.exit_code != 0:
            return ToolResult(
                tool_name=self.name,
                status=ExecutionStatus.ERROR,
                output=init_res.stdout,
                error=init_res.stderr or 'dotnet project initialization failed'
            )
        return None

    def _cpp_commands(self, main_filename: str) -> Tuple[Optional[str], str]:
        """Build and run commands for C++ using optional detected flags."""
        flags = ' ' + ' '.join(MultiCodeExecutor._cpp_rt_flags_cache) if MultiCodeExecutor._cpp_rt_flags_cache else ''
        return f'g++ -std=c++17 {main_filename} -o app{flags}', './app'

    def _scala_commands(self, main_filename: str, code: Optional[str],
                        scala_classname: Optional[str]) -> Tuple[Optional[str], str]:
        """Build and run commands for Scala, ensuring an entrypoint object exists."""
        cls = scala_classname or (self._find_scala_classname(code or '') if code else None)
        if not cls:
            # Return a command that fails with a friendly message (consistent with previous behavior)
            return None, '/bin/sh -lc "echo Object name not found.; exit 1"'
        return f'scalac {main_filename}', f'scala {cls}'

    def _build_commands(self, lang: str, main_filename: str, code: Optional[str],
                        scala_classname: Optional[str]) -> Tuple[Optional[str], str]:
        """Mapping-based command builder for clarity and extensibility."""
        builders = {
            'python':
            lambda: (None, f'python {main_filename}'),
            'pytest':
            lambda: (None, f'pytest {main_filename}'),
            'cpp':
            lambda: self._cpp_commands(main_filename),
            'csharp':
            lambda: (None, 'dotnet run --project .'),
            'go':
            lambda: (f'go build -o app {main_filename}', './app'),
            'go_test':
            lambda: (None, f'go mod init {main_filename} && go test {main_filename}'),
            'java':
            lambda:
            (f'javac -cp "{self.JAVA_RUNTIME_CP}" {main_filename}', f'java -ea -cp "{self.JAVA_RUNTIME_CP}" Main'),
            'junit':
            lambda: (f'javac -cp "{self.JAVA_RUNTIME_CP}" *.java', f'java -ea -cp "{self.JAVA_RUNTIME_CP}" Main'),
            'nodejs':
            lambda: (None, f'node {main_filename}'),
            'js':
            lambda: (None, f'node {main_filename}'),
            'ts':
            lambda: (None, f'tsx {main_filename}'),
            'typescript':
            lambda: (None, f'tsx {main_filename}'),
            'rust':
            lambda: (f'rustc {main_filename} -o app', './app'),
            'php':
            lambda: (None, f'php -f {main_filename}'),
            'bash':
            lambda: (None, f'/bin/bash {main_filename}'),
            'jest':
            lambda: (None, 'npm run test'),
            'lua':
            lambda: (None, f'lua {main_filename}'),
            'r':
            lambda: (None, f'Rscript {main_filename}'),
            'perl':
            lambda: (None, f'perl {main_filename}'),
            'd_ut':
            lambda: (f'dmd {main_filename} -unittest -of=test', './test'),
            'ruby':
            lambda: (None, f'ruby {main_filename}'),
            'scala':
            lambda: self._scala_commands(main_filename, code, scala_classname),
            'julia':
            lambda: (None, f'julia {main_filename}'),
            'kotlin_script':
            lambda: (None, f'kotlin {main_filename}'),
            'verilog':
            lambda:
            (f'iverilog -Wall -Winfloop -Wno-timescale -g2012 -s tb -o test.vvp {main_filename}', 'vvp -n test.vvp'),
            'lean':
            lambda: (None, 'lake build || lean --run Main.lean'),
            'swift':
            lambda: (f'swiftc {main_filename} -o app', './app'),
            'racket':
            lambda: (None, f'racket {main_filename}'),
        }
        builder = builders.get(lang)
        if builder is None:
            return None, f'/bin/sh -lc "echo Unsupported language: {lang}; exit 1"'
        return builder()

    def _commands_for_language(
        self,
        language: str,
        main_filename: str,
        code: Optional[str] = None,
        scala_classname: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """Return (build_cmd, run_cmd) for the given language, executed with cwd=workdir."""
        lang = language.lower().strip()
        return self._build_commands(lang, main_filename, code, scala_classname)

    def _find_scala_classname(self, code: str) -> Optional[str]:
        """Extract the Scala object name used as entrypoint."""
        # Simple heuristic: capture identifier after `object`
        m = re.search(r'(?m)^\s*object\s+([A-Za-z_]\w*)\b', code)
        return m.group(1) if m else None
