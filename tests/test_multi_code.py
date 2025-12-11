import asyncio
import os
from typing import Dict, Optional

from ms_enclave.sandbox.manager import LocalSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

DEFAULT_IMAGE = os.environ.get('MCE_IMAGE', 'volcengine/sandbox-fusion:server-20250609')
COMPILE_TIMEOUT = int(os.environ.get('MCE_COMPILE_TIMEOUT', '60'))
RUN_TIMEOUT = int(os.environ.get('MCE_RUN_TIMEOUT', '30'))


async def run_single(language: str, code: str, files: Optional[Dict[str, str]] = None) -> None:
    """Create a sandbox, run multi_code_executor for the given language, print result, and cleanup."""
    async with LocalSandboxManager() as manager:
        config = DockerSandboxConfig(
            image=DEFAULT_IMAGE,
            memory_limit='4g',
            cpu_limit=4.0,
            tools_config={'multi_code_executor': {}},
        )
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

        params = {
            'language': language,
            'code': code,
            'files': files or {},
            'compile_timeout': COMPILE_TIMEOUT,
            'run_timeout': RUN_TIMEOUT,
        }
        result = await manager.execute_tool(sandbox_id, 'multi_code_executor', params)
        print(f'[{language}] status={result.status}')
        print(f'[{language}] result={result.model_dump(exclude_none=True)}')
        if result.output:
            print(f'[{language}] output:\n{result.output}')
        if result.error:
            print(f'[{language}] error:\n{result.error}')


async def test_python() -> None:
    await run_single('python', 'print("hello from python")')


async def test_pytest() -> None:
    # Minimal pytest: single passing test
    await run_single('pytest', 'def test_ok():\n    assert 1 + 1 == 2\n')


async def test_cpp() -> None:
    cpp_code = "using namespace std;\n#include<optional>\n#include<cassert>\n#include<stdlib.h>\n#include<algorithm>\n#include<cmath>\n#include<math.h>\n#include<numeric>\n#include<stdio.h>\n#include<vector>\n#include<set>\n#include<map>\n#include<queue>\n#include<stack>\n#include<list>\n#include<deque>\n#include<boost/any.hpp>\n#include<string>\n#include<climits>\n#include<cstring>\n#include<iostream>\n#include<sstream>\n#include<fstream>\n#include<assert.h>\n#include<bits/stdc++.h>\n// Write a cppthon function to identify non-prime numbers.\nbool is_not_prime(long n) {\n    // Handle edge cases\n    if (n <= 1) return true;  // 0 and 1 are not prime\n    if (n <= 3) return false; // 2 and 3 are prime\n    if (n % 2 == 0 || n % 3 == 0) return true; // Divisible by 2 or 3\n    \n    // Check for divisors from 5 up to sqrt(n)\n    // Using 6k±1 optimization\n    for (long i = 5; i * i <= n; i += 6) {\n        if (n % i == 0 || n % (i + 2) == 0) {\n            return true;\n        }\n    }\n    \n    return false; // No divisors found, so it's prime\n}\nint main() {\n    auto candidate = is_not_prime;\n    assert(candidate((2)) == (false));\n    assert(candidate((10)) == (true));\n    assert(candidate((35)) == (true));\n    assert(candidate((37)) == (false));\n}\n"
    await run_single('cpp', cpp_code)


async def test_go() -> None:
    await run_single('go', 'package main\nimport "fmt"\nfunc main(){ fmt.Println("hello from go") }\n')


async def test_go_test() -> None:
    code = 'package is_not_prime_test\n\nimport "fmt"\nimport "testing"\n\n\n\n// Write a gothon function to identify non-prime numbers.\nfunc is_not_prime(n int) bool {\n    // Handle edge cases: numbers less than 2 are not prime\n    if n < 2 {\n        return true\n    }\n    \n    // 2 is prime, so it\'s not non-prime\n    if n == 2 {\n        return false\n    }\n    \n    // Even numbers greater than 2 are not prime\n    if n%2 == 0 {\n        return true\n    }\n    \n    // Check for odd divisors from 3 up to sqrt(n)\n    for i := 3; i*i <= n; i += 2 {\n        if n%i == 0 {\n            return true\n        }\n    }\n    \n    // If no divisors found, the number is prime, so it\'s not non-prime\n    return false\n}\nfunc TestIs_Not_Prime(t *testing.T) {\n  candidate := is_not_prime\n\ttype test struct {\n\t\tactual   interface{}\n\t\texpected interface{}\n\t}\n   tests := []test{\n     { actual: candidate(2), expected: false },\n     { actual: candidate(10), expected: true },\n     { actual: candidate(35), expected: true },\n     { actual: candidate(37), expected: false },\n   }\n\n\tfor i, tc := range tests {\n\t\tt.Run(fmt.Sprintf("test num % d", i), func(t *testing.T) {\n\t\t\tif fmt.Sprintf("%v", tc.actual) != fmt.Sprintf("%v", tc.expected) {\n\t\t\t\tt.Errorf("expected \'%s\', got \'%s\'", tc.expected, tc.actual)\n\t\t\t}\n\t\t})\n\t}\n}\n'
    await run_single('go_test',  code)


async def test_java() -> None:
    await run_single('java', 'public class Main { public static void main(String[] args){ System.out.println("hello from java"); } }\n')


async def test_nodejs() -> None:
    await run_single('nodejs', 'console.log("hello from nodejs")\n')


async def test_ts() -> None:
    # Requires tsx in the image
    await run_single('ts', 'console.log("hello from ts")\n')


async def test_rust() -> None:
    await run_single('rust', 'fn main(){ println!("hello from rust"); }\n')


async def test_php() -> None:
    await run_single('php', '<?php echo "hello from php\\n";\n')


async def test_bash() -> None:
    await run_single('bash', 'echo "hello from bash"\n')


# Added tests for more languages

async def test_lua() -> None:
    await run_single('lua', 'print("hello from lua")\n')


async def test_r() -> None:
    await run_single('r', 'cat("hello from r\\n")\n')


async def test_perl() -> None:
    await run_single('perl', 'print "hello from perl\\n";\n')


async def test_d_ut() -> None:
    await run_single('d_ut', 'unittest { assert(1 + 1 == 2); }\nvoid main() {}\n')


async def test_ruby() -> None:
    await run_single('ruby', 'puts "hello from ruby"\n')


async def test_scala() -> None:
    code = (
        'object Main {\n'
        '  def main(args: Array[String]): Unit = {\n'
        '    println("hello from scala")\n'
        '  }\n'
        '}\n'
    )
    await run_single('scala', code)


async def test_julia() -> None:
    await run_single('julia', 'println("hello from julia")\n')


async def test_kotlin_script() -> None:
    await run_single('kotlin_script', 'println("hello from kotlin")\n')


async def test_verilog() -> None:
    # Minimal SV testbench with top module tb
    code = 'module tb; initial begin $display("hello from verilog"); $finish; end endmodule\n'
    await run_single('verilog', code)


async def test_lean() -> None:
    # Fallback path uses `lean --run` if lake is not available
    await run_single('lean', 'def main : IO Unit := IO.println "hello from lean"\n')


async def test_swift() -> None:
    await run_single('swift', 'print("hello from swift")\n')


async def test_racket() -> None:
    await run_single('racket', '#lang racket\n(displayln "hello from racket")\n')

async def test_csharp() -> None:
    code = 'using System;\nusing System.Numerics;\nusing System.Diagnostics;\nusing System.Collections.Generic;\nusing System.Linq;\nusing System.Text;\nusing System.Security.Cryptography;\nclass Problem {\n    // Write a csthon function to identify non-prime numbers.\n    public static bool IsNotPrime(long n) {\n        // Handle edge cases\n        if (n < 2) return true; // Numbers less than 2 are not prime\n        if (n == 2) return false; // 2 is prime\n        if (n % 2 == 0) return true; // Even numbers > 2 are not prime\n        \n        // Check odd divisors from 3 up to sqrt(n)\n        long sqrt = (long)Math.Sqrt(n);\n        for (long i = 3; i <= sqrt; i += 2) {\n            if (n % i == 0) {\n                return true; // Found a divisor, so n is not prime\n            }\n        }\n        \n        return false; // No divisors found, so n is prime\n    }\n    public static void Main(string[] args) {\n    Debug.Assert(IsNotPrime((2L)) == (false));\n    Debug.Assert(IsNotPrime((10L)) == (true));\n    Debug.Assert(IsNotPrime((35L)) == (true));\n    Debug.Assert(IsNotPrime((37L)) == (false));\n    }\n\n}\n'
    await run_single('csharp', code)

async def main() -> None:
    # Run all tests sequentially to keep resource usage predictable
    # await test_python()
    # await test_pytest()
    # await test_cpp()
    # await test_go()
    await test_go_test()
    # await test_java()
    # await test_nodejs()
    # await test_ts()
    # await test_rust()
    # await test_php()
    # await test_bash()
    # # Added languages
    # await test_lua()
    # await test_r()
    # await test_perl()
    # await test_d_ut()
    # await test_ruby()
    # await test_scala()
    # await test_julia()
    # await test_kotlin_script()
    # await test_verilog()
    # await test_lean()
    # await test_swift()
    # await test_racket()
    # await test_csharp()


if __name__ == '__main__':
    asyncio.run(main())
