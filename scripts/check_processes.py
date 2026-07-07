import os
print("Running processes inside container:")
for p in os.listdir('/proc'):
    if p.isdigit():
        try:
            print("  ", p, ":", open(f'/proc/{p}/comm').read().strip())
        except Exception:
            pass
