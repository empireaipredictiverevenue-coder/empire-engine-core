import sys, re
text = sys.stdin.read()
m = re.search(r'_SPA_JS = r"""(.*?)"""', text, re.DOTALL)
if m:
    sys.stdout.write(m.group(1))
else:
    sys.exit(1)
