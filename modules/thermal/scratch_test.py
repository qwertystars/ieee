import sys

class PlatformStr(str):
    def __contains__(self, item):
        if item == "win":
            return False
        return super().__contains__(item)

sys.platform = PlatformStr("darwin")

print("sys.platform:", sys.platform)
print("sys.platform == 'darwin':", sys.platform == 'darwin')
print("'win' in sys.platform:", "win" in sys.platform)
print("'dar' in sys.platform:", "dar" in sys.platform)
