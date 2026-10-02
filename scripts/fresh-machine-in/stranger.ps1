# What a stranger gets: install four-asserts from GitHub on a machine that has
# never seen it, run its tests, and run the README's four usages verbatim.
#
# NO LOCAL CHECKOUT is mapped in. The only things on this machine are a Python
# interpreter, this script, and a network connection.
#
# `pip install git+https://...` is NOT used, and that is the first thing a
# stranger meets: a fresh Windows machine has no git either, so the git+ form
# fails before it reaches the network. The archive URL needs nothing but pip.

$ErrorActionPreference = "Continue"
$out  = "C:\Users\WDAGUtilityAccount\Desktop\out"
$page = Join-Path $out "stranger.txt"
$py   = "C:\Users\WDAGUtilityAccount\Desktop\python\python.exe"
# The package lives in a folder of naidx0/research; pip takes the folder from the
# `#subdirectory=` fragment and the source tree is that folder inside the zip.
$zip  = "https://github.com/naidx0/research/archive/refs/heads/main.zip"
$pkg  = "four-asserts @ $zip#subdirectory=frameworks/four-asserts"

function Run($label, $block) {
    "" | Out-File -Append -Encoding utf8 $page
    "`$ $label" | Out-File -Append -Encoding utf8 $page
    $result = & $block 2>&1 | Out-String
    $code = $LASTEXITCODE
    $result.TrimEnd() | Out-File -Append -Encoding utf8 $page
    "  -> exit $code" | Out-File -Append -Encoding utf8 $page
}

"=== what this machine has ===" | Out-File -Encoding utf8 $page
("git on PATH:    " + [bool](Get-Command git -ErrorAction SilentlyContinue)) | Out-File -Append -Encoding utf8 $page
("python on PATH: " + [bool](Get-Command python -ErrorAction SilentlyContinue)) | Out-File -Append -Encoding utf8 $page
& $py -c "import four_asserts" 2>$null
("four_asserts already installed: " + ($LASTEXITCODE -eq 0)) | Out-File -Append -Encoding utf8 $page

# A VIRTUAL ENVIRONMENT FIRST, and the first attempt did not and was refused:
# the interpreter mapped into this sandbox is uv-managed, so PEP 668 marks it
# externally managed and pip declines to touch it. That refusal was an artefact
# of the machine I built, not of the package or of anything a stranger would
# meet - and a venv is what pip's own message implies and what anybody
# installing a library should do anyway.
# ON THE SANDBOX'S OWN DISK, not in the mapped folder. A venv built into a
# mapped share produced no page at all and no partial one either; a mapped
# folder is not a local filesystem and a venv expects one.
$venv = "C:\Users\WDAGUtilityAccount\Desktop\venv"
Run "python -m venv venv" { & $py -m venv $venv }
$py = "$venv\Scripts\python.exe"
Run "python -m pip install $pkg" { & $py -m pip install --no-cache-dir --quiet $pkg }
Run "python -c ""import four_asserts; print(four_asserts.__version__)""" { & $py -c "import four_asserts; print(four_asserts.__version__)" }

# The tests are not part of the installed package, so a stranger who wants to
# run them has to fetch the source. That is a finding, not a workaround.
Run "does pip install bring the tests?" { & $py -c "import four_asserts, pathlib, sys; p=pathlib.Path(four_asserts.__file__).parent.parent; print('tests dir present:', (p/'tests').is_dir())" }

Invoke-WebRequest -Uri $zip -OutFile "$out\src.zip" -UseBasicParsing
Expand-Archive -Path "$out\src.zip" -DestinationPath "$out\src" -Force
$src = Join-Path (Get-ChildItem "$out\src" -Directory | Select-Object -First 1).FullName "frameworksour-asserts"

Run "python -m unittest discover -s tests -t tests   (from the downloaded source)" {
    Push-Location $src
    & $py -m unittest discover -s tests -t tests
    Pop-Location
}

# --- the README's four one-line usages, verbatim ---------------------------
"" | Out-File -Append -Encoding utf8 $page
"=== the README's four usages, run verbatim ===" | Out-File -Append -Encoding utf8 $page

Run "from four_asserts import assert_ran, Hold, witness, void_unless" {
    & $py -c "from four_asserts import assert_ran, Hold, witness, void_unless; print('imported')"
}
Run "ran = assert_ran(discovered, ran, unimported=modules)" {
    & $py -c "from four_asserts import assert_ran
discovered, ran, modules = 10, 10, ()
ran = assert_ran(discovered, ran, unimported=modules)
print(ran.verdict, '| exit_code', ran.exit_code)"
}
Run "with Hold('/tmp/gpu.hold', holder='lane-a', purpose='a suite'): ..." {
    & $py -c "from four_asserts import Hold
with Hold('/tmp/gpu.hold', holder='lane-a', purpose='a suite'):
    print('held')"
}
Run "kept = witness('rows.jsonl')" {
    & $py -c "from four_asserts import witness
kept = witness('rows.jsonl')
print(kept.how)"
}
Run "rulings = void_unless(verdicts)" {
    & $py -c "from four_asserts import void_unless, Verdict, account
verdicts = [Verdict('KEEP', 'The rewrite drops a clause.', 'a b c', 'a b')]
rulings = void_unless(verdicts)
print(account(rulings))"
}

"done" | Out-File -Encoding utf8 (Join-Path $out "finished")
