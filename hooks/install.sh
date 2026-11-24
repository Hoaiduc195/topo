#!/bin/sh
# Installs the Topo leak guard as this clone's pre-commit hook. Every worktree shares it, and it runs
# the copy of hooks/pre-commit on whichever branch is checked out: topo/hooks/pre-commit when Topo is a
# folder of a larger repository, hooks/pre-commit in Topo's own repository (neither: no check).
set -e
hooks=$(git rev-parse --git-common-dir)/hooks
target=$hooks/pre-commit
line='root="$(git rev-parse --show-toplevel)"; for hook in "$root/topo/hooks/pre-commit" "$root/hooks/pre-commit"; do [ ! -x "$hook" ] || { "$hook" || exit 1; break; }; done'
if [ -e "$target" ] && ! grep -q topo-leak-guard "$target"; then
  echo "$target already exists; add this line to it instead:" >&2
  echo "  $line" >&2
  exit 1
fi
mkdir -p "$hooks"
cat > "$target" <<'HOOK'
#!/bin/sh
# topo-leak-guard (installed by hooks/install.sh)
root="$(git rev-parse --show-toplevel)"
for hook in "$root/topo/hooks/pre-commit" "$root/hooks/pre-commit"; do
  if [ -x "$hook" ]; then exec "$hook"; fi
done
exit 0
HOOK
chmod +x "$target"
echo "installed $target"
