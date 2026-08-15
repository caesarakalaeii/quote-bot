{
  # Keep this line accurate and one line long: `nix flake metadata` prints it,
  # and it is the first thing a cold agent learns about the repo.
  description = "quote-bot -- Discord bot for DM quote submission, button voting and PostgreSQL storage. Run `nix flake show` for the command map.";

  # nixpkgs is the only input, on purpose.
  #
  # flake-utils would buy exactly one thing here -- eachDefaultSystem -- which is
  # the three-line genAttrs below. In exchange it costs a second lock node, a
  # second upstream that can break, and a hardcoded system list this repo cannot
  # edit. That list is currently broken: it still contains x86_64-darwin, which
  # now throws (see `systems` below).
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    # `self` is named, not for an output but for one shell line: it is the only
    # handle a wrapper has on "the source this invocation named", which is what
    # $SRC_ROOT is and what $REPO_ROOT falls back to (see rootPreamble). It is
    # also what a candidate work tree is compared AGAINST, so a sibling checkout
    # cannot capture the verbs. `...` rather than a closed
    # { self, nixpkgs }: adding a second input later would otherwise fail with
    # "called with unexpected argument".
    { self, nixpkgs, ... }:
    let
      lib = nixpkgs.lib;

      # x86_64-darwin is deliberately absent. nixpkgs 26.11 replaced that whole
      # attribute set with `throw "Nixpkgs 26.11 has dropped support for
      # x86_64-darwin"`. genAttrs is lazy, so plain `nix develop` on Linux would
      # not notice -- it detonates later, on `nix flake check --all-systems`.
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      # Stand-in for flake-utils.lib.eachDefaultSystem. Passes `pkgs` rather than
      # a system string, because that is what every call site below wants.
      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # ======================================================================
      # PER-REPO BLOCK 1 -- the toolchain
      # ======================================================================
      # `nix flake check` realises this closure, so a typo'd attr name fails at
      # the flake gate instead of surfacing as "command not found" halfway
      # through a task. Explicit `pkgs.foo`, never `with pkgs; [ ... ]`.
      toolchain = pkgs: [
        # ---- this repo's ecosystem ----
        # python311, not the fleet default python313: both the Dockerfile
        # (`FROM python:3.11-slim`) and .github/workflows/test.yml
        # (`python-version: '3.11'`) pin 3.11, and matching them is what makes a
        # local repro of a CI failure meaningful. Pinned by MAJOR either way --
        # never `python3`, whose moving target would invalidate every .venv in
        # the fleet on the same afternoon.
        pkgs.python311
        pkgs.uv
        pkgs.ruff

        # The bot talks to PostgreSQL and ships schema.sql, so `psql` is the tool
        # an agent needs to load the schema or inspect a dev database by hand.
        # _15 matches `image: postgres:15` in both docker-compose files.
        #
        # This is the psql CLIENT and nothing more. It is explicitly NOT the nix
        # equivalent of the Dockerfile's `gcc` + `libpq-dev`: `pg_config` is
        # absent from every output of postgresql_15 on the pinned nixpkgs -- .dev
        # carries include/pg_config.h and lib/pgxs but no pg_config binary, and
        # there is no top-level `pg_config` attribute to fall back on. Verified,
        # not assumed: `find` over out/dev/lib matches only *.h.
        #
        # That costs this repo nothing, because requirements.txt pins
        # psycopg2-binary: a manylinux wheel that vendors its own libpq
        # (site-packages/psycopg2_binary.libs/libpq-*.so.5) and compiles nothing
        # at install time. Swapping it for a source build of psycopg2 needs a
        # pg_config this shell cannot hand it -- setup.py discovers every path
        # through that one binary -- so that swap is a requirements.txt change
        # AND a flake change. Do not assume the header half is enough.
        pkgs.postgresql_15

        # ---- present in every repo in the fleet ----
        pkgs.git
        pkgs.jq
        pkgs.gnumake
      ];

      # ======================================================================
      # PER-REPO BLOCK 2 -- libraries that get dlopened, not linked
      # ======================================================================
      # psycopg2-binary is a manylinux wheel: its .so files are dlopened at
      # runtime, so neither patchelf nor the nix linker ever sees them and NixOS
      # has no /usr/lib for them to find. stdenv.cc.cc.lib supplies libstdc++.
      # Keep this list minimal -- LD_LIBRARY_PATH is a blunt instrument.
      nativeLibs = pkgs: [
        pkgs.stdenv.cc.cc.lib
        pkgs.zlib
      ];

      # ======================================================================
      # PER-REPO BLOCK 3 -- constant environment variables
      # ======================================================================
      # Only constants belong here. Anything that must READ an existing value
      # (LD_LIBRARY_PATH), UNSET something (SOURCE_DATE_EPOCH) or touch the work
      # tree goes in the shellHook further down. This attrset is applied to BOTH
      # surfaces -- the dev shell and every `nix run` wrapper -- so a command
      # cannot behave differently depending on how it was invoked.
      envVars = pkgs: {
        # Keep uv on the nix interpreter. Left alone it downloads its own
        # portable CPython, which then resolves a different set of wheels than
        # this shell pins: two Pythons, one venv, no way to tell which is live.
        UV_PYTHON = "${pkgs.python311}/bin/python";
        UV_PYTHON_DOWNLOADS = "never";
        # /nix/store and the work tree are usually different filesystems, so
        # uv's default hardlink strategy warns on every single install.
        UV_LINK_MODE = "copy";
        PIP_DISABLE_PIP_VERSION_CHECK = "1";
      };

      # ======================================================================
      # PER-REPO BLOCK 4 -- the command map
      # ======================================================================
      # THE single source of truth. It generates `apps` (so `nix run .#test`
      # works), the `dev-*` wrappers on PATH inside the shell, and `dev-help`.
      # Nothing is written twice, so `nix flake show` can never disagree with
      # what `dev-test` actually runs.
      #
      # `build` is deliberately absent: the only artifact this repo produces is
      # the ghcr.io container image, and that is built by
      # .github/workflows/docker-publish.yml with a docker daemon this shell does
      # not and should not provide. Absence is information -- a stub that echoed
      # "not applicable" would turn the command map into a liar.
      commands = pkgs: {
        setup = {
          description = "(network) create .venv from requirements.txt";
          text = ''
            # $REPO_ROOT is the read-only store snapshot whenever the caller is
            # not standing in a checkout of THIS repo (see rootPreamble). Say so
            # here, rather than let uv fail two lines down with an EACCES on a
            # /nix/store path that reads like a nix bug.
            need_writable_checkout
            # --allow-existing, because "a .venv is already there" is the NORMAL
            # case: every rerun after a requirements.txt change, and every agent
            # retry. Without it uv exits 2 on "A virtual environment already
            # exists at: .venv" and `set -e` kills the wrapper BEFORE the install
            # line runs -- the bootstrap verb failing precisely when it is being
            # used to recover. Not --clear, which would throw away a working venv
            # (and any editable install in it) to redo work uv can do in place.
            uv venv --allow-existing "$REPO_ROOT/.venv"
            uv pip install --python "$REPO_ROOT/.venv/bin/python" -r "$REPO_ROOT/requirements.txt"
          '';
        };
        test = {
          # There is no pytest suite in this repo. This is exactly what CI runs
          # as its "Validate setup" step, plus the same import smoke test the
          # workflow does inline -- so a green `dev-test` means the same thing a
          # green CI run does. It needs no DISCORD_TOKEN and no database:
          # config.py only reads env vars, and Config.validate() is never called
          # at import time.
          #
          # The venv interpreter by absolute path, not a bare `python`. The
          # wrappers prepend the nix toolchain to PATH, so a bare name would
          # resolve to the store copy and miss every dependency `setup`
          # installed.
          description = "run validate_setup.py, the same check CI runs (needs `setup` first)";
          text = ''
            # cd, unlike everywhere else in this template, because
            # validate_setup.py resolves "requirements.txt", "config.py" and
            # friends against the CURRENT directory -- running it from a
            # subdirectory reports six phantom missing files.
            cd "$REPO_ROOT"
            "$REPO_ROOT/.venv/bin/python" validate_setup.py "$@"
          '';
        };
        lint = {
          # "${@:-$REPO_ROOT}", not a bare "$@": with no arguments ruff falls back
          # to its own default of ".", i.e. the CALLER's directory, so
          # `nix run /path/to/quote-bot#lint` from anywhere else used to exit 0
          # on "No Python files found under the given path(s)". Explicit
          # arguments still win, so `dev-lint --fix bot.py` is unaffected.
          #
          # Read-only, so no need_writable_checkout: when there is no checkout of
          # this repo in reach, $REPO_ROOT is the store snapshot of this same
          # source and linting it yields the same verdict. What it must never do
          # is lint the SIBLING checkout the caller happens to stand in -- see
          # rootPreamble, which is what stops that.
          #
          # --cache-dir, because the argument is only half the story: ruff writes
          # .ruff_cache next to the CURRENT directory, so reading the right files
          # while dropping a cache tree in the caller's directory would still
          # break the "touches nothing outside the repo" rule. Pinning the cache
          # is better than `cd "$REPO_ROOT"` here, which would silently
          # reinterpret a relative path the user passed. .ruff_cache/ is already
          # covered by .gitignore. --no-cache for the read-only store snapshot,
          # where ruff otherwise dies on "Failed to create temporary file" rather
          # than degrading to no caching.
          description = "ruff check";
          text = ''
            if [ -w "$REPO_ROOT" ]; then
              ruff check --cache-dir "$REPO_ROOT/.ruff_cache" "''${@:-$REPO_ROOT}"
            else
              ruff check --no-cache "''${@:-$REPO_ROOT}"
            fi
          '';
        };
        fmt = {
          # Same default as lint, and it matters more here: ruff format WRITES.
          # A bare "$@" made `nix run /path/to/quote-bot#fmt` reformat whatever
          # Python happened to sit in the invoking directory.
          description = "ruff format (rewrites files)";
          text = ''
            # Same guard as setup: a mutating verb pointed at the store snapshot
            # has nothing useful to do, so refuse rather than half-fail. `set --`
            # rather than an inline "''${@:-...}" so the guard runs in the
            # no-argument branch only -- an explicit path is the caller's own
            # instruction and is forwarded untouched, as `dev-fmt bot.py` always
            # was.
            if [ "$#" -eq 0 ]; then
              need_writable_checkout
              set -- "$REPO_ROOT"
            fi
            # --cache-dir for the reason spelled out under lint, and the
            # --no-cache branch for the same reason too: after the guard the
            # no-argument case always has a writable $REPO_ROOT, but an explicit
            # path can be passed from outside a checkout, where $REPO_ROOT is the
            # read-only snapshot and ruff dies on "Failed to create temporary
            # file" rather than degrading to no caching.
            if [ -w "$REPO_ROOT" ]; then
              ruff format --cache-dir "$REPO_ROOT/.ruff_cache" "$@"
            else
              ruff format --no-cache "$@"
            fi
          '';
        };
        run = {
          # Same cd rationale as `test`: config.py calls load_dotenv() at import
          # time, which searches upwards from the current directory, so starting
          # the bot from outside the tree would silently pick up no .env at all
          # and die on "Missing required environment variables".
          description = "start the Discord bot (needs .env and a reachable PostgreSQL)";
          text = ''
            cd "$REPO_ROOT"
            "$REPO_ROOT/.venv/bin/python" bot.py "$@"
          '';
        };
      };

      # ======================================================================
      # GENERIC MACHINERY -- byte-identical across the fleet, do not edit
      # ======================================================================

      # Prepend, never assign: a host LD_LIBRARY_PATH may be carrying something
      # the user needs, and clobbering it breaks binaries they launch from here.
      # Linux only -- on darwin the loader variable is DYLD_*, and exporting a
      # Linux-shaped value there is at best useless.
      ldPreamble =
        pkgs:
        lib.optionalString (pkgs.stdenv.hostPlatform.isLinux && nativeLibs pkgs != [ ]) ''
          export LD_LIBRARY_PATH="${lib.makeLibraryPath (nativeLibs pkgs)}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        '';

      # Every command gets $SRC_ROOT and $REPO_ROOT. `nix run` and `nix develop`
      # both start in whatever directory they were invoked from, and no verb may
      # act on that directory -- these two are what it acts on instead.
      #
      # $SRC_ROOT is this flake's own source, snapshotted into the store when
      # the flake was evaluated. It is the one anchor that is always available:
      # `nix run /path/to/quote-bot#lint` tells the running program nothing
      # whatever about /path/to/quote-bot (flake refs are location-independent
      # by design, and there is no $FLAKE_DIR to read), so without `self` a
      # wrapper invoked that way has literally no way to name the repo it
      # belongs to. Its one limitation is that it is read-only, being a store
      # path.
      #
      # $REPO_ROOT is the writable checkout when the caller is standing in one,
      # and $SRC_ROOT when they are not. `git rev-parse --show-toplevel` alone
      # is NOT enough to find that checkout: run from inside some OTHER git
      # repo it cheerfully answers with THAT repo's top level, and a verb that
      # trusts the answer formats a stranger's source tree. Probing that answer
      # for marker FILENAMES -- what this used to do, with bot.py and
      # requirements.txt -- only narrows the bug, and in this fleet it does not
      # narrow it at all: every sibling Discord bot checked out next to this one
      # has a root bot.py and a requirements.txt, so `nix run
      # /path/to/quote-bot#lint` from inside dc-bot passed the probe and
      # reported dc-bot's 61 findings as this repo's. A filename cannot tell
      # apart two repos that share the filename. So a candidate has to prove it
      # is a checkout of THIS flake, by carrying a byte-identical flake.nix --
      # the one file guaranteed to differ between any two repos in the fleet,
      # since it carries their description, toolchain and command map. Compared
      # with bash's own $(<file) rather than cmp or sha256sum, so the check
      # depends on no package at all.
      #
      # Consequence worth knowing: edit flake.nix and the dev-* wrappers in an
      # already-open `nix develop` stop recognising the tree, because they were
      # built from the previous flake.nix. That is a stale shell telling you so
      # -- re-enter it. `nix run` re-evaluates every time and never sees this.
      #
      # The fallback is a /nix/store path, so it is READ-ONLY. Verbs that write
      # (setup, fmt) call need_writable_checkout below rather than letting the
      # tool die on a bare EACCES three layers down.
      rootPreamble = ''
        SRC_ROOT=${lib.escapeShellArg self}
        export SRC_ROOT
        REPO_ROOT="$SRC_ROOT"
        _toplevel="$(git rev-parse --show-toplevel 2>/dev/null || true)"
        if [ -n "$_toplevel" ] && [ -f "$_toplevel/flake.nix" ] &&
          [ "$(<"$_toplevel/flake.nix")" = "$(<"$SRC_ROOT/flake.nix")" ]; then
          REPO_ROOT="$_toplevel"
        fi
        unset _toplevel
        export REPO_ROOT
      '';

      # Wrappers only, not the shellHook -- an interactive shell has no business
      # carrying this function around. Any command text that writes files calls
      # it first, and it is the reason a mutating verb can fail loudly instead of
      # falling back to "well, the cwd then".
      guardPreamble = ''
        need_writable_checkout() {
          if [ "$REPO_ROOT" != "$SRC_ROOT" ]; then
            return 0
          fi
          echo "This command rewrites files, so it needs a writable checkout of" >&2
          echo "this repo -- and standing in $PWD there is none: no parent" >&2
          echo "directory is a checkout of this flake. The only tree in reach is" >&2
          echo "the read-only store snapshot $SRC_ROOT, and rewriting $PWD" >&2
          echo "instead is exactly the bug this guard exists to prevent." >&2
          echo "cd into the repo (or \`nix develop\` it), or pass an explicit path." >&2
          exit 1
        }
      '';

      # One derivation per command, reused by both `apps` and the dev shell, so
      # the two can never diverge. `dev-` prefixed because a bare `test` binary
      # earlier on PATH would shadow the POSIX shell builtin and quietly break
      # every script in the repo that uses it.
      wrappers =
        pkgs:
        lib.mapAttrs (
          name: cmd:
          pkgs.writeShellApplication {
            name = "dev-${name}";
            runtimeInputs = toolchain pkgs;
            runtimeEnv = envVars pkgs;
            meta.description = cmd.description;
            text = ''
              ${rootPreamble}
              ${guardPreamble}
              ${ldPreamble pkgs}
              ${cmd.text}
            '';
          }
        ) (commands pkgs);

      helpFor =
        pkgs:
        let
          cmds = commands pkgs;
          names = lib.attrNames cmds;
          width = lib.foldl' (a: n: lib.max a (builtins.stringLength n)) 0 names;
          pad = n: n + lib.concatStrings (lib.genList (_: " ") (width - builtins.stringLength n));
          line = n: c: "  dev-${pad n}  ${c.description}";
        in
        pkgs.writeShellApplication {
          name = "dev-help";
          meta.description = "print this repo's command map (works offline)";
          text = ''
            cat <<'EOF'
            ${lib.concatStringsSep "\n" (lib.mapAttrsToList line cmds)}
            EOF
          '';
        };
    in
    {
      # `nix flake show` -- the discovery entrypoint, and deliberately the whole
      # machine-facing contract: every app carries a meta.description, which
      # `nix flake show` prints inline and `nix flake show --json` exposes at
      # .apps.<system>.<name>.description. Pure evaluation, so an agent gets the
      # entire command map in one cheap call without reading a README.
      apps = forAllSystems (
        pkgs:
        lib.mapAttrs (name: cmd: {
          type = "app";
          program = "${(wrappers pkgs).${name}}/bin/dev-${name}";
          meta.description = cmd.description;
        }) (commands pkgs)
      );

      # `nix develop` -- the toolchain, plus a dev-<verb> for every app.
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = toolchain pkgs ++ lib.attrValues (wrappers pkgs) ++ [ (helpFor pkgs) ];

          env = envVars pkgs;

          # Some C extensions compile at -O0, where glibc's _FORTIFY_SOURCE
          # becomes a hard error instead of a warning.
          hardeningDisable = [ "fortify" ];

          shellHook = ''
            # mkShell inherits SOURCE_DATE_EPOCH=315532800 (1980-01-01) from
            # stdenv, and any wheel or zip built in here then dies with "ZIP does
            # not support timestamps before 1980".
            unset SOURCE_DATE_EPOCH

            ${rootPreamble}
            ${ldPreamble pkgs}

            # Nothing networked, nothing stateful and nothing interactive above
            # this line, and nothing below it either. No venv creation, no
            # `pip install`. Bootstrapping in the hook makes a cold
            # `nix develop -c python bot.py` start downloading before it runs
            # anything, on EVERY invocation -- the exact failure an unattended
            # agent cannot diagnose. That is what `dev-setup` is for.

            # The banner is interactive-only, and this guard is load-bearing:
            # shellHook output lands on the STDOUT of `nix develop -c <cmd>`, so
            # an unguarded echo corrupts anything parsing it
            # (`nix develop -c cat x.json | jq` fails to parse). $- is the only
            # reliable discriminator -- it lacks `i` for `nix develop -c` and has
            # it at an interactive prompt. Do not test $PS1 (unset in both) or
            # $IN_NIX_SHELL (set in both). `[ -t 1 ]` is NOT enough: agent
            # harnesses allocate a pty, and the banner then leaks.
            case $- in
              *i*) echo "quote-bot dev shell -- 'dev-help' for the command map" >&2 ;;
            esac
          '';
        };
      });

      # `nix flake check` -- honest by construction. It realises the toolchain
      # closure (so a typo'd or currently-broken attr fails here) and builds
      # every wrapper, which runs shellcheck over every command text. NEVER add a
      # check that always passes: an agent reads "all checks passed!" as a
      # signal, and a fake check makes `nix flake check` a liar.
      checks = forAllSystems (pkgs: {
        toolchain =
          pkgs.runCommand "toolchain-check"
            {
              nativeBuildInputs = toolchain pkgs ++ lib.attrValues (wrappers pkgs);
            }
            ''
              for verb in ${lib.escapeShellArgs (lib.attrNames (commands pkgs))}; do
                command -v "dev-$verb" > /dev/null || {
                  echo "dev-$verb is not on PATH" >&2
                  exit 1
                }
              done
              touch "$out"
            '';
      });

      # `nix fmt` -- formats the *Nix* in this repo; project code is `dev-fmt`.
      # nixfmt-tree (the treefmt wrapper) rather than bare nixfmt, because bare
      # nixfmt tries to parse every path handed to it and fails on non-Nix files.
      formatter = forAllSystems (pkgs: pkgs.nixfmt-tree);
    };
}
