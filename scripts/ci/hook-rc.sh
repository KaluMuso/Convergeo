# Lefthook sources this before selecting commands or hiding unstaged changes.
# Git runs pre-commit from the working-tree root; other hooks keep their tasks.
case "$0" in
  */pre-commit | pre-commit)
    node scripts/ci/check-staged-symlinks.mjs || exit $?
    ;;
esac
