# -*- mode: python ; coding: utf-8 -*-


block_cipher = None

add_files = [
    ('ico\\favicon.ico', 'ico'),
    ('ico\\*.png', 'ico'),
    ('snd\\*.wav', 'snd'),
]

a = Analysis(['rybafish.py'],
             pathex=[],
             binaries=[],
             datas=add_files,
             hiddenimports=[],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,  
          [],
          name='rybafish',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None , icon='ico\\favicon.ico')
