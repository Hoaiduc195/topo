# Security

## Reporting a vulnerability

Report it privately through GitHub: on this repository's **Security** tab, choose **Report a
vulnerability**. Please don't open a public issue for it. Say what an attacker could do, and how to
reproduce it.

## What counts

Topo reads code that may not be yours and writes a page people open in a browser, so these matter
most:

- **Reading repositories.** The pipeline reads committed files through `git archive` and never runs
  the code it maps. A way to make it run code, write outside its output folders, or change a mapped
  repository is a vulnerability.
- **The map page.** Box names, summaries, details and code excerpts come from code and from mapping
  agents, and the viewer must show them as text. A way to make a map run script in the page that its
  template did not ship is a vulnerability.
- **The leak guard.** `pipeline/leakscan.py` blocks private files and names from commits. A way for a
  private name or file to get past it without `--no-verify` is a bug worth reporting privately.

Secrets that a mapping agent finds committed in a repository you mapped belong to that repository's
owner: tell them, not this project.
