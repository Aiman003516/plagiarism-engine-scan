import zipfile

with zipfile.ZipFile('dummy_project.zip', 'w') as z:
    z.writestr('main.py', 'print("Hello World")\ndef test():\n    return 42\n')
    z.writestr('readme.md', 'Test project for plagiarism engine.')
