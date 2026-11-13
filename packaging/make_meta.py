"""deltaapp/__init__.py'deki sürümden packaging/version_info.txt (exe) ve version.iss (kurulum) üretir."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "deltaapp", "__init__.py"), encoding="utf-8").read()
ver = re.search(r'__version__\s*=\s*"([^"]+)"', src).group(1)
nums = [int(x) for x in re.findall(r"\d+", ver)[:4]]
nums += [0] * (4 - len(nums))
t = tuple(nums)
txt = f"""# UTF-8 — make_meta.py tarafından üretildi
VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041F04B0', [
      StringStruct('CompanyName', 'delta'),
      StringStruct('FileDescription', 'delta'),
      StringStruct('FileVersion', '{".".join(map(str, t))}'),
      StringStruct('InternalName', 'delta'),
      StringStruct('OriginalFilename', 'delta.exe'),
      StringStruct('ProductName', 'delta'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1055, 1200])])
  ]
)
"""
open(os.path.join(ROOT, "packaging", "version_info.txt"), "w", encoding="utf-8").write(txt)
with open(os.path.join(ROOT, "packaging", "version.iss"), "w", encoding="utf-8-sig") as f:
    f.write(f'#define AppVersion "{ver}"\n')
print(ver)
